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

import json
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import repos
from .._http_json import leer_json
from ..dominio import estudio_imagen
from ..seguridad import autor_de_peticion


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


def _doc_de_version(version: dict[str, Any] | None) -> Any:
    if not version:
        return None
    try:
        return json.loads(version.get("documento") or "{}")
    except (ValueError, TypeError):
        return None


async def pieza_documento(request: Request) -> Response:
    """GET /api/editor/pieza/{contenido_id}/{plataforma_id}: documento editable de la pieza.

    Devuelve la ÚLTIMA versión guardada del documento (o `null` si aún no se editó con el editor),
    más el número de versiones. El frontend, si es `null`, arranca de la plantilla de la marca.
    """
    cid = request.path_params["contenido_id"]
    pid = request.path_params["plataforma_id"]
    versiones = repos.listar_documento_versiones(cid, pid)
    ultima = versiones[0] if versiones else None
    return JSONResponse({"documento": _doc_de_version(ultima), "versiones": len(versiones)})


async def pieza_guardar(request: Request) -> Response:
    """POST /api/editor/pieza/{contenido_id}/{plataforma_id} {documento}: guarda el documento en la pieza.

    Valida y renderiza el documento (PNG fiel), APENDE una versión al historial y fija la `imagen`
    de la publicación al PNG renderizado. -> `{id, url, version}` | 400 | 404.
    """
    cid = request.path_params["contenido_id"]
    pid = request.path_params["plataforma_id"]
    datos = await leer_json(request)
    doc = datos.get("documento") if isinstance(datos, dict) else None
    if not isinstance(doc, dict):
        return JSONResponse({"error": "Falta el 'documento'."}, status_code=400)
    try:
        doc_ok = estudio_imagen.validar_documento(doc)
        render = estudio_imagen.renderizar_documento(doc_ok)
    except estudio_imagen.EstudioError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    # Fija la imagen de la pieza (404 si la plataforma no existe).
    actualizada = repos.actualizar_contenido_plataforma(pid, {"imagen": render["id"]})
    if actualizada is None:
        return JSONResponse({"error": "Esa publicación no existe."}, status_code=404)

    version = repos.crear_documento_version(
        contenido_id=cid,
        plataforma_id=pid,
        documento=json.dumps(doc_ok, ensure_ascii=False),
        render_objeto=render["id"],
        autor=autor_de_peticion(request),
    )
    return JSONResponse({"id": render["id"], "url": render["url"], "version": version["version"]})


async def pieza_versiones(request: Request) -> Response:
    """GET /api/editor/pieza/{contenido_id}/{plataforma_id}/versiones: historial (sin el documento)."""
    cid = request.path_params["contenido_id"]
    pid = request.path_params["plataforma_id"]
    versiones = [
        {
            "id": v["id"],
            "version": v["version"],
            "render_objeto": v["render_objeto"],
            "render_url": f"/api/media/{v['render_objeto']}" if v.get("render_objeto") else "",
            "documento": _doc_de_version(v),
            "autor_nombre": v["autor_nombre"],
            "creado": v["creado"],
        }
        for v in repos.listar_documento_versiones(cid, pid)
    ]
    return JSONResponse({"versiones": versiones})


RUTAS = [
    Route("/api/editor/render", render, methods=["POST"]),
    Route("/api/editor/plantilla/{marca}/{formato}", plantilla, methods=["GET"]),
    Route("/api/editor/pieza/{contenido_id}/{plataforma_id}", pieza_documento, methods=["GET"]),
    Route("/api/editor/pieza/{contenido_id}/{plataforma_id}", pieza_guardar, methods=["POST"]),
    Route("/api/editor/pieza/{contenido_id}/{plataforma_id}/versiones", pieza_versiones, methods=["GET"]),
]
