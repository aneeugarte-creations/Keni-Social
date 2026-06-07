"""Motor de TRANSCRIPCION ASR para subtitulos quemados es-MX (Ola VIDEO) — BASE / stub.

DUEÑO: este modulo POSEE el ASR de subtitulos del motor de video. Un AGENTE posterior (B) lo
rellena; en la BASE es un STUB que marca la generacion en error con un mensaje claro (NO hace
trabajo real). La firma y el contrato de abajo son el CONTRATO con el resto del sistema.

NO CONFUNDIR con `keni_consola.transcripcion` (modulo de nivel raiz): aquel transcribe un clip
subido para alimentar el AUTO-COPY (whisper.cpp, flujo clip-a-copy). ESTE genera SUBTITULOS
word-level para QUEMARLOS en el video con faster-whisper. Son caminos distintos a proposito.

QUE DEBE HACER EL EJECUTOR REAL (a implementar)
================================================
`ejecutar_transcripcion(gen_id, spec)` recibe el `spec` PLANO del job de proceso (lo arma
`jobspec.construir_proceso(PROC_TRANSCRIBIR, params)` via `generaciones.encolar_job_proceso`):

    spec = {
      "version": 1,
      "kind": "transcribir",
      "subtitulo_id": "<id de video_subtitulos>",   # fila a rellenar (estado 'pendiente')
      "media_id": "videos/<sha>.mp4",               # de donde sacar el audio
      "idioma": "es-MX",                             # opcional (def es-MX)
      # ...
    }

Pasos esperados del ASR real (decision de arquitectura YA tomada — ver el doc):
  1. Bajar el media (`media.leer_objeto(media_id)`); extraer el audio con ffmpeg
     (`config.ffmpeg_bin`) a wav 16 kHz mono.
  2. Transcribir con faster-whisper (modelo `config.whisper_modelo`, def "medium"),
     WORD-LEVEL (timestamps por palabra para subtitulos karaoke). IMPORT PEREZOSO Y OPCIONAL:
     si la lib no esta instalada, DEGRADAR con un error claro en espanol (NO romper el import
     de este modulo). faster-whisper/torch NO van baked en la imagen (pesado); se instalan en
     el servidor (ver deploy/worker/Dockerfile).
  3. Escribir el resultado en `video_subtitulos`: `segmentos` (JSON word-level), `ass` (el ASS
     renderizado con el estilo de la pista de subtitulos), `estado='transcrito'`,
     `transcrito_en=ahora`. Usar `repos.actualizar_video_subtitulo(subtitulo_id, {...})`.
  4. Marcar la generacion `completado` con un resultado minimo (p. ej. `{"subtitulo_id": ...}`).

REPORTE A ACTIVIDAD IA: igual que el render (ver `motores/estudio_video`): usa
`generaciones.actualizar(...)` para progreso/estado/error. El worker libera el cupo y termina
el job; si el ejecutor revienta sin marcar terminal, el worker lo marca en error.

GATEO: el encolado solo ocurre si `config.transcripcion_activa()` (flag `KENI_TRANSCRIPCION`,
def OFF, gateado por maquina).
"""

from __future__ import annotations

import logging

from ... import generaciones

_log = logging.getLogger("keni_consola.motores.transcripcion")


def ejecutar_transcripcion(gen_id: str, spec: dict) -> None:
    """STUB de la BASE: marca la generacion en error (el motor de ASR aun no existe).

    Firma del CONTRATO (no cambiar): `ejecutar(gen_id: str, spec: dict) -> None`. El agente B
    reemplaza el cuerpo por el ASR faster-whisper real (ver el docstring del modulo). En la BASE
    NO hace trabajo: deja un error honesto para que Actividad IA lo muestre sin romper el worker.
    """
    _log.warning(
        "transcripcion.ejecutar_transcripcion: stub (gen %s); el motor de ASR no esta implementado",
        gen_id,
    )
    generaciones.actualizar(
        gen_id,
        {
            "estado": generaciones.ESTADO_ERROR,
            "error": "El motor de transcripcion de video aun no esta implementado.",
            "fecha_fin": generaciones.ahora_iso(),
        },
    )


__all__ = ["ejecutar_transcripcion"]
