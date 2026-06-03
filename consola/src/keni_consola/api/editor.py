"""API del Editor profesional: render de DOCUMENTOS de capas y arranque desde plantilla de marca.

El editor (navegador, react-konva) edita un DOCUMENTO de capas en local y, para el archivo final
(o una vista previa de alta fidelidad), pide al servidor que lo re-renderice con el MISMO dibujante
(`render_node/dibujar.mjs::dibujarDocumento`) que el editor usa en cliente — garantizando fuentes
embebidas y un PNG reproducible.

Endpoints:
  - `POST /api/editor/render`                      {documento, bindings?} -> {id, url}
  - `GET  /api/editor/plantilla/{marca}/{formato}`                        -> {documento}

SEGURIDAD: el documento se valida en el dominio (`documento.validar`); los errores salen como
400 en español, sin tracebacks. El nombre del PNG lo genera el servidor (media).
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .._http_json import leer_json
from ..dominio import estudio_imagen


async def render(request: Request) -> Response:
    """Renderiza un documento de capas a PNG -> `{id, url}` (400 si el documento no valida)."""
    datos = await leer_json(request)
    if not isinstance(datos, dict):
        return JSONResponse({"error": "Cuerpo JSON inválido."}, status_code=400)
    doc = datos.get("documento") if "documento" in datos else datos
    bindings = datos.get("bindings") if isinstance(datos.get("bindings"), dict) else None
    if not isinstance(doc, dict):
        return JSONResponse({"error": "Falta el 'documento'."}, status_code=400)
    try:
        res = estudio_imagen.renderizar_documento(doc, bindings=bindings)
    except estudio_imagen.EstudioError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse(res)


async def plantilla(request: Request) -> Response:
    """Documento de capas editable derivado de la plantilla de una marca -> `{documento}`."""
    marca = request.path_params["marca"]
    formato = request.path_params["formato"]
    try:
        doc: dict[str, Any] = estudio_imagen.documento_desde_plantilla(marca, formato)
    except estudio_imagen.EstudioError as e:
        codigo = 404 if str(e) == "Marca desconocida." else 400
        return JSONResponse({"error": str(e)}, status_code=codigo)
    return JSONResponse({"documento": doc})


RUTAS = [
    Route("/api/editor/render", render, methods=["POST"]),
    Route("/api/editor/plantilla/{marca}/{formato}", plantilla, methods=["GET"]),
]
