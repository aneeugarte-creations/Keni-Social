"""Motor de RENDER de video server-side con FFmpeg (Ola VIDEO) — BASE / stub.

DUEÑO: este modulo POSEE el render. Un AGENTE posterior (A) lo rellena; en la BASE es un STUB
que marca la generacion en error con un mensaje claro (NO hace trabajo real). La firma y el
contrato de abajo son el CONTRATO con el resto del sistema y NO deben cambiar sin actualizar
el seam (`worker._procesar_job_proceso`) y `docs/maquina-contenido/G-video-engine.md`.

QUE DEBE HACER EL EJECUTOR REAL (a implementar)
================================================
`ejecutar_render(gen_id, spec)` recibe el `spec` PLANO del job de proceso (lo arma
`jobspec.construir_proceso(PROC_RENDER_VIDEO, params)` via `generaciones.encolar_job_proceso`):

    spec = {
      "version": 1,
      "kind": "render-video",
      "composicion_id": "<id de video_composiciones>",   # de donde leer el documento JSON
      # ...otros params que el API decida (p. ej. overrides de formato)
    }

Pasos esperados del render real (decision de arquitectura YA tomada — ver el doc):
  1. Cargar la composicion (`repos.obtener_video_composicion(composicion_id)`) y validar su
     `documento` con `keni_shared.video.validar_composicion`.
  2. Bajar los media base (clips) de S3 (`media.leer_objeto` / categoria `videos`).
  3. Renderizar la pista `overlay` (capas estilo `Documento` del Estudio de imagen) a PNG
     transparente con `dominio.estudio_imagen.renderizar_documento_bytes` (REUTILIZAR, no
     reinventar capas) y los subtitulos a ASS (de `video_subtitulos.ass`).
  4. Componer con FFmpeg (`config.ffmpeg_bin`): scale/crop/pad (reencuadre por preset),
     `overlay` (marcos / image-in-video / PNG del estudio), xstack/vstack (doble pista/PiP),
     `subtitles=...ass` (subtitulos quemados). Timeout = `config.video_render_timeout`.
  5. Guardar el mp4 de salida en media categoria `render` (content-addressed sha256, igual que
     `dominio.estudio_imagen` guarda el PNG) y marcar la generacion `completado` con
     `resultado = {"media_id": "render/<sha>.mp4", "url": "/api/media/render/<sha>.mp4"}`.

REPORTE A ACTIVIDAD IA
======================
Usa `generaciones.actualizar(gen_id, {...})` para progreso/estado/errores:
  - en marcha:   `{"estado": ESTADO_EJECUTANDO, "fase": "...", "salida": "..."}` (opcional).
  - exito:       `{"estado": ESTADO_COMPLETADO, "resultado": {...}, "fecha_fin": ahora_iso()}`.
  - error:       `{"estado": ESTADO_ERROR, "error": "<es>", "fecha_fin": ahora_iso()}`.
El worker (`_procesar_job_proceso`) libera el cupo de admision y saca el job de la cola; si el
ejecutor revienta sin marcar terminal, el worker lo marca en error como red de seguridad.

GATEO: el encolado solo ocurre si `config.video_render_activo()` (flag `KENI_VIDEO_RENDER`,
def OFF, gateado por maquina). FFmpeg se instala en la imagen del `worker` (deploy).
"""

from __future__ import annotations

import logging

from ... import generaciones

_log = logging.getLogger("keni_consola.motores.estudio_video")


def ejecutar_render(gen_id: str, spec: dict) -> None:
    """STUB de la BASE: marca la generacion en error (el motor de render aun no existe).

    Firma del CONTRATO (no cambiar): `ejecutar(gen_id: str, spec: dict) -> None`. El agente A
    reemplaza el cuerpo por el render FFmpeg real (ver el docstring del modulo). En la BASE NO
    hace trabajo: deja un error honesto para que Actividad IA lo muestre sin romper el worker.
    """
    _log.warning("estudio_video.ejecutar_render: stub (gen %s); el motor de render no esta implementado", gen_id)
    generaciones.actualizar(
        gen_id,
        {
            "estado": generaciones.ESTADO_ERROR,
            "error": "El motor de render de video aun no esta implementado.",
            "fecha_fin": generaciones.ahora_iso(),
        },
    )


__all__ = ["ejecutar_render"]
