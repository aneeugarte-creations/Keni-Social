"""API HTTP de la app «Fotos» — el LANZADOR de la herramienta local keni-fotos.

Fotos no procesa imágenes en la nube: la consola no puede leer el disco del equipo de
Ale, así que esta superficie sirve para DESCARGAR la herramienta local (el `.dmg` de la app
de escritorio Tauri) y entregar el prompt + los comandos para montarla con un Claude local.

QUE VIVE AQUI
=============
  - `GET /api/fotos/info`    -> `{version, prompt_claude, comandos, instrucciones}`: el texto
                                que la página muestra para copiar (prompt de Claude, comandos y
                                pasos). Constantes legibles, fuente única de verdad del lanzador.
  - `GET /api/fotos/app`     -> descarga el `.dmg` de la app de escritorio (FileResponse,
                                attachment). La ruta sale de `KENI_FOTOS_APP`; por defecto, el
                                fichero colocado junto a este módulo en `_fotos_bundle/`.
  - `GET /api/fotos/bundle`  -> descarga `keni-fotos.zip` (el código, modo avanzado con Claude).
                                Ruta de `KENI_FOTOS_BUNDLE` o el de por defecto en `_fotos_bundle/`.
                                Si falta el fichero, responde 404 claro, no casca.
  - `GET /api/fotos/actualizacion/{target}/{arch}/{version}` -> endpoint del auto-update de Tauri
                                (`tauri-plugin-updater`). 204 si la versión instalada ya es la
                                última; 200 con el JSON Tauri (version/notes/pub_date/platforms)
                                si hay una más nueva. La release actual sale del manifiesto
                                `_fotos_release/release.json`. Es PUBLICO (lo poletea la app sin
                                sesión); ver la exención en `seguridad.py`.
  - `POST /api/fotos/autorizar` -> lado-nube del login OPCIONAL del escritorio (flujo loopback).
                                Lo llama la página `/fotos/autorizar` del SPA tras el «Autorizar» de
                                una persona con sesión: emite un TOKEN opaco ligado al usuario y
                                devuelve `{redirect}` (la URL loopback `cb?token=&state=`).
  - `GET /api/fotos/sesion`  -> identifica al escritorio por su token (`Authorization: Bearer`) ->
                                `{usuario}`. PUBLICO en el middleware: hace su PROPIA auth con el
                                token de escritorio (no usa cookie de sesión ni token de Consola).

App propia (`apps/fotos.toml`, modulos_backend=["fotos"]): sin cruces de frontera. Las descargas y
el lanzador son de solo lectura; la autorización del escritorio emite un token MCP por identidad
(`auth.crear_token_mcp`). Errores como JSON `{"error": ...}` en español, sin tracebacks.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from .. import auth, fotos_tunel
from .._http_json import leer_json

_log = logging.getLogger("keni_consola.fotos")

# Versión de la herramienta local que sirve este lanzador. Es la fuente de verdad del
# auto-update: la app local compara su versión contra esta y se actualiza si va por detrás.
VERSION = "0.3.0"

# Changelog corto (2-3 líneas) de la versión actual; se muestra en la ficha de la página.
CHANGELOG = [
    "Mismo marco que keni-social: menú de usuario, tema claro/oscuro y página Sistema.",
    "Galería con la lista de partidos procesados; sube y revisa varios.",
    "Copia y descarta fotos/ráfagas (a la Papelera) y detecta Claude al instante.",
]

# Prompt que el equipo pega en su Claude local tras descomprimir el bundle. El Claude local NO
# procesa fotos: su único trabajo es COMPILAR y LANZAR la app; la propia app guía a la persona.
PROMPT_CLAUDE = (
    "Eres el agente local de keni-fotos. Tu ÚNICO trabajo es compilar y lanzar la app: "
    "lee el CLAUDE.md de esta carpeta y déjala abierta en el navegador. NO proceses fotos "
    "tú; la propia app guía a la persona para elegir la carpeta del partido, ponerle nombre "
    "y ejecutar el etiquetado. Cuando la app esté abierta, avísame."
)

# Comandos para descomprimir y arrancar, en orden. `ls -t … | head -1` coge el zip más reciente,
# así funciona aunque el navegador lo guarde como «keni-fotos (1).zip», «(2)», etc.
COMANDOS = [
    "cd ~/Downloads",
    'unzip -o "$(ls -t keni-fotos*.zip | head -1)"',
    "cd keni-fotos && claude",
]

# Pasos 1·2·3 que guían a la persona desde la descarga hasta tener la app abierta.
INSTRUCCIONES = [
    "Descarga keni-fotos y descomprímelo (los comandos de abajo lo hacen por ti).",
    "Abre Claude Code en la carpeta keni-fotos y pega el prompt: compila y lanza la app.",
    "En la app: elige tu carpeta de fotos, ponle nombre al partido y pulsa Procesar.",
]

# Dos artefactos descargables (Content-Disposition attachment):
#  - keni-fotos.dmg : la app de escritorio Tauri (.dmg), vía principal de la página ("Descargar app").
#  - keni-fotos.zip : el código, que usa el modo avanzado (montar con Claude). Ambos en `_fotos_bundle/`.
# Binarios servidos desde aquí (Garage es interno, no tiene URL pública): el .dmg de descarga,
# el zip del modo avanzado y el .app.tar.gz firmado del auto-update (al que apunta `release.json`).
_NOMBRE_BUNDLE = "keni-fotos.zip"
_NOMBRE_UPDATER = "keni-fotos.app.tar.gz"
_DIR_BUNDLE = Path(__file__).parent / "_fotos_bundle"
_APP_DEFECTO = _DIR_BUNDLE / "keni-fotos.dmg"
_BUNDLE_DEFECTO = _DIR_BUNDLE / _NOMBRE_BUNDLE
_UPDATER_DEFECTO = _DIR_BUNDLE / _NOMBRE_UPDATER

# Manifiesto de la release actual (lo actualiza el release script de keni-fotos en cada versión).
# Fuente única de verdad del auto-update: versión, notas, fecha y, por plataforma, firma + url.
_RELEASE_DEFECTO = Path(__file__).parent / "_fotos_release" / "release.json"

# Plataformas que sirve el updater hoy (clave Tauri `{target}-{arch}`). Solo Apple Silicon.
_PLATAFORMAS = ("darwin-aarch64",)


def _ruta_app() -> Path:
    """Ruta del .dmg de la app: `KENI_FOTOS_APP` si está definida, si no la de por defecto."""
    env = (os.environ.get("KENI_FOTOS_APP") or "").strip()
    return Path(env) if env else _APP_DEFECTO


def _ruta_bundle() -> Path:
    """Ruta del zip a servir: `KENI_FOTOS_BUNDLE` si está definida, si no la de por defecto."""
    env = (os.environ.get("KENI_FOTOS_BUNDLE") or "").strip()
    return Path(env) if env else _BUNDLE_DEFECTO


def _ruta_updater() -> Path:
    """Ruta del .app.tar.gz del auto-update: `KENI_FOTOS_UPDATER` si está, si no la de por defecto."""
    env = (os.environ.get("KENI_FOTOS_UPDATER") or "").strip()
    return Path(env) if env else _UPDATER_DEFECTO


def _ruta_release() -> Path:
    """Ruta del manifiesto de release: `KENI_FOTOS_RELEASE` si está definida, si no la de por defecto."""
    env = (os.environ.get("KENI_FOTOS_RELEASE") or "").strip()
    return Path(env) if env else _RELEASE_DEFECTO


def _leer_release() -> dict | None:
    """Lee y parsea el manifiesto de release; None si falta o no es JSON válido (no casca)."""
    ruta = _ruta_release()
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return datos if isinstance(datos, dict) else None


def _parsear_version(texto: str) -> tuple[int, int, int] | None:
    """`"1.2"` -> `(1, 2, 0)`. Ignora pre-release/build (`-rc1`, `+meta`). None si no es numérica.

    Normaliza a `major.minor.patch` (rellena con 0 lo que falte) para comparar sin sorpresas
    entre longitudes (`(0, 1)` vs `(0, 1, 0)`).
    """
    nucleo = texto.strip().split("+", 1)[0].split("-", 1)[0]
    partes = nucleo.split(".")
    if not nucleo or len(partes) > 3:
        return None
    try:
        nums = [int(p) for p in partes]
    except ValueError:
        return None
    while len(nums) < 3:
        nums.append(0)
    return (nums[0], nums[1], nums[2])


async def info(request: Request) -> Response:
    """GET /api/fotos/info: el texto del lanzador (prompt, comandos y pasos) + la versión."""
    return JSONResponse(
        {
            "version": VERSION,
            "changelog": CHANGELOG,
            "prompt_claude": PROMPT_CLAUDE,
            "comandos": COMANDOS,
            "instrucciones": INSTRUCCIONES,
        }
    )


def _servir_descarga(ruta: Path, nombre: str, media_type: str) -> Response:
    """Sirve un fichero como descarga, o 404 con mensaje si aún no está colocado."""
    if not ruta.is_file():
        return JSONResponse(
            {"error": "La herramienta keni-fotos aún no está disponible para descargar."},
            status_code=404,
        )
    return FileResponse(ruta, media_type=media_type, filename=nombre)


def _nombre_dmg() -> str:
    """Nombre del `.dmg` descargado, con la versión del manifiesto: `keni-fotos_<ver>_aarch64.dmg`."""
    release = _leer_release()
    version = str(release.get("version") or "").strip() if release else ""
    return f"keni-fotos_{version}_aarch64.dmg" if version else "keni-fotos_aarch64.dmg"


async def app_descarga(request: Request) -> Response:
    """GET /api/fotos/app: descarga el `.dmg` de la app de escritorio Tauri (macOS Apple Silicon)."""
    return _servir_descarga(_ruta_app(), _nombre_dmg(), "application/x-apple-diskimage")


async def bundle(request: Request) -> Response:
    """GET /api/fotos/bundle: el código `keni-fotos.zip` (modo avanzado, montar con Claude)."""
    return _servir_descarga(_ruta_bundle(), _NOMBRE_BUNDLE, "application/zip")


async def updater(request: Request) -> Response:
    """GET /api/fotos/updater: el `.app.tar.gz` firmado del auto-update (lo descarga Tauri)."""
    return _servir_descarga(_ruta_updater(), _NOMBRE_UPDATER, "application/gzip")


async def actualizacion(request: Request) -> Response:
    """GET /api/fotos/actualizacion/{target}/{arch}/{version}: endpoint del updater de Tauri.

    Compara la versión instalada (`version`, en la URL) con la del manifiesto de release. Si la
    instalada es igual o mayor, o no hay binario para `{target}-{arch}`, devuelve 204 (sin update).
    Si va por detrás, 200 con el JSON Tauri `{version, notes, pub_date, platforms:{<plat>:{signature,
    url}}}` para esa plataforma. Cualquier dato ausente/ilegible se trata como «sin update» (204).
    """
    plataforma = f"{request.path_params['target']}-{request.path_params['arch']}"
    release = _leer_release()
    if release is None or plataforma not in _PLATAFORMAS:
        return Response(status_code=204)

    binario = release.get(plataforma)
    ultima = _parsear_version(str(release.get("version") or ""))
    instalada = _parsear_version(str(request.path_params["version"]))
    if not isinstance(binario, dict) or ultima is None or instalada is None or instalada >= ultima:
        return Response(status_code=204)

    return JSONResponse(
        {
            "version": release.get("version"),
            "notes": release.get("notes", ""),
            "pub_date": release.get("pub_date", ""),
            "platforms": {
                plataforma: {
                    "signature": binario.get("signature", ""),
                    "url": binario.get("url", ""),
                }
            },
        }
    )


# --------------------------------------------------------------------------- #
# Login OPCIONAL del escritorio keni-fotos (flujo loopback)                     #
# --------------------------------------------------------------------------- #
#
# La app de escritorio levanta un servidor http EFÍMERO en `127.0.0.1:<puerto>` y abre en el
# navegador `https://social.kenitech.io/fotos/autorizar?cb=http://127.0.0.1:<puerto>/cb&state=<azar>`.
# Esa PÁGINA (ruta del SPA, no de aquí) exige sesión de keni-social y, al pulsar «Autorizar», llama
# a `POST /api/fotos/autorizar`: emitimos un TOKEN opaco ligado al usuario y devolvemos la URL de
# retorno `cb?token=<token>&state=<state>`, a la que el navegador redirige. La app valida el `state`
# (anti-CSRF) y guarda el token en su keychain. Ese token (un token MCP por identidad,
# `auth.crear_token_mcp`) es el único secreto del escritorio: hoy lo valida `GET /api/fotos/sesion`
# (quién está conectado) y mañana autenticará el túnel y el updater.

# Etiqueta humana del token de escritorio en el listado de tokens del usuario.
_ETIQUETA_TOKEN_FOTOS = "keni-fotos (escritorio)"

# Topes anti-DoS de los parámetros del callback (se reflejan en la URL de retorno).
_MAX_LARGO_CB = 512
_MAX_LARGO_STATE = 256

# Hosts loopback admitidos como destino del callback: SOLO la máquina local. Cualquier otro host se
# rechaza para que esta página no sea un open-redirect que filtre el token a un tercero.
_HOSTS_LOOPBACK = frozenset({"127.0.0.1", "localhost"})


def _cb_loopback_valido(cb: str) -> bool:
    """True si `cb` es un callback loopback seguro: `http://127.0.0.1|localhost[:puerto]/...`.

    Exige esquema http (la app escucha en http plano sobre loopback) y host loopback. Rechaza
    cualquier otro esquema/host: el token solo se entrega a un servidor de la propia máquina.
    """
    if not cb or len(cb) > _MAX_LARGO_CB:
        return False
    try:
        partes = urlsplit(cb)
    except ValueError:
        return False
    return partes.scheme == "http" and (partes.hostname or "") in _HOSTS_LOOPBACK


def _token_bearer(request: Request) -> str | None:
    """Token presentado en `Authorization: Bearer <token>` (None si no viene o está vacío)."""
    cabecera = request.headers.get("authorization", "")
    if cabecera.lower().startswith("bearer "):
        valor = cabecera[len("bearer "):].strip()
        if valor:
            return valor
    return None


async def autorizar(request: Request) -> Response:
    """POST /api/fotos/autorizar: emite el token de escritorio y devuelve la URL de retorno.

    Lo llama la página `/fotos/autorizar` del SPA tras el «Autorizar» de una persona con sesión.
    Exige sesión real (el token de mantenimiento no tiene usuario -> 401). Valida que `cb` es un
    loopback seguro (anti open-redirect) y emite un token MCP ligado al usuario; responde
    `{"redirect": "<cb>?token=<token>&state=<state>"}` para que el navegador redirija al loopback.
    """
    usuario = getattr(request.state, "usuario", None)
    if not isinstance(usuario, dict):
        return JSONResponse(
            {"error": "Necesitas una sesión iniciada para autorizar keni-fotos."},
            status_code=401,
        )
    datos = await leer_json(request)
    cb = datos.get("cb")
    state = datos.get("state")
    if not isinstance(cb, str) or not _cb_loopback_valido(cb):
        return JSONResponse(
            {"error": "El destino de la autorización no es válido."}, status_code=400
        )
    if not isinstance(state, str) or not state or len(state) > _MAX_LARGO_STATE:
        return JSONResponse({"error": "Falta el parámetro de seguridad."}, status_code=400)

    token = auth.crear_token_mcp(usuario["id"], _ETIQUETA_TOKEN_FOTOS)
    separador = "&" if "?" in cb else "?"
    redirect = f"{cb}{separador}{urlencode({'token': token, 'state': state})}"
    return JSONResponse({"redirect": redirect})


async def sesion(request: Request) -> Response:
    """GET /api/fotos/sesion: identifica al escritorio por su token (Bearer) -> `{usuario}`.

    PUBLICO en el middleware (la app no tiene cookie de sesión ni el token de mantenimiento): hace
    su PROPIA auth con el token de escritorio (`Authorization: Bearer <token>`), que valida
    `auth.token_mcp_valido`. 401 si falta, es inválido, está revocado o caducó.
    """
    token = _token_bearer(request)
    usuario = auth.token_mcp_valido(token) if token else None
    if usuario is None:
        return JSONResponse(
            {"error": "Token de keni-fotos inválido o caducado."}, status_code=401
        )
    return JSONResponse(
        {"usuario": {"id": usuario["id"], "usuario": usuario["usuario"], "rol": usuario["rol"]}}
    )


# --------------------------------------------------------------------------- #
# Túnel keni-fotos (WebSocket app -> backend)                                   #
# --------------------------------------------------------------------------- #
#
# La app de escritorio abre un WebSocket SALIENTE hacia `/api/tunel/fotos`, autenticado con su
# token de escritorio (el mismo token MCP que valida `/api/fotos/sesion`). El backend registra la
# conexión por usuario (`fotos_tunel`) y, cuando el SPA busca/adjunta fotos «Propio», hace RPC por
# este canal. El middleware `SeguridadConsola` solo actúa sobre HTTP: el scope websocket pasa intacto,
# así que la auth la hace este handler a mano (Bearer -> `auth.token_mcp_valido`).


def _procesar_mensaje(conexion: fotos_tunel.Conexion, mensaje: dict) -> None:
    """Despacha un mensaje de la app: `hola` (registro) o respuesta de un RPC pendiente."""
    tipo = mensaje.get("tipo")
    if tipo == "hola":
        conexion.registrar_hola(mensaje)
        return
    reqid = mensaje.get("id")
    if not isinstance(reqid, str):
        return
    if tipo in ("resultado", "original_datos"):
        conexion.resolver(reqid, mensaje)
    elif tipo == "error":
        conexion.fallar(reqid, str(mensaje.get("mensaje") or ""))


async def tunel(websocket: WebSocket) -> None:
    """WebSocket del túnel keni-fotos: la app de escritorio se conecta y queda registrada por usuario.

    Acepta, valida el token de escritorio (`Authorization: Bearer`); si no vale, cierra (4401). Mientras
    dure, procesa `hola`/`resultado`/`original_datos`/`error` (los dos del medio resuelven los RPC del
    dispatcher). Al desconectar, limpia el registro y falla los RPC vivos.
    """
    await websocket.accept()
    token = _token_bearer_ws(websocket)
    usuario = await run_in_threadpool(auth.token_mcp_valido, token) if token else None
    if usuario is None:
        await websocket.close(code=4401)
        return
    conexion = fotos_tunel.Conexion(websocket, usuario["id"])
    fotos_tunel.registrar(conexion)
    try:
        while True:
            try:
                mensaje = await websocket.receive_json()
            except WebSocketDisconnect:
                break
            if isinstance(mensaje, dict):
                _procesar_mensaje(conexion, mensaje)
    except Exception:  # noqa: BLE001 -- cualquier fallo del canal cierra la conexión limpiamente
        _log.debug("Túnel keni-fotos: conexión terminada por un error.", exc_info=True)
    finally:
        fotos_tunel.desregistrar(conexion)


def _token_bearer_ws(websocket: WebSocket) -> str | None:
    """Token `Authorization: Bearer <token>` de la cabecera del WebSocket (None si falta)."""
    cabecera = websocket.headers.get("authorization", "")
    if cabecera.lower().startswith("bearer "):
        valor = cabecera[len("bearer "):].strip()
        if valor:
            return valor
    return None


RUTAS = [
    Route("/api/fotos/info", info, methods=["GET"]),
    Route("/api/fotos/app", app_descarga, methods=["GET"]),
    Route("/api/fotos/bundle", bundle, methods=["GET"]),
    Route("/api/fotos/updater", updater, methods=["GET"]),
    Route(
        "/api/fotos/actualizacion/{target}/{arch}/{version}",
        actualizacion,
        methods=["GET"],
    ),
    Route("/api/fotos/autorizar", autorizar, methods=["POST"]),
    Route("/api/fotos/sesion", sesion, methods=["GET"]),
    WebSocketRoute("/api/tunel/fotos", tunel),
]
