"""Versionado (git) y PUBLICACIÓN inmutable + solicitudes.

Historial/versión/revertir (lectura del historial git del doc) y el modelo de publicación
de la Prompts: EDITAR es libre (working copy + commits git); los pipelines inyectan
SIEMPRE un cuerpo ESTABLE (la versión PUBLICADA si hay puntero, si no el HEAD git), nunca el
working copy mutable que el autosave reescribe en vivo. Publicar = mover el puntero
"producción" (solo ADMIN). Un editor PROPONE publicar vía una SOLICITUD que el admin aprueba
(publica) o rechaza. Sin puntero ni commit legible, fallback a working copy (migración suave).
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ... import libprompts, permisos
from ..._http_json import leer_json
from ...seguridad import autor_de_peticion
from ._comun import _doc_json

# --------------------------------------------------------------------------- #
# Historial de versiones (git)                                                 #
# --------------------------------------------------------------------------- #


async def historial(request: Request) -> Response:
    """`GET /api/prompts/{doc_id}/historial` -> `{historial: [{sha, fecha, autor, mensaje}]}`."""
    try:
        items = libprompts.historial(request.path_params["doc_id"])
    except libprompts.PromptsError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    return JSONResponse({"historial": items})


async def version(request: Request) -> Response:
    """`GET /api/prompts/{doc_id}/version/{sha}` -> `{documento}` de esa version (404)."""
    doc = libprompts.version(request.path_params["doc_id"], request.path_params["sha"])
    if doc is None:
        return JSONResponse({"error": "No se encontró esa versión."}, status_code=404)
    return JSONResponse({"documento": _doc_json(doc)})


async def revertir(request: Request) -> Response:
    """`POST /api/prompts/{doc_id}/revertir/{sha}` -> "Traer al borrador" -> `{documento}`.

    NO crea un commit ni publica; CARGA el contenido de esa versión en el working copy
    (borrador). El usuario decide después si lo publica.
    """
    try:
        doc = libprompts.restaurar_version(
            request.path_params["doc_id"], request.path_params["sha"],
            autor=autor_de_peticion(request),
        )
    except libprompts.PromptsError as e:
        codigo = 404 if ("no existe" in str(e) or "esa versión" in str(e)) else 400
        return JSONResponse({"error": str(e)}, status_code=codigo)
    return JSONResponse({"documento": _doc_json(doc)})


async def descartar(request: Request) -> Response:
    """`POST /api/prompts/{doc_id}/descartar` -> resetea el borrador a lo PUBLICADO -> `{documento}`.

    Reescribe el working copy con el contenido del puntero de producción SIN crear commit.
    404 si el doc no existe; 400 si no hay versión publicada a la que volver.
    """
    doc_id = request.path_params["doc_id"]
    if libprompts.obtener(doc_id) is None:
        return JSONResponse({"error": "Ese documento no existe."}, status_code=404)
    try:
        doc = libprompts.descartar_borrador(doc_id)
    except libprompts.PromptsError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"documento": _doc_json(doc)})


# --------------------------------------------------------------------------- #
# Publicación: versiones inmutables + puntero "producción" + solicitudes       #
# --------------------------------------------------------------------------- #

_MSG_SOLO_ADMIN_PUBLICAR = "Solo un administrador puede publicar a producción."
_MSG_VACIO = "No se puede publicar un documento vacío: escribe contenido antes de publicar o solicitar."


def _autor_nombre(request: Request) -> str:
    """Nombre del usuario autenticado para la atribución de piezas/solicitudes."""
    autor = autor_de_peticion(request)
    return (autor or {}).get("usuario", "") or ""


def _resolver_sha(doc_id: str, datos: dict) -> tuple[str | None, Response | None]:
    """Resuelve un sha EXPLÍCITO del body (fijar una versión existente) y lo VALIDA.

    Devuelve:
      - `(sha, None)`   : el body trajo un sha que SÍ corresponde a una versión legible.
      - `(None, error)` : el body trajo un sha inválido o inexistente (400).
      - `(None, None)`  : el body NO trajo sha -> el llamante debe COMITEAR el borrador como
                          versión nueva (commit intencionado con la nota, ver `fijar_version`).

    El autosave no commitea, así que el caso normal de "Publicar" es comitear el working copy
    ahora (no fijar un HEAD preexistente).
    """
    sha = datos.get("sha")
    if sha is None:
        return None, None
    if not isinstance(sha, str):
        return None, JSONResponse({"error": "El sha no es válido."}, status_code=400)
    sha = sha.strip()
    if not sha:
        return None, None
    if libprompts.version(doc_id, sha) is None:
        return None, JSONResponse(
            {"error": "No se encontró esa versión del documento."}, status_code=400
        )
    return sha, None


def _sha_a_publicar(
    doc_id: str, datos: dict, *, autor: dict[str, str] | None
) -> tuple[str | None, Response | None]:
    """Sha que se va a fijar como producción/propuesta: el EXPLÍCITO del body, o uno NUEVO
    comiteando el working copy con la `nota` como mensaje (commit intencionado).

    Una VERSIÓN = una publicación: sin sha explícito, publicar/solicitar CREA la versión.
    Rechaza (400) publicar/solicitar un cuerpo VACÍO, tanto fijando un sha existente sin
    contenido como comiteando un working copy en blanco.
    """
    sha, error = _resolver_sha(doc_id, datos)
    if error is not None:
        return None, error
    if sha is not None:
        pieza = libprompts.version(doc_id, sha)
        if pieza is None or not pieza.cuerpo.strip():
            return None, JSONResponse({"error": _MSG_VACIO}, status_code=400)
        return sha, None
    nota = datos.get("nota") if isinstance(datos.get("nota"), str) else ""
    try:
        sha = libprompts.fijar_version(doc_id, nota=nota, autor=autor)
    except libprompts.PromptsError as e:
        return None, JSONResponse({"error": str(e)}, status_code=400)
    if not sha:
        return None, JSONResponse(
            {"error": "Este documento no se puede versionar (el versionado git no está disponible)."},
            status_code=400,
        )
    return sha, None


async def publicar(request: Request) -> Response:
    """`POST /api/prompts/{doc_id}/publicar` body `{sha?, nota}` -> `{documento}`. SOLO ADMIN.

    Versionado INTENCIONADO: sin `sha` en el body, COMITEA el working copy (la `nota` del
    usuario es el mensaje del commit) y mueve el puntero de PRODUCCIÓN a ese sha nuevo (una
    versión = una publicación). Con `sha` explícito, fija esa versión existente. 403 si no es
    admin; 404 si el doc no existe; 400 si el sha no es una versión o no hay versionado.
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN_PUBLICAR)
    doc_id = request.path_params["doc_id"]
    doc = libprompts.obtener(doc_id)
    if doc is None:
        return JSONResponse({"error": "Ese documento no existe."}, status_code=404)
    datos = await leer_json(request)
    sha, error = _sha_a_publicar(doc_id, datos, autor=autor_de_peticion(request))
    if error is not None:
        return error
    from ... import db

    db.crear_texto_publicacion(
        doc_id=doc_id, sha=sha,
        autor=_autor_nombre(request),
        nota=datos.get("nota") if isinstance(datos.get("nota"), str) else "",
    )
    # Relee el doc: el commit del borrador no cambió el working copy, pero `_doc_json`
    # recalcula el estado de publicación (con puntero y `sin_publicar` actualizado).
    return JSONResponse({"documento": _doc_json(libprompts.obtener(doc_id) or doc)})


async def solicitar(request: Request) -> Response:
    """`POST /api/prompts/{doc_id}/solicitar` body `{sha?, nota}` -> `{solicitud}`.

    Crea una solicitud ABIERTA de publicación (cualquier usuario autenticado). Si ya había
    una abierta para ese doc, la SUSTITUYE (la última propuesta del equipo es la que cuenta).
    """
    doc_id = request.path_params["doc_id"]
    doc = libprompts.obtener(doc_id)
    if doc is None:
        return JSONResponse({"error": "Ese documento no existe."}, status_code=404)
    datos = await leer_json(request)
    # Igual que publicar: sin sha explícito, COMITEA el borrador actual para proponer ESA
    # versión (no un HEAD preexistente).
    sha, error = _sha_a_publicar(doc_id, datos, autor=autor_de_peticion(request))
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
    doc = libprompts.obtener(str(sol.get("doc_id", "")))
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
    """`GET /api/prompts/solicitudes?estado=abierta` -> `{solicitudes: [...]}` (recientes 1º).

    `estado` (opcional) filtra por `abierta`/`aprobada`/`rechazada`; sin él, todas.
    """
    from ... import db

    estado = request.query_params.get("estado") or None
    if estado is not None and estado not in db.ESTADOS_SOLICITUD_TEXTO:
        return JSONResponse({"error": "Estado de solicitud desconocido."}, status_code=400)
    items = db.listar_texto_solicitudes(estado)
    return JSONResponse({"solicitudes": [_solicitud_json(s) for s in items]})


async def solicitud_aprobar(request: Request) -> Response:
    """`POST /api/prompts/solicitudes/{sid}/aprobar` body `{comentario?}`. SOLO ADMIN.

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
    doc = libprompts.obtener(sol["doc_id"])
    if doc is None:
        return JSONResponse({"error": "El documento de esa solicitud ya no existe."}, status_code=400)
    if libprompts.version(sol["doc_id"], sol["sha_propuesto"]) is None:
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
    """`POST /api/prompts/solicitudes/{sid}/rechazar` body `{comentario?}`. SOLO ADMIN.

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
