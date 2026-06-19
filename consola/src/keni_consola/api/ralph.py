"""API Ralph (panel ADMIN): proxy del `back` al listener de worker-ralph.

Los agentes Ralph son procesos `claude` PERSISTENTES que viven en worker-ralph (con `claude`),
no en el `back`. Estas rutas son la cara ADMIN de ese servicio: validan sesion admin (lanzar y
conversar con un agente que tiene Bash/Write/Edit sin sandbox es sensible) y REENVIAN por la red
interna a `KENI_RALPH_URL` con el bearer compartido (auto-persistido en /data, el mismo del
control de `daemons`). Gemelo de `api/sistema/cuenta.py`. ACTIVO por defecto: si worker-ralph no
responde, degrada a `disponible:false` en vez de 500.

Endpoints (bajo `/api/ralph`, CONTRATO con el frontend):
  - GET  /api/ralph              -> {disponible, ralphs:[...]}
  - POST /api/ralph/spawn        -> {ralph} | {error}
  - GET  /api/ralph/{id}/stream  -> SSE (eventos `mensaje` y `estado`)
  - POST /api/ralph/{id}/mensaje -> {ok}
  - POST /api/ralph/{id}/kill    -> {ok}
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from urllib.parse import quote

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from .. import config, cuenta_claude, permisos
from ..observabilidad import NOMBRE_LOGGER

_logger = logging.getLogger(NOMBRE_LOGGER)

# Timeout del proxy a worker-ralph para las llamadas NO-stream (spawn/list/mensaje/kill).
_TIMEOUT_PROXY = 30.0


def _hay_sesion(request: Request) -> bool:
    """True si la peticion la hace un usuario REAL con sesion (cualquier rol).

    El Ralph operativo es para TODO el equipo (admins y editores), no solo admins; el token de
    mantenimiento (sin usuario) no cuenta."""
    return getattr(request.state, "usuario", None) is not None


def _rechazo_sin_sesion() -> Response:
    return JSONResponse({"error": "Necesitas iniciar sesión."}, status_code=401)


def _llamar(metodo: str, ruta: str, json: dict | None = None) -> tuple[int, dict]:
    """Llama al listener de worker-ralph (httpx sincrono; se invoca en el threadpool).

    Devuelve (status, payload). Cualquier fallo de red/timeout se traduce a 502 con un payload
    de error legible (la seccion degrada, nunca casca)."""
    import httpx

    base = config.ralph_url().rstrip("/")
    bearer = cuenta_claude.bearer_efectivo()
    url = f"{base}{ruta}"
    cabeceras = {"Authorization": f"Bearer {bearer}"}
    try:
        with httpx.Client(timeout=_TIMEOUT_PROXY) as cliente:
            if metodo == "GET":
                r = cliente.get(url, headers=cabeceras)
            else:
                r = cliente.post(url, headers=cabeceras, json=json or {})
        try:
            payload = r.json()
        except ValueError:
            payload = {"error": "respuesta no JSON de worker-ralph"}
        return r.status_code, (payload if isinstance(payload, dict) else {"error": "payload inesperado"})
    except httpx.HTTPError as e:
        _logger.warning("fallo al alcanzar worker-ralph (%s %s): %s", metodo, ruta, e)
        return 502, {"error": "no se pudo contactar worker-ralph"}


async def listar(request: Request) -> Response:
    """GET /api/ralph: lista los Ralphs vivos (admin). Degrada `disponible:false` si no hay servicio."""
    if not _hay_sesion(request):
        return _rechazo_sin_sesion()
    superadmin = permisos.es_superadmin(request)
    # Cada persona ve SOLO sus propios Ralphs: pasamos su id para que worker-ralph filtre.
    usuario = getattr(request.state, "usuario", None)
    ruta = "/control/ralph/list"
    if isinstance(usuario, dict) and usuario.get("id"):
        ruta += f"?usuario_id={quote(str(usuario['id']))}"
    status, payload = await run_in_threadpool(_llamar, "GET", ruta)
    if status != 200:
        return JSONResponse({"disponible": False, "superadmin": superadmin, "ralphs": []})
    return JSONResponse(
        {"disponible": True, "superadmin": superadmin, "ralphs": payload.get("ralphs", [])}
    )


async def spawn(request: Request) -> Response:
    """POST /api/ralph/spawn `{prompt, modelo?, tipo?}`: lanza un Ralph.

    `tipo` por defecto `operativo` (asistente del equipo, MCP de la app). El tipo `dev` (agente de
    desarrollo sobre el repo, sin sandbox) queda RESERVADO a superadmins."""
    if not _hay_sesion(request):
        return _rechazo_sin_sesion()
    try:
        datos = await request.json()
        cuerpo = datos if isinstance(datos, dict) else {}
    except Exception:  # noqa: BLE001 -- cuerpo ausente/no-JSON: lo tratamos como vacio
        cuerpo = {}
    tipo = cuerpo.get("tipo") or "operativo"
    if tipo == "dev" and not permisos.es_superadmin(request):
        return JSONResponse(
            {"error": "Solo un superadmin puede lanzar un Ralph de desarrollo."}, status_code=403
        )
    cuerpo["tipo"] = tipo
    # Identidad heredada: el Ralph operativo actuará en el MCP como el usuario que lo lanza
    # (acotado a sus permisos), no como el usuario fijo del MCP.
    usuario = getattr(request.state, "usuario", None)
    if isinstance(usuario, dict) and usuario.get("id"):
        cuerpo["usuario_id"] = usuario["id"]
    status, payload = await run_in_threadpool(_llamar, "POST", "/control/ralph/spawn", cuerpo)
    return JSONResponse(payload, status_code=status)


async def mensaje(request: Request) -> Response:
    """POST /api/ralph/{id}/mensaje `{texto}`: turno del humano (admin)."""
    if not _hay_sesion(request):
        return _rechazo_sin_sesion()
    ralph_id = request.path_params.get("ralph_id")
    try:
        datos = await request.json()
        cuerpo = datos if isinstance(datos, dict) else {}
    except Exception:  # noqa: BLE001 -- cuerpo ausente/no-JSON: lo tratamos como vacio
        cuerpo = {}
    status, payload = await run_in_threadpool(
        _llamar, "POST", f"/control/ralph/{ralph_id}/mensaje", cuerpo
    )
    return JSONResponse(payload, status_code=status)


async def kill(request: Request) -> Response:
    """POST /api/ralph/{id}/kill: mata el Ralph (admin)."""
    if not _hay_sesion(request):
        return _rechazo_sin_sesion()
    ralph_id = request.path_params.get("ralph_id")
    status, payload = await run_in_threadpool(_llamar, "POST", f"/control/ralph/{ralph_id}/kill")
    return JSONResponse(payload, status_code=status)


async def stream(request: Request) -> Response:
    """GET /api/ralph/{id}/stream: reenvia el SSE del Ralph desde worker-ralph (admin).

    Abre un stream httpx hacia el listener y reemite sus lineas tal cual (es ya text/event-stream).
    Si worker-ralph no responde, cierra limpio (el SPA degrada). Autenticacion como sus hermanos:
    la aporta el middleware global (`/api` exige sesion); `EventSource` lleva la cookie en
    same-origin. El bearer hacia worker-ralph lo pone este proxy."""
    if not _hay_sesion(request):
        return _rechazo_sin_sesion()
    ralph_id = request.path_params.get("ralph_id")

    async def eventos() -> AsyncIterator[bytes]:
        import httpx

        base = config.ralph_url().rstrip("/")
        bearer = cuenta_claude.bearer_efectivo()
        url = f"{base}/control/ralph/{ralph_id}/stream"
        cabeceras = {"Authorization": f"Bearer {bearer}", "Accept": "text/event-stream"}
        try:
            async with httpx.AsyncClient(timeout=None) as cliente:
                async with cliente.stream("GET", url, headers=cabeceras) as r:
                    if r.status_code != 200:
                        return
                    async for trozo in r.aiter_raw():
                        if await request.is_disconnected():
                            return
                        if trozo:
                            yield trozo
        except httpx.HTTPError as e:
            _logger.warning("fallo al reenviar el stream de Ralph %s: %s", ralph_id, e)
            return

    return StreamingResponse(
        eventos(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


RUTAS = [
    Route("/api/ralph", listar, methods=["GET"]),
    Route("/api/ralph/spawn", spawn, methods=["POST"]),
    Route("/api/ralph/{ralph_id}/stream", stream, methods=["GET"]),
    Route("/api/ralph/{ralph_id}/mensaje", mensaje, methods=["POST"]),
    Route("/api/ralph/{ralph_id}/kill", kill, methods=["POST"]),
]
