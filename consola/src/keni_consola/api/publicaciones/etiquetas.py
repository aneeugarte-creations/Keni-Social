"""Handlers de etiquetas de un contenido (asignar/quitar sobre el N:M).

La asignación de etiquetas cuelga del contenido (mismo recurso padre); el catálogo de
etiquetas en sí vive en `api/etiquetas.py`.

CONCURRENCIA: los handlers son `async` pero el acceso a Postgres (`repos`) es síncrono;
el trabajo de BD de cada petición va en `run_in_threadpool` (un helper síncrono por
petición) para no bloquear el event loop.
"""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ._comun import leer_json, repos


def _asignar_etiqueta(publicacion_id: str, datos: dict) -> tuple[int, dict]:
    if repos.obtener_publicacion(publicacion_id) is None:
        return 404, {"error": "Ese contenido ya no existe."}
    etiqueta_id = datos.get("etiqueta_id")
    if not isinstance(etiqueta_id, str) or not etiqueta_id:
        return 400, {"error": "Falta la etiqueta."}
    if repos.obtener_etiqueta(etiqueta_id) is None:
        return 404, {"error": "Esa etiqueta ya no existe."}
    repos.asignar_etiqueta(publicacion_id, etiqueta_id)
    etiquetas = repos.etiquetas_por_contenido().get(publicacion_id, [])
    return 200, {"etiquetas": etiquetas}


async def asignar_etiqueta(request: Request) -> Response:
    """POST /api/publicaciones/{id}/etiquetas: asigna una etiqueta (`{"etiqueta_id": ...}`)."""
    publicacion_id = request.path_params["publicacion_id"]
    datos = await leer_json(request)
    status, cuerpo = await run_in_threadpool(_asignar_etiqueta, publicacion_id, datos)
    return JSONResponse(cuerpo, status_code=status)


def _quitar_etiqueta(publicacion_id: str, etiqueta_id: str) -> tuple[int, dict]:
    if not repos.quitar_etiqueta(publicacion_id, etiqueta_id):
        return 404, {"error": "Esa etiqueta no estaba asignada."}
    etiquetas = repos.etiquetas_por_contenido().get(publicacion_id, [])
    return 200, {"etiquetas": etiquetas}


async def quitar_etiqueta(request: Request) -> Response:
    """DELETE /api/publicaciones/{id}/etiquetas/{etiqueta_id}: quita una etiqueta del contenido."""
    publicacion_id = request.path_params["publicacion_id"]
    etiqueta_id = request.path_params["etiqueta_id"]
    status, cuerpo = await run_in_threadpool(_quitar_etiqueta, publicacion_id, etiqueta_id)
    return JSONResponse(cuerpo, status_code=status)
