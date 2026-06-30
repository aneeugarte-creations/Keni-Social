"""Motor de RENDER de video server-side con FFmpeg (Ola VIDEO).

DUEÑO de este modulo: el RENDER. `ejecutar_render(gen_id, spec)` es el EJECUTOR del job de
proceso `render-video` (lo despacha `worker._procesar_job_proceso`). La firma es el CONTRATO
con el seam y NO cambia sin actualizar `worker` + `docs/maquina-contenido/08-video-engine.md`.

El render (ffmpeg) es LOCAL, gratuito y BAJO DEMANDA (lo dispara un humano, no un daemon, y no
consume tokens), asi que NO tiene kill-switch ni gateo por maquina: el worker ejecuta lo que
se encolo.

QUE HACE
========
1. Carga la composicion (`repos.obtener_video_composicion`) y valida su `documento`
   (`keni_shared.video.validar_composicion`).
2. Baja los clips base/PiP de S3 (`media.leer_objeto`, categoria `videos`) a temporales.
3. Hornea la pista `overlay` (capas estilo Documento del Estudio de imagen) a un PNG
   transparente del tamano del formato con `estudio_imagen.renderizar_documento_bytes`
   (REUTILIZA el Estudio; no reinventa capas).
4. Materializa el ASS de subtitulos (de `video_subtitulos.ass`) si existe (si no hay ASS aun,
   OMITE subtitulos: no falla el render).
5. Construye el filtergraph (`filtros.construir_comando`) y corre ffmpeg SIN shell, con timeout
   `config.video_render_timeout()`, parseando `-progress pipe:1` para reportar avance.
6. Guarda el mp4 en media categoria `render` (content-addressed sha256) y marca la generacion
   `completado` con `resultado = {"media_id": "render/<sha>.mp4", "url": ".../render/<sha>.mp4"}`.

REPORTE A ACTIVIDAD IA: via `generaciones.actualizar(gen_id, {...})` (fase/salida en marcha,
resultado al exito, error en espanol al fallar). El worker libera el cupo y saca el job.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from keni_shared import video as video_shared

from ... import almacen_media, config, generaciones, media, repos
from ...dominio import estudio_imagen
from . import filtros

_log = logging.getLogger("keni_consola.motores.estudio_video")

# Categoria de almacen del mp4 de salida (los clips de entrada viven en `videos`).
_CAT_RENDER = "render"

# Regex para extraer `out_time_ms`/`out_time_us` del stream de progreso de ffmpeg.
_RE_PROGRESO = re.compile(r"^out_time_(?:ms|us)=(\d+)", re.MULTILINE)


class RenderError(RuntimeError):
    """Error de render con mensaje ya en espanol, listo para Actividad IA."""


def ejecutar_render(gen_id: str, spec: dict) -> None:
    """Ejecuta el render de una composicion de video. Firma del CONTRATO (no cambiar)."""
    try:
        _render(gen_id, spec)
    except RenderError as exc:
        _marcar_error(gen_id, str(exc))
    except Exception as exc:  # noqa: BLE001 - cualquier fallo se reporta, no crashea el worker
        _log.exception("estudio_video.ejecutar_render: fallo inesperado (gen %s)", gen_id)
        _marcar_error(gen_id, f"Error inesperado en el render: {exc}")


# --------------------------------------------------------------------------- #
# Cuerpo del render                                                            #
# --------------------------------------------------------------------------- #


def _render(gen_id: str, spec: dict) -> None:
    composicion_id = str(spec.get("composicion_id") or "").strip()
    if not composicion_id:
        raise RenderError("Falta 'composicion_id' en el job de render.")

    _fase(gen_id, "cargando", "Cargando la composicion.")
    comp = repos.obtener_video_composicion(composicion_id)
    if comp is None:
        raise RenderError(f"No existe la composicion '{composicion_id}'.")

    documento = _documento_validado(comp)
    pistas = documento.get("pistas") or []
    formato = documento.get("formato") or {}

    base_clip = filtros._clip_base(pistas)
    if not base_clip or not (base_clip.get("media_id") or "").strip():
        raise RenderError("La composicion no tiene un clip de video base con 'media_id'.")

    with tempfile.TemporaryDirectory(prefix="keni-render-") as tmp:
        carpeta = Path(tmp)

        # 2) Clip base.
        _fase(gen_id, "descargando", "Descargando el clip base.")
        base_path = _materializar_clip(base_clip["media_id"], carpeta, "base")

        # 3) Clip PiP (si hay segunda pista de video).
        pip_path: str | None = None
        pip_clip = filtros._pista_pip(pistas)
        if pip_clip and (pip_clip.get("media_id") or "").strip():
            _fase(gen_id, "descargando", "Descargando el clip PiP.")
            pip_path = _materializar_clip(pip_clip["media_id"], carpeta, "pip")

        # 4) Overlay -> PNG horneado por el Estudio de imagen.
        overlay_png: str | None = None
        pista_ovl = filtros.pista_overlay(pistas)
        if pista_ovl and (pista_ovl.get("capas") or []):
            _fase(gen_id, "componiendo overlay", "Horneando la pista de overlay a PNG.")
            overlay_png = _hornear_overlay(pista_ovl, formato, documento.get("marca", ""), carpeta)

        # 4b) Musica -> input de audio (si la pista `audio` trae un clip con media).
        musica_path: str | None = None
        clip_musica = filtros._clip_musica(pistas)
        if clip_musica and (clip_musica.get("media_id") or "").strip():
            _fase(gen_id, "descargando", "Descargando la musica.")
            musica_path = _materializar_clip(clip_musica["media_id"], carpeta, "musica")

        # 5) Subtitulos -> ASS a disco (si hay).
        ass_path: str | None = None
        pista_subs = filtros.pista_subtitulos(pistas)
        if pista_subs is not None:
            ass = _ass_de_pista(pista_subs, composicion_id)
            if ass:
                _fase(gen_id, "quemando subtitulos", "Preparando subtitulos quemados.")
                ass_path = str(carpeta / "subs.ass")
                Path(ass_path).write_text(ass, encoding="utf-8")
            else:
                _log.info("estudio_video: pista de subtitulos sin ASS aun; se omite (gen %s)", gen_id)

        # 6) Filtergraph + ffmpeg.
        salida_path = str(carpeta / "salida.mp4")
        argv = filtros.construir_comando(
            config.ffmpeg_bin(),
            documento,
            base_path=base_path,
            pip_path=pip_path,
            overlay_png=overlay_png,
            ass_path=ass_path,
            musica_path=musica_path,
            salida_path=salida_path,
        )
        _fase(gen_id, "codificando", "Codificando el video con ffmpeg.")
        _correr_ffmpeg(argv, timeout=config.video_render_timeout(), gen_id=gen_id, documento=documento)

        salida = Path(salida_path)
        if not salida.is_file() or salida.stat().st_size == 0:
            raise RenderError("ffmpeg termino sin producir un archivo de salida.")

        # 7) Persistir el mp4.
        _fase(gen_id, "guardando", "Guardando el video renderizado.")
        clave = _guardar_render(salida.read_bytes())

        # 8) Cablear el mp4 a la pieza ligada (si la hay): sin esto el render es un callejon sin
        #    salida (no fluye a feed/aprobacion/pieza). Va ANTES de marcar COMPLETADO porque
        #    `_adjuntar_a_pieza` reporta su propia fase (`_fase` -> estado EJECUTANDO); si corriera
        #    DESPUES, pisaria el estado terminal y la generacion quedaria colgada en "ejecutando".
        #    Es best-effort: un fallo aqui se loggea + se avisa en `salida`, pero NO degrada a
        #    error (el mp4 ya existe y queda en `resultado`).
        publicacion_id = str(comp.get("publicacion_id") or "").strip()
        if publicacion_id:
            _adjuntar_a_pieza(gen_id, publicacion_id, clave)

        # 9) Completar (estado terminal, EL ULTIMO paso para que ninguna fase posterior lo pise).
        generaciones.actualizar(
            gen_id,
            {
                "estado": generaciones.ESTADO_COMPLETADO,
                "fase": "completado",
                "resultado": {"media_id": clave, "url": f"/api/media/{clave}"},
                "fecha_fin": generaciones.ahora_iso(),
            },
        )


# --------------------------------------------------------------------------- #
# Cableado a la pieza                                                          #
# --------------------------------------------------------------------------- #


def _adjuntar_a_pieza(gen_id: str, publicacion_id: str, clave: str) -> None:
    """Adjunta el mp4 renderizado a las plataformas de video de la pieza ligada.

    Best-effort: el render YA esta completado. Si el adjuntado falla, se loggea y se refleja un
    aviso en la generacion (campo `salida`), pero NO se marca error (el mp4 vive en `resultado`).
    """
    _fase(gen_id, "adjuntando a la pieza", "Adjuntando el video renderizado a la pieza.")
    try:
        tocadas = repos.adjuntar_video_a_pieza(publicacion_id, clave)
    except Exception as exc:  # noqa: BLE001 - el render no debe degradarse por el cableado
        _log.exception(
            "estudio_video: fallo al adjuntar el render a la pieza %s (gen %s)",
            publicacion_id,
            gen_id,
        )
        generaciones.actualizar(
            gen_id,
            {
                "salida": (
                    "El video se renderizo pero no se pudo adjuntar a la pieza "
                    f"({exc}). Adjuntalo manualmente."
                )
            },
        )
        return
    if tocadas:
        _log.info(
            "estudio_video: video %s adjuntado a la pieza %s (%s redes)",
            clave,
            publicacion_id,
            len(tocadas),
        )
    else:
        _log.info(
            "estudio_video: la pieza %s no tiene plataformas de video; render no adjuntado",
            publicacion_id,
        )


# --------------------------------------------------------------------------- #
# Helpers de carga / horneado                                                  #
# --------------------------------------------------------------------------- #


def _documento_validado(comp: dict[str, Any]) -> dict[str, Any]:
    """Parsea y valida el `documento` JSON de la composicion (forma del sobre)."""
    crudo = comp.get("documento") or "{}"
    try:
        doc = json.loads(crudo) if isinstance(crudo, str) else crudo
    except (ValueError, TypeError) as exc:
        raise RenderError("El documento de la composicion no es JSON valido.") from exc
    try:
        return video_shared.validar_composicion(doc)
    except ValueError as exc:
        raise RenderError(f"Composicion invalida: {exc}") from exc


def _materializar_clip(media_id: str, carpeta: Path, nombre: str) -> str:
    """Baja un clip de media (categoria `videos`) a un temporal; devuelve su ruta."""
    datos = media.leer_objeto(media_id)
    if datos is None:
        raise RenderError(f"No se encontro el clip '{media_id}' en el almacen.")
    ext = Path(media_id).suffix.lower() or ".mp4"
    ruta = carpeta / f"{nombre}{ext}"
    ruta.write_bytes(datos)
    return str(ruta)


def _hornear_overlay(
    pista: dict[str, Any], formato: dict[str, Any], marca: str, carpeta: Path
) -> str:
    """Hornea la pista `overlay` (capas) a un PNG transparente del tamano del formato.

    REUTILIZA `estudio_imagen.renderizar_documento_bytes`: arma un Documento con las capas de la
    pista y el formato de la composicion, sin reimplementar el dibujo de capas.
    """
    documento_overlay = {
        "version": 1,
        "marca": marca or "",
        "formato": {"w": int(formato.get("w") or 0), "h": int(formato.get("h") or 0)},
        # Fondo transparente: el overlay solo aporta sus capas sobre el video.
        "fondo": {"tipo": "color", "color": "#00000000"},
        "capas": pista.get("capas") or [],
    }
    try:
        png = estudio_imagen.renderizar_documento_bytes(documento_overlay)
    except estudio_imagen.EstudioError as exc:
        raise RenderError(f"No se pudo hornear el overlay: {exc}") from exc
    ruta = carpeta / "overlay.png"
    ruta.write_bytes(png)
    return str(ruta)


def _ass_de_pista(pista: dict[str, Any], composicion_id: str) -> str:
    """ASS de la pista de subtitulos: por `subtitulo_id` o, en su defecto, por composicion.

    Si no hay un ASS listo todavia (el agente de ASR aun no transcribio), devuelve "" para que
    el render OMITA subtitulos en vez de fallar.
    """
    sub_id = str(pista.get("subtitulo_id") or "").strip()
    sub: dict[str, Any] | None = None
    if sub_id:
        sub = repos.obtener_video_subtitulo(sub_id)
    if sub is None:
        subs = repos.listar_video_subtitulos(composicion_id=composicion_id)
        sub = subs[0] if subs else None
    if sub is None:
        return ""
    return str(sub.get("ass") or "")


def _guardar_render(datos: bytes) -> str:
    """Guarda el mp4 en media categoria `render` content-addressed (sha256); devuelve la key."""
    digest = hashlib.sha256(datos).hexdigest()
    clave = almacen_media.componer_clave(_CAT_RENDER, f"{digest}.mp4")
    if not almacen_media.objeto_existe(clave):
        almacen_media.guardar_objeto(clave, datos, content_type="video/mp4")
    return clave


# --------------------------------------------------------------------------- #
# ffmpeg + progreso                                                            #
# --------------------------------------------------------------------------- #


def _correr_ffmpeg(
    argv: list[str], *, timeout: int, gen_id: str, documento: dict[str, Any]
) -> None:
    """Corre ffmpeg SIN shell, capturando stderr; parsea `-progress pipe:1` para el avance.

    Modulo-nivel para que los tests monkeypatcheen este punto (no ejecuten ffmpeg). Lanza
    `RenderError` (mensaje en espanol) ante timeout o codigo de salida != 0.
    """
    duracion_ms = int(documento.get("duracion_ms") or 0)
    try:
        proc = subprocess.run(  # noqa: S603 - argv lista, sin shell; binario de config, rutas del server
            argv, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise RenderError(f"El render supero el tiempo limite ({timeout}s).") from exc
    except FileNotFoundError as exc:
        raise RenderError("No se encontro el binario de ffmpeg.") from exc

    # Reporte de progreso: ultimo `out_time` visto sobre la duracion declarada (best-effort).
    _reportar_progreso(gen_id, proc.stdout or "", duracion_ms)

    if proc.returncode != 0:
        cola = _ultima_linea_error(proc.stderr or "")
        raise RenderError(f"ffmpeg fallo (codigo {proc.returncode}): {cola}")


def _reportar_progreso(gen_id: str, salida_progreso: str, duracion_ms: int) -> None:
    """Escribe el ultimo avance de ffmpeg a la generacion (porcentaje si hay duracion)."""
    if not salida_progreso:
        return
    coincidencias = _RE_PROGRESO.findall(salida_progreso)
    if not coincidencias:
        return
    # out_time_us son microsegundos; out_time_ms en ffmpeg recientes tambien viene en us.
    ultimo_us = int(coincidencias[-1])
    ultimo_ms = ultimo_us // 1000
    if duracion_ms > 0:
        pct = min(100, int(ultimo_ms * 100 / duracion_ms))
        _fase(gen_id, "codificando", f"Codificando: {pct}%")
    else:
        _fase(gen_id, "codificando", f"Codificando: {ultimo_ms} ms procesados")


def _ultima_linea_error(stderr: str) -> str:
    """Ultima linea no vacia de stderr de ffmpeg (el mensaje de error mas util)."""
    lineas = [ln.strip() for ln in stderr.splitlines() if ln.strip()]
    return lineas[-1] if lineas else "sin detalle"


# --------------------------------------------------------------------------- #
# Reporte a Actividad IA                                                       #
# --------------------------------------------------------------------------- #


def _fase(gen_id: str, fase: str, salida: str) -> None:
    """Reporta una fase en marcha a la generacion (Actividad IA)."""
    generaciones.actualizar(
        gen_id, {"estado": generaciones.ESTADO_EJECUTANDO, "fase": fase, "salida": salida}
    )


def _marcar_error(gen_id: str, mensaje: str) -> None:
    """Marca la generacion en error (estado terminal) con mensaje en espanol."""
    generaciones.actualizar(
        gen_id,
        {
            "estado": generaciones.ESTADO_ERROR,
            "error": mensaje,
            "fecha_fin": generaciones.ahora_iso(),
        },
    )


__all__ = ["RenderError", "ejecutar_render"]
