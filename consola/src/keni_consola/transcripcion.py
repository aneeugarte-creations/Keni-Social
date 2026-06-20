"""Transcripcion de audio/video (whisper, vía faster-whisper), capa transversal (SHELL).

MOTOR: `faster-whisper` (CTranslate2). ES whisper (mismos pesos OpenAI, modelo `large-v3-turbo`),
pero se instala como WHEEL precompilado (extra `asr`: `pip install 'keni-consola[asr]'`) — NO se
compila nada, a diferencia de whisper.cpp — y trae su propio decodificador de audio (av/ffmpeg
embebido en la rueda), así que tampoco necesita un `ffmpeg` del sistema.

ECONOMIA / "no rehagas lo que ya tienes"
========================================
  - El MODELO se descarga UNA vez a un cache PERSISTENTE (`KENI_WHISPER_DIR`, p. ej. `/data/models`
    en hosted) y se reutiliza siempre; faster-whisper comprueba el cache y no lo vuelve a bajar.
  - El modelo se carga UNA vez EN MEMORIA (singleton perezoso `_cargar_modelo`) y se reutiliza
    entre transcripciones del mismo proceso (no se relee por cada audio).

DEGRADA CON HONESTIDAD
======================
Si el extra `asr` no está instalado (p. ej. el back, que no transcribe), `transcripcion_disponible`
es False y los handlers degradan con un mensaje claro en español; el motor de transcripción del
gestor de audio/subtítulos corre en el servicio dedicado `transcriptor`, que SÍ lleva el extra.

SEGURIDAD / TESTS
=================
  - Los bytes subidos se escriben a un temporal con nombre GENERADO por nosotros (uuid), nunca el
    del cliente; el directorio temporal se borra al salir.
  - Limite de tamano (`LIMITE_CLIP`, 200 MB) antes de tocar disco.
  - Punto INYECTABLE `_TRANSCRIPTOR_JSON` (modulo-nivel): los tests lo parchean para NUNCA cargar
    el modelo real. Es el unico acoplamiento con faster-whisper.
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

_log = logging.getLogger("keni_consola.transcripcion")


class TranscripcionError(RuntimeError):
    """Error de transcripcion con mensaje ya en espanol, apto para mostrar al usuario."""


# Mimes de video/audio aceptados -> extension canonica del temporal en disco. faster-whisper
# decodifica el contenedor sea cual sea; mapeamos los formatos habituales del equipo.
_MIME_A_EXT: dict[str, str] = {
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "video/webm": "webm",
    "video/x-matroska": "mkv",
    "video/mpeg": "mpeg",
    "video/3gpp": "3gp",
    "audio/mpeg": "mp3",
    "audio/mp4": "m4a",
    "audio/aac": "aac",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/webm": "weba",
    "audio/ogg": "ogg",
    "audio/flac": "flac",
}

# Extensiones (sin punto) que reconocemos por el NOMBRE del cliente cuando no llega content-type.
_EXTS_VALIDAS: frozenset[str] = frozenset(
    {"mp4", "mov", "webm", "mkv", "mpeg", "mpg", "3gp", "m4v", "mp3", "m4a", "aac", "wav", "weba", "ogg", "oga", "flac"}
)

# Limite de tamano de un clip subido (bytes). Un clip de redes pesa decenas de MB; 200 MB
# da margen sin permitir subidas absurdas que llenarian el disco temporal.
LIMITE_CLIP = 200 * 1024 * 1024  # 200 MB

# Trozo de lectura al medir el tamano (sin cargar todo en memoria de golpe).
_TROZO = 1024 * 1024  # 1 MB

# Configuracion del motor (todo overridable por env; los defaults sirven en local y hosted):
#   - KENI_WHISPER_MODELO   tamano/repo del modelo faster-whisper (def "large-v3-turbo" = v3 turbo).
#   - KENI_WHISPER_DIR      cache PERSISTENTE donde se descarga el modelo (def: cache de faster-whisper).
#   - KENI_WHISPER_COMPUTE  precision de computo (def "int8": rapido y de baja memoria en CPU).
ENV_MODELO = "KENI_WHISPER_MODELO"
ENV_DIR = "KENI_WHISPER_DIR"
ENV_COMPUTE = "KENI_WHISPER_COMPUTE"
_MODELO_DEF = "large-v3-turbo"
_COMPUTE_DEF = "int8"

# Idioma por defecto de la transcripcion (el piloto es es-MX). Whisper autodetecta, pero
# fijarlo evita que un clip con poca habla salga rotulado como otro idioma.
_IDIOMA = "es"


def _codigo_idioma(idioma: str | None) -> str:
    """Codigo base que entiende whisper ('es-MX' -> 'es'). Cae a 'es' si viene vacio."""
    return (idioma or _IDIOMA).split("-", 1)[0].strip().lower() or _IDIOMA


def transcripcion_disponible() -> bool:
    """True si el motor de transcripcion (`faster-whisper`) esta instalado.

    Lo usa el handler para decidir si OFRECER el clip o degradar con un mensaje claro. El MODELO no
    hace falta tenerlo ya: se descarga al primer uso. No toca disco ni red aqui.
    """
    try:
        import faster_whisper  # noqa: F401, PLC0415
    except ImportError:
        return False
    return True


def ext_de_subida(content_type: str | None, nombre: str | None) -> str | None:
    """Extension canonica de un clip de video/audio (por content-type o nombre); None si no lo es.

    Primero el content-type (lo manda el navegador); si falta o no lo conocemos, cae al
    sufijo del nombre del cliente. Devuelve la extension SIN punto, o None si no es un
    formato de video/audio aceptado.
    """
    if content_type:
        base = content_type.split(";", 1)[0].strip().lower()
        ext = _MIME_A_EXT.get(base)
        if ext:
            return ext
    if nombre:
        suf = Path(nombre).suffix.lower().lstrip(".")
        if suf in _EXTS_VALIDAS:
            return suf
    return None


# --------------------------------------------------------------------------- #
# Motor faster-whisper: modelo cargado UNA vez (singleton perezoso)             #
# --------------------------------------------------------------------------- #

_modelo_cache: dict[str, Any] = {}
_modelo_lock = threading.Lock()


def _cargar_modelo() -> Any:
    """Carga (o reutiliza) el `WhisperModel`. Lo DESCARGA la 1ª vez al cache persistente.

    Singleton protegido por lock (el pool de transcripción tiene varios hilos): el modelo se carga
    una sola vez y se comparte. Lanza `TranscripcionError` (es) si falta el extra `asr` o si la
    carga/descarga falla.
    """
    m = _modelo_cache.get("m")
    if m is not None:
        return m
    with _modelo_lock:
        m = _modelo_cache.get("m")
        if m is not None:
            return m
        try:
            from faster_whisper import WhisperModel  # noqa: PLC0415
        except ImportError as e:
            raise TranscripcionError(
                "Falta el motor de transcripción en este servicio "
                "(instala el extra: pip install 'keni-consola[asr]')."
            ) from e
        modelo = os.environ.get(ENV_MODELO) or _MODELO_DEF
        compute = os.environ.get(ENV_COMPUTE) or _COMPUTE_DEF
        dir_cache = os.environ.get(ENV_DIR) or None
        # CTranslate2 no respeta el límite de cpus del cgroup (ve os.cpu_count del host): sin esto
        # lanzaría hilos para TODOS los cores del host y el cgroup lo estrangularía. `KENI_WHISPER_
        # CPU_THREADS` fija los hilos al cupo real del contenedor (0 = auto). Más hilos = más rápido.
        try:
            hilos = int(os.environ.get("KENI_WHISPER_CPU_THREADS", "0"))
        except (TypeError, ValueError):
            hilos = 0
        try:
            m = WhisperModel(
                modelo, device="cpu", compute_type=compute, download_root=dir_cache, cpu_threads=hilos
            )
        except Exception as e:  # noqa: BLE001 -- descarga/disco/modelo: mensaje claro al usuario
            _log.warning("transcripcion: no se pudo cargar el modelo whisper '%s': %s", modelo, e)
            raise TranscripcionError(
                "No se pudo cargar el modelo de whisper (descarga o disco)."
            ) from e
        _modelo_cache["m"] = m
        return m


def _campo(obj: Any, nombre: str) -> Any:
    """Lee un atributo (objeto faster-whisper) o una clave (dict de test). None si no esta."""
    if isinstance(obj, dict):
        return obj.get(nombre)
    return getattr(obj, nombre, None)


def _seg_ms(valor: Any) -> int:
    """Convierte un timestamp en SEGUNDOS (float de faster-whisper) a milisegundos enteros."""
    try:
        return max(0, round(float(valor) * 1000))
    except (TypeError, ValueError):
        return 0


def mapear_segmentos(segmentos_fw: Any, *, word_level: bool = False) -> list[dict[str, Any]]:
    """Mapea la salida de faster-whisper a la forma canonica de segmentos. FUNCION PURA.

    `segmentos_fw` es un iterable de `Segment` (atributos `start`, `end`, `text`, y `words` ->
    objetos con `start`, `end`, `word`). Con `word_level` arma tambien las `palabras` (para el
    karaoke del motor de video). Acepta objetos o dicts (facil de testear sin la libreria). Descarta
    los segmentos sin texto ni palabras; tiempos en milisegundos enteros.

        [{"inicio_ms", "fin_ms", "texto", "palabras": [{"inicio_ms", "fin_ms", "texto"}, ...]}, ...]
    """
    salida: list[dict[str, Any]] = []
    for seg in segmentos_fw:
        ini = _seg_ms(_campo(seg, "start"))
        fin = _seg_ms(_campo(seg, "end"))
        texto = (_campo(seg, "text") or "").strip()
        palabras: list[dict[str, Any]] = []
        if word_level:
            for w in _campo(seg, "words") or []:
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
            {"inicio_ms": ini, "fin_ms": max(ini, fin), "texto": texto, "palabras": palabras}
        )
    return salida


def _srt_tiempo(ms: Any) -> str:
    """Formatea milisegundos como tiempo SRT `HH:MM:SS,mmm`."""
    try:
        ms = max(0, int(ms))
    except (TypeError, ValueError):
        ms = 0
    h, resto = divmod(ms, 3_600_000)
    m, resto = divmod(resto, 60_000)
    s, mmm = divmod(resto, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{mmm:03d}"


def srt_de_segmentos(segmentos: list[dict[str, Any]]) -> str:
    """Construye un SRT (SubRip) desde los segmentos `[{inicio_ms,fin_ms,texto}]`. FUNCION PURA.

    Numera los bloques desde 1, descarta los segmentos sin texto, y usa el formato de tiempo SRT
    `HH:MM:SS,mmm --> HH:MM:SS,mmm`. Devuelve "" si no hay segmentos con texto.
    """
    bloques: list[str] = []
    n = 1
    for seg in segmentos:
        texto = (seg.get("texto") or "").strip()
        if not texto:
            continue
        ini = int(seg.get("inicio_ms", 0) or 0)
        fin = max(ini, int(seg.get("fin_ms", ini) or ini))
        bloques.append(f"{n}\n{_srt_tiempo(ini)} --> {_srt_tiempo(fin)}\n{texto}")
        n += 1
    return ("\n\n".join(bloques) + "\n") if bloques else ""


def _transcribir_faster(
    datos: bytes,
    *,
    ext: str,
    idioma: str = _IDIOMA,
    word_level: bool = False,
    progreso: Any = None,
) -> dict[str, Any]:
    """Transcribe bytes de audio/video a `{"texto", "segmentos"}` con faster-whisper.

    Escribe los bytes a un temporal (faster-whisper lo decodifica con su av embebido) y transcribe
    con el modelo cacheado. `word_level=True` ademas trocea cada segmento en palabras. `progreso`, si
    se pasa, es un callback `(segundos_hechos: float, segundos_total: float)` que se invoca por cada
    segmento conforme avanza (faster-whisper EMITE los segmentos en streaming): permite reportar el
    progreso REAL del motor. Un fallo del callback nunca interrumpe la transcripcion.
    """
    modelo = _cargar_modelo()
    with tempfile.TemporaryDirectory(prefix="keni-transcripcion-") as tmp:
        ruta = Path(tmp) / f"{uuid.uuid4().hex}.{ext}"
        ruta.write_bytes(datos)
        try:
            seg_iter, info = modelo.transcribe(
                str(ruta),
                language=_codigo_idioma(idioma),
                word_timestamps=word_level,
                vad_filter=True,
            )
            # `transcribe` devuelve un GENERADOR perezoso: la transcripcion REAL ocurre al iterarlo.
            # Lo recorremos aqui (dentro del temporal) reportando el avance por segmento.
            duracion = float(getattr(info, "duration", 0) or 0)
            crudos: list[Any] = []
            for seg in seg_iter:
                crudos.append(seg)
                if progreso is not None:
                    try:
                        progreso(float(getattr(seg, "end", 0) or 0), duracion)
                    except Exception:  # noqa: BLE001 -- el reporte nunca rompe la transcripcion
                        pass
            segmentos = mapear_segmentos(crudos, word_level=word_level)
        except TranscripcionError:
            raise
        except Exception as e:  # noqa: BLE001 -- audio ilegible/formato raro: mensaje claro
            _log.warning("transcripcion: faster-whisper fallo: %s", e)
            raise TranscripcionError(
                "No se pudo transcribir el audio (formato no soportado o archivo corrupto)."
            ) from e
    texto = " ".join(s["texto"] for s in segmentos).strip()
    return {"texto": texto, "segmentos": segmentos}


# Punto INYECTABLE: lo unico que carga/llama a faster-whisper real. Los tests lo parchean.
_TRANSCRIPTOR_JSON = _transcribir_faster


# --------------------------------------------------------------------------- #
# Transcripcion POR TRAMOS (resumible)                                          #
#                                                                               #
# Para audios largos, el gestor de audio decodifica UNA vez y transcribe en     #
# ventanas; persiste el avance tras cada tramo y puede REANUDAR desde el ultimo #
# (resiliencia a reinicios/deploys). Inyectables aparte (no cargan el modelo).  #
# --------------------------------------------------------------------------- #

TASA_MUESTREO = 16000  # faster-whisper trabaja a 16 kHz mono.


def _decodificar_audio_real(datos: bytes, ext: str) -> Any:
    """Decodifica los bytes a un array mono 16 kHz (numpy float32) con el `av` embebido."""
    try:
        try:
            from faster_whisper import decode_audio  # noqa: PLC0415
        except ImportError:
            from faster_whisper.audio import decode_audio  # noqa: PLC0415
    except ImportError as e:
        raise TranscripcionError(
            "Falta el motor de transcripción en este servicio "
            "(instala el extra: pip install 'keni-consola[asr]')."
        ) from e
    with tempfile.TemporaryDirectory(prefix="keni-transcripcion-") as tmp:
        ruta = Path(tmp) / f"{uuid.uuid4().hex}.{ext}"
        ruta.write_bytes(datos)
        try:
            return decode_audio(str(ruta), sampling_rate=TASA_MUESTREO)
        except Exception as e:  # noqa: BLE001 -- formato raro/archivo corrupto: mensaje claro
            _log.warning("transcripcion: no se pudo decodificar el audio: %s", e)
            raise TranscripcionError(
                "No se pudo decodificar el audio (formato no soportado o archivo corrupto)."
            ) from e


def _transcribir_fragmento_real(
    audio: Any, *, inicio_s: float, fin_s: float, idioma: str = _IDIOMA, word_level: bool = False
) -> list[dict[str, Any]]:
    """Transcribe la ventana `[inicio_s, fin_s)` del audio decodificado. Timestamps ABSOLUTOS."""
    modelo = _cargar_modelo()
    a = max(0, int(inicio_s * TASA_MUESTREO))
    b = int(fin_s * TASA_MUESTREO)
    try:
        seg_iter, _info = modelo.transcribe(
            audio[a:b],
            language=_codigo_idioma(idioma),
            word_timestamps=word_level,
            vad_filter=True,
        )
        segmentos = mapear_segmentos(seg_iter, word_level=word_level)
    except TranscripcionError:
        raise
    except Exception as e:  # noqa: BLE001 -- audio ilegible: mensaje claro
        _log.warning("transcripcion: faster-whisper fallo en el tramo: %s", e)
        raise TranscripcionError(
            "No se pudo transcribir el audio (formato no soportado o archivo corrupto)."
        ) from e
    return desplazar_segmentos(segmentos, int(round(inicio_s * 1000)))


def desplazar_segmentos(segmentos: list[dict[str, Any]], desplazamiento_ms: int) -> list[dict[str, Any]]:
    """Suma `desplazamiento_ms` a los timestamps de una lista de segmentos. FUNCION PURA."""
    for s in segmentos:
        s["inicio_ms"] = int(s.get("inicio_ms", 0)) + desplazamiento_ms
        s["fin_ms"] = int(s.get("fin_ms", 0)) + desplazamiento_ms
        for w in s.get("palabras") or []:
            w["inicio_ms"] = int(w.get("inicio_ms", 0)) + desplazamiento_ms
            w["fin_ms"] = int(w.get("fin_ms", 0)) + desplazamiento_ms
    return segmentos


# Inyectables del camino por tramos (los tests los parchean; NUNCA cargan el modelo real).
_DECODIFICAR_AUDIO = _decodificar_audio_real
_TRANSCRIPTOR_FRAGMENTO = _transcribir_fragmento_real


def decodificar_audio(datos: bytes, *, ext: str) -> Any:
    """Decodifica los bytes a un array de muestras 16 kHz (para transcribir por tramos)."""
    return _DECODIFICAR_AUDIO(datos, ext)


def duracion_audio(audio: Any) -> float:
    """Duracion en SEGUNDOS de un audio decodificado (numero de muestras / tasa)."""
    try:
        return len(audio) / TASA_MUESTREO
    except TypeError:
        return 0.0


def transcribir_fragmento(
    audio: Any, *, inicio_s: float, fin_s: float, idioma: str = _IDIOMA, word_level: bool = False
) -> list[dict[str, Any]]:
    """Transcribe la ventana `[inicio_s, fin_s)`; devuelve segmentos con timestamps ABSOLUTOS."""
    return _TRANSCRIPTOR_FRAGMENTO(
        audio, inicio_s=inicio_s, fin_s=fin_s, idioma=idioma, word_level=word_level
    )


def transcribir_datos(
    datos: bytes,
    *,
    ext: str,
    idioma: str = _IDIOMA,
    word_level: bool = False,
    progreso: Any = None,
) -> dict[str, Any]:
    """Transcribe bytes de audio/video a `{"texto", "segmentos"}` con timestamps (motor compartido).

    Entrada del gestor de audio y del motor de subtitulos de video. Delega en `_TRANSCRIPTOR_JSON`
    (parcheable en tests; NUNCA carga el modelo real ahi). `word_level=True` trocea en palabras.
    `progreso` (opcional) reporta el avance real por segmento; ver `_transcribir_faster`.
    """
    return _TRANSCRIPTOR_JSON(
        datos, ext=ext, idioma=idioma, word_level=word_level, progreso=progreso
    )


async def transcribir_subida(archivo, *, content_type: str | None = None) -> str:  # noqa: ANN001
    """Lee un `UploadFile` de video/audio y devuelve su TRANSCRIPCION (texto plano).

    - Acepta SOLO mimes/extensiones de video/audio (`ext_de_subida`); cualquier otra cosa ->
      `TranscripcionError`.
    - Lee en trozos MIDIENDO el tamano; si supera `LIMITE_CLIP`, aborta antes de transcribir.
    - Delega en `transcribir_datos` (motor compartido; parcheable en tests).

    Devuelve el texto transcrito (puede ser "" si el clip no tenia habla). Lanza `TranscripcionError`
    (en espanol) ante formato no soportado, clip vacio o demasiado grande, o si el motor falla.
    """
    ct = content_type if content_type is not None else getattr(archivo, "content_type", None)
    ext = ext_de_subida(ct, getattr(archivo, "filename", None))
    if ext is None:
        raise TranscripcionError(
            "Solo se aceptan clips de vídeo o audio (MP4, MOV, MP3, M4A, WAV…)."
        )

    trozos: list[bytes] = []
    total = 0
    try:
        while True:
            trozo = await archivo.read(_TROZO)
            if not trozo:
                break
            total += len(trozo)
            if total > LIMITE_CLIP:
                raise TranscripcionError(
                    "El clip es demasiado grande (máximo 200 MB); sube uno más corto."
                )
            trozos.append(trozo)
    except TranscripcionError:
        raise
    except Exception as e:  # noqa: BLE001 -- cualquier fallo de E/S: reporta en espanol
        raise TranscripcionError("No se pudo leer el clip subido.") from e
    if total == 0:
        raise TranscripcionError("El clip está vacío.")

    return transcribir_datos(b"".join(trozos), ext=ext)["texto"]
