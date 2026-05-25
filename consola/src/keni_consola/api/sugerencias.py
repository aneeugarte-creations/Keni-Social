"""API Buzón de sugerencias (/api/sugerencias): CRUD ligero de ideas del equipo.

Almacén autónomo en JSON local (`consola.sugerencias`), sin la capa repos/db. Cada
sugerencia: {id, titulo, detalle, categoria, estado, autor, creada}. El GET incluye
los catálogos (`categorias`, `estados`) para que la UI no los duplique.

VALIDACIÓN: título obligatorio; categoría/estado solo del catálogo; errores en
español, sin tracebacks.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import sugerencias
from .._http_json import leer_json


async def listar(request: Request) -> Response:
    """Listado de sugerencias + catálogos para la UI."""
    return JSONResponse(
        {
            "sugerencias": sugerencias.listar(),
            "categorias": list(sugerencias.CATEGORIAS),
            "estados": list(sugerencias.ESTADOS),
        }
    )


async def crear(request: Request) -> Response:
    """Crea una sugerencia `{titulo, detalle?, categoria?, autor?}` -> `{sugerencia}`."""
    datos = await leer_json(request)
    titulo = datos.get("titulo")
    if not isinstance(titulo, str) or not titulo.strip():
        return JSONResponse({"error": "El título es obligatorio."}, status_code=400)

    detalle = datos.get("detalle", "")
    if detalle is None:
        detalle = ""
    if not isinstance(detalle, str):
        return JSONResponse({"error": "El detalle debe ser texto."}, status_code=400)

    categoria = datos.get("categoria", sugerencias.CATEGORIA_DEFECTO)
    if categoria is None or categoria == "":
        categoria = sugerencias.CATEGORIA_DEFECTO
    if categoria not in sugerencias.CATEGORIAS:
        return JSONResponse({"error": "Categoría no permitida."}, status_code=400)

    autor = datos.get("autor", "")
    if autor is None:
        autor = ""
    if not isinstance(autor, str):
        return JSONResponse({"error": "El autor debe ser texto."}, status_code=400)

    sugerencia = sugerencias.crear(titulo, detalle=detalle, categoria=categoria, autor=autor)
    return JSONResponse({"sugerencia": sugerencia})


async def actualizar(request: Request) -> Response:
    """Cambia el estado de una sugerencia `{estado}` -> `{sugerencia}`."""
    sugerencia_id = request.path_params["sugerencia_id"]
    datos = await leer_json(request)
    estado = datos.get("estado")
    if estado not in sugerencias.ESTADOS:
        return JSONResponse({"error": "Estado no permitido."}, status_code=400)
    actualizada = sugerencias.actualizar_estado(sugerencia_id, estado)
    if actualizada is None:
        return JSONResponse({"error": "Esa sugerencia ya no existe."}, status_code=404)
    return JSONResponse({"sugerencia": actualizada})


async def borrar(request: Request) -> Response:
    sugerencia_id = request.path_params["sugerencia_id"]
    if not sugerencias.borrar(sugerencia_id):
        return JSONResponse({"error": "Esa sugerencia ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Sugerencia borrada."})


RUTAS = [
    Route("/api/sugerencias", listar, methods=["GET"]),
    Route("/api/sugerencias", crear, methods=["POST"]),
    Route("/api/sugerencias/{sugerencia_id}", actualizar, methods=["PATCH"]),
    Route("/api/sugerencias/{sugerencia_id}", borrar, methods=["DELETE"]),
]
