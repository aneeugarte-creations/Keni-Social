"""API HTTP del GESTOR DE AUDIO (audio→texto) — Estudio de Audio.

Sube un audio/vídeo, lo transcribe (faster-whisper, v3 turbo, con timestamps) y produce ARTEFACTOS:
`srt` por defecto + los tratamientos elegidos (texto plano, y los de Claude: limpio/resumen/
preguntas/ideas). Capa fina entre el frontend y la base: NO transcribe ni corre los agentes (eso lo
hacen el servicio `transcriptor` y el worker via la cola); solo CRUD de `audio_transcripciones` /
`audio_artefactos` y ENCOLADO de jobs.

QUE VIVE AQUI
=============
  - `GET    /api/audio/transcripciones?marca=&estado=`              lista de audios.
  - `POST   /api/audio/transcripciones`  (multipart)               sube + crea + encola el ASR
                                                                    (con los `tratamientos` elegidos).
  - `GET    /api/audio/transcripciones/{id}`                        detalle del audio (base ASR).
  - `PUT    /api/audio/transcripciones/{id}`                        edita nombre/idioma/estado/segmentos/texto.
  - `DELETE /api/audio/transcripciones/{id}`                        borra el audio y sus artefactos.
  - `POST   /api/audio/transcripciones/{id}/transcribir`           reintenta el ASR.
  - `GET    /api/audio/transcripciones/{id}/artefactos`            lista de artefactos del audio.
  - `POST   /api/audio/transcripciones/{id}/artefacto`            crea un tratamiento de Claude (-> artefacto).
  - `GET    /api/audio/artefactos/{id}`                            un artefacto.
  - `PUT    /api/audio/artefactos/{id}`                            edita el contenido (no el SRT crudo).
  - `DELETE /api/audio/artefactos/{id}`                            borra un artefacto.
  - `POST   /api/audio/artefactos/{id}/corregir`                   aplica respuestas (sobre 'preguntas') -> 'corregido'.

SEGURIDAD: errores en español como JSON `{"error": ...}` sin tracebacks; SQL parametrizado en
`repos`/`db`. El NOMBRE del objeto de media lo genera el servidor (sha256), nunca el cliente.
"""

from __future__ import annotations

import json
import logging

from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import db, generaciones, marcas, media, repos
from .._http_json import leer_json
from ..dominio import audio_artefactos, jobspec

_log = logging.getLogger("keni_consola.audio")

# Tratamientos elegibles al subir (además del SRT, que va siempre). 'texto' lo genera el motor; el
# resto son de Claude (`audio_artefactos.TRATAMIENTOS`). 'corregido' NO se elige al subir (es un
# seguimiento de 'preguntas' con las respuestas del equipo).
TRATAMIENTOS_SUBIDA = ("texto", "limpio", "resumen", "preguntas", "ideas")


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #


def _validar_marca(marca: object) -> tuple[str | None, str | None]:
    """Valida la marca de una transcripción. Devuelve (marca_normalizada, error_o_None)."""
    if not isinstance(marca, str) or not marca.strip():
        return None, "Falta la marca."
    marca = marca.strip()
    if not marcas.es_marca(marca):
        return None, "Marca no permitida."
    return marca, None


def _segmentos_de(item: dict) -> list[dict]:
    """Parsea los `segmentos` (string JSON) de una fila a lista de objetos (vacía si no hay)."""
    crudo = item.get("segmentos") or ""
    try:
        segs = json.loads(crudo) if isinstance(crudo, str) and crudo else (crudo or [])
    except (ValueError, TypeError):
        segs = []
    return segs if isinstance(segs, list) else []


def _transcripcion_a_dict(item: dict) -> dict:
    """Serializa un audio: `segmentos`/`tratamientos` como listas, URL de media y nombre de marca."""
    media_id = item.get("media_id") or ""
    crudo = item.get("tratamientos") or ""
    tratamientos = [t for t in crudo.split(",") if t] if isinstance(crudo, str) else []
    return {
        **item,
        "segmentos": _segmentos_de(item),
        "tratamientos": tratamientos,
        "media_url": f"/api/media/{media_id}" if media_id else "",
        "marca_nombre": marcas.etiqueta_de(item["marca"]) if item.get("marca") else "",
    }


def _respuestas_de(art: dict) -> dict:
    """Parsea las `respuestas` (string JSON) del cajón de preguntas a objeto (vacío si no hay)."""
    crudo = art.get("respuestas") or ""
    try:
        obj = json.loads(crudo) if isinstance(crudo, str) and crudo else {}
    except (ValueError, TypeError):
        obj = {}
    return obj if isinstance(obj, dict) else {}


def _artefacto_a_dict(art: dict) -> dict:
    """Serializa un artefacto (`respuestas` como objeto). Reconcilia 'generando': si el job falló, 'error'.

    El post-procesado escribe el artefacto SOLO al completar el job; si el job de Claude FALLA, el
    artefacto se quedaría 'generando'. Al leerlo, si su generación ya está en error, lo reflejamos
    (y lo persistimos) para que el frontend deje de sondear y muestre el fallo.
    """
    if art.get("estado") == "generando" and art.get("gen_id"):
        g = generaciones.obtener(art["gen_id"])
        if g is not None and g.get("estado") == generaciones.ESTADO_ERROR:
            mensaje = g.get("error") or "El tratamiento falló."
            repos.actualizar_audio_artefacto(art["id"], {"estado": "error", "error": mensaje})
            art = {**art, "estado": "error", "error": mensaje}
    return {**art, "respuestas": _respuestas_de(art)}


# --------------------------------------------------------------------------- #
# Audios (transcripciones)                                                      #
# --------------------------------------------------------------------------- #


async def listar_transcripciones(request: Request) -> Response:
    """GET /api/audio/transcripciones?marca=&estado=: lista de audios (recientes primero)."""
    marca = request.query_params.get("marca") or None
    if marca is not None and not marcas.es_marca(marca):
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    estado = request.query_params.get("estado") or None
    filas = repos.listar_audio_transcripciones(marca=marca, estado=estado)
    return JSONResponse({"transcripciones": [_transcripcion_a_dict(f) for f in filas]})


async def crear_transcripcion(request: Request) -> Response:
    """POST /api/audio/transcripciones (multipart `archivo`, `marca`, opc. `idioma`/`nombre`/`tratamientos`).

    Sube el audio/vídeo, crea la fila (estado 'pendiente') y encola el ASR con los `tratamientos`
    elegidos (además del SRT, que el motor crea siempre). -> `{transcripcion, gen_id}` | 400/429.
    """
    try:
        form = await request.form()
    except Exception:  # noqa: BLE001 -- multipart malformado => mensaje claro, sin traza
        return JSONResponse({"error": "No se pudo leer el archivo subido."}, status_code=400)
    archivo = form.get("archivo")
    if not isinstance(archivo, UploadFile):
        return JSONResponse({"error": "No se recibió ningún archivo."}, status_code=400)
    marca, err = _validar_marca(form.get("marca"))
    if err:
        return JSONResponse({"error": err}, status_code=400)
    idioma = form.get("idioma")
    idioma = idioma.strip() if isinstance(idioma, str) and idioma.strip() else "es-MX"
    nombre = form.get("nombre")
    nombre = nombre.strip() if isinstance(nombre, str) and nombre.strip() else (
        getattr(archivo, "filename", None) or "audio"
    )
    # `tratamientos`: campos repetidos del multipart, filtrados a los válidos al subir.
    tratamientos = [t for t in form.getlist("tratamientos") if t in TRATAMIENTOS_SUBIDA]

    try:
        media_id = await media.guardar_audio_subida(archivo)
    except media.MediaError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        return JSONResponse({"error": "No se pudo guardar el archivo."}, status_code=500)

    fila = repos.crear_audio_transcripcion(
        marca=marca, nombre=nombre, media_id=media_id, idioma=idioma, estado="pendiente",
        tratamientos=",".join(tratamientos),
    )
    gen = _encolar_asr(fila, idioma, tratamientos)
    if isinstance(gen, Response):
        # No se pudo encolar (cola llena): NO dejar una fila huérfana en 'pendiente' sin job.
        repos.borrar_audio_transcripcion(fila["id"])
        return gen
    # Liga el job del motor (whisper) para seguir su progreso en vivo desde la página.
    fila = repos.actualizar_audio_transcripcion(fila["id"], {"gen_id": gen["id"]}) or fila
    return JSONResponse(
        {"transcripcion": _transcripcion_a_dict(fila), "gen_id": gen["id"]}, status_code=201
    )


def _encolar_asr(fila: dict, idioma: str, tratamientos: list[str]) -> dict | Response:
    """Encola el job de transcripción del motor de audio. Devuelve el registro o un 429."""
    try:
        return generaciones.encolar_job_proceso(
            kind=jobspec.PROC_TRANSCRIBIR_AUDIO,
            params={
                "transcripcion_id": fila["id"],
                "media_id": fila["media_id"],
                "idioma": idioma,
                "tratamientos": tratamientos,
            },
            marca=fila["marca"],
            etiqueta="Transcripción de audio",
        )
    except generaciones.ColaLlenaError:
        return JSONResponse(
            {"error": "La cola de generación está saturada; reintenta en un momento."},
            status_code=429,
        )


async def obtener_transcripcion(request: Request) -> Response:
    """GET /api/audio/transcripciones/{id}: detalle del audio (404 si no existe)."""
    fila = repos.obtener_audio_transcripcion(request.path_params["transcripcion_id"])
    if fila is None:
        return JSONResponse({"error": "Esa transcripción no existe."}, status_code=404)
    return JSONResponse({"transcripcion": _transcripcion_a_dict(fila)})


async def actualizar_transcripcion(request: Request) -> Response:
    """PUT /api/audio/transcripciones/{id}: edita nombre/idioma/estado y, si se quiere, segmentos/texto."""
    transcripcion_id = request.path_params["transcripcion_id"]
    if repos.obtener_audio_transcripcion(transcripcion_id) is None:
        return JSONResponse({"error": "Esa transcripción no existe."}, status_code=404)
    datos = await leer_json(request)

    cambios: dict[str, object] = {}
    if "segmentos" in datos:
        segs = datos["segmentos"]
        if not isinstance(segs, (list, str)):
            return JSONResponse({"error": "`segmentos` debe ser una lista."}, status_code=400)
        cambios["segmentos"] = segs if isinstance(segs, str) else json.dumps(segs, ensure_ascii=False)
    for campo in ("texto", "nombre", "idioma"):
        if campo in datos:
            if not isinstance(datos[campo], str):
                return JSONResponse({"error": f"`{campo}` debe ser texto."}, status_code=400)
            cambios[campo] = datos[campo]
    if "estado" in datos:
        if datos["estado"] not in db.ESTADOS_AUDIO_TRANSCRIPCION:
            return JSONResponse({"error": "Estado de transcripción no válido."}, status_code=400)
        cambios["estado"] = datos["estado"]
    if not cambios:
        return JSONResponse({"error": "Nada que actualizar."}, status_code=400)

    fila = repos.actualizar_audio_transcripcion(transcripcion_id, cambios)
    return JSONResponse({"transcripcion": _transcripcion_a_dict(fila)})


async def borrar_transcripcion(request: Request) -> Response:
    """DELETE /api/audio/transcripciones/{id}: borra el audio y sus artefactos (204)."""
    ok = repos.borrar_audio_transcripcion(request.path_params["transcripcion_id"])
    if not ok:
        return JSONResponse({"error": "Esa transcripción no existe."}, status_code=404)
    return Response(status_code=204)


async def retranscribir(request: Request) -> Response:
    """POST /api/audio/transcripciones/{id}/transcribir: re-encola el ASR. -> `{gen_id}` | 404/429."""
    transcripcion_id = request.path_params["transcripcion_id"]
    fila = repos.obtener_audio_transcripcion(transcripcion_id)
    if fila is None:
        return JSONResponse({"error": "Esa transcripción no existe."}, status_code=404)
    if not fila.get("media_id"):
        return JSONResponse({"error": "La transcripción no tiene un audio asociado."}, status_code=400)
    gen = _encolar_asr(fila, fila.get("idioma") or "es-MX", [])
    if isinstance(gen, Response):
        return gen
    repos.actualizar_audio_transcripcion(transcripcion_id, {"gen_id": gen["id"]})
    return JSONResponse({"gen_id": gen["id"]})


# --------------------------------------------------------------------------- #
# Artefactos                                                                    #
# --------------------------------------------------------------------------- #


def _asegurar_artefactos_base(fila: dict) -> None:
    """Crea el SRT (y el texto plano) desde los segmentos ya guardados.

    Para audios que se transcribieron ANTES del modelo de artefactos: tienen `segmentos`/`texto` en
    la fila pero ninguna fila en `audio_artefactos`, así que su lista saldría vacía. Reconstruimos
    aquí el SRT por defecto (y el texto plano) sin volver a transcribir ni llamar a Claude.
    """
    from .. import transcripcion as asr  # noqa: PLC0415 -- import perezoso (evita ciclo)

    segs = _segmentos_de(fila)
    try:
        if segs:
            repos.crear_audio_artefacto(
                transcripcion_id=fila["id"], tipo="srt", titulo="Subtítulos (SRT)",
                contenido=asr.srt_de_segmentos(segs), formato="srt", estado="listo",
            )
        if fila.get("texto"):
            repos.crear_audio_artefacto(
                transcripcion_id=fila["id"], tipo="texto", titulo="Texto plano",
                contenido=fila["texto"], formato="txt", estado="listo",
            )
    except Exception:  # noqa: BLE001 -- un fallo de backfill no debe tumbar el listado
        _log.exception("audio: no se pudo reconstruir el SRT de %s", fila["id"])


async def listar_artefactos(request: Request) -> Response:
    """GET /api/audio/transcripciones/{id}/artefactos: artefactos del audio (srt primero)."""
    transcripcion_id = request.path_params["transcripcion_id"]
    fila = repos.obtener_audio_transcripcion(transcripcion_id)
    if fila is None:
        return JSONResponse({"error": "Esa transcripción no existe."}, status_code=404)
    arts = repos.listar_audio_artefactos(transcripcion_id)
    if not arts and fila["estado"] in ("transcrito", "editado"):
        _asegurar_artefactos_base(fila)
        arts = repos.listar_audio_artefactos(transcripcion_id)
    return JSONResponse({"artefactos": [_artefacto_a_dict(a) for a in arts]})


async def crear_artefacto(request: Request) -> Response:
    """POST /api/audio/transcripciones/{id}/artefacto (`{tipo}`): lanza un tratamiento de Claude.

    `tipo` ∈ {limpio, resumen, preguntas, ideas}. Devuelve el artefacto (estado 'generando') que el
    worker rellenará. El SRT y el texto plano se crean al transcribir, no aquí.
    """
    transcripcion_id = request.path_params["transcripcion_id"]
    fila = repos.obtener_audio_transcripcion(transcripcion_id)
    if fila is None:
        return JSONResponse({"error": "Esa transcripción no existe."}, status_code=404)
    datos = await leer_json(request)
    tipo = datos.get("tipo")
    if tipo not in audio_artefactos.TRATAMIENTOS or tipo == "corregido":
        return JSONResponse(
            {"error": "Tipo de tratamiento no válido (limpio, resumen, preguntas o ideas)."},
            status_code=400,
        )
    # `origen_id`: artefacto del que parte (herencia). Si no se indica, parte del SRT (base
    # canónica = transcripción con timestamps). Debe pertenecer a este audio.
    origen = _resolver_origen(transcripcion_id, datos.get("origen_id"))
    if isinstance(origen, Response):
        return origen
    try:
        r = audio_artefactos.lanzar_tratamiento(fila, tipo, origen=origen)
    except audio_artefactos.AudioArtefactoError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"artefacto": _artefacto_a_dict(r["artefacto"])}, status_code=201)


def _resolver_origen(transcripcion_id: str, origen_id: object) -> dict | None | Response:
    """Artefacto fuente de un tratamiento. None/'' => el SRT del audio (base). 400 si no encaja."""
    arts = repos.listar_audio_artefactos(transcripcion_id)
    if isinstance(origen_id, str) and origen_id.strip():
        origen = next((a for a in arts if a["id"] == origen_id), None)
        if origen is None:
            return JSONResponse({"error": "El artefacto de origen no existe."}, status_code=400)
        return origen
    return next((a for a in arts if a["tipo"] == "srt"), None)


async def obtener_artefacto(request: Request) -> Response:
    """GET /api/audio/artefactos/{id}: un artefacto (404 si no existe)."""
    art = repos.obtener_audio_artefacto(request.path_params["artefacto_id"])
    if art is None:
        return JSONResponse({"error": "Ese artefacto no existe."}, status_code=404)
    return JSONResponse({"artefacto": _artefacto_a_dict(art)})


async def actualizar_artefacto(request: Request) -> Response:
    """PUT /api/audio/artefactos/{id}: edita `contenido`/`titulo`. El SRT crudo NO es editable."""
    art = repos.obtener_audio_artefacto(request.path_params["artefacto_id"])
    if art is None:
        return JSONResponse({"error": "Ese artefacto no existe."}, status_code=404)
    if art["tipo"] == "srt":
        return JSONResponse({"error": "El SRT no es editable."}, status_code=400)
    datos = await leer_json(request)
    cambios: dict[str, object] = {}
    for campo in ("contenido", "titulo"):
        if campo in datos:
            if not isinstance(datos[campo], str):
                return JSONResponse({"error": f"`{campo}` debe ser texto."}, status_code=400)
            cambios[campo] = datos[campo]
    if not cambios:
        return JSONResponse({"error": "Nada que actualizar."}, status_code=400)
    # Al editar a mano, el artefacto queda 'listo' (por si venía de un error o a medias).
    cambios["estado"] = "listo"
    actualizado = repos.actualizar_audio_artefacto(art["id"], cambios)
    return JSONResponse({"artefacto": _artefacto_a_dict(actualizado)})


async def borrar_artefacto(request: Request) -> Response:
    """DELETE /api/audio/artefactos/{id}: borra un artefacto (204)."""
    ok = repos.borrar_audio_artefacto(request.path_params["artefacto_id"])
    if not ok:
        return JSONResponse({"error": "Ese artefacto no existe."}, status_code=404)
    return Response(status_code=204)


async def guardar_respuestas(request: Request) -> Response:
    """PUT /api/audio/artefactos/{id}/respuestas (`{respuestas:{...}}`): guarda las respuestas del cajón.

    PERSISTENCIA REAL (servidor) de las respuestas del formulario de preguntas, por artefacto. El
    cuerpo es un objeto `{<índice>: "<respuesta>"}`; se guardan solo las no vacías.
    """
    art = repos.obtener_audio_artefacto(request.path_params["artefacto_id"])
    if art is None:
        return JSONResponse({"error": "Ese artefacto no existe."}, status_code=404)
    datos = await leer_json(request)
    respuestas = datos.get("respuestas")
    if not isinstance(respuestas, dict):
        return JSONResponse({"error": "`respuestas` debe ser un objeto."}, status_code=400)
    limpio = {
        str(k): v.strip()
        for k, v in respuestas.items()
        if isinstance(v, str) and v.strip()
    }
    actualizado = repos.actualizar_audio_artefacto(
        art["id"], {"respuestas": json.dumps(limpio, ensure_ascii=False) if limpio else ""}
    )
    return JSONResponse({"artefacto": _artefacto_a_dict(actualizado)})


async def corregir_artefacto(request: Request) -> Response:
    """POST /api/audio/artefactos/{id}/corregir (`{respuestas:[...]}`): aplica respuestas -> 'corregido'.

    `{id}` es un artefacto de 'preguntas'. Lanza un tratamiento 'corregido' sobre su transcripción con
    las respuestas del equipo. Devuelve el nuevo artefacto (estado 'generando').
    """
    art = repos.obtener_audio_artefacto(request.path_params["artefacto_id"])
    if art is None:
        return JSONResponse({"error": "Ese artefacto no existe."}, status_code=404)
    fila = repos.obtener_audio_transcripcion(art["transcripcion_id"])
    if fila is None:
        return JSONResponse({"error": "El audio de ese artefacto ya no existe."}, status_code=404)
    datos = await leer_json(request)
    respuestas = datos.get("respuestas")
    if not isinstance(respuestas, list) or not any(
        isinstance(r, str) and r.strip() for r in respuestas
    ):
        return JSONResponse({"error": "Faltan las respuestas a las dudas."}, status_code=400)
    try:
        # El 'corregido' hereda del propio artefacto de 'preguntas' (su herencia visible).
        r = audio_artefactos.lanzar_tratamiento(
            fila, "corregido", origen=art, respuestas=respuestas
        )
    except audio_artefactos.AudioArtefactoError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"artefacto": _artefacto_a_dict(r["artefacto"])}, status_code=201)


RUTAS = [
    Route("/api/audio/transcripciones", listar_transcripciones, methods=["GET"]),
    Route("/api/audio/transcripciones", crear_transcripcion, methods=["POST"]),
    Route("/api/audio/transcripciones/{transcripcion_id}", obtener_transcripcion, methods=["GET"]),
    Route("/api/audio/transcripciones/{transcripcion_id}", actualizar_transcripcion, methods=["PUT"]),
    Route("/api/audio/transcripciones/{transcripcion_id}", borrar_transcripcion, methods=["DELETE"]),
    Route(
        "/api/audio/transcripciones/{transcripcion_id}/transcribir", retranscribir, methods=["POST"]
    ),
    Route(
        "/api/audio/transcripciones/{transcripcion_id}/artefactos", listar_artefactos, methods=["GET"]
    ),
    Route(
        "/api/audio/transcripciones/{transcripcion_id}/artefacto", crear_artefacto, methods=["POST"]
    ),
    Route("/api/audio/artefactos/{artefacto_id}", obtener_artefacto, methods=["GET"]),
    Route("/api/audio/artefactos/{artefacto_id}", actualizar_artefacto, methods=["PUT"]),
    Route("/api/audio/artefactos/{artefacto_id}", borrar_artefacto, methods=["DELETE"]),
    Route("/api/audio/artefactos/{artefacto_id}/respuestas", guardar_respuestas, methods=["PUT"]),
    Route("/api/audio/artefactos/{artefacto_id}/corregir", corregir_artefacto, methods=["POST"]),
]
