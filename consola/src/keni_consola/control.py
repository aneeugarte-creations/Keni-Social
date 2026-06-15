"""Listener de CONTROL interno del proceso `daemons`: gestion de la cuenta de Claude.

POR QUE UN LISTENER APARTE (y no la API del back): cambiar la cuenta de Claude exige
EJECUTAR `claude` (auth status/login/logout, /usage). El `back` NO tiene `claude` (solo
encola); quien lo tiene es la imagen del worker (worker/daemons). El `daemons` es de
INSTANCIA UNICA (no escala como el worker), asi que es el sitio natural para alojar el
login interactivo, que mantiene un proceso vivo entre dos peticiones (URL -> pegar codigo).

SUPERFICIE: un Starlette minimo servido por uvicorn en un hilo del `daemons`, en la red
INTERNA de docker (NUNCA por Traefik). Lo protege un BEARER (`KENI_CONTROL_BEARER`): sin el
configurado, el listener NO se monta (apagado por defecto). El `back` lo proxea (admin-gated)
enviando ese bearer. Las operaciones son BLOQUEANTES (subprocess `claude`): se corren en el
threadpool para no bloquear el bucle asincrono.

Rutas (bajo `/control/cuenta`, contrato con el proxy del back en `api/sistema/cuenta.py`):
  - GET  /control/cuenta/estado        -> {auth:{...}, uso:{...}}
  - POST /control/cuenta/login/iniciar -> {sesion, url, salida}  (lanza login, devuelve URL)
  - POST /control/cuenta/login/codigo  -> {ok, mensaje, salida}  (pega el codigo)
  - POST /control/cuenta/login/cancelar-> {ok}
  - POST /control/cuenta/logout        -> {ok, mensaje}
  - GET  /control/healthz              -> {ok:true}  (sonda, sin bearer)
"""

from __future__ import annotations

import logging
import secrets
import threading

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from . import config, cuenta_claude

_log = logging.getLogger("keni_consola.control")


def _autorizado(request: Request) -> bool:
    """True si la peticion trae `Authorization: Bearer <KENI_CONTROL_BEARER>` (tiempo cte.)."""
    esperado = config.control_bearer()
    if not esperado:
        return False
    cabecera = request.headers.get("authorization", "")
    if not cabecera.lower().startswith("bearer "):
        return False
    presentado = cabecera[len("bearer ") :].strip()
    return secrets.compare_digest(presentado, esperado)


def _rechazo() -> Response:
    return JSONResponse({"error": "no autorizado"}, status_code=401)


async def _cuerpo(request: Request) -> dict:
    try:
        datos = await request.json()
    except Exception:  # noqa: BLE001 -- cuerpo ausente/no-JSON: tratamos como vacio
        return {}
    return datos if isinstance(datos, dict) else {}


async def healthz(request: Request) -> Response:
    return JSONResponse({"ok": True})


async def estado(request: Request) -> Response:
    if not _autorizado(request):
        return _rechazo()
    auth = await run_in_threadpool(cuenta_claude.estado)
    uso = await run_in_threadpool(cuenta_claude.uso)
    return JSONResponse({"auth": auth, "uso": uso})


async def login_iniciar(request: Request) -> Response:
    if not _autorizado(request):
        return _rechazo()
    cuerpo = await _cuerpo(request)
    consola = bool(cuerpo.get("console"))
    email = cuerpo.get("email") or None
    sso = bool(cuerpo.get("sso"))
    res = await run_in_threadpool(
        cuenta_claude.iniciar_login, console=consola, email=email, sso=sso
    )
    status = 200 if res.get("url") else 502
    return JSONResponse(res, status_code=status)


async def login_codigo(request: Request) -> Response:
    if not _autorizado(request):
        return _rechazo()
    cuerpo = await _cuerpo(request)
    sid = cuerpo.get("sesion")
    codigo = cuerpo.get("codigo")
    if not isinstance(sid, str) or not isinstance(codigo, str) or not codigo.strip():
        return JSONResponse({"ok": False, "mensaje": "falta sesion o codigo"}, status_code=400)
    res = await run_in_threadpool(cuenta_claude.enviar_codigo, sid, codigo)
    return JSONResponse(res, status_code=200 if res.get("ok") else 502)


async def login_cancelar(request: Request) -> Response:
    if not _autorizado(request):
        return _rechazo()
    cuerpo = await _cuerpo(request)
    sid = cuerpo.get("sesion")
    if not isinstance(sid, str):
        return JSONResponse({"ok": False, "mensaje": "falta sesion"}, status_code=400)
    return JSONResponse(await run_in_threadpool(cuenta_claude.cancelar_login, sid))


async def logout(request: Request) -> Response:
    if not _autorizado(request):
        return _rechazo()
    res = await run_in_threadpool(cuenta_claude.logout)
    return JSONResponse(res, status_code=200 if res.get("ok") else 502)


def crear_app_control() -> Starlette:
    """App Starlette del listener de control (rutas de cuenta + healthz)."""
    return Starlette(
        routes=[
            Route("/control/healthz", healthz, methods=["GET"]),
            Route("/control/cuenta/estado", estado, methods=["GET"]),
            Route("/control/cuenta/login/iniciar", login_iniciar, methods=["POST"]),
            Route("/control/cuenta/login/codigo", login_codigo, methods=["POST"]),
            Route("/control/cuenta/login/cancelar", login_cancelar, methods=["POST"]),
            Route("/control/cuenta/logout", logout, methods=["POST"]),
        ]
    )


def iniciar_control() -> threading.Thread | None:
    """Arranca el listener de control en un hilo daemon, SI hay bearer configurado.

    Sin `KENI_CONTROL_BEARER` no se monta (apagado por defecto): devuelve None. Escucha en
    `0.0.0.0:KENI_CONTROL_PORT` (red interna docker; nunca por Traefik). uvicorn NO instala
    manejadores de senal fuera del hilo principal, asi que corre limpio en un hilo daemon.
    """
    if not config.control_bearer():
        _log.info("listener de control: sin KENI_CONTROL_BEARER -> no se monta (apagado).")
        return None

    import uvicorn

    puerto = config.control_puerto()
    cfg = uvicorn.Config(
        crear_app_control(),
        host="0.0.0.0",  # noqa: S104 -- red INTERNA docker; el bearer es la barrera
        port=puerto,
        log_level="warning",
        access_log=False,
    )
    servidor = uvicorn.Server(cfg)
    # uvicorn ya omite los signal handlers fuera del hilo principal; lo forzamos por claridad.
    servidor.install_signal_handlers = lambda: None  # type: ignore[method-assign]
    hilo = threading.Thread(target=servidor.run, name="control", daemon=True)
    hilo.start()
    _log.info("listener de control escuchando en :%s (red interna).", puerto)
    return hilo
