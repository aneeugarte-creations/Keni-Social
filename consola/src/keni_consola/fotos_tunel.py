"""Túnel keni-fotos ↔ keni-social: registro COMPARTIDO de conexiones + bus RPC cross-worker.

La app de escritorio keni-fotos abre un WebSocket SALIENTE hacia la Consola (autenticada con su
token de escritorio; la auth la hace el handler del WS) y declara a qué MARCAS comparte su galería.
El registro es POR MARCA, no por usuario: las búsquedas y el listado de dispositivos cruzan usuarios
(si Ale comparte a `claro-sports`, quien trabaja esa marca ve la galería de Ale). El backend hace
FAN-OUT de las búsquedas a las apps que comparten la marca, agrega los resultados y, al adjuntar,
pide el ORIGINAL por el mismo canal. Es infra transversal: los endpoints HTTP (`api/artes.py`,
fuente «Propio») y el handler del WS (`api/fotos.py`) la usan.

MULTI-WORKER (Postgres LISTEN/NOTIFY). El back corre con varios workers uvicorn: el WebSocket de
una app vive en memoria de UN worker, pero las peticiones HTTP caen en cualquiera. Para que todos
vean los mismos dispositivos y puedan enrutar los RPC al worker dueño:
  - `tunel_conexiones` (tabla) es el registro compartido: cada worker hace INSERT/heartbeat/DELETE
    de SUS conexiones; cualquier worker lo lee para listar la Galería y elegir destino.
  - `tunel_rpc` (tabla) es el bus: el worker que recibe la petición HTTP encola la llamada
    dirigida a una `conexion_id`; el worker que tiene ese WebSocket la ejecuta y deja el resultado.
  - `pg_notify` (canales `tunel_cambio`/`tunel_rpc`/`tunel_rpc_done`) avisa a los workers para que
    re-empujen el SSE o ejecuten/recojan un RPC sin sondear. El payload del NOTIFY solo lleva ids;
    el dato grande (thumbs/original en base64) va en la columna `resultado`. Un sondeo perezoso de
    respaldo (bucle de mantenimiento) cubre cualquier aviso perdido o la LISTEN caída.

PROTOCOLO (contrato del túnel): mensajes JSON `{tipo, id, ...}`. El backend correla cada RPC por
`id` (uuid) con un `asyncio.Future`: manda `buscar`/`original`/`rafaga` y espera
`resultado`/`original_datos`/`rafaga_datos` (o `error`). Timeouts: 20 s búsqueda/ráfaga, 60 s original.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import os
import socket
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from starlette.concurrency import run_in_threadpool

from . import config, repos
from .tiempo import ahora_iso, iso_utc

_log = logging.getLogger("keni_consola.fotos_tunel")

# Timeouts por RPC (segundos): la búsqueda aplana ráfagas; el original viaja en base64.
_TIMEOUT_BUSCAR = 20.0
_TIMEOUT_RAFAGA = 20.0
_TIMEOUT_ORIGINAL = 60.0

# Recortes defensivos de los metadatos que declara la app al saludar.
_MAX_DISPOSITIVO = 200
_MAX_VERSION = 40

# Etiqueta del token de escritorio: identifica a los usuarios REGISTRADOS en keni-fotos (los que
# aparecen en la Galería, online u offline). La emite `api/fotos.py` al autorizar el escritorio.
ETIQUETA_ESCRITORIO = "keni-fotos (escritorio)"

# Una conexión cuyo heartbeat (`visto_en`) lleve más de esto sin refrescarse es de un worker caído:
# se ignora en las lecturas y se barre. Mayor que el periodo de heartbeat (~20 s) con holgura.
_TTL_CONEXION = 90.0
# Las filas de RPC más viejas que esto son peticiones huérfanas (worker caído a medias): se barren.
_TTL_RPC = 300.0
# Cada cuánto re-lee el waiter la fila del RPC si el NOTIFY no le ha despertado antes (respaldo).
_POLL_RPC = 0.5
# Cada cuánto corre el bucle de mantenimiento (ejecuta pendientes locales + barrido perezoso).
_POLL_MANT = 5.0
# Espera entre reintentos de la conexión LISTEN (o cuando falta `DATABASE_URL`).
_BACKOFF_LISTEN = 2.0


class TunelError(RuntimeError):
    """Fallo de un RPC del túnel (timeout, conexión cerrada, dato corrupto o `error` de la app)."""


def _normalizar_marcas(valor: Any) -> set[str]:
    """Conjunto de ids de marca (cadenas no vacías) a partir de la lista declarada por la app."""
    if not isinstance(valor, list):
        return set()
    return {m.strip() for m in valor if isinstance(m, str) and m.strip()}


class Conexion:
    """Una app de escritorio conectada: su WebSocket + lo que declaró al saludar (`hola`).

    Vive en memoria del worker que aceptó el WebSocket (mapa `_CONEXIONES`, clave `id`). Guarda el
    `usuario` dueño, el `dispositivo`, sus `galerias` y el set de `marcas` a las que comparte la
    galería. Correla los RPC por `id` con un `asyncio.Future` por petición pendiente. Al cerrarse,
    `cancelar_todo` falla los futuros vivos para que ningún `await` quede colgado.
    """

    def __init__(self, websocket: Any, usuario: str) -> None:
        self.id = uuid.uuid4().hex
        self.ws = websocket
        self.usuario = usuario
        self.dispositivo = ""
        self.version = ""
        self.galerias: list[dict[str, Any]] = []
        self.marcas: set[str] = set()
        self._pendientes: dict[str, asyncio.Future] = {}

    def registrar_hola(self, datos: dict[str, Any]) -> None:
        """Guarda dispositivo/versión/galerías/marcas declarados en el `hola` de la app."""
        self.dispositivo = str(datos.get("dispositivo") or "")[:_MAX_DISPOSITIVO]
        self.version = str(datos.get("version") or "")[:_MAX_VERSION]
        galerias = datos.get("galerias")
        self.galerias = [g for g in galerias if isinstance(g, dict)] if isinstance(galerias, list) else []
        self.marcas = _normalizar_marcas(datos.get("marcas"))

    def actualizar_marcas(self, valor: Any) -> None:
        """Reemplaza las marcas a las que comparte (mensaje `marcas`, sin reconectar)."""
        self.marcas = _normalizar_marcas(valor)

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


# --------------------------------------------------------------------------- #
# Estado EN MEMORIA del proceso (un worker)                                     #
# --------------------------------------------------------------------------- #
# `_CONEXIONES`: las conexiones cuyo WebSocket vive en ESTE worker (clave = `Conexion.id`). Es el
# mapa que decide qué RPC del bus puede ejecutar este worker (los de SUS conexiones).
_CONEXIONES: dict[str, Conexion] = {}

# RPC que este worker está ejecutando ahora mismo: evita lanzarlo dos veces si llegan dos avisos.
_EN_CURSO: set[str] = set()

# Pub/sub LOCAL del registro: la página Galería NO sondea, se suscribe por SSE
# (`GET /api/artes/propio/eventos`). Cada suscriptor es una Queue por la que se encola un aviso
# ante cada cambio (lo dispara este worker o un NOTIFY `tunel_cambio` de otro); el endpoint, al
# recibirlo, reenvía el snapshot vigente (que lee de la tabla, consistente en cualquier worker).
_SUSCRIPTORES: set[asyncio.Queue[None]] = set()

# Evento que despierta a los waiters de RPC cuando llega un `tunel_rpc_done` (o el ejecutor local
# termina). Ligado al bucle de eventos vigente; se recrea si el bucle cambia (tests).
_evento_done: asyncio.Event | None = None
_evento_loop: Any = None

# Tareas del bus (listener + mantenimiento) de ESTE worker, y su bandera de parada.
_tarea_listen: asyncio.Task | None = None
_tarea_mant: asyncio.Task | None = None
_parar = False


def _worker_id() -> str:
    """Identificador del proceso dueño de una conexión: `host:pid`."""
    return f"{socket.gethostname()}:{os.getpid()}"


def _umbral_vivo() -> str:
    """ISO UTC por debajo del cual una conexión se considera muerta (worker caído)."""
    return iso_utc(datetime.now(UTC) - timedelta(seconds=_TTL_CONEXION))


def _umbral_rpc() -> str:
    """ISO UTC por debajo del cual una fila de RPC es huérfana y se barre."""
    return iso_utc(datetime.now(UTC) - timedelta(seconds=_TTL_RPC))


def _cargar_lista(crudo: Any) -> list[Any]:
    """Parsea una columna JSON (TEXT) a lista; [] si está vacía o corrupta."""
    if isinstance(crudo, list):
        return crudo
    if not crudo:
        return []
    try:
        valor = json.loads(crudo)
    except (ValueError, TypeError):
        return []
    return valor if isinstance(valor, list) else []


def _cargar_dict(crudo: Any) -> dict[str, Any]:
    """Parsea una columna JSON (TEXT) a dict; {} si está vacía o corrupta."""
    if isinstance(crudo, dict):
        return crudo
    if not crudo:
        return {}
    try:
        valor = json.loads(crudo)
    except (ValueError, TypeError):
        return {}
    return valor if isinstance(valor, dict) else {}


# --------------------------------------------------------------------------- #
# Pub/sub LOCAL del SSE de la Galería                                            #
# --------------------------------------------------------------------------- #


def _notificar_cambio() -> None:
    """Avisa a los suscriptores SSE de ESTE worker de que el registro cambió."""
    for cola in _SUSCRIPTORES:
        try:
            cola.put_nowait(None)
        except asyncio.QueueFull:
            # Ya tiene un aviso pendiente: uno basta para que reenvíe el snapshot vigente.
            pass


def suscribir() -> asyncio.Queue[None]:
    """Da de alta un suscriptor del registro y devuelve su cola de avisos (cierra con `desuscribir`).

    La cola es de tamaño 1: varios cambios seguidos colapsan en un único aviso pendiente, que
    basta para reenviar el snapshot vigente. La consume el SSE de la Galería.
    """
    cola: asyncio.Queue[None] = asyncio.Queue(maxsize=1)
    _SUSCRIPTORES.add(cola)
    return cola


def desuscribir(cola: asyncio.Queue[None]) -> None:
    """Da de baja un suscriptor del registro. Idempotente."""
    _SUSCRIPTORES.discard(cola)


async def _avisar_cambio() -> None:
    """Despierta el SSE local y propaga el cambio al resto de workers (NOTIFY `tunel_cambio`)."""
    _notificar_cambio()
    await run_in_threadpool(repos.tunel_notificar, "tunel_cambio", "")


# --------------------------------------------------------------------------- #
# Registro de conexiones (lo orquesta el handler del WS, en su worker)          #
# --------------------------------------------------------------------------- #


def _persistir(conexion: Conexion) -> None:
    """Da de alta/refresca la fila de `conexion` en `tunel_conexiones` (con su heartbeat)."""
    repos.tunel_upsert_conexion(
        id=conexion.id,
        worker=_worker_id(),
        usuario=conexion.usuario,
        dispositivo=conexion.dispositivo,
        version=conexion.version,
        marcas=json.dumps(sorted(conexion.marcas), ensure_ascii=False),
        galerias=json.dumps(conexion.galerias, ensure_ascii=False),
        visto_en=ahora_iso(),
    )


async def registrar(conexion: Conexion) -> None:
    """Da de alta una conexión: la guarda en este worker, la persiste y avisa a los suscriptores."""
    _CONEXIONES[conexion.id] = conexion
    await run_in_threadpool(_persistir, conexion)
    await _avisar_cambio()


async def actualizar(conexion: Conexion) -> None:
    """Persiste el estado declarado por la app (`hola`/`marcas`) y avisa a los suscriptores."""
    await run_in_threadpool(_persistir, conexion)
    await _avisar_cambio()


async def latido(conexion: Conexion) -> None:
    """Refresca el `visto_en` de la conexión (heartbeat ~20 s; mantiene viva su fila)."""
    await run_in_threadpool(repos.tunel_latido_conexion, conexion.id, ahora_iso())


async def desregistrar(conexion: Conexion) -> None:
    """Da de baja una conexión, falla sus RPC vivos, borra su fila y avisa. Idempotente."""
    _CONEXIONES.pop(conexion.id, None)
    conexion.cancelar_todo()
    await run_in_threadpool(repos.tunel_baja_conexion, conexion.id)
    await _avisar_cambio()


# --------------------------------------------------------------------------- #
# Lecturas del registro compartido (consistentes en CUALQUIER worker)           #
# --------------------------------------------------------------------------- #


def _conexiones_vivas() -> list[dict[str, Any]]:
    """Filas de conexiones vivas (heartbeat fresco), parseadas; barre las muertas de paso."""
    umbral = _umbral_vivo()
    vivas = [_fila_a_conexion(f) for f in repos.tunel_conexiones_vivas(umbral)]
    repos.tunel_purgar_conexiones_muertas(umbral)
    return vivas


def _fila_a_conexion(f: dict[str, Any]) -> dict[str, Any]:
    """Normaliza una fila de `tunel_conexiones` (marcas/galerias de JSON a lista)."""
    return {
        "id": f.get("id", ""),
        "worker": f.get("worker", ""),
        "usuario": f.get("usuario", ""),
        "dispositivo": f.get("dispositivo", ""),
        "version": f.get("version", ""),
        "marcas": [m for m in _cargar_lista(f.get("marcas")) if isinstance(m, str)],
        "galerias": [g for g in _cargar_lista(f.get("galerias")) if isinstance(g, dict)],
        "visto_en": f.get("visto_en", ""),
    }


def conexiones_de_marca(marca: str | None) -> list[dict[str, Any]]:
    """Conexiones vivas que comparten su galería a `marca` (cualquier dueño)."""
    if not marca:
        return []
    return [c for c in _conexiones_vivas() if marca in c["marcas"]]


def dispositivos_registrados() -> list[dict[str, Any]]:
    """Listado de la Galería: usuarios REGISTRADOS (token de escritorio) con flag `online`.

    NO se filtra por marca (la marca filtra la BÚSQUEDA, no el listado). Cada item es
    `{usuario, online, dispositivo?, marcas?, galerias?}`: los offline solo `{usuario, online:False}`;
    los online llevan los datos de su conexión viva. Un dispositivo conectado sin token registrado
    (no debería pasar: el token es obligatorio) también se incluye, como online.
    """
    registrados = repos.tunel_usuarios_registrados(ETIQUETA_ESCRITORIO, ahora_iso())
    vivas = _conexiones_vivas()
    por_usuario: dict[str, dict[str, Any]] = {}
    for c in vivas:  # `_conexiones_vivas` viene por `visto_en` desc: la más reciente gana
        por_usuario.setdefault(c["usuario"], c)

    items: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for reg in registrados:
        uid = reg.get("usuario_id", "")
        vistos.add(uid)
        items.append(_item_dispositivo(uid, por_usuario.get(uid)))
    for uid, conexion in por_usuario.items():
        if uid not in vistos:
            items.append(_item_dispositivo(uid, conexion))
    return items


def _item_dispositivo(usuario: str, conexion: dict[str, Any] | None) -> dict[str, Any]:
    """Forma de un item del listado de la Galería para `usuario` (online si hay `conexion`)."""
    if conexion is None:
        return {"usuario": usuario, "online": False}
    return {
        "usuario": usuario,
        "online": True,
        "dispositivo": conexion["dispositivo"],
        "marcas": conexion["marcas"],
        "galerias": conexion["galerias"],
    }


def nombre_galeria(marca: str | None, galeria_id: str) -> str:
    """Nombre declarado de la galería `galeria_id` (entre las apps que comparten `marca`); '' si no hay.

    La biblioteca lo usa como `grupo` (carpeta lógica, p. ej. el partido) al guardar una foto
    remota: la app declara sus galerías como `{id, nombre}` en el `hola`. Si ninguna conexión la
    declara con nombre, devuelve '' (el llamante cae al `galeria_id`).
    """
    if not galeria_id:
        return ""
    conns = conexiones_de_marca(marca) if marca else _conexiones_vivas()
    for conexion in conns:
        for g in conexion["galerias"]:
            if str(g.get("id") or "") == galeria_id:
                nombre = str(g.get("nombre") or "").strip()
                if nombre:
                    return nombre
    return ""


def _elegir_conexion(
    marca: str | None, galeria_id: str, dispositivo: str
) -> dict[str, Any] | None:
    """Conexión que sirve el original (entre las que comparten `marca`): por `dispositivo`, luego galería, luego la 1ª."""
    conns = conexiones_de_marca(marca)
    if not conns:
        return None
    if dispositivo:
        for conexion in conns:
            if conexion["dispositivo"] == dispositivo:
                return conexion
    if galeria_id:
        for conexion in conns:
            if any(str(g.get("id") or "") == galeria_id for g in conexion["galerias"]):
                return conexion
    return conns[0]


# --------------------------------------------------------------------------- #
# Bus RPC: encolar (lado peticionario) y ejecutar (worker dueño del WebSocket)   #
# --------------------------------------------------------------------------- #


def _mensaje_rpc(tipo: str, payload: dict[str, Any]) -> tuple[dict[str, Any] | None, float]:
    """Construye el mensaje del protocolo WS y su timeout a partir del tipo + payload del RPC."""
    if tipo == "buscar":
        return {"tipo": "buscar", "q": payload.get("q", ""), "limite": payload.get("limite", 0)}, _TIMEOUT_BUSCAR
    if tipo == "original":
        return {
            "tipo": "original",
            "galeria_id": payload.get("galeria_id", ""),
            "archivo": payload.get("archivo", ""),
        }, _TIMEOUT_ORIGINAL
    if tipo == "rafaga":
        return {
            "tipo": "rafaga",
            "galeria_id": payload.get("galeria_id", ""),
            "archivo": payload.get("archivo", ""),
            "limite": payload.get("limite", 24),
        }, _TIMEOUT_RAFAGA
    if tipo == "galeria":
        return {
            "tipo": "galeria",
            "galeria_id": payload.get("galeria_id", ""),
            "limite": payload.get("limite", 200),
        }, _TIMEOUT_BUSCAR
    return None, 0.0


def _despertar() -> None:
    """Despierta a los waiters de RPC de ESTE worker (un `tunel_rpc_done` o un ejecutor que acabó)."""
    if _evento_done is not None and _evento_loop is _bucle_actual():
        _evento_done.set()


def _bucle_actual() -> Any:
    """Bucle de eventos en curso, o None si no hay (no debería llamarse fuera de async)."""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def _evento() -> asyncio.Event:
    """Evento de despertar de RPC ligado al bucle vigente (lo recrea si el bucle cambió)."""
    global _evento_done, _evento_loop
    loop = asyncio.get_running_loop()
    if _evento_done is None or _evento_loop is not loop:
        _evento_done = asyncio.Event()
        _evento_loop = loop
    return _evento_done


def _crear_rpc_row(rid: str, tipo: str, conexion_id: str, payload: dict[str, Any]) -> None:
    """Inserta el RPC `pendiente` y avisa (NOTIFY `tunel_rpc`) a los workers. Corre en threadpool."""
    repos.tunel_crear_rpc(
        id=rid,
        tipo=tipo,
        conexion_id=conexion_id,
        payload=json.dumps(payload, ensure_ascii=False),
        creado=ahora_iso(),
    )
    repos.tunel_notificar("tunel_rpc", rid)


async def _esperar_rpc(rid: str, timeout: float) -> dict[str, Any] | None:
    """Espera a que el RPC `rid` deje de estar `pendiente` (NOTIFY despierta; el sondeo respalda)."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        ev = _evento()
        ev.clear()
        fila = await run_in_threadpool(repos.tunel_leer_rpc, rid)
        if fila is None or fila.get("estado") != "pendiente":
            return fila
        restante = deadline - loop.time()
        if restante <= 0:
            return fila
        try:
            await asyncio.wait_for(ev.wait(), min(restante, _POLL_RPC))
        except TimeoutError:
            pass


async def _pedir_rpc(
    tipo: str, conexion_id: str, payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    """Encola un RPC a `conexion_id`, espera su resultado y lo devuelve (o lanza `TunelError`)."""
    rid = uuid.uuid4().hex
    await run_in_threadpool(_crear_rpc_row, rid, tipo, conexion_id, payload)
    # Si el WebSocket destino vive en ESTE worker, dispara la ejecución ya (sin esperar al NOTIFY):
    # cubre el caso de un solo worker y el de los tests, sin depender del bus de fondo.
    if conexion_id in _CONEXIONES:
        await _pasada_local()
    fila = await _esperar_rpc(rid, timeout)
    await run_in_threadpool(repos.tunel_borrar_rpc, rid)
    estado = fila.get("estado") if fila else "pendiente"
    resultado = _cargar_dict(fila.get("resultado")) if fila else {}
    if estado == "listo":
        return resultado
    if estado == "error":
        raise TunelError(resultado.get("error") or "El dispositivo devolvió un error.")
    raise TunelError("El dispositivo no respondió a tiempo.")


async def _pasada_local() -> None:
    """Ejecuta los RPC `pendiente` dirigidos a conexiones de ESTE worker (idempotente por `_EN_CURSO`)."""
    if not _CONEXIONES:
        return
    filas = await run_in_threadpool(repos.tunel_rpc_pendientes)
    for fila in filas:
        rid = fila.get("id", "")
        conexion_id = fila.get("conexion_id", "")
        if conexion_id in _CONEXIONES and rid not in _EN_CURSO:
            _EN_CURSO.add(rid)
            asyncio.ensure_future(_ejecutar_rpc(rid))


async def _ejecutar_rpc(rid: str) -> None:
    """Ejecuta el RPC `rid` sobre el WebSocket local dueño y deja su resultado en la tabla."""
    try:
        fila = await run_in_threadpool(repos.tunel_leer_rpc, rid)
        if fila is None or fila.get("estado") != "pendiente":
            return
        conexion = _CONEXIONES.get(fila.get("conexion_id", ""))
        if conexion is None:
            return
        mensaje, timeout = _mensaje_rpc(fila.get("tipo", ""), _cargar_dict(fila.get("payload")))
        if mensaje is None:
            estado, resultado = "error", {"error": "Tipo de RPC no soportado."}
        else:
            try:
                resultado = await conexion.rpc(mensaje, timeout)
                estado = "listo"
            except TunelError as e:
                estado, resultado = "error", {"error": str(e)}
        await run_in_threadpool(
            repos.tunel_resolver_rpc, rid, estado, json.dumps(resultado, ensure_ascii=False)
        )
        await run_in_threadpool(repos.tunel_notificar, "tunel_rpc_done", rid)
        _despertar()
    except Exception:  # noqa: BLE001 -- un fallo aquí no debe tumbar el bus; el waiter degrada por timeout
        _log.debug("Túnel keni-fotos: fallo ejecutando un RPC local.", exc_info=True)
    finally:
        _EN_CURSO.discard(rid)


# --------------------------------------------------------------------------- #
# RPC públicos (lado peticionario): los usan los endpoints HTTP de «Propio»     #
# --------------------------------------------------------------------------- #


async def buscar(marca: str | None, q: str, limite: int) -> list[dict[str, Any]]:
    """Fan-out de la búsqueda a las apps que comparten `marca`; agrega candidatos y trocea a `limite`.

    Cruza usuarios: cualquier dueño que comparta `marca` participa. Cada candidato lleva su
    `dispositivo` (de qué app vino) para que el adjuntar luego sepa a quién pedir el original. Una
    app caída/lenta no rompe la búsqueda: aporta `[]`.
    """
    if not marca or not q.strip() or limite <= 0:
        return []
    conns = await run_in_threadpool(conexiones_de_marca, marca)
    if not conns:
        return []

    async def _una(conexion: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            respuesta = await _pedir_rpc(
                "buscar", conexion["id"], {"q": q, "limite": limite}, _TIMEOUT_BUSCAR
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
            etiquetado.setdefault("dispositivo", conexion["dispositivo"])
            salida.append(etiquetado)
        return salida

    grupos = await asyncio.gather(*(_una(c) for c in conns))
    agregados = [candidato for grupo in grupos for candidato in grupo]
    return agregados[:limite]


async def rafaga(
    marca: str | None, galeria_id: str, archivo: str, dispositivo: str = "", limite: int = 24
) -> list[dict[str, Any]]:
    """Fotos del MISMO burst (ráfaga) que `archivo`, por el túnel; lista de `{archivo, thumb}`.

    Pide a la app (la que mejor encaja: por `dispositivo`, luego la que declaró la galería, luego la
    primera que comparte `marca`) las fotos del disparo continuo del keeper, para navegarlas como
    thumbs. Devuelve `[]` si no hay dispositivo, no responde o la respuesta llega vacía/corrupta (la
    UI degrada a "sin ráfaga"). El `thumb` es el `thumb_b64` que manda la app (data URL o desnudo).
    """
    conexion = await run_in_threadpool(_elegir_conexion, marca, galeria_id, dispositivo)
    if conexion is None or not archivo:
        return []
    try:
        respuesta = await _pedir_rpc(
            "rafaga",
            conexion["id"],
            {"galeria_id": galeria_id, "archivo": archivo, "limite": limite},
            _TIMEOUT_RAFAGA,
        )
    except TunelError:
        _log.debug("Túnel keni-fotos: la app no respondió a la ráfaga; se omite.")
        return []
    crudos = respuesta.get("fotos") if isinstance(respuesta, dict) else None
    salida: list[dict[str, Any]] = []
    for foto in crudos or []:
        if not isinstance(foto, dict):
            continue
        nombre = str(foto.get("archivo") or "")
        thumb = str(foto.get("thumb_b64") or foto.get("thumb") or "")
        if nombre:
            salida.append({"archivo": nombre, "thumb": thumb})
    return salida[:limite]


async def galeria(
    marca: str | None, galeria_id: str, dispositivo: str = "", limite: int = 200
) -> list[dict[str, Any]]:
    """Lista los KEEPERS de una galería (partido) conectada, para navegarla como una carpeta.

    Pide a la app que mejor encaja (por `dispositivo`, luego la que declaró la galería, luego la
    primera que comparte `marca`) los candidatos del manifiesto de `galeria_id`, en la MISMA forma
    que `buscar` (cada candidato con su `thumb_b64`). Cada candidato se etiqueta con el `dispositivo`
    que lo sirvió para poder pedir luego el original. Devuelve `[]` si no hay dispositivo, no responde
    o la respuesta llega vacía/corrupta (la UI degrada a "carpeta vacía").
    """
    conexion = await run_in_threadpool(_elegir_conexion, marca, galeria_id, dispositivo)
    if conexion is None or not galeria_id or limite <= 0:
        return []
    try:
        respuesta = await _pedir_rpc(
            "galeria", conexion["id"], {"galeria_id": galeria_id, "limite": limite}, _TIMEOUT_BUSCAR
        )
    except TunelError:
        _log.debug("Túnel keni-fotos: la app no respondió al listado de la galería; se omite.")
        return []
    crudos = respuesta.get("candidatos") if isinstance(respuesta, dict) else None
    salida: list[dict[str, Any]] = []
    for candidato in crudos or []:
        if not isinstance(candidato, dict):
            continue
        etiquetado = dict(candidato)
        etiquetado.setdefault("dispositivo", conexion["dispositivo"])
        salida.append(etiquetado)
    return salida[:limite]


async def pedir_original(
    marca: str | None, galeria_id: str, archivo: str, dispositivo: str = ""
) -> tuple[bytes, str]:
    """Pide el ORIGINAL (`galeria_id`/`archivo`) por el túnel; devuelve `(bytes, mime)`.

    Solo a apps que comparten `marca` (no se expone una galería a una marca que no tiene permitida).
    Entre ellas elige la que mejor encaja: la del `dispositivo` indicado, si no la que declaró esa
    galería, y si no la primera. Lanza `TunelError` si no hay dispositivo, no responde o la imagen
    llega vacía/corrupta.
    """
    conexion = await run_in_threadpool(_elegir_conexion, marca, galeria_id, dispositivo)
    if conexion is None:
        raise TunelError("No hay ningún dispositivo conectado con esa galería.")
    respuesta = await _pedir_rpc(
        "original", conexion["id"], {"galeria_id": galeria_id, "archivo": archivo}, _TIMEOUT_ORIGINAL
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


# --------------------------------------------------------------------------- #
# Bus de fondo (por worker): LISTEN para promptness + mantenimiento (respaldo)   #
# --------------------------------------------------------------------------- #


async def _manejar_notify(canal: str, payload: str) -> None:
    """Reacciona a un NOTIFY: re-empuja el SSE, ejecuta RPC locales o despierta a los waiters."""
    if canal == "tunel_cambio":
        _notificar_cambio()
    elif canal == "tunel_rpc":
        await _pasada_local()
    elif canal == "tunel_rpc_done":
        _despertar()


async def _bucle_listen() -> None:
    """LISTEN a los canales del túnel: traduce cada NOTIFY a su efecto local. Reconecta con backoff."""
    import psycopg

    while not _parar:
        url = config.database_url()
        if not url:
            await asyncio.sleep(_BACKOFF_LISTEN)
            continue
        aconn = None
        try:
            aconn = await psycopg.AsyncConnection.connect(url, autocommit=True)
            await aconn.execute("LISTEN tunel_cambio")
            await aconn.execute("LISTEN tunel_rpc")
            await aconn.execute("LISTEN tunel_rpc_done")
            await _pasada_local()  # al (re)conectar, recoge lo que se hubiera encolado mientras tanto
            async for notify in aconn.notifies():
                if _parar:
                    break
                await _manejar_notify(notify.channel, notify.payload)
        except asyncio.CancelledError:
            break
        except Exception:  # noqa: BLE001 -- la LISTEN se cayó: reconecta; el mantenimiento cubre el hueco
            _log.debug("Túnel keni-fotos: la conexión LISTEN terminó; se reintenta.", exc_info=True)
        finally:
            if aconn is not None:
                try:
                    await aconn.close()
                except Exception:  # noqa: BLE001 -- cerrar es best-effort
                    pass
        if not _parar:
            await asyncio.sleep(_BACKOFF_LISTEN)


def _sweep() -> None:
    """Barrido perezoso: borra conexiones muertas (worker caído) y RPC huérfanos."""
    repos.tunel_purgar_conexiones_muertas(_umbral_vivo())
    repos.tunel_purgar_rpc_viejos(_umbral_rpc())


async def _bucle_mantenimiento() -> None:
    """Respaldo del bus: ejecuta pendientes locales (avisos perdidos) y barre filas viejas."""
    while not _parar:
        try:
            await _pasada_local()
            await run_in_threadpool(_sweep)
        except Exception:  # noqa: BLE001 -- el mantenimiento no debe tumbar el worker
            _log.debug("Túnel keni-fotos: fallo en el mantenimiento del bus.", exc_info=True)
        try:
            await asyncio.sleep(_POLL_MANT)
        except asyncio.CancelledError:
            break


def iniciar_bus() -> None:
    """Arranca el bus del túnel (LISTEN + mantenimiento) en el bucle vigente. Idempotente.

    Lo llama el arranque del back (lifespan). Cada worker tiene su propio bus: la LISTEN da
    promptness y el bucle de mantenimiento es el respaldo (sondeo) si un NOTIFY se pierde.
    """
    global _parar, _tarea_listen, _tarea_mant
    # Bajo pytest no se arranca el bus de fondo: los tests ejercitan el registro y el bus llamando
    # a sus funciones directamente; un listener/mantenimiento de fondo añadiría tareas y una
    # conexión LISTEN a cada app de test sin aportar cobertura.
    if "PYTEST_CURRENT_TEST" in os.environ:
        return
    _parar = False
    loop = asyncio.get_running_loop()
    if _tarea_listen is None or _tarea_listen.done():
        _tarea_listen = loop.create_task(_bucle_listen())
    if _tarea_mant is None or _tarea_mant.done():
        _tarea_mant = loop.create_task(_bucle_mantenimiento())


async def detener_bus() -> None:
    """Para el bus del túnel (cancela sus tareas). Best-effort; idempotente."""
    global _parar, _tarea_listen, _tarea_mant
    _parar = True
    for tarea in (_tarea_listen, _tarea_mant):
        if tarea is not None:
            tarea.cancel()
            try:
                await tarea
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 -- parada best-effort
                pass
    _tarea_listen = None
    _tarea_mant = None
