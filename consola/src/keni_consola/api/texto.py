"""API de la TEXTO: documentos (prompts + linea editorial) + lanzar generacion.

CRUD del almacen unico de documentos markdown (`texto`) + el endpoint de LANZAR un
prompt sobre un target (contenido pegado / archivo / url / area de la Consola), que compone
el prompt (prompt + linea editorial adjunta + contexto) y ENCOLA un trabajo de `claude -p`
reutilizando la infra de generaciones (`dominio.texto_lanzar`). El frontend sondea
`GET /api/generaciones/{id}` hasta el estado terminal.

La app descubre este modulo por su variable `RUTAS` (ver `api/__init__.py`); no se toca
`app.py`. Errores como JSON en espanol. `ColaLlenaError` se deja PROPAGAR: el manejador
central de `app.py` la traduce a 429.

ORDEN DE RUTAS: las estaticas (`/papelera`, `/editoriales`, `/validacion`, `/areas`,
`/lanzar`, `/lanzar-archivo`, `/maquina`, `/estrategia`) van ANTES que la parametrica
`/{doc_id:path}` (que captura barras) para que Starlette las case primero.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import uuid
from pathlib import Path

from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import libtexto, marcas, permisos, prompts_procesos, redes
from .._http_json import leer_json
from ..dominio import texto_lanzar, extraccion_url
from ..seguridad import autor_de_peticion

# Tope de tamano del bloque de contexto (texto pegado / leido de archivo / url) en chars.
_MAX_TEXTO = 200_000
# Subida de archivo: limite y trozo de lectura.
_MAX_SUBIDA = 100 * 1024 * 1024  # 100 MB
_TROZO = 1024 * 1024
# Extensiones que tratamos como TEXTO (se leen e incrustan); el resto es MEDIA (se pasa la ruta).
_EXTS_TEXTO = frozenset({"", ".txt", ".md", ".markdown", ".csv", ".json", ".rtf", ".log"})
_RE_EXT = re.compile(r"^\.[a-z0-9]{1,8}$")


# --------------------------------------------------------------------------- #
# CRUD de documentos                                                          #
# --------------------------------------------------------------------------- #


def _doc_json(
    doc: libtexto.Documento, *, estado_pub: dict[str, object] | None = None
) -> dict[str, object]:
    """Serializa un documento + `procesos` (transparencia) + el estado de PUBLICACIÓN.

    `procesos` es de SOLO LECTURA y sale del catálogo en código (`prompts_procesos`), no del
    contenido editable: refleja qué módulo inyecta el prompt en un agente. [] si no está catalogado
    (p. ej. documentos editoriales o prompts aún sin cablear).

    Estado de PUBLICACIÓN (rediseño de la Biblioteca; CONTRATO con el frontend, también en
    el listado): `produccion` (`{sha, autor, nota, creado}` | null), `sha_actual` (HEAD git
    del doc | null) y `sin_publicar` (hay cambios sin publicar; false sin puntero).
    `estado_pub` (opcional) lo precalculan los listados POR LOTE para no pagar una consulta
    SQL + un subproceso git por documento.
    """
    if estado_pub is None:
        estado_pub = libtexto.estado_publicacion(doc.id)
    return {**doc.a_dict(), "procesos": prompts_procesos.procesos_de(doc.id), **estado_pub}


def _facetas(docs: list[libtexto.Documento]) -> dict[str, object]:
    """Resumen de facetas (conteos) para poblar los filtros de navegacion del SPA."""
    etiquetas: dict[str, int] = {}
    estados: dict[str, int] = {}
    pipelines: dict[str, int] = {}
    for d in docs:
        estados[d.estado] = estados.get(d.estado, 0) + 1
        for e in d.etiquetas:
            etiquetas[e] = etiquetas.get(e, 0) + 1
        for p in d.pipelines:
            pipelines[p] = pipelines.get(p, 0) + 1
    return {
        "etiquetas": sorted(({"valor": k, "total": v} for k, v in etiquetas.items()), key=lambda x: x["valor"]),
        "estados": estados,
        "pipelines": pipelines,
    }


async def listar(request: Request) -> Response:
    """`GET /api/texto` -> `{documentos, carpetas, facetas}` con facetas opcionales.

    Filtros (query, todos opcionales): `tipo`, `carpeta`, `q`, `estado`, `etiqueta`, `marca`,
    `clase`, `pipeline`. Las `facetas` resumen etiquetas/estados/pipelines del resultado para
    poblar los filtros de la nueva navegacion.
    """
    qp = request.query_params
    docs = libtexto.listar(
        tipo=qp.get("tipo") or None,
        carpeta=qp.get("carpeta") or None,
        q=qp.get("q") or None,
        estado=qp.get("estado") or None,
        etiqueta=qp.get("etiqueta") or None,
        marca=qp.get("marca") or None,
        clase=qp.get("clase") or None,
        pipeline=qp.get("pipeline") or None,
    )
    # Estado de publicación POR LOTE: una consulta SQL (punteros) + una llamada git (HEADs)
    # para TODO el listado, en vez de una por documento.
    punteros = libtexto.producciones()
    shas = libtexto.shas_actuales()
    return JSONResponse({
        "documentos": [
            _doc_json(d, estado_pub=libtexto.estado_publicacion(d.id, punteros=punteros, shas=shas))
            for d in docs
        ],
        "carpetas": libtexto.listar_carpetas(tipo=qp.get("tipo") or None),
        "facetas": _facetas(docs),
    })


async def crear(request: Request) -> Response:
    """`POST /api/texto` -> crea un documento `{titulo, tipo, ...}` -> `{documento}`."""
    datos = await leer_json(request)
    titulo = datos.get("titulo")
    if not isinstance(titulo, str) or not titulo.strip():
        return JSONResponse({"error": "El título es obligatorio."}, status_code=400)
    kwargs: dict[str, object] = {}
    for clave in ("descripcion", "tipo", "carpeta", "cuerpo", "clase", "estado", "rol"):
        valor = datos.get(clave)
        if isinstance(valor, str):
            kwargs[clave] = valor
    for clave in ("marcas", "etiquetas", "pipelines"):
        if isinstance(datos.get(clave), list):
            kwargs[clave] = [m for m in datos[clave] if isinstance(m, str)]
    if isinstance(datos.get("prioridad"), int) and not isinstance(datos.get("prioridad"), bool):
        kwargs["prioridad"] = datos["prioridad"]
    try:
        doc = libtexto.crear(titulo, **kwargs)
    except libtexto.TextoError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"documento": _doc_json(doc)})


async def obtener(request: Request) -> Response:
    """`GET /api/texto/{doc_id}` -> `{documento}` (404 si no existe)."""
    doc = libtexto.obtener(request.path_params["doc_id"])
    if doc is None:
        return JSONResponse({"error": "Ese documento no existe."}, status_code=404)
    return JSONResponse({"documento": _doc_json(doc)})


async def guardar(request: Request) -> Response:
    """`PUT /api/texto/{doc_id}` -> actualiza -> `{documento}` (puede cambiar el id)."""
    doc_id = request.path_params["doc_id"]
    datos = await leer_json(request)
    kwargs: dict[str, object] = {}
    for clave in ("titulo", "descripcion", "cuerpo", "carpeta", "clase", "estado", "rol"):
        valor = datos.get(clave)
        if isinstance(valor, str):
            kwargs[clave] = valor
    for clave in ("marcas", "etiquetas", "pipelines"):
        if isinstance(datos.get(clave), list):
            kwargs[clave] = [m for m in datos[clave] if isinstance(m, str)]
    if isinstance(datos.get("prioridad"), int) and not isinstance(datos.get("prioridad"), bool):
        kwargs["prioridad"] = datos["prioridad"]
    try:
        doc = libtexto.guardar(doc_id, **kwargs)
    except libtexto.TextoError as e:
        # "no existe" -> 404; el resto (validacion) -> 400.
        codigo = 404 if "no existe" in str(e) else 400
        return JSONResponse({"error": str(e)}, status_code=codigo)
    return JSONResponse({"documento": _doc_json(doc)})


async def borrar(request: Request) -> Response:
    """`DELETE /api/texto/{doc_id}` -> a papelera -> `{mensaje}` (404)."""
    try:
        libtexto.borrar(request.path_params["doc_id"])
    except libtexto.TextoError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    return JSONResponse({"mensaje": "Documento movido a la papelera."})


# --------------------------------------------------------------------------- #
# Papelera                                                                     #
# --------------------------------------------------------------------------- #


async def papelera_listar(request: Request) -> Response:
    """`GET /api/texto/papelera` -> `{papelera: [...]}`."""
    return JSONResponse({"papelera": libtexto.listar_papelera()})


async def papelera_restaurar(request: Request) -> Response:
    """`POST /api/texto/papelera/{pid}/restaurar` -> `{documento}` (400/404)."""
    try:
        doc = libtexto.restaurar(request.path_params["pid"])
    except libtexto.TextoError as e:
        codigo = 404 if "no está en la papelera" in str(e) else 400
        return JSONResponse({"error": str(e)}, status_code=codigo)
    return JSONResponse({"documento": _doc_json(doc)})


# --------------------------------------------------------------------------- #
# Linea editorial: auto-adjunto + areas disponibles                            #
# --------------------------------------------------------------------------- #


async def editoriales(request: Request) -> Response:
    """`GET /api/texto/editoriales?marca=&pipeline=` -> `{editoriales: [...]}` (auto-adjunto).

    `pipeline` (opcional) acota el auto-adjunto al conjunto que entra en ese proceso.
    """
    marca = request.query_params.get("marca") or ""
    pipeline = request.query_params.get("pipeline") or None
    if pipeline is not None and pipeline not in libtexto.PIPELINES:
        return JSONResponse({"error": "Pipeline desconocido."}, status_code=404)
    docs = libtexto.editoriales_de_marca(marca, pipeline=pipeline)
    return JSONResponse({"editoriales": [d.a_dict() for d in docs]})


async def validacion(request: Request) -> Response:
    """`GET /api/texto/validacion?marca=` -> diagnostico de los 4 pilares editoriales.

    Devuelve `{completa, faltan, recomendacion, pilares}` (ver `libtexto.validacion_editorial`).
    Lo consume el SPA para avisar si la linea editorial de la marca esta incompleta ANTES de
    lanzar una generacion.
    """
    marca = request.query_params.get("marca") or ""
    return JSONResponse(libtexto.validacion_editorial(marca))


async def areas(request: Request) -> Response:
    """`GET /api/texto/areas` -> `{areas: [{id, nombre}]}` (secciones como contexto)."""
    return JSONResponse({"areas": texto_lanzar.areas_disponibles()})


async def marcas_disponibles(request: Request) -> Response:
    """`GET /api/texto/marcas` -> `{marcas: [{id, nombre}]}` (catalogo de marcas).

    La Texto es autosuficiente: expone su propio catalogo de marcas (en vez de
    depender del endpoint de skills, que se retira) para poblar el selector del SPA.
    """
    return JSONResponse({"marcas": [{"id": mid, "nombre": nombre} for mid, nombre in marcas.opciones()]})


# --------------------------------------------------------------------------- #
# Pipelines: registro, atribucion y preview del prompt ensamblado              #
# --------------------------------------------------------------------------- #


async def pipelines_listar(request: Request) -> Response:
    """`GET /api/texto/pipelines` -> `{pipelines: [{id, titulo, descripcion, rol, prompt_base_id}]}`.

    Es el catalogo de procesos de generacion: para cada uno, su prompt base EFECTIVO (resuelto
    por el registro, considerando rebindeos en la Texto). Sostiene la vista de atribucion.
    """
    items = []
    for pid, spec in libtexto.PIPELINES.items():
        try:
            base = libtexto.prompt_base_de(pid)
        except libtexto.TextoError:
            base = spec.get("prompt_defecto", "")
        items.append({
            "id": pid,
            "titulo": spec.get("titulo", pid),
            "descripcion": spec.get("descripcion", ""),
            "rol": spec.get("rol", ""),
            "prompt_base_id": base,
        })
    return JSONResponse({"pipelines": items})


async def pipeline_preview(request: Request) -> Response:
    """`GET /api/texto/pipelines/{pid}/preview?marca=&contexto=` -> prompt ENSAMBLADO.

    "Lo que inyectas es lo que ves": muestra el prompt final (base + editoriales + contexto)
    que recibiria `claude -p`, SIN lanzar nada. Resuelve de raiz "no se que se inyecta donde".
    """
    pid = request.path_params["pid"]
    if pid not in libtexto.PIPELINES:
        return JSONResponse({"error": "Pipeline desconocido."}, status_code=404)
    marca = request.query_params.get("marca") or ""
    contexto = request.query_params.get("contexto") or ""
    return JSONResponse(libtexto.previsualizar_pipeline(pid, marca, contexto[:_MAX_TEXTO]))


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
#
# Modelo (rediseño de la Biblioteca): EDITAR es libre (working copy + commits git); los
# pipelines inyectan SIEMPRE la versión PUBLICADA (sha git fijado). Publicar = mover el
# puntero (solo ADMIN). Un editor PROPONE publicar vía una SOLICITUD que el admin aprueba
# (publica) o rechaza. Sin puntero, fallback a working copy (migración suave).

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
    from .. import db

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
    from .. import db

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
    from .. import db

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
    from .. import db

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
    from .. import db

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


# --------------------------------------------------------------------------- #
# Catálogo de variables {{VAR}} + la "máquina" (riel de pipelines)             #
# --------------------------------------------------------------------------- #


async def variables(request: Request) -> Response:
    """`GET /api/texto/variables` -> `{variables: [{nombre, descripcion, ejemplo, origen}]}`.

    Catálogo (en código, fuente única) de los marcadores `{{VAR}}` que la Consola sustituye
    al inyectar prompts: transparencia para el editor de la Biblioteca.
    """
    return JSONResponse({"variables": libtexto.catalogo_variables()})


# Las TRES MÁQUINAS del riel (ADR 0011): Investigación (el motor de noticias), Producción
# (la máquina de contenido) y las Herramientas de importación. Cada etapa es:
#   - `mecanica`: paso del proceso SIN prompt de la Biblioteca (código puro o prompt
#     hardcodeado, p. ej. el clasificador de marca con Haiku). Da contexto: el riel cuenta
#     la historia completa del proceso, no solo los prompts editables.
#   - `prompt` : etapa cuyo prompt vive en la Biblioteca. `doc_id=None` => se resuelve por el
#     REGISTRO (`prompt_base_de`, ver `_ETAPA_PIPELINE`): respeta rebindeos sin tocar código.
#
# El ORDEN sigue el modelo conceptual del ADR 0011 (frontera: la validación QA es
# Investigación; copy/arte son Producción), apoyado en el orden real de los daemons
# (`ingesta_daemon.ejecutar_barrido`, `pipeline_contenido._barrido`). Donde difieren hoy
# manda el ADR: la clasificación de marca corre DENTRO del clustering y la QA corre tras
# la admisión del lado `contenido` (hasta F3), pero el riel los presenta como etapas del
# proceso de Investigación. La fusión semántica son DOS prompts: la verificación
# (`prompt/fusion-verificacion`) corre por grupo propuesto ANTES de fundir.
# Tupla de etapa: (tipo, id, titulo, doc_id | None, seccion | None).
_Etapa = tuple[str, str, str, str | None, str | None]
_MAQUINAS: tuple[tuple[str, str, str, tuple[_Etapa, ...]], ...] = (
    ("investigacion", "Investigación", "El motor de noticias", (
        ("mecanica", "ingesta", "Sondeo RSS + agencias", None, None),
        ("mecanica", "clustering", "Clustering y merge léxico", None, None),
        ("prompt", "fusion-verificacion", "Verificación pre-fusión", "prompt/fusion-verificacion", None),
        ("prompt", "fusion", "Fusión semántica", "prompt/fusion", None),
        ("prompt", "traduccion", "Traducción y localización MX", "prompt/traduccion", None),
        # El clasificador de marca usa un prompt HARDCODEADO (dominio.clasificador_marca),
        # no un doc de la Biblioteca: etapa mecánica hasta que ese prompt se externalice.
        ("mecanica", "clasificacion-marca", "Clasificación de marca (IA)", None, None),
        ("prompt", "ranking", "Ranking · perfil de relevancia", "prompt/editorial", None),
        ("mecanica", "admision", "Admisión", None, None),
        ("prompt", "validacion", "Validación de fuente (QA)", None, None),  # prompt_base_de("qa")
        ("prompt", "algoritmos", "Algoritmos · digest diario", "prompt/sugerencias", None),
    )),
    ("produccion", "Producción", "La máquina de contenido", (
        ("prompt", "copy", "Redacción editorial (copy)", None, None),       # prompt_base_de("copy")
        ("prompt", "arte", "Arte (imagen de la pieza)", "prompt/arte", None),
        ("mecanica", "avance", "Avance a revisión", None, None),
        ("mecanica", "publicacion", "Publicación", None, None),
        ("prompt", "evergreen", "Taller evergreen", None, "taller"),        # prompt_base_de("evergreen")
    )),
    ("importacion", "Herramientas de importación", "Insumos y documentos del equipo", (
        ("prompt", "insumos-portal", "Insumos · Portal/SMS", "prompt/insumos/portal", None),
        ("prompt", "insumos-corresponsales", "Insumos · Corresponsales", "prompt/insumos/corresponsales", None),
        ("prompt", "insumos-reporteros", "Insumos · Reporteros", "prompt/insumos/reporteros", None),
        ("prompt", "insumos-eventos-claro", "Insumos · Eventos Claro Sports", "prompt/insumos/eventos-claro", None),
        ("prompt", "importar-calendario", "Importar calendario", "prompt/importar/calendario", None),
        ("prompt", "importar-parrilla", "Importar rota/parrilla", "prompt/importar/parrilla", None),
    )),
)

# id de etapa -> pipeline del registro cuyo prompt base efectivo la alimenta (rebindeable).
_ETAPA_PIPELINE = {"validacion": "qa", "copy": "copy", "evergreen": "evergreen"}


def _doc_id_de_etapa(eid: str, doc_id: str | None) -> str:
    """Resuelve el doc de una etapa `prompt`: fijo, o el prompt base EFECTIVO del registro."""
    if doc_id is not None:
        return doc_id
    pipeline = _ETAPA_PIPELINE[eid]
    try:
        return libtexto.prompt_base_de(pipeline)
    except libtexto.TextoError:
        return libtexto.PIPELINES.get(pipeline, {}).get("prompt_defecto", "")


async def maquina(request: Request) -> Response:
    """`GET /api/texto/maquina?marca=` -> `{maquinas}`: las TRES máquinas del ADR 0011.

    Forma (CONTRATO con el frontend del rediseño): `maquinas` es la lista
    Investigación -> Producción -> Importación; cada una `{id, titulo, subtitulo, etapas}`
    con sus etapas en el orden del proceso (ver `_MAQUINAS`):
      - etapa `mecanica`: `{tipo, id, titulo}` (sin prompt de la Biblioteca; contexto).
      - etapa `prompt`  : `{tipo, id, titulo, doc_id, produccion, sha_actual, sin_publicar}`
        (+ `seccion` opcional, p. ej. `"taller"` para el evergreen) con el estado de
        publicación del documento que se inyecta en esa etapa.

    Las CAPAS editoriales ya no salen aquí: el ensamblaje por marca vive en
    `GET /api/texto/estrategia?marca=` (`orden_inyeccion` + pilares). `marca` se acepta
    por compatibilidad pero el riel es global (no depende de la marca).
    """
    punteros = libtexto.producciones()
    shas = libtexto.shas_actuales()

    def estado(doc_id: str) -> dict[str, object]:
        return libtexto.estado_publicacion(doc_id, punteros=punteros, shas=shas)

    maquinas = []
    for mid, titulo, subtitulo, etapas in _MAQUINAS:
        filas: list[dict[str, object]] = []
        for tipo, eid, etitulo, doc_id, seccion in etapas:
            if tipo == "mecanica":
                filas.append({"tipo": "mecanica", "id": eid, "titulo": etitulo})
                continue
            efectivo = _doc_id_de_etapa(eid, doc_id)
            fila: dict[str, object] = {
                "tipo": "prompt", "id": eid, "titulo": etitulo,
                "doc_id": efectivo, **estado(efectivo),
            }
            if seccion:
                fila["seccion"] = seccion
            filas.append(fila)
        maquinas.append({"id": mid, "titulo": titulo, "subtitulo": subtitulo, "etapas": filas})
    return JSONResponse({"maquinas": maquinas})


# Los 4+1 pilares de la estrategia de marca, SIEMPRE presentes y en orden fijo: los 4
# obligatorios (`PILARES_EDITORIALES`) + `reglas` (auxiliar). El bool es el `global` que se
# etiqueta cuando NO hay documento (con doc manda `es_editorial_global`, el mismo criterio
# que usa el auto-adjunto).
_PILARES_ESTRATEGIA: tuple[tuple[str, str, bool], ...] = (
    ("marca", "Identidad de marca", False),
    ("voz", "Voz y tono", False),
    ("tropicalizacion", "Tropicalización MX", True),
    ("plataforma", "Convenciones de plataforma", True),
    ("reglas", "Reglas globales", True),
)


async def estrategia(request: Request) -> Response:
    """`GET /api/texto/estrategia?marca=` -> la estrategia editorial de la marca.

    Forma (CONTRATO con el frontend del rediseño de "Estrategia de marca"):
      - `marca`: la pedida (puede ser "").
      - `completitud`: `{completa, faltan, recomendacion}` (misma lógica que `/validacion`).
      - `pilares`: SIEMPRE los 4+1 en orden fijo (marca, voz, tropicalizacion, plataforma,
        reglas); cada uno `{clase, titulo, doc_id|null, vacio, global, produccion,
        sha_actual, sin_publicar, actualizado}`. Sin documento: `doc_id` null y `vacio`
        true. `vacio` = cuerpo en blanco (mismo criterio que `/validacion`).
      - `extras`: documentos editoriales del auto-adjunto SIN clase-pilar (p. ej. los
        patrones medidos), con la misma forma (titulo = el del documento).
      - `orden_inyeccion`: ids en el ORDEN real de `adjuntos_copy()` para esa marca (lo
        que se adjunta al copy, capa a capa).
    """
    from ..dominio import generar  # perezoso: generar importa libtexto

    marca = request.query_params.get("marca") or ""
    punteros = libtexto.producciones()
    shas = libtexto.shas_actuales()

    def fila_doc(d: libtexto.Documento) -> dict[str, object]:
        return {
            "doc_id": d.id,
            "vacio": not d.cuerpo.strip(),
            "global": libtexto.es_editorial_global(d),
            **libtexto.estado_publicacion(d.id, punteros=punteros, shas=shas),
            "actualizado": d.actualizado,
        }

    docs = libtexto.editoriales_de_marca(marca)
    # Primer doc por clase en el orden del auto-adjunto: el que representa al pilar.
    por_clase: dict[str, libtexto.Documento] = {}
    for d in docs:
        por_clase.setdefault(d.clase, d)

    pilares: list[dict[str, object]] = []
    for clase, titulo, global_defecto in _PILARES_ESTRATEGIA:
        d = por_clase.get(clase)
        if d is None:
            pilares.append({
                "clase": clase, "titulo": titulo, "doc_id": None, "vacio": True,
                "global": global_defecto, "produccion": None, "sha_actual": None,
                "sin_publicar": False, "actualizado": None,
            })
        else:
            pilares.append({"clase": clase, "titulo": titulo, **fila_doc(d)})

    clases_pilar = {clase for clase, _, _ in _PILARES_ESTRATEGIA}
    extras = [
        {"clase": d.clase, "titulo": d.titulo, **fila_doc(d)}
        for d in docs
        if d.clase not in clases_pilar
    ]

    completitud = {
        k: v
        for k, v in libtexto.validacion_editorial(marca).items()
        if k in ("completa", "faltan", "recomendacion")
    }
    return JSONResponse({
        "marca": marca,
        "completitud": completitud,
        "pilares": pilares,
        "extras": extras,
        "orden_inyeccion": [d.id for d in generar.adjuntos_copy(marca)],
    })


# --------------------------------------------------------------------------- #
# Lanzar (JSON: contenido / url / area) y lanzar-archivo (multipart)           #
# --------------------------------------------------------------------------- #


def _adjuntos_lista(crudo: object) -> list[str]:
    """Normaliza la lista de ids de documentos editoriales a adjuntar."""
    return [a for a in crudo if isinstance(a, str)] if isinstance(crudo, list) else []


def _redes_lista(crudo: object) -> list[str]:
    """Filtra ids de red contra las canonicas (orden de llegada, sin duplicar).

    Solo importa en el MODO PIEZAS (prompt `salida=piezas`); para prompts normales el
    dominio ignora las redes. Devuelve [] si no llega una lista o no hay ids validos.
    """
    if not isinstance(crudo, list):
        return []
    vistas: list[str] = []
    for r in crudo:
        if isinstance(r, str) and redes.es_red(r) and r not in vistas:
            vistas.append(r)
    return vistas


def _bloque_de_target(target: dict, marca: str) -> tuple[str, str, Response | None]:
    """Resuelve el target a un BLOQUE DE CONTEXTO. Devuelve (bloque, titulo_sugerido, error).

    `titulo_sugerido` solo lo da la URL (el titular real de la página): sirve para que el
    borrador NO se titule con la primera línea del bloque (que, en una URL, es el AVISO de
    extracción automática). Para el resto de targets es "" (el título se deriva del contenido).
    """
    tipo = target.get("tipo") if isinstance(target, dict) else None
    valor = target.get("valor") if isinstance(target, dict) else None

    if not tipo or tipo == "ninguno":
        return "", "", None
    if tipo == "contenido":
        return (valor if isinstance(valor, str) else "")[:_MAX_TEXTO], "", None
    if tipo == "area":
        try:
            return texto_lanzar.area_contexto(valor if isinstance(valor, str) else "", marca), "", None
        except libtexto.TextoError as e:
            return "", "", JSONResponse({"error": str(e)}, status_code=400)
    if tipo == "url":
        url_limpia, error = extraccion_url.validar_url(valor)
        if error is not None:
            return "", "", JSONResponse({"error": error}, status_code=400)
        try:
            titulo, cuerpo = extraccion_url.extraer_texto(url_limpia)
        except extraccion_url.ExtraccionError as e:
            return "", "", JSONResponse({"error": str(e)}, status_code=502)
        nota = extraccion_url.componer_nota_no_verificada(url_limpia, titulo, cuerpo)
        return nota[:_MAX_TEXTO], titulo.strip(), None
    return "", "", JSONResponse({"error": "Tipo de target no válido."}, status_code=400)


async def lanzar(request: Request) -> Response:
    """`POST /api/texto/lanzar` -> compone y ENCOLA -> `{generacion}`.

    Cuerpo JSON: `{prompt_id?|texto?, titulo?, marca, adjuntos?: [ids], target: {tipo, valor}}`.
    `target.tipo ∈ {ninguno, contenido, url, area}`. Marca/prompt los valida el dominio.
    """
    datos = await leer_json(request)
    marca = datos.get("marca")
    if not isinstance(marca, str) or not marca:
        return JSONResponse({"error": "Falta la marca."}, status_code=400)

    bloque, titulo_contenido, error = _bloque_de_target(datos.get("target") or {}, marca)
    if error is not None:
        return error

    try:
        gen = texto_lanzar.lanzar(
            prompt_id=datos.get("prompt_id") if isinstance(datos.get("prompt_id"), str) else None,
            texto=datos.get("texto") if isinstance(datos.get("texto"), str) else None,
            titulo=datos.get("titulo") if isinstance(datos.get("titulo"), str) else "",
            marca=marca,
            adjuntos_ids=_adjuntos_lista(datos.get("adjuntos")),
            bloque_contexto=bloque,
            titulo_contenido=titulo_contenido,
            redes_ids=_redes_lista(datos.get("redes")),
            autor=autor_de_peticion(request),
        )
    except libtexto.TextoError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"generacion": gen})


def _extension_segura(nombre: str | None) -> str:
    """Extension en minusculas (`.mp4`, `.txt`) o "" si no es reconocible."""
    if not nombre:
        return ""
    suf = Path(nombre).suffix.lower()
    return suf if _RE_EXT.match(suf) else ""


async def _guardar_subida(archivo: UploadFile) -> tuple[Path, Path, str]:
    """Vuelca un `UploadFile` a un temporal saneado. Devuelve (ruta, dir_temporal, extension)."""
    dir_temporal = Path(tempfile.mkdtemp(prefix="keni-texto-"))
    ext = _extension_segura(archivo.filename)
    destino = dir_temporal / f"{uuid.uuid4().hex}{ext}"
    total = 0
    try:
        with destino.open("wb") as salida:
            while True:
                trozo = await archivo.read(_TROZO)
                if not trozo:
                    break
                total += len(trozo)
                if total > _MAX_SUBIDA:
                    raise libtexto.TextoError("El archivo es demasiado grande.")
                salida.write(trozo)
    except libtexto.TextoError:
        shutil.rmtree(dir_temporal, ignore_errors=True)
        raise
    except Exception as e:  # noqa: BLE001
        shutil.rmtree(dir_temporal, ignore_errors=True)
        raise libtexto.TextoError("No se pudo guardar el archivo subido.") from e
    if total == 0:
        shutil.rmtree(dir_temporal, ignore_errors=True)
        raise libtexto.TextoError("El archivo está vacío.")
    return destino, dir_temporal, ext


async def lanzar_archivo(request: Request) -> Response:
    """`POST /api/texto/lanzar-archivo` (multipart) -> compone con el archivo -> `{generacion}`.

    Form: `archivo`, `marca`, `prompt_id?`/`texto?`, `titulo?`, `adjuntos` (repetido o CSV).
    Texto (.txt/.md/...) se LEE e incrusta; media (imagen/video) se pasa por RUTA temporal
    (claude la lee en local; el lanzador borra el temporal al terminar).
    """
    try:
        form = await request.form()
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "No se pudo leer el archivo subido."}, status_code=400)
    marca = form.get("marca")
    archivo = form.get("archivo")
    if not isinstance(marca, str) or not marca:
        return JSONResponse({"error": "Falta la marca."}, status_code=400)
    if not isinstance(archivo, UploadFile):
        return JSONResponse({"error": "No se recibió ningún archivo."}, status_code=400)

    adjuntos: list[str] = []
    for valor in form.getlist("adjuntos"):
        if isinstance(valor, str):
            adjuntos.extend(p.strip() for p in valor.split(",") if p.strip())

    # Redes (modo PIEZAS): campo repetido o CSV. Se filtran contra las canonicas.
    redes_crudas: list[str] = []
    for valor in form.getlist("redes"):
        if isinstance(valor, str):
            redes_crudas.extend(p.strip() for p in valor.split(",") if p.strip())
    redes_ids = _redes_lista(redes_crudas)

    try:
        ruta, dir_temporal, ext = await _guardar_subida(archivo)
    except libtexto.TextoError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    bloque = ""
    dir_para_lanzar: Path | None = None
    if ext in _EXTS_TEXTO:
        try:
            bloque = ruta.read_text(encoding="utf-8", errors="replace")[:_MAX_TEXTO]
        finally:
            shutil.rmtree(dir_temporal, ignore_errors=True)
        if not bloque.strip():
            return JSONResponse({"error": "El archivo está vacío."}, status_code=400)
    else:
        # MEDIA: el temporal vive hasta que termine el trabajo (claude lo lee en local).
        bloque = f"Hay un archivo adjunto para esta tarea en la ruta local: {ruta}"
        dir_para_lanzar = dir_temporal

    def _campo(nombre: str) -> str | None:
        v = form.get(nombre)
        return v if isinstance(v, str) and v else None

    try:
        gen = texto_lanzar.lanzar(
            prompt_id=_campo("prompt_id"),
            texto=_campo("texto"),
            titulo=_campo("titulo") or "",
            marca=marca,
            adjuntos_ids=adjuntos,
            bloque_contexto=bloque,
            redes_ids=redes_ids,
            dir_temporal=dir_para_lanzar,
            autor=autor_de_peticion(request),
        )
    except libtexto.TextoError as e:
        if dir_para_lanzar is not None:
            shutil.rmtree(dir_para_lanzar, ignore_errors=True)
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"generacion": gen})


# Rutas: estaticas y multi-segmento ANTES que la parametrica `/{doc_id:path}` (captura barras).
RUTAS = [
    Route("/api/texto", listar, methods=["GET"]),
    Route("/api/texto", crear, methods=["POST"]),
    Route("/api/texto/papelera", papelera_listar, methods=["GET"]),
    Route("/api/texto/papelera/{pid}/restaurar", papelera_restaurar, methods=["POST"]),
    Route("/api/texto/editoriales", editoriales, methods=["GET"]),
    Route("/api/texto/validacion", validacion, methods=["GET"]),
    Route("/api/texto/areas", areas, methods=["GET"]),
    Route("/api/texto/marcas", marcas_disponibles, methods=["GET"]),
    Route("/api/texto/pipelines", pipelines_listar, methods=["GET"]),
    Route("/api/texto/pipelines/{pid}/preview", pipeline_preview, methods=["GET"]),
    Route("/api/texto/lanzar", lanzar, methods=["POST"]),
    Route("/api/texto/lanzar-archivo", lanzar_archivo, methods=["POST"]),
    # Publicación (rediseño): catálogo de variables, riel de la máquina (tres máquinas,
    # ADR 0011), estrategia de marca y solicitudes.
    Route("/api/texto/variables", variables, methods=["GET"]),
    Route("/api/texto/maquina", maquina, methods=["GET"]),
    Route("/api/texto/estrategia", estrategia, methods=["GET"]),
    Route("/api/texto/solicitudes", solicitudes_listar, methods=["GET"]),
    Route("/api/texto/solicitudes/{sid}/aprobar", solicitud_aprobar, methods=["POST"]),
    Route("/api/texto/solicitudes/{sid}/rechazar", solicitud_rechazar, methods=["POST"]),
    # Multi-segmento de versionado: el sufijo literal ancla la captura del `doc_id:path`.
    Route("/api/texto/{doc_id:path}/historial", historial, methods=["GET"]),
    Route("/api/texto/{doc_id:path}/version/{sha}", version, methods=["GET"]),
    Route("/api/texto/{doc_id:path}/revertir/{sha}", revertir, methods=["POST"]),
    Route("/api/texto/{doc_id:path}/publicar", publicar, methods=["POST"]),
    Route("/api/texto/{doc_id:path}/solicitar", solicitar, methods=["POST"]),
    Route("/api/texto/{doc_id:path}", obtener, methods=["GET"]),
    Route("/api/texto/{doc_id:path}", guardar, methods=["PUT"]),
    Route("/api/texto/{doc_id:path}", borrar, methods=["DELETE"]),
]
