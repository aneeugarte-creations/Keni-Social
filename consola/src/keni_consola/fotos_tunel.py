"""Túnel keni-fotos ↔ keni-social: registro de conexiones + RPC sobre WebSocket.

La app de escritorio keni-fotos abre un WebSocket SALIENTE hacia la Consola y se registra
por usuario (autenticada con su token de escritorio; la auth la hace el handler del WS). El
backend hace FAN-OUT de las búsquedas a las apps conectadas de ese usuario, agrega los
resultados y, al adjuntar, pide el ORIGINAL por el mismo canal. Es infra transversal: los
endpoints HTTP (`api/artes.py`, fuente «Propio») y el handler del WS (`api/fotos.py`) la usan;
el GATE a la marca `claro-sports` vive en esos endpoints, no aquí.

REGISTRO EN MEMORIA del proceso `back` (un solo contenedor; suficiente para el piloto). Si algún
día se escala horizontal hará falta un broker compartido — NO se construye ahora.

PROTOCOLO (contrato del túnel): mensajes JSON `{tipo, id, ...}`. El backend correla cada RPC por
`id` (uuid) con un `asyncio.Future`: manda `buscar`/`original` y espera `resultado`/`original_datos`
(o `error`). Timeouts: 20 s búsqueda, 60 s original.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import uuid
from typing import Any

_log = logging.getLogger("keni_consola.fotos_tunel")

# Timeouts por RPC (segundos): la búsqueda aplana ráfagas; el original viaja en base64.
_TIMEOUT_BUSCAR = 20.0
_TIMEOUT_ORIGINAL = 60.0

# Recortes defensivos de los metadatos que declara la app al saludar.
_MAX_DISPOSITIVO = 200
_MAX_VERSION = 40


class TunelError(RuntimeError):
    """Fallo de un RPC del túnel (timeout, conexión cerrada, dato corrupto o `error` de la app)."""


class Conexion:
    """Una app de escritorio conectada: su WebSocket + lo que declaró al saludar (`hola`).

    Correla los RPC por `id` con un `asyncio.Future` por petición pendiente. Al cerrarse,
    `cancelar_todo` falla los futuros vivos para que ningún `await` quede colgado.
    """

    def __init__(self, websocket: Any, usuario_id: str) -> None:
        self.ws = websocket
        self.usuario_id = usuario_id
        self.dispositivo = ""
        self.version = ""
        self.galerias: list[dict[str, Any]] = []
        self._pendientes: dict[str, asyncio.Future] = {}

    def registrar_hola(self, datos: dict[str, Any]) -> None:
        """Guarda dispositivo/versión/galerías declarados en el `hola` de la app."""
        self.dispositivo = str(datos.get("dispositivo") or "")[:_MAX_DISPOSITIVO]
        self.version = str(datos.get("version") or "")[:_MAX_VERSION]
        galerias = datos.get("galerias")
        self.galerias = [g for g in galerias if isinstance(g, dict)] if isinstance(galerias, list) else []

    def describir(self) -> dict[str, Any]:
        """Forma del dispositivo para `GET /api/artes/propio/dispositivos`."""
        return {
            "dispositivo": self.dispositivo,
            "version": self.version,
            "galerias": self.galerias,
        }

    def tiene_galeria(self, galeria_id: str) -> bool:
        """True si la app declaró la galería `galeria_id` en su `hola`."""
        return any(str(g.get("id") or "") == galeria_id for g in self.galerias)

    async def rpc(self, mensaje: dict[str, Any], timeout: float) -> dict[str, Any]:
        """Manda `mensaje` (con un `id` nuevo) y espera la respuesta correlada por ese `id`.

        Lanza `TunelError` si la respuesta no llega a tiempo, la conexión se cierra o la app
        responde un `error`.
        """
        reqid = uuid.uuid4().hex
        mensaje = {**mensaje, "id": reqid}
        futuro: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pendientes[reqid] = futuro
        try:
            await self.ws.send_json(mensaje)
            return await asyncio.wait_for(futuro, timeout)
        except TimeoutError as e:
            raise TunelError("El dispositivo no respondió a tiempo.") from e
        except TunelError:
            raise
        except Exception as e:  # noqa: BLE001 -- un fallo de envío/transporte es un RPC fallido
            raise TunelError("Se perdió la conexión con el dispositivo.") from e
        finally:
            self._pendientes.pop(reqid, None)

    def resolver(self, reqid: str, resultado: dict[str, Any]) -> None:
        """Completa el RPC pendiente `reqid` con la respuesta de la app (`resultado`/`original_datos`)."""
        futuro = self._pendientes.get(reqid)
        if futuro is not None and not futuro.done():
            futuro.set_result(resultado)

    def fallar(self, reqid: str, mensaje: str) -> None:
        """Falla el RPC pendiente `reqid` con el `error` que devolvió la app."""
        futuro = self._pendientes.get(reqid)
        if futuro is not None and not futuro.done():
            futuro.set_exception(TunelError(mensaje or "El dispositivo devolvió un error."))

    def cancelar_todo(self) -> None:
        """Falla todos los RPC vivos (la conexión se cerró): ningún `await` queda colgado."""
        for futuro in self._pendientes.values():
            if not futuro.done():
                futuro.set_exception(TunelError("La conexión con el dispositivo se cerró."))
        self._pendientes.clear()


# Registro EN MEMORIA: usuario_id -> conexiones vivas de ese usuario.
_REGISTRO: dict[str, set[Conexion]] = {}


def registrar(conexion: Conexion) -> None:
    """Da de alta una conexión bajo su usuario."""
    _REGISTRO.setdefault(conexion.usuario_id, set()).add(conexion)


def desregistrar(conexion: Conexion) -> None:
    """Da de baja una conexión y falla sus RPC vivos. Idempotente."""
    conjunto = _REGISTRO.get(conexion.usuario_id)
    if conjunto is not None:
        conjunto.discard(conexion)
        if not conjunto:
            _REGISTRO.pop(conexion.usuario_id, None)
    conexion.cancelar_todo()


def conexiones(usuario_id: str | None) -> list[Conexion]:
    """Conexiones vivas de un usuario (lista nueva, segura de iterar)."""
    if not usuario_id:
        return []
    return list(_REGISTRO.get(usuario_id, ()))


def dispositivos(usuario_id: str | None) -> list[dict[str, Any]]:
    """Dispositivos conectados de un usuario (forma de `GET /api/artes/propio/dispositivos`)."""
    return [c.describir() for c in conexiones(usuario_id)]


async def buscar(usuario_id: str | None, q: str, limite: int) -> list[dict[str, Any]]:
    """Fan-out de la búsqueda a todas las apps del usuario; agrega candidatos y trocea a `limite`.

    Cada candidato lleva su `dispositivo` (de qué app vino) para que el adjuntar luego sepa a
    quién pedir el original. Una app caída/lenta no rompe la búsqueda: aporta `[]`.
    """
    conns = conexiones(usuario_id)
    if not conns or not q.strip() or limite <= 0:
        return []

    async def _una(conexion: Conexion) -> list[dict[str, Any]]:
        try:
            respuesta = await conexion.rpc(
                {"tipo": "buscar", "q": q, "limite": limite}, _TIMEOUT_BUSCAR
            )
        except TunelError:
            _log.debug("Túnel keni-fotos: una app no respondió a la búsqueda; se omite.")
            return []
        crudos = respuesta.get("candidatos") if isinstance(respuesta, dict) else None
        salida: list[dict[str, Any]] = []
        for candidato in crudos or []:
            if not isinstance(candidato, dict):
                continue
            etiquetado = dict(candidato)
            etiquetado.setdefault("dispositivo", conexion.dispositivo)
            salida.append(etiquetado)
        return salida

    grupos = await asyncio.gather(*(_una(c) for c in conns))
    agregados = [candidato for grupo in grupos for candidato in grupo]
    return agregados[:limite]


async def pedir_original(
    usuario_id: str | None, galeria_id: str, archivo: str, dispositivo: str = ""
) -> tuple[bytes, str]:
    """Pide el ORIGINAL (`galeria_id`/`archivo`) por el túnel; devuelve `(bytes, mime)`.

    Elige la app que mejor encaja: la del `dispositivo` indicado, si no la que declaró esa
    galería, y si no la primera conectada. Lanza `TunelError` si no hay dispositivo, no responde
    o la imagen llega vacía/corrupta.
    """
    conexion = _elegir_conexion(usuario_id, galeria_id, dispositivo)
    if conexion is None:
        raise TunelError("No hay ningún dispositivo conectado con esa galería.")
    respuesta = await conexion.rpc(
        {"tipo": "original", "galeria_id": galeria_id, "archivo": archivo}, _TIMEOUT_ORIGINAL
    )
    if not isinstance(respuesta, dict):
        raise TunelError("El dispositivo no devolvió la foto original.")
    mime = str(respuesta.get("mime") or "image/jpeg")
    crudo = str(respuesta.get("datos_b64") or "")
    # La app puede mandar el base64 desnudo o como data URL (`data:image/jpeg;base64,...`).
    if crudo.startswith("data:") and "," in crudo:
        crudo = crudo.split(",", 1)[1]
    try:
        datos = base64.b64decode(crudo, validate=False)
    except (ValueError, binascii.Error) as e:
        raise TunelError("La foto original llegó corrupta.") from e
    if not datos:
        raise TunelError("La foto original llegó vacía.")
    return datos, mime


def _elegir_conexion(usuario_id: str | None, galeria_id: str, dispositivo: str) -> Conexion | None:
    """Conexión que sirve el original: por `dispositivo`, luego por galería, luego la primera."""
    conns = conexiones(usuario_id)
    if not conns:
        return None
    if dispositivo:
        for conexion in conns:
            if conexion.dispositivo == dispositivo:
                return conexion
    if galeria_id:
        for conexion in conns:
            if conexion.tiene_galeria(galeria_id):
                return conexion
    return conns[0]
