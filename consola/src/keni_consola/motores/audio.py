"""Motor de TRANSCRIPCION del gestor de AUDIO (audio→texto).

Ejecutor del job de proceso `transcribir-audio`: transcribe un audio/video subido con el MOTOR
COMPARTIDO `keni_consola.transcripcion` (faster-whisper + modelo `v3 turbo`, con timestamps) y
persiste el resultado en `audio_transcripciones`. Mismo camino, gratuito y BAJO DEMANDA que el ASR
de subtitulos de video; la unica degradacion es por DISPONIBILIDAD del motor (el extra `asr`), que
el motor compartido reporta con un error claro en espanol.

Sobre la transcripcion bruta, el equipo trabaja con AGENTES de Claude (limpiar/resumir/aclarar/
corregir) desde la API `api/audio.py` — eso NO vive aqui: este modulo solo produce el borrador con
timestamps (estado 'transcrito').

CONTRATO (no cambiar la firma): `ejecutar_transcripcion_audio(gen_id: str, spec: dict) -> None`.

    spec = {
      "version": 1,
      "kind": "transcribir-audio",
      "transcripcion_id": "<id de audio_transcripciones>",  # fila a rellenar (estado 'pendiente')
      "media_id": "audios/<sha>.<ext>",                     # de donde sacar el audio
      "idioma": "es-MX",                                    # opcional (def es-MX)
    }
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .. import generaciones, media, repos
from .. import transcripcion as asr

_log = logging.getLogger("keni_consola.motores.audio")

# Idioma por defecto del piloto (es-MX); el motor compartido reduce al codigo base ("es").
_IDIOMA_DEF = "es-MX"


def ejecutar_transcripcion_audio(gen_id: str, spec: dict) -> None:
    """Ejecutor del job de proceso `transcribir-audio` (ver docstring del modulo).

    Firma del CONTRATO (no cambiar). Reporta progreso/estado/error a Actividad IA via
    `generaciones.actualizar` y refleja el estado en la fila `audio_transcripciones`. Deja la
    transcripcion en estado 'transcrito' (borrador con timestamps para revision/agentes) y la
    generacion en 'completado'.
    """
    transcripcion_id = (spec.get("transcripcion_id") or "").strip()
    try:
        media_id = (spec.get("media_id") or "").strip()
        idioma = (spec.get("idioma") or _IDIOMA_DEF).strip() or _IDIOMA_DEF
        if not transcripcion_id:
            _terminar_error(gen_id, "", "Falta 'transcripcion_id' en el job de transcripcion.")
            return
        if not media_id:
            _terminar_error(
                gen_id, transcripcion_id, "Falta 'media_id' (audio a transcribir) en el job."
            )
            return
        if repos.obtener_audio_transcripcion(transcripcion_id) is None:
            _terminar_error(gen_id, "", f"No existe la transcripcion {transcripcion_id}.")
            return

        generaciones.actualizar(
            gen_id, {"estado": generaciones.ESTADO_EJECUTANDO, "fase": "extrayendo audio"}
        )
        repos.actualizar_audio_transcripcion(transcripcion_id, {"estado": "transcribiendo"})

        # 1) Bajar el media a transcribir.
        datos = media.leer_objeto(media_id)
        if datos is None:
            _terminar_error(
                gen_id, transcripcion_id, f"No se encontro el media {media_id} en el almacen."
            )
            return

        # 2) Transcribir con el motor compartido (faster-whisper + v3 turbo, con timestamps).
        generaciones.actualizar(
            gen_id, {"estado": generaciones.ESTADO_EJECUTANDO, "fase": "transcribiendo"}
        )
        ext = Path(media_id).suffix.lstrip(".") or "mp4"
        try:
            resultado = asr.transcribir_datos(datos, ext=ext, idioma=idioma, word_level=False)
        except asr.TranscripcionError as e:
            _terminar_error(gen_id, transcripcion_id, str(e))
            return

        segmentos = resultado["segmentos"]
        texto = resultado["texto"]
        duracion_ms = int(segmentos[-1]["fin_ms"]) if segmentos else 0

        # 3) Persistir el borrador con timestamps (estado 'transcrito').
        repos.actualizar_audio_transcripcion(
            transcripcion_id,
            {
                "estado": "transcrito",
                "segmentos": json.dumps(segmentos, ensure_ascii=False),
                "texto": texto,
                "duracion_ms": duracion_ms,
                "error": "",
            },
        )

        # 4) Artefactos: SRT (siempre) + texto plano (si se pidió), síncronos; y los tratamientos de
        #    Claude pedidos (limpio/resumen/preguntas/ideas), que se generan en 2º plano (un job por
        #    artefacto que el worker rellena). El SRT/texto no dependen de Claude.
        tratamientos = [t for t in (spec.get("tratamientos") or []) if isinstance(t, str)]
        generaciones.actualizar(
            gen_id, {"estado": generaciones.ESTADO_EJECUTANDO, "fase": "generando artefactos"}
        )
        _crear_artefactos(transcripcion_id, segmentos, texto, tratamientos)

        generaciones.actualizar(
            gen_id,
            {
                "estado": generaciones.ESTADO_COMPLETADO,
                "salida": texto,
                "resultado": {
                    "transcripcion_id": transcripcion_id,
                    "segmentos": len(segmentos),
                },
                "fecha_fin": generaciones.ahora_iso(),
            },
        )
    except Exception as e:  # noqa: BLE001 -- red de seguridad: nunca dejar el job sin terminal
        _log.exception("audio.ejecutar_transcripcion_audio: fallo inesperado (gen %s)", gen_id)
        _terminar_error(gen_id, transcripcion_id, f"Error inesperado al transcribir: {e}")


def _crear_artefactos(
    transcripcion_id: str, segmentos: list, texto: str, tratamientos: list[str]
) -> None:
    """Crea el SRT (siempre) y el texto plano (si se pidió) y lanza los tratamientos de Claude.

    El SRT y el texto son síncronos (no necesitan Claude). Cada tratamiento de Claude
    (limpio/resumen/preguntas/ideas) se lanza como su propia generación que el worker rellena; si
    uno falla al lanzarse (cola/presupuesto), su artefacto queda en 'error' y los demás siguen.
    """
    from ..dominio import audio_artefactos  # noqa: PLC0415 -- import perezoso (evita ciclo)

    srt = None
    try:
        srt = repos.crear_audio_artefacto(
            transcripcion_id=transcripcion_id, tipo="srt", titulo="Subtítulos (SRT)",
            contenido=asr.srt_de_segmentos(segmentos), formato="srt", estado="listo",
        )
        if "texto" in tratamientos:
            repos.crear_audio_artefacto(
                transcripcion_id=transcripcion_id, tipo="texto", titulo="Texto plano",
                contenido=texto, formato="txt", estado="listo",
            )
    except Exception:  # noqa: BLE001 -- un fallo creando SRT/texto no debe tumbar la transcripción
        _log.exception("audio: no se pudieron crear los artefactos base de %s", transcripcion_id)

    fila = repos.obtener_audio_transcripcion(transcripcion_id)
    if fila is None:
        return
    for tipo in tratamientos:
        if tipo not in audio_artefactos.TRATAMIENTOS:
            continue
        try:
            # Heredan del SRT (base canónica): mismo origen que al lanzarlos desde la UI.
            audio_artefactos.lanzar_tratamiento(fila, tipo, origen=srt)
        except Exception:  # noqa: BLE001 -- un tratamiento que no arranca no frena a los demás
            _log.exception("audio: no se pudo lanzar el tratamiento %s de %s", tipo, transcripcion_id)


def _terminar_error(gen_id: str, transcripcion_id: str, mensaje: str) -> None:
    """Marca la generacion (y, si se conoce, la fila) en error con un mensaje claro en espanol."""
    _log.warning("audio (gen %s): %s", gen_id, mensaje)
    if transcripcion_id:
        try:
            repos.actualizar_audio_transcripcion(
                transcripcion_id, {"estado": "error", "error": mensaje}
            )
        except Exception:  # noqa: BLE001 -- el error principal manda; no enmascarar con uno de BD
            _log.exception("audio: no se pudo marcar la transcripcion %s en error", transcripcion_id)
    generaciones.actualizar(
        gen_id,
        {
            "estado": generaciones.ESTADO_ERROR,
            "error": mensaje,
            "fecha_fin": generaciones.ahora_iso(),
        },
    )


__all__ = ["ejecutar_transcripcion_audio"]
