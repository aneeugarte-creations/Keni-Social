"""Handlers de etiquetas de un contenido (asignar/quitar sobre el N:M).

La asignación de etiquetas cuelga del contenido (mismo recurso padre); el catálogo de
etiquetas en sí vive en `api/etiquetas.py`.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ._comun import leer_json, repos


async def asignar_etiqueta(request: Request) -> Response:
    """POST /api/contenido/{id}/etiquetas: asigna una etiqueta (`{"etiqueta_id": ...}`)."""
    contenido_id = request.path_params["contenido_id"]
    item = repos.obtener_contenido(contenido_id)
    if item is None:
        return JSONResponse({"error": "Ese contenido ya no existe."}, status_code=404)
    datos = await leer_json(request)
    etiqueta_id = datos.get("etiqueta_id")
    if not isinstance(etiqueta_id, str) or not etiqueta_id:
        return JSONResponse({"error": "Falta la etiqueta."}, status_code=400)
    if repos.obtener_etiqueta(etiqueta_id) is None:
        return JSONResponse({"error": "Esa etiqueta ya no existe."}, status_code=404)
    repos.asignar_etiqueta(contenido_id, etiqueta_id)
    etiquetas = repos.etiquetas_por_contenido().get(contenido_id, [])
    return JSONResponse({"etiquetas": etiquetas})


async def quitar_etiqueta(request: Request) -> Response:
    """DELETE /api/contenido/{id}/etiquetas/{etiqueta_id}: quita una etiqueta del contenido."""
    contenido_id = request.path_params["contenido_id"]
    etiqueta_id = request.path_params["etiqueta_id"]
    if not repos.quitar_etiqueta(contenido_id, etiqueta_id):
        return JSONResponse({"error": "Esa etiqueta no estaba asignada."}, status_code=404)
    etiquetas = repos.etiquetas_por_contenido().get(contenido_id, [])
    return JSONResponse({"etiquetas": etiquetas})
