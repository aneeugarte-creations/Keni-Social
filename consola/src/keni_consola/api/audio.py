"""API HTTP del GESTOR DE AUDIO (audio→texto) — Estudio de Audio.

Superficie REST del gestor integral de transcripciones: subir un audio/vídeo, transcribirlo en
local con whisper.cpp (v3 turbo, timestamps) y trabajar el texto con agentes de Claude
(limpiar/resumir/aclarar/corregir). Capa fina entre el frontend y la base: NO transcribe ni corre
los agentes (eso lo ejecutan el motor `motores/audio` y el worker via la cola); solo CRUD de
`audio_transcripciones` y ENCOLADO de jobs.

QUE VIVE AQUI
=============
  - `GET    /api/audio/transcripciones?marca=&estado=`        lista (filtros combinables).
  - `POST   /api/audio/transcripciones`  (multipart)          sube + crea + encola el ASR.
  - `GET    /api/audio/transcripciones/{id}`                  detalle (404 si no existe).
  - `PUT    /api/audio/transcripciones/{id}`                  edita segmentos/texto/estado/resumen.
  - `DELETE /api/audio/transcripciones/{id}`                  borra la transcripción.
  - `POST   /api/audio/transcripciones/{id}/transcribir`      reintenta el ASR (re-encola).
  - `POST   /api/audio/transcripciones/{id}/agente`           lanza un agente de Claude (-> gen_id).

CONTRATO
========
  - El ASR se encola con `generaciones.encolar_job_proceso(kind=PROC_TRANSCRIBIR_AUDIO, ...)`:
    local, gratuito y BAJO DEMANDA (sin kill-switch ni gateo). El resultado lo escribe el motor en
    la fila; el frontend sondea la generación para ver el progreso/texto.
  - Los agentes (`/agente`) se lanzan con `dominio.prompts_lanzar.lanzar(prompt_id=prompt/audio/...,
    marca=..., bloque_contexto=<transcripción>)`: devuelven un `gen_id`; el frontend sondea la
    generación, ve el resultado y decide aceptar (PUT) o, en 'aclarar', responder y 'corregir'.
  - Multi-tenant por marca: la marca se valida contra el catálogo único (`consola.marcas`).

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
from ..dominio import jobspec, prompts_lanzar
from ..libprompts import PromptsError
from ..seguridad import autor_de_peticion

_log = logging.getLogger("keni_consola.audio")

# Agentes de Claude disponibles sobre una transcripción -> prompt de librería `prompt/audio/<op>`.
OPERACIONES_AGENTE = ("limpiar", "resumir", "aclarar", "corregir")


# --------------------------------------------------------------------------- #
# Helpers comunes                                                              #
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
    """Serializa una transcripción: `segmentos` como objeto, URL de media y nombre de marca."""
    media_id = item.get("media_id") or ""
    return {
        **item,
        "segmentos": _segmentos_de(item),
        "media_url": f"/api/media/{media_id}" if media_id else "",
        "marca_nombre": marcas.etiqueta_de(item["marca"]) if item.get("marca") else "",
    }


def _mmss(ms: object) -> str:
    """Formatea milisegundos como `mm:ss` para el bloque de contexto de los agentes."""
    try:
        total = max(0, int(ms)) // 1000
    except (TypeError, ValueError):
        total = 0
    return f"{total // 60:02d}:{total % 60:02d}"


def _bloque_transcripcion(item: dict) -> str:
    """Texto de la transcripción con timestamps por segmento, para que el agente los referencie."""
    segs = _segmentos_de(item)
    if segs:
        return "\n".join(f"[{_mmss(s.get('inicio_ms', 0))}] {s.get('texto', '')}".rstrip() for s in segs)
    return item.get("texto") or ""


# --------------------------------------------------------------------------- #
# GET /api/audio/transcripciones                                              #
# --------------------------------------------------------------------------- #


async def listar_transcripciones(request: Request) -> Response:
    """GET /api/audio/transcripciones?marca=&estado=: lista (filtros combinables, recientes 1º)."""
    marca = request.query_params.get("marca") or None
    if marca is not None and not marcas.es_marca(marca):
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    estado = request.query_params.get("estado") or None
    filas = repos.listar_audio_transcripciones(marca=marca, estado=estado)
    return JSONResponse({"transcripciones": [_transcripcion_a_dict(f) for f in filas]})


# --------------------------------------------------------------------------- #
# POST /api/audio/transcripciones  (multipart: sube + crea + encola ASR)      #
# --------------------------------------------------------------------------- #


async def crear_transcripcion(request: Request) -> Response:
    """POST /api/audio/transcripciones (multipart `archivo`, `marca`, opc. `idioma`/`nombre`).

    Sube el audio/vídeo (content-addressed bajo `audios/`), crea la fila (estado 'pendiente') y
    encola el ASR. -> `{transcripcion, gen_id}` | 400/429.
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

    try:
        media_id = await media.guardar_audio_subida(archivo)
    except media.MediaError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        return JSONResponse({"error": "No se pudo guardar el archivo."}, status_code=500)

    fila = repos.crear_audio_transcripcion(
        marca=marca, nombre=nombre, media_id=media_id, idioma=idioma, estado="pendiente"
    )
    gen = _encolar_asr(fila, idioma)
    if isinstance(gen, Response):
        return gen
    return JSONResponse(
        {"transcripcion": _transcripcion_a_dict(fila), "gen_id": gen["id"]}, status_code=201
    )


def _encolar_asr(fila: dict, idioma: str) -> dict | Response:
    """Encola el job de transcripción del motor de audio. Devuelve el registro o un 429."""
    try:
        return generaciones.encolar_job_proceso(
            kind=jobspec.PROC_TRANSCRIBIR_AUDIO,
            params={
                "transcripcion_id": fila["id"],
                "media_id": fila["media_id"],
                "idioma": idioma,
            },
            marca=fila["marca"],
            etiqueta="Transcripción de audio",
        )
    except generaciones.ColaLlenaError:
        return JSONResponse(
            {"error": "La cola de generación está saturada; reintenta en un momento."},
            status_code=429,
        )


# --------------------------------------------------------------------------- #
# GET / PUT / DELETE /api/audio/transcripciones/{id}                          #
# --------------------------------------------------------------------------- #


async def obtener_transcripcion(request: Request) -> Response:
    """GET /api/audio/transcripciones/{id}: detalle (404 si no existe)."""
    fila = repos.obtener_audio_transcripcion(request.path_params["transcripcion_id"])
    if fila is None:
        return JSONResponse({"error": "Esa transcripción no existe."}, status_code=404)
    return JSONResponse({"transcripcion": _transcripcion_a_dict(fila)})


async def actualizar_transcripcion(request: Request) -> Response:
    """PUT /api/audio/transcripciones/{id}: edita segmentos/texto/estado/resumen/nombre/idioma.

    La corrección humana y la aceptación del resultado de un agente entran por aquí. `segmentos`
    puede llegar como lista (se serializa a JSON). Estado típico tras editar: 'editado'.
    """
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
    for campo in ("texto", "resumen", "nombre", "idioma"):
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
    """DELETE /api/audio/transcripciones/{id}: borra la fila (204). El media (dedup) se conserva."""
    ok = repos.borrar_audio_transcripcion(request.path_params["transcripcion_id"])
    if not ok:
        return JSONResponse({"error": "Esa transcripción no existe."}, status_code=404)
    return Response(status_code=204)


# --------------------------------------------------------------------------- #
# POST /api/audio/transcripciones/{id}/transcribir  (reintento del ASR)       #
# --------------------------------------------------------------------------- #


async def retranscribir(request: Request) -> Response:
    """POST /api/audio/transcripciones/{id}/transcribir: re-encola el ASR. -> `{gen_id}` | 404/429."""
    transcripcion_id = request.path_params["transcripcion_id"]
    fila = repos.obtener_audio_transcripcion(transcripcion_id)
    if fila is None:
        return JSONResponse({"error": "Esa transcripción no existe."}, status_code=404)
    if not fila.get("media_id"):
        return JSONResponse({"error": "La transcripción no tiene un audio asociado."}, status_code=400)
    gen = _encolar_asr(fila, fila.get("idioma") or "es-MX")
    if isinstance(gen, Response):
        return gen
    return JSONResponse({"gen_id": gen["id"]})


# --------------------------------------------------------------------------- #
# POST /api/audio/transcripciones/{id}/agente  (agentes de Claude)            #
# --------------------------------------------------------------------------- #


async def lanzar_agente(request: Request) -> Response:
    """POST /api/audio/transcripciones/{id}/agente: lanza un agente sobre la transcripción.

    Cuerpo: `operacion` ∈ {limpiar, resumir, aclarar, corregir}; `respuestas` (opcional, lista de
    strings) para 'corregir' (respuestas del equipo a las dudas de 'aclarar'). Compone la
    transcripción (con timestamps) como contexto y lanza `prompt/audio/<operacion>`. -> `{gen_id}`.
    """
    transcripcion_id = request.path_params["transcripcion_id"]
    fila = repos.obtener_audio_transcripcion(transcripcion_id)
    if fila is None:
        return JSONResponse({"error": "Esa transcripción no existe."}, status_code=404)

    datos = await leer_json(request)
    operacion = datos.get("operacion")
    if operacion not in OPERACIONES_AGENTE:
        return JSONResponse(
            {"error": f"Operación no válida (usa: {', '.join(OPERACIONES_AGENTE)})."},
            status_code=400,
        )
    if not fila.get("marca"):
        return JSONResponse({"error": "Asigna una marca a la transcripción primero."}, status_code=400)

    bloque = _bloque_transcripcion(fila)
    if not bloque.strip():
        return JSONResponse({"error": "La transcripción aún no tiene texto."}, status_code=400)
    respuestas = datos.get("respuestas")
    if operacion == "corregir" and isinstance(respuestas, list) and respuestas:
        dudas = "\n".join(f"- {r}" for r in respuestas if isinstance(r, str) and r.strip())
        if dudas:
            bloque = f"{bloque}\n\n## Respuestas del equipo a las dudas\n{dudas}"

    try:
        gen = prompts_lanzar.lanzar(
            prompt_id=f"prompt/audio/{operacion}",
            marca=fila["marca"],
            bloque_contexto=bloque,
            autor=autor_de_peticion(request) or {},
        )
    except PromptsError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except generaciones.ColaLlenaError:
        return JSONResponse(
            {"error": "La cola de generación está saturada; reintenta en un momento."},
            status_code=429,
        )
    return JSONResponse({"gen_id": gen["id"], "operacion": operacion})


RUTAS = [
    Route("/api/audio/transcripciones", listar_transcripciones, methods=["GET"]),
    Route("/api/audio/transcripciones", crear_transcripcion, methods=["POST"]),
    Route("/api/audio/transcripciones/{transcripcion_id}", obtener_transcripcion, methods=["GET"]),
    Route("/api/audio/transcripciones/{transcripcion_id}", actualizar_transcripcion, methods=["PUT"]),
    Route("/api/audio/transcripciones/{transcripcion_id}", borrar_transcripcion, methods=["DELETE"]),
    Route(
        "/api/audio/transcripciones/{transcripcion_id}/transcribir",
        retranscribir,
        methods=["POST"],
    ),
    Route(
        "/api/audio/transcripciones/{transcripcion_id}/agente",
        lanzar_agente,
        methods=["POST"],
    ),
]
