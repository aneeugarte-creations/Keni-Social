"""API del kanban de sugerencias / auto-desarrollo (/api/sugerencias).

CRUD del kanban + disparadores del motor de desarrollo (discovery, construir, checkpoint,
promover). La persistencia es Postgres (`db_sugerencias`); la máquina de estados y el
lanzamiento de jobs viven en `keni_consola.sugerencias`. Errores en español, sin tracebacks.
"""

from __future__ import annotations

import logging

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import config, cuenta_claude, generaciones, permisos, sugerencias
from .._http_json import leer_json
from ..observabilidad import NOMBRE_LOGGER

_logger = logging.getLogger(NOMBRE_LOGGER)

# Timeout del proxy a worker-dev para la promoción (fetch+rebase+push puede tardar).
_TIMEOUT_PROMOVER = 120.0


def _llamar_dev(metodo: str, ruta: str, json: dict | None = None) -> tuple[int, dict]:
    """Llama al listener de promoción de worker-dev (httpx sincrono; se invoca en el threadpool).

    Devuelve (status, payload). Cualquier fallo de red/timeout se traduce a 502 con un payload
    de error legible (la promoción degrada con mensaje, nunca casca)."""
    import httpx

    base = config.dev_url().rstrip("/")
    bearer = cuenta_claude.bearer_efectivo()
    url = f"{base}{ruta}"
    cabeceras = {"Authorization": f"Bearer {bearer}"}
    try:
        with httpx.Client(timeout=_TIMEOUT_PROMOVER) as cliente:
            if metodo == "GET":
                r = cliente.get(url, headers=cabeceras)
            else:
                r = cliente.post(url, headers=cabeceras, json=json or {})
        try:
            payload = r.json()
        except ValueError:
            payload = {"ok": False, "detalle": "respuesta no JSON de worker-dev"}
        return r.status_code, (payload if isinstance(payload, dict) else {"ok": False, "detalle": "payload inesperado"})
    except httpx.HTTPError as e:
        _logger.warning("fallo al alcanzar worker-dev (%s %s): %s", metodo, ruta, e)
        return 502, {"ok": False, "detalle": "No se pudo contactar worker-dev para promover."}


def _catalogos() -> dict[str, list[str]]:
    """Catálogos para la UI (no duplicarlos en el front)."""
    return {
        "categorias": list(sugerencias.CATEGORIAS),
        "estados": list(sugerencias.ESTADOS),
    }


async def listar(request: Request) -> Response:
    """GET /api/sugerencias: kanban completo + catálogos."""
    return JSONResponse({"sugerencias": sugerencias.listar(), **_catalogos()})


async def crear(request: Request) -> Response:
    """POST /api/sugerencias `{titulo, detalle?, categoria?, autor?}` -> `{sugerencia}`."""
    datos = await leer_json(request)
    titulo = datos.get("titulo")
    if not isinstance(titulo, str) or not titulo.strip():
        return JSONResponse({"error": "El título es obligatorio."}, status_code=400)

    detalle = datos.get("detalle") or ""
    if not isinstance(detalle, str):
        return JSONResponse({"error": "El detalle debe ser texto."}, status_code=400)

    categoria = datos.get("categoria") or sugerencias.CATEGORIA_DEFECTO
    if categoria not in sugerencias.CATEGORIAS:
        return JSONResponse({"error": "Categoría no permitida."}, status_code=400)

    autor = datos.get("autor") or ""
    if not isinstance(autor, str):
        return JSONResponse({"error": "El autor debe ser texto."}, status_code=400)

    sugerencia = sugerencias.crear(titulo, detalle=detalle, categoria=categoria, autor=autor)
    return JSONResponse({"sugerencia": sugerencia})


async def actualizar(request: Request) -> Response:
    """PATCH /api/sugerencias/{id} `{estado?|titulo?|detalle?|categoria?}` -> `{sugerencia}`."""
    sugerencia_id = request.path_params["sugerencia_id"]
    datos = await leer_json(request)

    # Cambio de ESTADO (validado por la máquina de estados).
    if "estado" in datos:
        estado = datos.get("estado")
        if estado not in sugerencias.ESTADOS:
            return JSONResponse({"error": "Estado no permitido."}, status_code=400)
        try:
            actualizada = sugerencias.cambiar_estado(sugerencia_id, estado)
        except sugerencias.TransicionInvalida:
            return JSONResponse(
                {"error": "Ese cambio de estado no está permitido."}, status_code=400
            )
        if actualizada is None:
            return JSONResponse({"error": "Esa sugerencia ya no existe."}, status_code=404)

    # Edición de TEXTO (titulo/detalle/categoria) en el mismo PATCH si vienen.
    texto = {k: datos[k] for k in ("titulo", "detalle", "categoria") if k in datos}
    if texto:
        try:
            actualizada = sugerencias.editar(sugerencia_id, texto)
        except ValueError:
            return JSONResponse({"error": "El título es obligatorio."}, status_code=400)
        if actualizada is None:
            return JSONResponse({"error": "Esa sugerencia ya no existe."}, status_code=404)

    if "estado" not in datos and not texto:
        return JSONResponse({"error": "No hay nada que actualizar."}, status_code=400)

    actual = sugerencias.obtener(sugerencia_id)
    if actual is None:
        return JSONResponse({"error": "Esa sugerencia ya no existe."}, status_code=404)
    return JSONResponse({"sugerencia": actual})


async def borrar(request: Request) -> Response:
    """DELETE /api/sugerencias/{id} -> `{ok: true}`."""
    sugerencia_id = request.path_params["sugerencia_id"]
    if not sugerencias.borrar(sugerencia_id):
        return JSONResponse({"error": "Esa sugerencia ya no existe."}, status_code=404)
    return JSONResponse({"ok": True})


def _lanzar_o_error(funcion, *args, **kwargs) -> Response:
    """Ejecuta un lanzador del motor y mapea sus resultados/errores a una respuesta.

    None -> 404 (la sugerencia no existe); `ColaLlenaError` -> 429; éxito -> `{generacion}`.
    """
    try:
        gen = funcion(*args, **kwargs)
    except generaciones.ColaLlenaError as e:
        return JSONResponse(
            {"error": str(e) or "Hay demasiadas generaciones en curso; inténtalo en unos segundos."},
            status_code=429,
        )
    if gen is None:
        return JSONResponse({"error": "Esa sugerencia ya no existe."}, status_code=404)
    return JSONResponse({"generacion": gen})


async def discovery(request: Request) -> Response:
    """POST /api/sugerencias/{id}/discovery -> `{generacion}` (encola el job dev-discovery)."""
    return _lanzar_o_error(sugerencias.lanzar_discovery, request.path_params["sugerencia_id"])


async def construir(request: Request) -> Response:
    """POST /api/sugerencias/{id}/construir -> `{generacion}` (en_cola + primera fase)."""
    sugerencia_id = request.path_params["sugerencia_id"]
    datos = await leer_json(request)
    complejidad = datos.get("complejidad") or ""
    if not isinstance(complejidad, str):
        complejidad = ""
    return _lanzar_o_error(
        sugerencias.lanzar_construir, sugerencia_id, complejidad=complejidad
    )


# Acciones válidas del checkpoint humano sobre una sugerencia en `revision`.
_ACCIONES_CHECKPOINT = ("continuar", "cambios", "cancelar")


async def checkpoint(request: Request) -> Response:
    """POST /api/sugerencias/{id}/checkpoint `{accion, comentario?}` -> `{sugerencia}`.

    - continuar: sigue el pipeline (lanza la siguiente fase si la hay; si no, queda lista para
      promover).
    - cambios: re-ejecuta la construcción con el comentario como feedback.
    - cancelar: descarta la sugerencia.
    """
    sugerencia_id = request.path_params["sugerencia_id"]
    datos = await leer_json(request)
    accion = datos.get("accion")
    if accion not in _ACCIONES_CHECKPOINT:
        return JSONResponse({"error": "Acción de checkpoint no permitida."}, status_code=400)
    comentario = datos.get("comentario") or ""
    if not isinstance(comentario, str):
        comentario = ""

    sug = sugerencias.obtener(sugerencia_id)
    if sug is None:
        return JSONResponse({"error": "Esa sugerencia ya no existe."}, status_code=404)

    try:
        actualizada = sugerencias.aplicar_checkpoint(sugerencia_id, accion, comentario=comentario)
    except sugerencias.TransicionInvalida:
        return JSONResponse(
            {"error": "El checkpoint no es aplicable en este estado."}, status_code=400
        )
    except generaciones.ColaLlenaError as e:
        return JSONResponse(
            {"error": str(e) or "Hay demasiadas generaciones en curso; inténtalo en unos segundos."},
            status_code=429,
        )
    if actualizada is None:
        return JSONResponse({"error": "Esa sugerencia ya no existe."}, status_code=404)
    return JSONResponse({"sugerencia": actualizada})


async def promover(request: Request) -> Response:
    """POST /api/sugerencias/{id}/promover -> `{ok, detalle, rama}` (checkpoint humano → main).

    ADMIN-gated: promover ejecuta un `git push` REAL a `main`. PROXEA (httpx+bearer) al listener
    de worker-dev (`KENI_DEV_URL`), que hace fetch+rebase+push de la rama de la sugerencia dentro
    de su worktree. Solo desde estado `revision`; si worker-dev no responde, degrada con error
    claro y NO mueve el kanban. Tras un push OK, marca la sugerencia `hecha`.
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin("Solo un administrador puede promover a main.")
    sugerencia_id = request.path_params["sugerencia_id"]
    sug = sugerencias.obtener(sugerencia_id)
    if sug is None:
        return JSONResponse({"error": "Esa sugerencia ya no existe."}, status_code=404)
    if sug["estado"] != "revision":
        return JSONResponse(
            {"ok": False, "detalle": "La sugerencia no está lista para promover."},
            status_code=400,
        )

    status, payload = await run_in_threadpool(
        _llamar_dev, "POST", "/control/dev/promover", {"sugerencia_id": sugerencia_id}
    )
    if status != 200 or not payload.get("ok"):
        detalle = payload.get("detalle") or payload.get("error") or "No se pudo promover la rama a main."
        return JSONResponse({"ok": False, "detalle": detalle}, status_code=status if status >= 400 else 502)

    # Push real OK: registra la decisión humana y mueve el kanban a `hecha`.
    try:
        local = sugerencias.promover(sugerencia_id)
    except sugerencias.TransicionInvalida:
        local = None
    return JSONResponse({
        "ok": True,
        "detalle": payload.get("detalle") or "Rama promovida a main.",
        "rama": payload.get("rama", ""),
        "sugerencia": (local or {}).get("sugerencia"),
    })


RUTAS = [
    Route("/api/sugerencias", listar, methods=["GET"]),
    Route("/api/sugerencias", crear, methods=["POST"]),
    Route("/api/sugerencias/{sugerencia_id}", actualizar, methods=["PATCH"]),
    Route("/api/sugerencias/{sugerencia_id}", borrar, methods=["DELETE"]),
    Route("/api/sugerencias/{sugerencia_id}/discovery", discovery, methods=["POST"]),
    Route("/api/sugerencias/{sugerencia_id}/construir", construir, methods=["POST"]),
    Route("/api/sugerencias/{sugerencia_id}/checkpoint", checkpoint, methods=["POST"]),
    Route("/api/sugerencias/{sugerencia_id}/promover", promover, methods=["POST"]),
]
