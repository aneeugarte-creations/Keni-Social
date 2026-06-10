"""API del Editor profesional: render de DOCUMENTOS de capas y arranque desde plantilla de marca.

El editor (navegador, react-konva) edita un DOCUMENTO de capas en local y, para el archivo final
(o una vista previa de alta fidelidad), pide al servidor que lo re-renderice con el MISMO dibujante
(`render_node/dibujar.mjs::dibujarDocumento`) que el editor usa en cliente — garantizando fuentes
embebidas y un PNG reproducible.

Endpoints:
  - `POST /api/imagen/render`                      {documento, bindings?} -> {id, url}
  - `GET  /api/imagen/plantilla/{marca}/{formato}`                        -> {documento}

Bindings (titular/pleca): las capas de texto con `binding:"copy_in"`/`"etiqueta_default"` se
renderizan con el TEXTO REAL de la publicación, no con el texto de muestra, cuando el cliente pasa
`bindings={"copy_in":..., "etiqueta_default":...}`. El GET de la pieza precarga esos valores
(copy_in de la fila + etiqueta_default de la marca) para que el editor los inyecte al render/guardar.

SEGURIDAD: el documento se valida en el dominio (`documento.validar`); los errores salen como
400 en español, sin tracebacks. El nombre del PNG lo genera el servidor (media).
"""

from __future__ import annotations

import json
from typing import Any

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import plantillas_marca, repos
from .._http_json import leer_json
from ..dominio import estudio_imagen
from ..seguridad import autor_de_peticion


def _bindings_de_pieza(cid: str, pid: str) -> dict[str, str]:
    """Bindings reales de una pieza: `copy_in` (titular) de la fila + `etiqueta_default` (pleca) de la marca.

    Tolerante: si la pieza/contenido/marca no existen devuelve lo que pueda (vacío). Lo usa el
    GET de la pieza (precarga) y el guardar (render con el texto real, no el de muestra).
    """
    plataforma = repos.obtener_contenido_plataforma(pid) or {}
    copy_in = str(plataforma.get("copy_in") or "")
    etiqueta = ""
    contenido = repos.obtener_contenido(cid) or {}
    marca = str(contenido.get("marca") or "")
    if marca:
        try:
            etiqueta = str(plantillas_marca.obtener(marca).get("etiqueta_default") or "")
        except plantillas_marca.PlantillaMarcaError:
            etiqueta = ""
    return {"copy_in": copy_in, "etiqueta_default": etiqueta}


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
        # Render es bloqueante (subprocess.run); ejecutar en threadpool para no bloquear el event loop.
        res = await run_in_threadpool(estudio_imagen.renderizar_documento, doc, bindings=bindings)
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
    """GET /api/imagen/pieza/{contenido_id}/{plataforma_id}: documento editable de la pieza.

    Devuelve la ÚLTIMA versión guardada del documento (o `null` si aún no se editó con el editor),
    más el número de versiones. Si no hay versión, el frontend arranca de la `plantilla` EFECTIVA
    (la misma que compone el feed) e inyecta las `fotos` de la pieza en sus huecos, para que el
    lienzo muestre el marco y la foto REALES (no la plantilla genérica de la marca ni una muestra).
    """
    cid = request.path_params["contenido_id"]
    pid = request.path_params["plataforma_id"]
    versiones = repos.listar_documento_versiones(cid, pid)
    ultima = versiones[0] if versiones else None
    # `pub` (fila publicación = contenido+plataforma) para resolver plantilla efectiva y fotos.
    pub = repos.obtener_publicacion(pid) or {}
    from ..dominio import render_pieza

    fotos = [
        f for f in (render_pieza.fotos_de_pieza(pub) if pub else [])
        if (f.get("objeto") or "").strip()
    ]
    return JSONResponse(
        {
            "documento": _doc_de_version(ultima),
            "versiones": len(versiones),
            # Bindings reales para que el editor renderice el titular/pleca de la publicación
            # (no el texto de muestra de las capas con `binding`).
            "bindings": _bindings_de_pieza(cid, pid),
            # Plantilla efectiva (mismo documento que publica el feed) y fotos por hueco: el editor
            # las usa solo cuando NO hay versión guardada (ver `abrirPiezaTab`).
            "plantilla": render_pieza.plantilla_efectiva_doc(pub) if pub else None,
            "fotos": fotos,
        }
    )


async def pieza_guardar(request: Request) -> Response:
    """POST /api/imagen/pieza/{contenido_id}/{plataforma_id} {documento}: guarda el documento en la pieza.

    Valida primero que la pieza existe (contenido + plataforma que le pertenece). Luego valida,
    renderiza el documento (PNG fiel), crea una versión en el historial y fija la `imagen`
    de la publicación al PNG renderizado. -> `{id, url, version}` | 400 | 404.
    """
    cid = request.path_params["contenido_id"]
    pid = request.path_params["plataforma_id"]
    datos = await leer_json(request)
    doc = datos.get("documento") if isinstance(datos, dict) else None
    if not isinstance(doc, dict):
        return JSONResponse({"error": "Falta el 'documento'."}, status_code=400)

    # VALIDACIÓN PREVIA: que la plataforma existe y pertenece al contenido (404 si no).
    # Se hace ANTES de renderizar para evitar huérfanos si el render falla después.
    plataforma = repos.obtener_contenido_plataforma(pid)
    if plataforma is None:
        return JSONResponse({"error": "Esa publicación no existe."}, status_code=404)
    if plataforma.get("contenido_id") != cid:
        return JSONResponse(
            {"error": "La plataforma no pertenece a ese contenido."}, status_code=404
        )

    # Bindings: el cliente puede enviarlos (valores VIGENTES del editor, aún sin persistir); si no,
    # se usan los reales de la pieza (copy_in de la fila + pleca de la marca). Así el PNG guardado
    # muestra el titular/pleca REAL en las capas con `binding`, no el texto de muestra.
    bindings = datos.get("bindings") if isinstance(datos, dict) else None
    if not isinstance(bindings, dict):
        bindings = _bindings_de_pieza(cid, pid)

    try:
        doc_ok = estudio_imagen.validar_documento(doc)
        # Render es bloqueante (subprocess.run); ejecutar en threadpool para no bloquear el event loop.
        render = await run_in_threadpool(estudio_imagen.renderizar_documento, doc_ok, bindings=bindings)
    except estudio_imagen.EstudioError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    # CREAR VERSIÓN PRIMERO: si la creación de versión falla, no habremos actualizado la imagen aún.
    # Así evitamos dejar la publicación apuntando a un PNG cuya versión nunca fue registrada.
    try:
        version = repos.crear_documento_version(
            contenido_id=cid,
            plataforma_id=pid,
            documento=json.dumps(doc_ok, ensure_ascii=False),
            render_objeto=render["id"],
            autor=autor_de_peticion(request),
        )
    except Exception as e:
        return JSONResponse(
            {"error": f"No se pudo guardar la versión: {str(e)}"}, status_code=500
        )

    # Solo después de crear la versión, fijar la imagen de la pieza.
    repos.actualizar_contenido_plataforma(pid, {"imagen": render["id"]})
    return JSONResponse({"id": render["id"], "url": render["url"], "version": version["version"]})


async def pieza_versiones(request: Request) -> Response:
    """GET /api/imagen/pieza/{contenido_id}/{plataforma_id}/versiones: historial (sin el documento)."""
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
    Route("/api/imagen/render", render, methods=["POST"]),
    Route("/api/imagen/plantilla/{marca}/{formato}", plantilla, methods=["GET"]),
    Route("/api/imagen/pieza/{contenido_id}/{plataforma_id}", pieza_documento, methods=["GET"]),
    Route("/api/imagen/pieza/{contenido_id}/{plataforma_id}", pieza_guardar, methods=["POST"]),
    Route("/api/imagen/pieza/{contenido_id}/{plataforma_id}/versiones", pieza_versiones, methods=["GET"]),
]
