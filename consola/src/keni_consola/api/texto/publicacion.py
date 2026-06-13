"""Versionado (git) y PUBLICACIÓN inmutable + solicitudes.

Historial/versión/revertir (lectura del historial git del doc) y el modelo de publicación
del rediseño de la Biblioteca: EDITAR es libre (working copy + commits git); los pipelines
inyectan SIEMPRE la versión PUBLICADA (sha git fijado). Publicar = mover el puntero
"producción" (solo ADMIN). Un editor PROPONE publicar vía una SOLICITUD que el admin aprueba
(publica) o rechaza. Sin puntero, fallback a working copy (migración suave).
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ... import libtexto, permisos
from ..._http_json import leer_json
from ...seguridad import autor_de_peticion
from ._comun import _doc_json

# --------------------------------------------------------------------------- #
# Historial de versiones (git)                                                 #
# --------------------------------------------------------------------------- #


async def historial(request: Request) -> Response:
    """`GET /api/texto/{doc_id}/historial` -> `{historial: [{sha, fecha, autor, mensaje}]}`."""
    try:
        items = libtexto.historial(request.path_params["doc_id"])
    except libtexto.TextoError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    return JSONResponse({"historial": items})


async def version(request: Request) -> Response:
    """`GET /api/texto/{doc_id}/version/{sha}` -> `{documento}` de esa version (404)."""
    doc = libtexto.version(request.path_params["doc_id"], request.path_params["sha"])
    if doc is None:
        return JSONResponse({"error": "No se encontró esa versión."}, status_code=404)
    return JSONResponse({"documento": _doc_json(doc)})


async def revertir(request: Request) -> Response:
    """`POST /api/texto/{doc_id}/revertir/{sha}` -> revierte (commit nuevo) -> `{documento}`."""
    try:
        doc = libtexto.restaurar_version(
            request.path_params["doc_id"], request.path_params["sha"],
            autor=autor_de_peticion(request),
        )
    except libtexto.TextoError as e:
        codigo = 404 if ("no existe" in str(e) or "esa versión" in str(e)) else 400
        return JSONResponse({"error": str(e)}, status_code=codigo)
    return JSONResponse({"documento": _doc_json(doc)})


# --------------------------------------------------------------------------- #
# Publicación: versiones inmutables + puntero "producción" + solicitudes       #
# --------------------------------------------------------------------------- #

_MSG_SOLO_ADMIN_PUBLICAR = "Solo un administrador puede publicar a producción."


def _autor_nombre(request: Request) -> str:
    """Nombre del usuario autenticado para la atribución de publicaciones/solicitudes."""
    autor = autor_de_peticion(request)
    return (autor or {}).get("usuario", "") or ""


def _resolver_sha(doc_id: str, datos: dict) -> tuple[str | None, Response | None]:
    """Resuelve el sha del body (o el HEAD git del doc por defecto) y lo VALIDA.

    Devuelve `(sha, None)` o `(None, respuesta_de_error)`. El sha debe corresponder a una
    versión LEGIBLE del documento (`libtexto.version`); sin versionado git no hay nada que
    fijar (400 accionable).
    """
    sha = datos.get("sha")
    if sha is not None and not isinstance(sha, str):
        return None, JSONResponse({"error": "El sha no es válido."}, status_code=400)
    sha = (sha or "").strip() or libtexto.sha_actual(doc_id)
    if not sha:
        return None, JSONResponse(
            {"error": "Este documento no tiene versiones (el versionado git no está disponible)."},
            status_code=400,
        )
    if libtexto.version(doc_id, sha) is None:
        return None, JSONResponse(
            {"error": "No se encontró esa versión del documento."}, status_code=400
        )
    return sha, None


async def publicar(request: Request) -> Response:
    """`POST /api/texto/{doc_id}/publicar` body `{sha?, nota}` -> `{documento}`. SOLO ADMIN.

    Mueve el puntero de PRODUCCIÓN del documento al `sha` (por defecto, el HEAD git del
    doc). 403 si no es admin; 404 si el doc no existe; 400 si el sha no es una versión.
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN_PUBLICAR)
    doc_id = request.path_params["doc_id"]
    doc = libtexto.obtener(doc_id)
    if doc is None:
        return JSONResponse({"error": "Ese documento no existe."}, status_code=404)
    datos = await leer_json(request)
    sha, error = _resolver_sha(doc_id, datos)
    if error is not None:
        return error
    from ... import db

    db.crear_texto_publicacion(
        doc_id=doc_id, sha=sha,
        autor=_autor_nombre(request),
        nota=datos.get("nota") if isinstance(datos.get("nota"), str) else "",
    )
    return JSONResponse({"documento": _doc_json(doc)})


async def solicitar(request: Request) -> Response:
    """`POST /api/texto/{doc_id}/solicitar` body `{sha?, nota}` -> `{solicitud}`.

    Crea una solicitud ABIERTA de publicación (cualquier usuario autenticado). Si ya había
    una abierta para ese doc, la SUSTITUYE (la última propuesta del equipo es la que cuenta).
    """
    doc_id = request.path_params["doc_id"]
    doc = libtexto.obtener(doc_id)
    if doc is None:
        return JSONResponse({"error": "Ese documento no existe."}, status_code=404)
    datos = await leer_json(request)
    sha, error = _resolver_sha(doc_id, datos)
    if error is not None:
        return error
    from ... import db

    sol = db.crear_texto_solicitud(
        doc_id=doc_id, sha_propuesto=sha,
        autor=_autor_nombre(request),
        nota=datos.get("nota") if isinstance(datos.get("nota"), str) else "",
    )
    return JSONResponse({"solicitud": _solicitud_json(sol)})


def _solicitud_json(sol: dict) -> dict[str, object]:
    """Forma pública de una solicitud (CONTRATO con el frontend del rediseño).

    `titulo` se resuelve del documento (cae al doc_id si el doc ya no existe);
    `revisor`/`comentario`/`resuelto` salen como null mientras la solicitud está abierta.
    """
    doc = libtexto.obtener(str(sol.get("doc_id", "")))
    return {
        "id": sol["id"],
        "doc_id": sol["doc_id"],
        "titulo": doc.titulo if doc is not None else sol["doc_id"],
        "sha_propuesto": sol["sha_propuesto"],
        "autor": sol["autor"],
        "nota": sol["nota"],
        "estado": sol["estado"],
        "revisor": sol["revisor"] or None,
        "comentario": sol["comentario"] or None,
        "creado": sol["creado"],
        "resuelto": sol["resuelto"] or None,
    }


async def solicitudes_listar(request: Request) -> Response:
    """`GET /api/texto/solicitudes?estado=abierta` -> `{solicitudes: [...]}` (recientes 1º).

    `estado` (opcional) filtra por `abierta`/`aprobada`/`rechazada`; sin él, todas.
    """
    from ... import db

    estado = request.query_params.get("estado") or None
    if estado is not None and estado not in db.ESTADOS_SOLICITUD_TEXTO:
        return JSONResponse({"error": "Estado de solicitud desconocido."}, status_code=400)
    items = db.listar_texto_solicitudes(estado)
    return JSONResponse({"solicitudes": [_solicitud_json(s) for s in items]})


async def solicitud_aprobar(request: Request) -> Response:
    """`POST /api/texto/solicitudes/{sid}/aprobar` body `{comentario?}`. SOLO ADMIN.

    PUBLICA el sha propuesto (mueve el puntero de producción) y marca la solicitud como
    `aprobada`. -> `{solicitud, documento}`. 404 si no existe; 409 si ya estaba resuelta;
    400 si la versión propuesta ya no es legible (la solicitud queda abierta).
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN_PUBLICAR)
    from ... import db

    sol = db.obtener_texto_solicitud(request.path_params["sid"])
    if sol is None:
        return JSONResponse({"error": "Esa solicitud no existe."}, status_code=404)
    if sol["estado"] != db.ESTADO_SOLICITUD_ABIERTA:
        return JSONResponse({"error": "Esa solicitud ya fue resuelta."}, status_code=409)
    doc = libtexto.obtener(sol["doc_id"])
    if doc is None:
        return JSONResponse({"error": "El documento de esa solicitud ya no existe."}, status_code=400)
    if libtexto.version(sol["doc_id"], sol["sha_propuesto"]) is None:
        return JSONResponse(
            {"error": "La versión propuesta ya no se puede leer del historial."}, status_code=400
        )
    datos = await leer_json(request)
    comentario = datos.get("comentario") if isinstance(datos.get("comentario"), str) else ""
    resuelta = db.resolver_texto_solicitud(
        sol["id"], estado=db.ESTADO_SOLICITUD_APROBADA,
        revisor=_autor_nombre(request), comentario=comentario,
    )
    if resuelta is None:  # carrera: otro admin la resolvió entre el SELECT y el UPDATE
        return JSONResponse({"error": "Esa solicitud ya fue resuelta."}, status_code=409)
    db.crear_texto_publicacion(
        doc_id=sol["doc_id"], sha=sol["sha_propuesto"],
        autor=_autor_nombre(request), nota=sol["nota"],
    )
    return JSONResponse({
        "solicitud": _solicitud_json(resuelta),
        "documento": _doc_json(doc),
    })


async def solicitud_rechazar(request: Request) -> Response:
    """`POST /api/texto/solicitudes/{sid}/rechazar` body `{comentario?}`. SOLO ADMIN.

    Marca la solicitud como `rechazada` (no toca el puntero). -> `{solicitud}`.
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN_PUBLICAR)
    from ... import db

    sol = db.obtener_texto_solicitud(request.path_params["sid"])
    if sol is None:
        return JSONResponse({"error": "Esa solicitud no existe."}, status_code=404)
    if sol["estado"] != db.ESTADO_SOLICITUD_ABIERTA:
        return JSONResponse({"error": "Esa solicitud ya fue resuelta."}, status_code=409)
    datos = await leer_json(request)
    comentario = datos.get("comentario") if isinstance(datos.get("comentario"), str) else ""
    resuelta = db.resolver_texto_solicitud(
        sol["id"], estado=db.ESTADO_SOLICITUD_RECHAZADA,
        revisor=_autor_nombre(request), comentario=comentario,
    )
    if resuelta is None:
        return JSONResponse({"error": "Esa solicitud ya fue resuelta."}, status_code=409)
    return JSONResponse({"solicitud": _solicitud_json(resuelta)})
