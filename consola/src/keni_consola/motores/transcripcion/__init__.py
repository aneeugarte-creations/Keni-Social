"""Motor de TRANSCRIPCION ASR para subtitulos quemados es-MX (Ola VIDEO).

DUEÑO: este modulo POSEE el ASR de subtitulos del motor de video. Genera SUBTITULOS
word-level para QUEMARLOS en el video como ASS karaoke. El resultado SIEMPRE queda en estado
'transcrito' (borrador): el principio del producto es que la correccion ortografica humana pasa
ANTES de quemar (estado 'editado'/'listo' los pone la edicion humana, NO este motor).

El ASR lo provee el MOTOR COMPARTIDO `keni_consola.transcripcion` (faster-whisper + modelo
`v3 turbo`): el mismo camino que el flujo clip-a-copy y que el gestor de audio. Este modulo solo
PIDE los segmentos word-level (`transcribir_datos(..., word_level=True)`) y los convierte en ASS
karaoke; las funciones PURAS `segmentos_a_ass`/`ESTILO_ASS_DEFECTO` viven aqui.

CONTRATO (no cambiar la firma): `ejecutar_transcripcion(gen_id: str, spec: dict) -> None`.

    spec = {
      "version": 1,
      "kind": "transcribir",
      "subtitulo_id": "<id de video_subtitulos>",   # fila a rellenar (estado 'pendiente')
      "media_id": "videos/<sha>.mp4",               # de donde sacar el audio
      "idioma": "es-MX",                             # opcional (def es-MX)
    }

El ASR es LOCAL, gratuito y BAJO DEMANDA (lo dispara un humano, no un daemon, y no consume
tokens), asi que NO tiene kill-switch ni gateo por maquina: el worker ejecuta lo que se encolo.
La unica degradacion que queda es por DISPONIBILIDAD: si falta el motor (extra `asr`),
`transcribir_datos` lanza un error claro en espanol y se reporta.

Pasos:
  1. Bajar el media (`media.leer_objeto`).
  2. Transcribir con el motor compartido (faster-whisper, con timestamps), WORD-LEVEL para
     karaoke -> segmentos `[{inicio_ms, fin_ms, texto, palabras:[...]}]`.
  3. Escribir en `video_subtitulos`: `segmentos` (JSON word-level), `ass` (ASS karaoke),
     `estado='transcrito'`, `transcrito_en=ahora`. Via `repos.actualizar_video_subtitulo`.
  4. Marcar la generacion `completado` con un resultado minimo.

REPORTE A ACTIVIDAD IA: `generaciones.actualizar(...)` para fases/estado/error.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ... import generaciones, media, repos
from ... import transcripcion as asr

_log = logging.getLogger("keni_consola.motores.transcripcion")

# Idioma por defecto del piloto (es-MX); el motor compartido reduce al codigo base ("es").
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
# Funciones PURAS: segmentos -> ASS karaoke                                     #
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

    FUNCION PURA y testeable: dados los `segmentos` (forma canonica word-level del motor
    compartido) produce el texto ASS completo (cabecera `[Script Info]`, `[V4+ Styles]` con un estilo base legible
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
# Orquestador: transcribir (motor compartido) + ASS + persistir                #
# --------------------------------------------------------------------------- #


def ejecutar_transcripcion(gen_id: str, spec: dict) -> None:
    """Ejecutor del job de proceso `transcribir` (ver docstring del modulo).

    Firma del CONTRATO (no cambiar). Reporta progreso/estado/error a Actividad IA via
    `generaciones.actualizar`. Deja el subtitulo en estado 'transcrito' (borrador para revision
    humana de ortografia ANTES de quemar) y la generacion en 'completado'.
    """
    try:
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

        generaciones.actualizar(
            gen_id, {"estado": generaciones.ESTADO_EJECUTANDO, "fase": "extrayendo audio"}
        )

        # 1) Bajar el media a transcribir.
        datos = media.leer_objeto(media_id)
        if datos is None:
            _terminar_error(gen_id, f"No se encontro el media {media_id} en el almacen.")
            return

        # 2) Transcribir WORD-LEVEL con el motor compartido (faster-whisper + v3 turbo, con
        #    timestamps). `transcribir_datos` lanza `TranscripcionError` (es) si faltan deps.
        generaciones.actualizar(
            gen_id, {"estado": generaciones.ESTADO_EJECUTANDO, "fase": "transcribiendo"}
        )
        ext = Path(media_id).suffix.lstrip(".") or "mp4"
        try:
            resultado = asr.transcribir_datos(datos, ext=ext, idioma=idioma, word_level=True)
        except asr.TranscripcionError as e:
            _terminar_error(gen_id, str(e))
            return
        segmentos = resultado["segmentos"]

        # 3) Generar el ASS karaoke y persistir el borrador (estado 'transcrito').
        generaciones.actualizar(
            gen_id,
            {
                "estado": generaciones.ESTADO_EJECUTANDO,
                "fase": "generando subtitulos",
                "salida": resultado["texto"],
            },
        )
        ass = segmentos_a_ass(segmentos)
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
    "ejecutar_transcripcion",
    "segmentos_a_ass",
]
