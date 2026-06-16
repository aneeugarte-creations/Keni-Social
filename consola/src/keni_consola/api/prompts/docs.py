"""CRUD del almacén único de documentos markdown + papelera + línea editorial.

Documentos (`texto`): listar/crear/obtener/guardar/borrar (a papelera) y restaurar; y los
catálogos editoriales de apoyo (auto-adjunto por marca, validación de pilares y marcas
disponibles) que pueblan los selectores del SPA. Errores como JSON en español.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ... import libprompts, marcas
from ..._http_json import leer_json
from ._comun import _doc_json

# --------------------------------------------------------------------------- #
# CRUD de documentos                                                          #
# --------------------------------------------------------------------------- #


def _facetas(docs: list[libprompts.Documento]) -> dict[str, object]:
    """Resumen de facetas (conteos) para poblar los filtros de navegacion del SPA."""
    etiquetas: dict[str, int] = {}
    pipelines: dict[str, int] = {}
    for d in docs:
        for e in d.etiquetas:
            etiquetas[e] = etiquetas.get(e, 0) + 1
        for p in d.pipelines:
            pipelines[p] = pipelines.get(p, 0) + 1
    return {
        "etiquetas": sorted(({"valor": k, "total": v} for k, v in etiquetas.items()), key=lambda x: x["valor"]),
        "pipelines": pipelines,
    }


async def listar(request: Request) -> Response:
    """`GET /api/prompts` -> `{documentos, carpetas, facetas}` con facetas opcionales.

    Filtros (query, todos opcionales): `tipo`, `carpeta`, `q`, `etiqueta`, `marca`,
    `clase`, `pipeline`. Las `facetas` resumen etiquetas/pipelines del resultado para
    poblar los filtros de la nueva navegacion.
    """
    qp = request.query_params
    docs = libprompts.listar(
        tipo=qp.get("tipo") or None,
        carpeta=qp.get("carpeta") or None,
        q=qp.get("q") or None,
        etiqueta=qp.get("etiqueta") or None,
        marca=qp.get("marca") or None,
        clase=qp.get("clase") or None,
        pipeline=qp.get("pipeline") or None,
    )
    # Estado de publicación POR LOTE: una consulta SQL (punteros) + una llamada git (HEADs)
    # para TODO el listado, en vez de una por documento.
    punteros = libprompts.producciones()
    shas = libprompts.shas_actuales()
    return JSONResponse({
        "documentos": [
            _doc_json(d, estado_pub=libprompts.estado_publicacion(d.id, punteros=punteros, shas=shas))
            for d in docs
        ],
        "carpetas": libprompts.listar_carpetas(tipo=qp.get("tipo") or None),
        "facetas": _facetas(docs),
    })


async def crear(request: Request) -> Response:
    """`POST /api/prompts` -> crea un documento `{titulo, tipo, ...}` -> `{documento}`."""
    datos = await leer_json(request)
    titulo = datos.get("titulo")
    if not isinstance(titulo, str) or not titulo.strip():
        return JSONResponse({"error": "El título es obligatorio."}, status_code=400)
    kwargs: dict[str, object] = {}
    for clave in ("descripcion", "tipo", "carpeta", "cuerpo", "clase", "rol"):
        valor = datos.get(clave)
        if isinstance(valor, str):
            kwargs[clave] = valor
    for clave in ("marcas", "etiquetas", "pipelines"):
        if isinstance(datos.get(clave), list):
            kwargs[clave] = [m for m in datos[clave] if isinstance(m, str)]
    if isinstance(datos.get("prioridad"), int) and not isinstance(datos.get("prioridad"), bool):
        kwargs["prioridad"] = datos["prioridad"]
    try:
        doc = libprompts.crear(titulo, **kwargs)
    except libprompts.PromptsError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"documento": _doc_json(doc)})


async def obtener(request: Request) -> Response:
    """`GET /api/prompts/{doc_id}` -> `{documento}` (404 si no existe)."""
    doc = libprompts.obtener(request.path_params["doc_id"])
    if doc is None:
        return JSONResponse({"error": "Ese documento no existe."}, status_code=404)
    return JSONResponse({"documento": _doc_json(doc)})


async def guardar(request: Request) -> Response:
    """`PUT /api/prompts/{doc_id}` -> actualiza -> `{documento}` (puede cambiar el id)."""
    doc_id = request.path_params["doc_id"]
    datos = await leer_json(request)
    kwargs: dict[str, object] = {}
    for clave in ("titulo", "descripcion", "cuerpo", "carpeta", "clase", "rol"):
        valor = datos.get(clave)
        if isinstance(valor, str):
            kwargs[clave] = valor
    for clave in ("marcas", "etiquetas", "pipelines"):
        if isinstance(datos.get(clave), list):
            kwargs[clave] = [m for m in datos[clave] if isinstance(m, str)]
    if isinstance(datos.get("prioridad"), int) and not isinstance(datos.get("prioridad"), bool):
        kwargs["prioridad"] = datos["prioridad"]
    # Concurrencia optimista (opcional): el cliente echa el `rev` que cargo; si falta, no hay
    # chequeo (autosave legado, last-write-wins).
    rev_base = datos.get("rev")
    if isinstance(rev_base, str):
        kwargs["rev_base"] = rev_base
    try:
        doc = libprompts.guardar(doc_id, **kwargs)
    except libprompts.ConflictoEdicion as e:
        # El working copy cambio debajo: 409 para que el frontend avise "recarga, no pises".
        return JSONResponse({"error": str(e)}, status_code=409)
    except libprompts.PromptsError as e:
        # "no existe" -> 404; el resto (validacion) -> 400.
        codigo = 404 if "no existe" in str(e) else 400
        return JSONResponse({"error": str(e)}, status_code=codigo)
    return JSONResponse({"documento": _doc_json(doc)})


async def borrar(request: Request) -> Response:
    """`DELETE /api/prompts/{doc_id}` -> a papelera -> `{mensaje}` (404)."""
    try:
        libprompts.borrar(request.path_params["doc_id"])
    except libprompts.PromptsError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    return JSONResponse({"mensaje": "Documento movido a la papelera."})


# --------------------------------------------------------------------------- #
# Papelera                                                                     #
# --------------------------------------------------------------------------- #


async def papelera_listar(request: Request) -> Response:
    """`GET /api/prompts/papelera` -> `{papelera: [...]}`."""
    return JSONResponse({"papelera": libprompts.listar_papelera()})


async def papelera_restaurar(request: Request) -> Response:
    """`POST /api/prompts/papelera/{pid}/restaurar` -> `{documento}` (400/404)."""
    try:
        doc = libprompts.restaurar(request.path_params["pid"])
    except libprompts.PromptsError as e:
        codigo = 404 if "no está en la papelera" in str(e) else 400
        return JSONResponse({"error": str(e)}, status_code=codigo)
    return JSONResponse({"documento": _doc_json(doc)})


# --------------------------------------------------------------------------- #
# Linea editorial: auto-adjunto + marcas disponibles                           #
# --------------------------------------------------------------------------- #


async def editoriales(request: Request) -> Response:
    """`GET /api/prompts/editoriales?marca=&pipeline=` -> `{editoriales: [...]}` (auto-adjunto).

    `pipeline` (opcional) acota el auto-adjunto al conjunto que entra en ese proceso.
    """
    marca = request.query_params.get("marca") or ""
    pipeline = request.query_params.get("pipeline") or None
    if pipeline is not None and pipeline not in libprompts.PIPELINES:
        return JSONResponse({"error": "Pipeline desconocido."}, status_code=404)
    docs = libprompts.editoriales_de_marca(marca, pipeline=pipeline)
    return JSONResponse({"editoriales": [d.a_dict() for d in docs]})


async def validacion(request: Request) -> Response:
    """`GET /api/prompts/validacion?marca=` -> diagnostico de los 4 pilares editoriales.

    Devuelve `{completa, faltan, recomendacion, pilares}` (ver `libprompts.validacion_editorial`).
    Lo consume el SPA para avisar si la linea editorial de la marca esta incompleta ANTES de
    lanzar una generacion.
    """
    marca = request.query_params.get("marca") or ""
    return JSONResponse(libprompts.validacion_editorial(marca))


async def marcas_disponibles(request: Request) -> Response:
    """`GET /api/prompts/marcas` -> `{marcas: [{id, nombre}]}` (catalogo de marcas).

    La Texto es autosuficiente: expone su propio catalogo de marcas (en vez de
    depender del endpoint de skills, que se retira) para poblar el selector del SPA.
    """
    return JSONResponse({"marcas": [{"id": mid, "nombre": nombre} for mid, nombre in marcas.opciones()]})
