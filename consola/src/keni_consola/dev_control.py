"""Listener de CONTROL del proceso `worker-dev`: promoción REAL a `main`.

POR QUE UN LISTENER APARTE (y no la API del back): promover una rama a `main` exige git+gh
(push con la credencial de la cuenta de GitHub de la maquina) y el WORKTREE de la sugerencia.
El `back` NO tiene git/gh ni los worktrees (solo encola); quien los tiene es la imagen del
worker. `worker-dev` es de INSTANCIA UNICA y dueño del clon `/repo`, así que es el sitio
natural para ejecutar el push de una sugerencia.

SUPERFICIE: un Starlette mínimo servido por uvicorn en un hilo de `worker-dev`, en la red
INTERNA de docker (NUNCA por Traefik). Lo protege el BEARER compartido
(`cuenta_claude.bearer_efectivo`), el mismo del control de `daemons`/`worker-ralph`. El `back`
lo proxea (admin-gated) desde `api/sugerencias.py`. Imita `control.py`/`worker_ralph`.

Rutas (bajo `/control/dev`, contrato con el proxy del back):
  - GET  /control/healthz       -> {ok:true}             (sonda, sin bearer)
  - POST /control/dev/promover  -> {ok, detalle, rama}   (fetch+rebase+push de la rama a main)
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

_log = logging.getLogger("keni_consola.dev_control")


def _autorizado(request: Request) -> bool:
    """True si la peticion trae `Authorization: Bearer <bearer efectivo>` (tiempo constante)."""
    esperado = cuenta_claude.bearer_efectivo()
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


async def promover(request: Request) -> Response:
    """POST /control/dev/promover `{sugerencia_id}` -> {ok, detalle, rama}.

    Ejecuta la promoción REAL (fetch+rebase+push de la rama de la sugerencia a `main`) en el
    threadpool (operación bloqueante de git). 200 si se promovió; 400 en caso contrario."""
    if not _autorizado(request):
        return _rechazo()
    cuerpo = await _cuerpo(request)
    sid = cuerpo.get("sugerencia_id")
    if not isinstance(sid, str) or not sid.strip():
        return JSONResponse({"ok": False, "detalle": "falta sugerencia_id"}, status_code=400)
    from . import worker_dev

    res = await run_in_threadpool(worker_dev.promover_sugerencia, sid.strip())
    return JSONResponse(res, status_code=200 if res.get("ok") else 400)


def crear_app_control_dev() -> Starlette:
    """App Starlette del listener de promoción del carril dev (rutas + healthz)."""
    return Starlette(
        routes=[
            Route("/control/healthz", healthz, methods=["GET"]),
            Route("/control/dev/promover", promover, methods=["POST"]),
        ]
    )


def iniciar_control_dev() -> threading.Thread:
    """Arranca el listener en un hilo daemon (`0.0.0.0:KENI_DEV_PORT`, red interna)."""
    import uvicorn

    puerto = config.dev_puerto()
    cfg = uvicorn.Config(
        crear_app_control_dev(),
        host="0.0.0.0",  # noqa: S104 -- red INTERNA docker; el bearer es la barrera
        port=puerto,
        log_level="warning",
        access_log=False,
    )
    servidor = uvicorn.Server(cfg)
    servidor.install_signal_handlers = lambda: None  # type: ignore[method-assign]
    hilo = threading.Thread(target=servidor.run, name="dev-control", daemon=True)
    hilo.start()
    _log.info("listener de promoción dev escuchando en :%s (red interna).", puerto)
    return hilo
