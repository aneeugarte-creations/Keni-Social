"""Motor de TRANSCRIPCION ASR para subtitulos quemados es-MX (Ola VIDEO).

DUEÑO: este modulo POSEE el ASR de subtitulos del motor de video. Genera SUBTITULOS
word-level (faster-whisper) para QUEMARLOS en el video como ASS karaoke. El resultado SIEMPRE
queda en estado 'transcrito' (borrador): el principio del producto es que la correccion
ortografica humana pasa ANTES de quemar (estado 'editado'/'listo' los pone la edicion humana,
NO este motor).

NO CONFUNDIR con `keni_consola.transcripcion` (modulo de nivel raiz): aquel transcribe un clip
subido para alimentar el AUTO-COPY (whisper.cpp, flujo clip-a-copy). ESTE genera SUBTITULOS
word-level con faster-whisper. Son caminos distintos a proposito.

CONTRATO (no cambiar la firma): `ejecutar_transcripcion(gen_id: str, spec: dict) -> None`.

    spec = {
      "version": 1,
      "kind": "transcribir",
      "subtitulo_id": "<id de video_subtitulos>",   # fila a rellenar (estado 'pendiente')
      "media_id": "videos/<sha>.mp4",               # de donde sacar el audio
      "idioma": "es-MX",                             # opcional (def es-MX)
    }

Pasos del ASR real:
  1. Gate de maquina (`config.transcripcion_activa`): si OFF -> error claro y termina.
  2. Bajar el media (`media.leer_objeto`); extraer el audio con ffmpeg (`config.ffmpeg_bin`,
     sin shell) a wav 16 kHz mono temporal.
  3. Transcribir con faster-whisper (modelo `config.whisper_modelo`, def "medium"), WORD-LEVEL
     (`word_timestamps=True`) para karaoke. IMPORT PEREZOSO Y OPCIONAL: si la lib no esta
     instalada, DEGRADAR con error claro en espanol (NO romper el import de este modulo).
     faster-whisper/torch NO van baked en la imagen (pesado); se instalan en el servidor.
  4. Escribir en `video_subtitulos`: `segmentos` (JSON word-level), `ass` (ASS karaoke),
     `estado='transcrito'`, `transcrito_en=ahora`. Via `repos.actualizar_video_subtitulo`.
  5. Marcar la generacion `completado` con un resultado minimo.

REPORTE A ACTIVIDAD IA: `generaciones.actualizar(...)` para fases/estado/error, emitiendo el
texto a medida que llegan segmentos (streaming) para que se vea token-a-token.
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ... import config, generaciones, media, repos

_log = logging.getLogger("keni_consola.motores.transcripcion")

# Idioma por defecto del piloto (es-MX). faster-whisper espera el codigo base ("es").
_IDIOMA_DEF = "es-MX"

# Estilo base legible es-MX del ASS (los nombres son los campos canonicos de un Style ASS v4+).
ESTILO_ASS_DEFECTO: dict[str, Any] = {
    "fuente": "Barlow",
    "tam": 64,
    # Colores en formato ASS &HBBGGRR& (no #RRGGBB). Texto blanco, resaltado karaoke amarillo,
    # contorno negro grueso para legibilidad sobre cualquier video.
    "primario": "&H00FFFFFF",     # texto aun no cantado (blanco)
    "secundario": "&H0000D7FF",   # texto cantado / resaltado karaoke (amarillo)
    "contorno": "&H00000000",     # borde (negro)
    "sombra": "&H80000000",       # sombra semitransparente
    "borde_px": 3,
    "sombra_px": 1,
    # Alineacion ASS numpad: 2 = inferior-centro.
    "alineacion": 2,
    "margen_v": 80,
    "res_x": 1080,
    "res_y": 1920,
}


# --------------------------------------------------------------------------- #
# (a) Funciones PURAS: mapeo faster-whisper -> segmentos                        #
# --------------------------------------------------------------------------- #


def _seg_ms(valor: Any) -> int:
    """Convierte un timestamp en SEGUNDOS (float de faster-whisper) a milisegundos enteros."""
    try:
        return max(0, round(float(valor) * 1000))
    except (TypeError, ValueError):
        return 0


def construir_segmentos(segmentos_fw: Any) -> list[dict[str, Any]]:
    """Mapea la salida de faster-whisper a nuestro JSON word-level.

    `segmentos_fw` es un iterable de objetos `Segment` (atributos `start`, `end`, `text`,
    `words` -> lista de objetos con `start`, `end`, `word`). Devolvemos la FORMA que edita el
    frontend:

        [{"inicio_ms", "fin_ms", "texto",
          "palabras": [{"inicio_ms", "fin_ms", "texto"}, ...]}, ...]

    Acepta tanto objetos (atributos) como dicts (claves), para que el mapeo sea facil de testear
    sin la libreria. Los tiempos se normalizan a milisegundos enteros.
    """
    salida: list[dict[str, Any]] = []
    for seg in segmentos_fw:
        ini = _campo(seg, "start")
        fin = _campo(seg, "end")
        texto = (_campo(seg, "text") or "").strip()
        palabras_fw = _campo(seg, "words") or []
        palabras: list[dict[str, Any]] = []
        for w in palabras_fw:
            w_texto = _campo(w, "word")
            if w_texto is None:
                w_texto = _campo(w, "text")
            w_texto = (w_texto or "").strip()
            if not w_texto:
                continue
            palabras.append(
                {
                    "inicio_ms": _seg_ms(_campo(w, "start")),
                    "fin_ms": _seg_ms(_campo(w, "end")),
                    "texto": w_texto,
                }
            )
        if not texto and not palabras:
            continue
        if not texto and palabras:
            texto = " ".join(p["texto"] for p in palabras)
        salida.append(
            {
                "inicio_ms": _seg_ms(ini),
                "fin_ms": _seg_ms(fin),
                "texto": texto,
                "palabras": palabras,
            }
        )
    return salida


def _campo(obj: Any, nombre: str) -> Any:
    """Lee un atributo (objeto faster-whisper) o una clave (dict de test). None si no esta."""
    if isinstance(obj, dict):
        return obj.get(nombre)
    return getattr(obj, nombre, None)


# --------------------------------------------------------------------------- #
# (b) Funciones PURAS: segmentos -> ASS karaoke                                 #
# --------------------------------------------------------------------------- #


def _ass_tiempo(ms: int) -> str:
    """Formatea milisegundos como tiempo ASS `H:MM:SS.cc` (centisegundos)."""
    ms = max(0, int(ms))
    cs = (ms % 1000) // 10
    s = ms // 1000
    h, resto = divmod(s, 3600)
    m, s = divmod(resto, 60)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def _linea_karaoke(palabras: list[dict[str, Any]], inicio_ms: int) -> str:
    """Texto de un Dialogue con tags `\\k` por palabra (duracion en CENTISEGUNDOS).

    El reloj del karaoke arranca en el `Start` del evento (`inicio_ms`). Para cada palabra
    emitimos `{\\kDUR}palabra ` donde DUR son los centisegundos que dura el resaltado. El hueco
    (silencio) entre el inicio del evento o la palabra previa y el comienzo de la palabra se
    representa con un `\\k` "vacio" sobre un espacio, para que el resaltado caiga en el momento
    exacto (sincronia karaoke real, no aproximada).
    """
    partes: list[str] = []
    reloj = inicio_ms
    for p in palabras:
        ini = max(reloj, int(p.get("inicio_ms", reloj)))
        fin = max(ini, int(p.get("fin_ms", ini)))
        hueco_cs = round((ini - reloj) / 10)
        if hueco_cs > 0:
            partes.append(f"{{\\k{hueco_cs}}} ")
        dur_cs = round((fin - ini) / 10)
        texto = _escapar_ass(str(p.get("texto", "")))
        partes.append(f"{{\\k{dur_cs}}}{texto} ")
        reloj = fin
    return "".join(partes).rstrip()


def _escapar_ass(texto: str) -> str:
    """Neutraliza caracteres que romperian una linea de Dialogue ASS (llaves, saltos)."""
    return (
        texto.replace("\\", "\\\\")
        .replace("{", "(")
        .replace("}", ")")
        .replace("\r\n", "\\N")
        .replace("\n", "\\N")
        .replace("\r", "\\N")
    )


def segmentos_a_ass(
    segmentos: list[dict[str, Any]], estilo: dict[str, Any] | None = None
) -> str:
    """Genera un ASS (Advanced SubStation Alpha) con karaoke word-level.

    FUNCION PURA y testeable: dados los `segmentos` (forma `construir_segmentos`) produce el
    texto ASS completo (cabecera `[Script Info]`, `[V4+ Styles]` con un estilo base legible
    es-MX, y `[Events]` con un `Dialogue` por segmento). Cada Dialogue lleva tags `\\k` por
    palabra (duracion en centisegundos) para el resaltado karaoke. Si un segmento no trae
    palabras, cae a una linea sin karaoke (texto plano), para no perder subtitulo.
    """
    e = {**ESTILO_ASS_DEFECTO, **(estilo or {})}
    fuente = e["fuente"]
    tam = int(e["tam"])
    cabecera = (
        "[Script Info]\n"
        "; Generado por keni-social (motor de transcripcion ASR)\n"
        "ScriptType: v4.00+\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n"
        f"PlayResX: {int(e['res_x'])}\n"
        f"PlayResY: {int(e['res_y'])}\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Keni,{fuente},{tam},{e['primario']},{e['secundario']},{e['contorno']},"
        f"{e['sombra']},-1,0,0,0,100,100,0,0,1,{int(e['borde_px'])},{int(e['sombra_px'])},"
        f"{int(e['alineacion'])},40,40,{int(e['margen_v'])},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lineas: list[str] = []
    for seg in segmentos:
        ini = int(seg.get("inicio_ms", 0))
        fin = max(ini, int(seg.get("fin_ms", ini)))
        palabras = seg.get("palabras") or []
        if palabras:
            texto = _linea_karaoke(palabras, ini)
        else:
            texto = _escapar_ass(str(seg.get("texto", "")))
        if not texto:
            continue
        lineas.append(
            f"Dialogue: 0,{_ass_tiempo(ini)},{_ass_tiempo(fin)},Keni,,0,0,0,,{texto}"
        )
    return cabecera + "\n".join(lineas) + ("\n" if lineas else "")


# --------------------------------------------------------------------------- #
# Orquestador: extraer audio + transcribir + persistir                         #
# --------------------------------------------------------------------------- #


def _extraer_audio_wav(origen: Path, destino: Path) -> None:
    """Extrae el audio del media a wav 16 kHz mono con ffmpeg (sin shell).

    16 kHz mono PCM es lo que faster-whisper espera; sin shell, argv lista (S603).
    """
    argv = [
        config.ffmpeg_bin(),
        "-nostdin",
        "-y",
        "-i", str(origen),
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-f", "wav",
        str(destino),
    ]
    try:
        subprocess.run(  # noqa: S603 -- argv lista, sin shell; rutas generadas por nosotros
            argv,
            check=True,
            capture_output=True,
            text=True,
            timeout=config.video_render_timeout(),
        )
    except FileNotFoundError as e:
        raise _ErrorTranscripcion(
            "No se encontro ffmpeg en este worker; instala ffmpeg para transcribir."
        ) from e
    except subprocess.TimeoutExpired as e:
        raise _ErrorTranscripcion(
            "La extraccion de audio tardo demasiado y se cancelo."
        ) from e
    except subprocess.CalledProcessError as e:
        _log.warning(
            "transcripcion: ffmpeg fallo (rc=%s): %s",
            e.returncode, (e.stderr or "").strip()[:500],
        )
        raise _ErrorTranscripcion(
            "No se pudo extraer el audio del video (formato no soportado o archivo corrupto)."
        ) from e


class _ErrorTranscripcion(Exception):
    """Error de proceso con mensaje en espanol apto para Actividad IA."""


def _codigo_idioma(idioma: str) -> str:
    """Codigo base que entiende faster-whisper ('es-MX' -> 'es')."""
    return (idioma or _IDIOMA_DEF).split("-", 1)[0].strip().lower() or "es"


def ejecutar_transcripcion(gen_id: str, spec: dict) -> None:
    """Ejecutor del job de proceso `transcribir` (ver docstring del modulo).

    Firma del CONTRATO (no cambiar). Reporta progreso/estado/error a Actividad IA via
    `generaciones.actualizar`. Deja el subtitulo en estado 'transcrito' (borrador para revision
    humana de ortografia ANTES de quemar) y la generacion en 'completado'.
    """
    try:
        # 1) Gate de maquina (kill-switch): si la transcripcion esta apagada, no hacemos trabajo.
        if not config.transcripcion_activa():
            _terminar_error(
                gen_id,
                "La maquina de transcripcion esta apagada (KENI_TRANSCRIPCION). "
                "Activala para generar subtitulos.",
            )
            return

        subtitulo_id = (spec.get("subtitulo_id") or "").strip()
        media_id = (spec.get("media_id") or "").strip()
        idioma = (spec.get("idioma") or _IDIOMA_DEF).strip() or _IDIOMA_DEF
        if not subtitulo_id:
            _terminar_error(gen_id, "Falta 'subtitulo_id' en el job de transcripcion.")
            return
        if not media_id:
            _terminar_error(gen_id, "Falta 'media_id' (video a transcribir) en el job.")
            return
        if repos.obtener_video_subtitulo(subtitulo_id) is None:
            _terminar_error(gen_id, f"No existe el subtitulo {subtitulo_id}.")
            return

        # 2) Import PEREZOSO y OPCIONAL de faster-whisper (no es dependencia dura del paquete).
        try:
            from faster_whisper import WhisperModel  # type: ignore  # noqa: PLC0415
        except ImportError:
            _terminar_error(
                gen_id,
                "faster-whisper no esta instalado en este worker; "
                "instala la dependencia ASR para transcribir.",
            )
            return

        generaciones.actualizar(
            gen_id, {"estado": generaciones.ESTADO_EJECUTANDO, "fase": "extrayendo audio"}
        )

        # 3) Bajar el media y extraer audio wav 16k mono a un temporal.
        datos = media.leer_objeto(media_id)
        if datos is None:
            _terminar_error(gen_id, f"No se encontro el media {media_id} en el almacen.")
            return

        with tempfile.TemporaryDirectory(prefix="keni-asr-") as tmp:
            tmp_dir = Path(tmp)
            ext = Path(media_id).suffix or ".mp4"
            origen = tmp_dir / f"origen{ext}"
            origen.write_bytes(datos)
            wav = tmp_dir / "audio.wav"
            _extraer_audio_wav(origen, wav)

            # 4) Transcribir word-level (streaming: faster-whisper devuelve un generador).
            generaciones.actualizar(
                gen_id,
                {"estado": generaciones.ESTADO_EJECUTANDO, "fase": "transcribiendo"},
            )
            modelo = WhisperModel(config.whisper_modelo())
            seg_iter, _info = modelo.transcribe(
                str(wav),
                language=_codigo_idioma(idioma),
                word_timestamps=True,
                vad_filter=True,
            )
            # Consumimos el generador emitiendo el texto a medida que llega (token-a-token).
            crudos: list[Any] = []
            acumulado: list[str] = []
            for seg in seg_iter:
                crudos.append(seg)
                txt = (_campo(seg, "text") or "").strip()
                if txt:
                    acumulado.append(txt)
                    generaciones.actualizar(
                        gen_id,
                        {
                            "estado": generaciones.ESTADO_EJECUTANDO,
                            "fase": "transcribiendo",
                            "salida": " ".join(acumulado),
                        },
                    )

        # 5) Mapear a nuestro JSON y generar el ASS karaoke.
        generaciones.actualizar(
            gen_id,
            {"estado": generaciones.ESTADO_EJECUTANDO, "fase": "generando subtitulos"},
        )
        segmentos = construir_segmentos(crudos)
        ass = segmentos_a_ass(segmentos)

        # 6) Persistir el borrador (estado 'transcrito' -> revision humana antes de quemar).
        repos.actualizar_video_subtitulo(
            subtitulo_id,
            {
                "segmentos": json.dumps(segmentos, ensure_ascii=False),
                "ass": ass,
                "estado": "transcrito",
                "transcrito_en": generaciones.ahora_iso(),
                "idioma": idioma,
            },
        )

        generaciones.actualizar(
            gen_id,
            {
                "estado": generaciones.ESTADO_COMPLETADO,
                "resultado": {
                    "subtitulo_id": subtitulo_id,
                    "segmentos": len(segmentos),
                },
                "fecha_fin": generaciones.ahora_iso(),
            },
        )
    except _ErrorTranscripcion as e:
        _terminar_error(gen_id, str(e))
    except Exception as e:  # noqa: BLE001 -- red de seguridad: nunca dejar el job sin terminal
        _log.exception("transcripcion.ejecutar_transcripcion: fallo inesperado (gen %s)", gen_id)
        _terminar_error(gen_id, f"Error inesperado al transcribir: {e}")


def _terminar_error(gen_id: str, mensaje: str) -> None:
    """Marca la generacion en error con un mensaje claro en espanol."""
    _log.warning("transcripcion (gen %s): %s", gen_id, mensaje)
    generaciones.actualizar(
        gen_id,
        {
            "estado": generaciones.ESTADO_ERROR,
            "error": mensaje,
            "fecha_fin": generaciones.ahora_iso(),
        },
    )


__all__ = [
    "ESTILO_ASS_DEFECTO",
    "construir_segmentos",
    "ejecutar_transcripcion",
    "segmentos_a_ass",
]
