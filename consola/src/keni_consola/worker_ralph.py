"""WORKER-RALPH: servicio que aloja las sesiones `claude` PERSISTENTES de los agentes Ralph.

    python -m keni_consola.worker_ralph

POR QUE UN SERVICIO APARTE (y no el back): cada Ralph es un proceso `claude` interactivo VIVO
entre peticiones (conversacion multi-turno; ver `ralph_sesiones`). El `back` no tiene `claude`
(solo encola) y escala, asi que no puede alojar procesos de larga vida con estado en memoria.
worker-ralph es de INSTANCIA UNICA (como `daemons`): el sitio natural para el registro de Ralphs.

SUPERFICIE: un Starlette minimo servido por uvicorn en un hilo, en la red INTERNA de docker
(NUNCA por Traefik), protegido por el BEARER compartido (`cuenta_claude.bearer_efectivo`, el
mismo que protege el control de `daemons`). El `back` lo proxea (admin-gated) desde
`api/ralph.py`. Imita `control.py` pero con su propio listener (no toca el de `daemons`).

Rutas (bajo `/control/ralph`, contrato con el proxy del back):
  - GET  /control/healthz                 -> {ok:true}            (sonda, sin bearer)
  - POST /control/ralph/spawn             -> {ralph}             (lanza un Ralph)
  - GET  /control/ralph/list              -> {ralphs:[...]}      (lista los Ralphs vivos)
  - GET  /control/ralph/{id}/stream       -> SSE                 (deltas de conversacion + estado)
  - POST /control/ralph/{id}/mensaje      -> {ok}                (turno del humano)
  - POST /control/ralph/{id}/kill         -> {ok}                (mata el Ralph)
"""

from __future__ import annotations

import json
import logging
import secrets
import sys
import threading
import time
from collections.abc import AsyncIterator

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from . import config, cuenta_claude, ralph_sesiones

_log = logging.getLogger("keni_consola.worker_ralph")

# Latido de liveness del proceso (igual que `daemons`): el healthcheck del contenedor tolera
# varios multiplos de esto.
_LATIDO_SEG = 30.0


def _autorizado(request: Request) -> bool:
    """True si la peticion trae `Authorization: Bearer <bearer efectivo>` (tiempo constante).

    El bearer es el compartido en /data (`cuenta_claude.bearer_efectivo`): el mismo que usa el
    control de `daemons`, asi back y worker-ralph se entienden sin configurar nada."""
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


async def spawn(request: Request) -> Response:
    if not _autorizado(request):
        return _rechazo()
    cuerpo = await _cuerpo(request)
    prompt = cuerpo.get("prompt")
    if not isinstance(prompt, str):
        prompt = ""
    modelo = cuerpo.get("modelo") if isinstance(cuerpo.get("modelo"), str) else None
    tipo = cuerpo.get("tipo") if isinstance(cuerpo.get("tipo"), str) else None
    usuario_id = cuerpo.get("usuario_id") if isinstance(cuerpo.get("usuario_id"), str) else None
    try:
        ralph = await run_in_threadpool(
            ralph_sesiones.gestor.spawn, prompt, modelo, tipo, usuario_id
        )
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=409)
    return JSONResponse({"ralph": ralph})


async def listar(request: Request) -> Response:
    if not _autorizado(request):
        return _rechazo()
    return JSONResponse({"ralphs": await run_in_threadpool(ralph_sesiones.gestor.listar)})


async def mensaje(request: Request) -> Response:
    if not _autorizado(request):
        return _rechazo()
    ralph_id = request.path_params.get("ralph_id")
    cuerpo = await _cuerpo(request)
    texto = cuerpo.get("texto")
    if not isinstance(texto, str) or not texto.strip():
        return JSONResponse({"ok": False, "error": "falta texto"}, status_code=400)
    res = await run_in_threadpool(ralph_sesiones.gestor.enviar, ralph_id, texto)
    return JSONResponse(res, status_code=200 if res.get("ok") else 404)


async def kill(request: Request) -> Response:
    if not _autorizado(request):
        return _rechazo()
    ralph_id = request.path_params.get("ralph_id")
    return JSONResponse(await run_in_threadpool(ralph_sesiones.gestor.kill, ralph_id))


def _evento_sse(nombre: str, datos: dict) -> str:
    """Serializa un evento SSE con nombre y payload JSON (una sola linea `data:`)."""
    return f"event: {nombre}\ndata: {json.dumps(datos, ensure_ascii=False)}\n\n"


async def stream(request: Request) -> Response:
    """SSE de la conversacion de un Ralph: eventos `mensaje` y `estado` (contrato del frontend).

    El gestor expone un generador BLOQUEANTE (`leer_stream`); lo consumimos por elementos en el
    threadpool para no bloquear el bucle asincrono. Cada evento del gestor lleva un `tipo` que es
    el NOMBRE del evento SSE; el resto de sus claves es el `data` (mensaje -> `{delta, fin?}`,
    estado -> `{estado}`). Los `ping` del gestor se mandan como comentario SSE (`:ping`) para
    mantener viva la conexion. Cierra limpio si el cliente desconecta o el Ralph termina."""
    if not _autorizado(request):
        return _rechazo()
    ralph_id = request.path_params.get("ralph_id")
    if ralph_sesiones.gestor.obtener(ralph_id) is None:
        return JSONResponse({"error": "Ralph desconocido"}, status_code=404)

    async def eventos() -> AsyncIterator[str]:
        import functools

        gen = ralph_sesiones.gestor.leer_stream(ralph_id)
        fin = object()
        siguiente = functools.partial(next, gen, fin)
        while True:
            if await request.is_disconnected():
                return
            ev = await run_in_threadpool(siguiente)
            if ev is fin:
                return
            tipo = ev.get("tipo")
            if tipo == "ping":
                yield ":ping\n\n"
            else:
                datos = {k: v for k, v in ev.items() if k != "tipo"}
                yield _evento_sse(tipo, datos)

    return StreamingResponse(
        eventos(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def crear_app() -> Starlette:
    """App Starlette del listener de worker-ralph (rutas de Ralph + healthz)."""
    return Starlette(
        routes=[
            Route("/control/healthz", healthz, methods=["GET"]),
            Route("/control/ralph/spawn", spawn, methods=["POST"]),
            Route("/control/ralph/list", listar, methods=["GET"]),
            Route("/control/ralph/{ralph_id}/stream", stream, methods=["GET"]),
            Route("/control/ralph/{ralph_id}/mensaje", mensaje, methods=["POST"]),
            Route("/control/ralph/{ralph_id}/kill", kill, methods=["POST"]),
        ]
    )


def iniciar_listener() -> threading.Thread:
    """Arranca el listener en un hilo daemon (`0.0.0.0:KENI_RALPH_PORT`, red interna)."""
    import uvicorn

    puerto = config.ralph_puerto()
    cfg = uvicorn.Config(
        crear_app(),
        host="0.0.0.0",  # noqa: S104 -- red INTERNA docker; el bearer es la barrera
        port=puerto,
        log_level="warning",
        access_log=False,
    )
    servidor = uvicorn.Server(cfg)
    servidor.install_signal_handlers = lambda: None  # type: ignore[method-assign]
    hilo = threading.Thread(target=servidor.run, name="worker-ralph", daemon=True)
    hilo.start()
    _log.info("listener de worker-ralph escuchando en :%s (red interna).", puerto)
    return hilo


def main() -> int:
    from .observabilidad import configurar_logging

    configurar_logging()
    iniciar_listener()
    # El listener corre en su hilo; el principal queda en un bucle de LATIDO para el healthcheck.
    from . import latidos

    while True:
        latidos.tocar_fichero()
        time.sleep(_LATIDO_SEG)
    return 0  # inalcanzable; conserva la firma


if __name__ == "__main__":
    sys.exit(main())
