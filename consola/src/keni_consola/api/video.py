"""API HTTP del motor de VIDEO (Ola VIDEO) — Estudio de Video.

Superficie REST sobre las composiciones y subtitulos del motor de video (ver el CONTRATO en
`docs/maquina-contenido/G-video-engine.md`). Es la capa fina entre el frontend (Estudio de
Video) y la base ya construida: NO hace render ni ASR (eso lo ejecutan los motores via el
worker), solo CRUD de composiciones/subtitulos y ENCOLADO de jobs de proceso.

QUE VIVE AQUI
=============
  - `GET    /api/video/formatos`                          presets de formato (+ red por formato).
  - `GET    /api/video/composiciones?marca=`              lista (filtro por marca).
  - `POST   /api/video/composiciones`                     crea (valida con keni_shared.video).
  - `GET    /api/video/composiciones/{id}`                detalle (404 si no existe).
  - `PUT    /api/video/composiciones/{id}`                actualiza documento/titulo/estado (valida).
  - `DELETE /api/video/composiciones/{id}`                borra la composicion (+ subtitulos).
  - `POST   /api/video/composiciones/{id}/render`         encola render (local, bajo demanda).
  - `POST   /api/video/composiciones/{id}/transcribir`    encola ASR (local; crea subtitulo).
  - `GET    /api/video/subtitulos?composicion_id=`        fila de subtitulos.
  - `PUT    /api/video/subtitulos/{id}`                   edita el texto corregido por el humano.

CONTRATO
========
  - La validacion del documento la hace `keni_shared.video.validar_composicion` (400 si falla,
    con el mensaje en espanol del ValueError). Solo valida la FORMA del sobre.
  - El encolado usa `generaciones.encolar_job_proceso(kind=..., params=..., marca=...)` con los
    kinds del seam (`dominio.jobspec.PROC_RENDER_VIDEO` / `PROC_TRANSCRIBIR`). Render (ffmpeg) y
    ASR (faster-whisper) son LOCALES, gratuitos y BAJO DEMANDA (los dispara un humano, no un
    daemon, y no consumen tokens), asi que NO tienen kill-switch ni gateo por maquina. La cola NO
    tiene tope (R-NO-LIMIT): solo el límite de presupuesto/pausa puede dar `ColaLlenaError` => 429.
  - Multi-tenant por marca: igual que el resto de la app, la marca de una peticion se valida
    contra el catalogo unico (`consola.marcas`) y el listado se filtra por ella.

SEGURIDAD: errores en espanol como JSON `{"error": ...}` sin tracebacks; SQL parametrizado vive
en `repos`/`db`. Este modulo NO publica nada real (no toca `KENI_PUBLICAR_REAL`).
"""

from __future__ import annotations

import json
import logging

from keni_shared import video as video_shared
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import db, generaciones, marcas, repos
from .._http_json import leer_json
from ..dominio import jobspec

_log = logging.getLogger("keni_consola.video")


# --------------------------------------------------------------------------- #
# Helpers comunes                                                              #
# --------------------------------------------------------------------------- #


def _validar_marca(marca: object) -> tuple[str | None, str | None]:
    """Valida la marca de una composicion. Devuelve (marca_normalizada, error_o_None).

    A diferencia de otros catalogos globales, una composicion de video SIEMPRE pertenece a una
    marca del piloto: '' / ausente NO es valido (cada render lleva voz/branding de su marca).
    """
    if not isinstance(marca, str) or not marca.strip():
        return None, "Falta la marca."
    marca = marca.strip()
    if not marcas.es_marca(marca):
        return None, "Marca no permitida."
    return marca, None


def _validar_estado(
    estado: object, *, defecto: str | None
) -> tuple[str | None, str | None]:
    """Valida el `estado` de una composicion (borrador | listo).

    Devuelve (estado_normalizado, error_o_None). `None`/ausente -> `defecto` (sin error). Un
    valor presente fuera del enum -> error (400 en el handler).
    """
    if estado is None:
        return defecto, None
    if not isinstance(estado, str) or estado not in db.ESTADOS_VIDEO_COMPOSICION:
        return None, "Estado de composición no válido."
    return estado, None


def _composicion_a_dict(item: dict) -> dict:
    """Serializa una composicion: parsea `documento` a objeto y adjunta el nombre de marca."""
    crudo = item.get("documento") or "{}"
    try:
        doc = json.loads(crudo) if isinstance(crudo, str) else crudo
    except (ValueError, TypeError):
        doc = {}
    if not isinstance(doc, dict):
        doc = {}
    return {
        **item,
        "documento": doc,
        "marca_nombre": marcas.etiqueta_de(item["marca"]) if item.get("marca") else "",
    }


def _subtitulo_a_dict(item: dict) -> dict:
    """Serializa una fila de subtitulos: `segmentos` como objeto JSON (no string crudo)."""
    crudo = item.get("segmentos") or ""
    try:
        segs = json.loads(crudo) if isinstance(crudo, str) and crudo else (crudo or [])
    except (ValueError, TypeError):
        segs = []
    return {**item, "segmentos": segs}


# --------------------------------------------------------------------------- #
# GET /api/video/formatos                                                      #
# --------------------------------------------------------------------------- #


async def formatos(request: Request) -> Response:
    """GET /api/video/formatos: presets de formato y que red usa cada uno.

    Devuelve `{formatos: [{preset, w, h, fps, safe_top, safe_bottom, redes: [...]}]}`. `redes`
    son los ids de red cuyo aspecto sugerido (via `VIDEO_SPECS`) mapea a ese preset, para que la
    UI sugiera el formato segun el destino.
    """
    # Mapa preset -> redes que lo usan (por el aspecto sugerido de cada red).
    from ..limites_plataforma import VIDEO_SPECS  # shell: catalogo de specs de video por red

    redes_por_preset: dict[str, list[str]] = {nombre: [] for nombre in video_shared.PRESETS_FORMATO}
    for red_id in VIDEO_SPECS:
        preset = video_shared.preset_para_red(red_id)
        nombre = str(preset.get("preset") or preset.get("aspecto") or video_shared.ASPECTO_DEFECTO)
        redes_por_preset.setdefault(nombre, []).append(red_id)

    out = []
    for nombre, datos in video_shared.PRESETS_FORMATO.items():
        out.append({"preset": nombre, **datos, "redes": redes_por_preset.get(nombre, [])})
    return JSONResponse({"formatos": out})


# --------------------------------------------------------------------------- #
# CRUD de composiciones                                                        #
# --------------------------------------------------------------------------- #


async def listar_composiciones(request: Request) -> Response:
    """GET /api/video/composiciones: composiciones (filtro `?marca=`). -> `{composiciones: [...]}`."""
    q = request.query_params
    marca = q.get("marca") or None
    if marca is not None and not marcas.es_marca(marca):
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    items = [
        _composicion_a_dict(item)
        for item in repos.listar_video_composiciones(
            marca=marca, publicacion_id=q.get("publicacion_id") or None
        )
    ]
    return JSONResponse({"composiciones": items})


async def crear_composicion(request: Request) -> Response:
    """POST /api/video/composiciones: crea una composicion. -> `{id}` | 400.

    Cuerpo: `marca` (obligatoria, del catalogo), `publicacion_id` (opcional, liga al tablero),
    `documento` (objeto de composicion, se valida con `keni_shared.video.validar_composicion`).
    """
    datos = await leer_json(request)

    marca, err = _validar_marca(datos.get("marca"))
    if err:
        return JSONResponse({"error": err}, status_code=400)

    documento = datos.get("documento")
    if not isinstance(documento, dict):
        return JSONResponse({"error": "Falta el documento de la composición."}, status_code=400)
    try:
        doc_norm = video_shared.validar_composicion({**documento, "marca": marca})
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    publicacion_id = datos.get("publicacion_id")
    publicacion_id = publicacion_id.strip() if isinstance(publicacion_id, str) else ""

    titulo = datos.get("titulo")
    titulo = titulo.strip() if isinstance(titulo, str) else ""

    estado, err = _validar_estado(datos.get("estado"), defecto="borrador")
    if err:
        return JSONResponse({"error": err}, status_code=400)

    comp = repos.crear_video_composicion(
        marca=marca,
        documento=json.dumps(doc_norm, ensure_ascii=False),
        publicacion_id=publicacion_id,
        titulo=titulo,
        estado=estado,
    )
    return JSONResponse({"id": comp["id"]})


async def obtener_composicion(request: Request) -> Response:
    """GET /api/video/composiciones/{id}: detalle de una composicion. -> `{composicion}` | 404."""
    comp = repos.obtener_video_composicion(request.path_params["composicion_id"])
    if comp is None:
        return JSONResponse({"error": "Esa composición no existe."}, status_code=404)
    return JSONResponse({"composicion": _composicion_a_dict(comp)})


async def actualizar_composicion(request: Request) -> Response:
    """PUT /api/video/composiciones/{id}: actualiza documento, titulo y/o estado. -> `{composicion}` | 400/404.

    Cuerpo: `documento` (opcional; si viene se valida con `keni_shared.video.validar_composicion`),
    `titulo` (opcional, str) y `estado` (opcional, ∈ {borrador, listo}). Todos son opcionales para
    poder renombrar o cambiar el estado de un borrador SIN reenviar el documento; pero el cuerpo
    debe traer al menos uno. La validacion del documento solo corre cuando el documento viene.
    """
    composicion_id = request.path_params["composicion_id"]
    comp = repos.obtener_video_composicion(composicion_id)
    if comp is None:
        return JSONResponse({"error": "Esa composición no existe."}, status_code=404)

    datos = await leer_json(request)
    campos: dict[str, object] = {}

    if "documento" in datos:
        documento = datos.get("documento")
        if not isinstance(documento, dict):
            return JSONResponse(
                {"error": "El documento de la composición debe ser un objeto."}, status_code=400
            )
        try:
            doc_norm = video_shared.validar_composicion({**documento, "marca": comp["marca"]})
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        campos["documento"] = json.dumps(doc_norm, ensure_ascii=False)

    if "titulo" in datos:
        titulo = datos.get("titulo")
        if not isinstance(titulo, str):
            return JSONResponse({"error": "El título debe ser texto."}, status_code=400)
        campos["titulo"] = titulo.strip()

    if "estado" in datos:
        estado, err = _validar_estado(datos.get("estado"), defecto=None)
        if err:
            return JSONResponse({"error": err}, status_code=400)
        campos["estado"] = estado

    if not campos:
        return JSONResponse({"error": "Nada que actualizar."}, status_code=400)

    actualizada = repos.actualizar_video_composicion(composicion_id, campos)
    if actualizada is None:
        return JSONResponse({"error": "Esa composición no existe."}, status_code=404)
    return JSONResponse({"composicion": _composicion_a_dict(actualizada)})


async def borrar_composicion(request: Request) -> Response:
    """DELETE /api/video/composiciones/{id}: borra la composicion y sus subtitulos. -> `{ok}` | 404."""
    composicion_id = request.path_params["composicion_id"]
    if not repos.borrar_video_composicion(composicion_id):
        return JSONResponse({"error": "Esa composición no existe."}, status_code=404)
    return JSONResponse({"ok": True})


# --------------------------------------------------------------------------- #
# Encolado de jobs de proceso (render / transcripcion)                          #
# --------------------------------------------------------------------------- #


async def render_composicion(request: Request) -> Response:
    """POST /api/video/composiciones/{id}/render: encola el render. -> `{gen_id}` | 404/429.

    Render local (ffmpeg) bajo demanda: sin kill-switch ni gateo por maquina. Encola
    `PROC_RENDER_VIDEO` con `params={"composicion_id": id}`.
    """
    composicion_id = request.path_params["composicion_id"]
    comp = repos.obtener_video_composicion(composicion_id)
    if comp is None:
        return JSONResponse({"error": "Esa composición no existe."}, status_code=404)

    try:
        gen = generaciones.encolar_job_proceso(
            kind=jobspec.PROC_RENDER_VIDEO,
            params={"composicion_id": composicion_id},
            marca=comp["marca"],
            etiqueta="Render de video",
        )
    except generaciones.ColaLlenaError:
        return JSONResponse(
            {"error": "La cola de generación está saturada; reintenta en un momento."},
            status_code=429,
        )
    return JSONResponse({"gen_id": gen["id"]})


async def transcribir_composicion(request: Request) -> Response:
    """POST /api/video/composiciones/{id}/transcribir: encola la transcripcion ASR.

    Cuerpo: `media_id` (clip del que sacar el audio, obligatorio), `idioma` (opcional, def
    es-MX). ASR local (faster-whisper) bajo demanda: sin kill-switch ni gateo por maquina. Si
    no hay fila `video_subtitulos` para la composicion, se CREA (estado 'pendiente') antes de
    encolar. -> `{gen_id, subtitulo_id}` | 400/404/429.
    """
    composicion_id = request.path_params["composicion_id"]
    comp = repos.obtener_video_composicion(composicion_id)
    if comp is None:
        return JSONResponse({"error": "Esa composición no existe."}, status_code=404)

    datos = await leer_json(request)
    media_id = datos.get("media_id")
    if not isinstance(media_id, str) or not media_id.strip():
        return JSONResponse({"error": "Falta el media a transcribir."}, status_code=400)
    media_id = media_id.strip()
    idioma = datos.get("idioma")
    idioma = idioma.strip() if isinstance(idioma, str) and idioma.strip() else "es-MX"

    # Reutiliza la fila de subtitulos de la composicion si existe; si no, la crea (pendiente).
    existentes = repos.listar_video_subtitulos(composicion_id=composicion_id)
    if existentes:
        subtitulo = existentes[0]
    else:
        subtitulo = repos.crear_video_subtitulo(
            composicion_id=composicion_id, idioma=idioma, estado="pendiente"
        )

    try:
        gen = generaciones.encolar_job_proceso(
            kind=jobspec.PROC_TRANSCRIBIR,
            params={
                "composicion_id": composicion_id,
                "subtitulo_id": subtitulo["id"],
                "media_id": media_id,
                "idioma": idioma,
            },
            marca=comp["marca"],
            etiqueta="Transcripción",
        )
    except generaciones.ColaLlenaError:
        return JSONResponse(
            {"error": "La cola de generación está saturada; reintenta en un momento."},
            status_code=429,
        )
    return JSONResponse({"gen_id": gen["id"], "subtitulo_id": subtitulo["id"]})


# --------------------------------------------------------------------------- #
# Subtitulos (lectura + correccion humana)                                      #
# --------------------------------------------------------------------------- #


async def listar_subtitulos(request: Request) -> Response:
    """GET /api/video/subtitulos?composicion_id=: la fila de subtitulos de una composicion.

    `composicion_id` es obligatorio. Devuelve `{subtitulo}` (None si no hay fila aun) con
    `segmentos` parseados, `ass` y `estado`. -> `{subtitulo}` | 400.
    """
    composicion_id = request.query_params.get("composicion_id")
    if not composicion_id:
        return JSONResponse({"error": "Falta la composición."}, status_code=400)
    filas = repos.listar_video_subtitulos(composicion_id=composicion_id)
    subtitulo = _subtitulo_a_dict(filas[0]) if filas else None
    return JSONResponse({"subtitulo": subtitulo})


async def actualizar_subtitulo(request: Request) -> Response:
    """PUT /api/video/subtitulos/{id}: edita el texto corregido por el humano. -> `{subtitulo}` | 400/404.

    Cuerpo: `segmentos` (opcional, JSON word-level corregido) y/o `estado` (opcional,
    p.ej. 'editado' / 'listo' tras la revision). Si cambian `segmentos`, REGENERA el `ass`
    reutilizando `keni_consola.motores.transcripcion.segmentos_a_ass` (import PEREZOSO: si el
    motor de ASR no expone ese helper, guarda los segmentos SIN ass, sin romper).
    """
    subtitulo_id = request.path_params["subtitulo_id"]
    sub = repos.obtener_video_subtitulo(subtitulo_id)
    if sub is None:
        return JSONResponse({"error": "Esos subtítulos no existen."}, status_code=404)

    datos = await leer_json(request)
    campos: dict[str, object] = {}

    if "segmentos" in datos:
        segmentos = datos.get("segmentos")
        if not isinstance(segmentos, list):
            return JSONResponse(
                {"error": "Los segmentos deben ser una lista."}, status_code=400
            )
        campos["segmentos"] = json.dumps(segmentos, ensure_ascii=False)
        # Regenerar el ASS desde los segmentos corregidos (best-effort, motor opcional).
        ass = _regenerar_ass(segmentos)
        if ass is not None:
            campos["ass"] = ass

    if "estado" in datos:
        estado = datos.get("estado")
        if estado not in db.ESTADOS_VIDEO_SUBTITULO:
            return JSONResponse({"error": "Estado de subtítulo no válido."}, status_code=400)
        campos["estado"] = estado

    if not campos:
        return JSONResponse({"error": "Nada que actualizar."}, status_code=400)

    actualizado = repos.actualizar_video_subtitulo(subtitulo_id, campos)
    if actualizado is None:
        return JSONResponse({"error": "Esos subtítulos no existen."}, status_code=404)
    return JSONResponse({"subtitulo": _subtitulo_a_dict(actualizado)})


def _regenerar_ass(segmentos: list) -> str | None:
    """Regenera el ASS desde segmentos word-level. None si el motor de ASR no esta disponible.

    Import PEREZOSO Y OPCIONAL: el motor de transcripcion (faster-whisper) puede no exponer aun
    `segmentos_a_ass` (lo rellena el agente B). Si falta, devolvemos None y el llamante guarda
    los segmentos SIN ass (la correccion humana del texto no se pierde).
    """
    try:
        from ..motores.transcripcion import segmentos_a_ass
    except (ImportError, AttributeError):
        return None
    try:
        return segmentos_a_ass(segmentos)
    except Exception:  # noqa: BLE001 -- regenerar el ass es best-effort; no debe tumbar el PUT
        _log.exception("No se pudo regenerar el ASS de los subtítulos.")
        return None


RUTAS = [
    Route("/api/video/formatos", formatos, methods=["GET"]),
    Route("/api/video/composiciones", listar_composiciones, methods=["GET"]),
    Route("/api/video/composiciones", crear_composicion, methods=["POST"]),
    Route("/api/video/composiciones/{composicion_id}", obtener_composicion, methods=["GET"]),
    Route("/api/video/composiciones/{composicion_id}", actualizar_composicion, methods=["PUT"]),
    Route("/api/video/composiciones/{composicion_id}", borrar_composicion, methods=["DELETE"]),
    Route("/api/video/composiciones/{composicion_id}/render", render_composicion, methods=["POST"]),
    Route(
        "/api/video/composiciones/{composicion_id}/transcribir",
        transcribir_composicion,
        methods=["POST"],
    ),
    Route("/api/video/subtitulos", listar_subtitulos, methods=["GET"]),
    Route("/api/video/subtitulos/{subtitulo_id}", actualizar_subtitulo, methods=["PUT"]),
]
