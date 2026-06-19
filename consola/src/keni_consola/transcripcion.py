"""Transcripcion LOCAL de video/audio (whisper.cpp), capa transversal (SHELL).

La PUERTA CREATIVA (`api/publicaciones.py:aportar`, Fase 1 / Flujo A) acepta foto y nota; este
modulo le anade VIDEO/AUDIO: el equipo sube un clip, se transcribe EN LOCAL y el texto entra
como material base del auto-copy (igual que el flujo clip-a-copy de la skill). El texto sale
del audio del propio equipo, asi que se trata como contenido NO verificado (como cualquier
nota): nunca se publica solo; el auto-copy lo redacta y el borrador para en la cola de revision.

POR QUE LOCAL (igual que la skill `clip-a-copy`)
================================================
La transcripcion NO sale de la maquina: usa `ffmpeg` (extrae/normaliza el audio a wav 16 kHz
mono) + `whisper-cli` (whisper.cpp) con un modelo `.bin` LOCAL. Mismo camino y mismas rutas de
modelo que `keni_metricas.doctor` (env `KENI_WHISPER_MODEL` > rutas habituales) y que el
`transcribir.sh` de la skill. v1 = solo lectura del audio; no toca la red.

DEGRADA CON HONESTIDAD
======================
Si faltan `whisper-cli`/`ffmpeg` o el modelo (perfil hosted donde no estan instalados), NO se
rompe el alta: se lanza `TranscripcionError` con un mensaje claro en espanol y el handler decide
(hoy: rechaza el clip con 400 y un mensaje accionable; el equipo puede pegar la nota a mano).

SEGURIDAD / TESTS
=================
  - argv como LISTA (sin `shell=True`); el nombre del cliente NUNCA llega al shell ni al disco
    (escribimos a un temporal con nombre generado por nosotros).
  - Limite de tamano (`LIMITE_CLIP`, 200 MB) antes de tocar disco.
  - Punto INYECTABLE `_TRANSCRIPTOR` (modulo-nivel): los tests lo parchean para NUNCA invocar
    whisper/ffmpeg reales. Es el unico acoplamiento con el binario.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

_log = logging.getLogger("keni_consola.transcripcion")


class TranscripcionError(RuntimeError):
    """Error de transcripcion con mensaje ya en espanol, apto para mostrar al usuario."""


# Mimes de video/audio aceptados -> extension canonica del temporal en disco. ffmpeg
# extrae el audio sea cual sea el contenedor; mapeamos los formatos habituales del equipo.
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

# Env var del modelo de whisper (misma que `keni_metricas.doctor` / `transcribir.sh`).
ENV_MODELO_WHISPER = "KENI_WHISPER_MODEL"

# Idioma por defecto de la transcripcion (el piloto es es-MX). Whisper autodetecta, pero
# fijarlo evita que un clip con poca habla salga rotulado como otro idioma.
_IDIOMA = "es"

# Timeout (segundos) de cada subproceso (ffmpeg / whisper) del flujo clip-a-copy (clips cortos
# de redes). El gestor de audio transcribe piezas mas largas y usa su propio margen (`_TIMEOUT_LARGO`).
_TIMEOUT = 600

# Timeout para audios/videos largos del gestor de transcripciones (hasta 30 min de habla).
_TIMEOUT_LARGO = 1800


def _codigo_idioma(idioma: str | None) -> str:
    """Codigo base que entiende whisper ('es-MX' -> 'es'). Cae a 'es' si viene vacio."""
    return (idioma or _IDIOMA).split("-", 1)[0].strip().lower() or _IDIOMA


def _rutas_modelo_whisper() -> list[Path]:
    """Rutas conocidas donde puede vivir el modelo de whisper (sin la env var).

    Mismo orden que `keni_metricas.doctor._rutas_modelo_whisper` (fuente de verdad del
    diagnostico); duplicado a proposito para no cruzar la frontera de paquetes (este modulo
    vive en la consola, no en keni-metricas).
    """
    home = Path.home()
    return [
        home / "models" / "ggml-large-v3-turbo.bin",
        home / ".cache" / "whisper" / "ggml-large-v3-turbo.bin",
    ]


def _resolver_modelo() -> Path | None:
    """Ruta al modelo `.bin` de whisper: `KENI_WHISPER_MODEL` > rutas habituales. None si no hay."""
    env = os.environ.get(ENV_MODELO_WHISPER)
    if env:
        p = Path(env).expanduser()
        return p if p.is_file() else None
    for cand in _rutas_modelo_whisper():
        if cand.is_file():
            return cand
    return None


def transcripcion_disponible() -> bool:
    """True si la maquina puede transcribir en local: `whisper-cli` + `ffmpeg` + modelo.

    Lo usa el handler para decidir si OFRECER el clip o degradar con un mensaje claro. No
    toca disco mas alla del `which` y el `is_file` del modelo.
    """
    return bool(
        shutil.which("whisper-cli")
        and shutil.which("ffmpeg")
        and _resolver_modelo() is not None
    )


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
# Transcripcion real (inyectable / mockeable)                                  #
# --------------------------------------------------------------------------- #


def _ejecutar(argv: list[str], *, etapa: str, timeout: int = _TIMEOUT) -> None:
    """Corre un subproceso (argv lista, sin shell) y lanza `TranscripcionError` si falla."""
    try:
        subprocess.run(  # noqa: S603 -- argv lista, sin shell; nombres generados por nosotros
            argv,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as e:
        raise TranscripcionError(
            "Falta una herramienta para transcribir en este equipo "
            "(instala whisper.cpp y ffmpeg)."
        ) from e
    except subprocess.TimeoutExpired as e:
        raise TranscripcionError(
            "La transcripción tardó demasiado y se canceló; sube un clip más corto."
        ) from e
    except subprocess.CalledProcessError as e:
        # No exponemos el stderr crudo al usuario, pero lo dejamos en el log para diagnostico.
        _log.warning("transcripcion: %s falló (rc=%s): %s", etapa, e.returncode, (e.stderr or "").strip()[:500])
        raise TranscripcionError(
            "No se pudo transcribir el clip (audio ilegible o formato no soportado)."
        ) from e


def _exigir_dependencias() -> Path:
    """Comprueba whisper-cli + ffmpeg + modelo; devuelve la ruta del modelo o lanza error claro."""
    modelo = _resolver_modelo()
    if modelo is None:
        raise TranscripcionError(
            "No hay un modelo de whisper en este equipo. Define KENI_WHISPER_MODEL "
            "o instala whisper.cpp con un modelo."
        )
    if not (shutil.which("whisper-cli") and shutil.which("ffmpeg")):
        raise TranscripcionError(
            "Falta whisper-cli o ffmpeg para transcribir en local "
            "(instálalos con: brew install whisper-cpp ffmpeg)."
        )
    return modelo


def _extraer_audio_wav(entrada: Path, wav: Path, *, timeout: int = _TIMEOUT) -> None:
    """Extrae/normaliza la pista de voz a wav 16 kHz mono con ffmpeg (lo que whisper.cpp espera).

    `-vn` descarta el video (transcribimos solo la voz, da igual el contenedor) y `-f wav` fija el
    formato de salida explicitamente. Sin shell (argv lista; rutas generadas por nosotros).
    """
    _ejecutar(
        [
            "ffmpeg", "-nostdin", "-y",
            "-i", str(entrada),
            "-vn",
            "-ac", "1",
            "-ar", "16000",
            "-f", "wav",
            str(wav),
        ],
        etapa="ffmpeg",
        timeout=timeout,
    )


def _transcribir_whisper(datos: bytes, *, ext: str) -> str:
    """Transcribe los bytes de un clip en LOCAL: ffmpeg (-> wav 16 kHz mono) + whisper-cli.

    Mismo camino que la skill `clip-a-copy` / `transcribir.sh`. Trabaja en un directorio
    temporal que se borra al salir; el nombre lo generamos nosotros (uuid), nunca el del
    cliente. Devuelve el texto transcrito (vacio si el clip no tenia habla).
    """
    modelo = _exigir_dependencias()
    with tempfile.TemporaryDirectory(prefix="keni-transcripcion-") as tmp:
        base = Path(tmp) / uuid.uuid4().hex
        entrada = base.with_suffix(f".{ext}")
        wav = base.with_suffix(".wav")
        entrada.write_bytes(datos)

        _extraer_audio_wav(entrada, wav)
        # whisper-cli: transcribe el wav a un .txt (`-otxt -of <base>` -> <base>.txt).
        _ejecutar(
            [
                "whisper-cli",
                "-m", str(modelo),
                "-f", str(wav),
                "-l", _IDIOMA,
                "-otxt",
                "-of", str(base),
            ],
            etapa="whisper-cli",
        )
        salida = base.with_suffix(".txt")
        try:
            texto = salida.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            raise TranscripcionError("No se pudo leer la transcripción generada.") from e
    return texto.strip()


# --------------------------------------------------------------------------- #
# Transcripcion con TIMESTAMPS (gestor de audio + subtitulos de video)          #
# --------------------------------------------------------------------------- #
#
# whisper.cpp emite JSON (`-ojf`, output-json-full) con offsets en milisegundos por SEGMENTO y,
# dentro, los `tokens` (subpalabras) con sus propios offsets. De ahi sacamos la forma canonica de
# segmentos que edita el frontend y de la que el motor de video arma el ASS karaoke:
#
#     [{"inicio_ms", "fin_ms", "texto", "palabras": [{"inicio_ms", "fin_ms", "texto"}, ...]}, ...]


def _ms(valor: Any) -> int:
    """Normaliza un offset de whisper.cpp (ya en ms) a entero no negativo."""
    try:
        return max(0, int(valor))
    except (TypeError, ValueError):
        return 0


def _palabras_de_tokens(tokens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Agrupa los tokens (subpalabras) de un segmento en PALABRAS con sus tiempos.

    whisper.cpp parte cada palabra en uno o mas tokens; una palabra nueva empieza cuando el texto
    del token trae un espacio inicial. Se descartan los tokens especiales (texto vacio o `[...]`,
    p. ej. marcas internas del modelo) para que no ensucien el karaoke.
    """
    palabras: list[dict[str, Any]] = []
    for tok in tokens:
        crudo = tok.get("text")
        if not isinstance(crudo, str):
            continue
        if not crudo.strip() or (crudo.strip().startswith("[") and crudo.strip().endswith("]")):
            continue
        off = tok.get("offsets") or {}
        ini, fin = _ms(off.get("from")), _ms(off.get("to"))
        nueva_palabra = crudo[:1].isspace() or not palabras
        limpio = crudo.strip()
        if nueva_palabra:
            palabras.append({"inicio_ms": ini, "fin_ms": max(ini, fin), "texto": limpio})
        else:
            p = palabras[-1]
            p["texto"] += limpio
            p["fin_ms"] = max(p["fin_ms"], fin)
    return palabras


def parsear_whispercpp(data: dict[str, Any], *, word_level: bool = False) -> list[dict[str, Any]]:
    """Mapea el JSON de whisper.cpp (`-ojf`) a la forma canonica de segmentos. FUNCION PURA.

    Lee `transcription[]` (cada item: `offsets.{from,to}` en ms, `text`, y `tokens[]` si es full).
    Con `word_level` arma tambien las `palabras` (para el karaoke del motor de video). Descarta los
    segmentos sin texto ni palabras. Tolera claves ausentes (degrada a lista vacia / segmento sin
    palabras) en vez de romper.
    """
    segmentos: list[dict[str, Any]] = []
    for seg in data.get("transcription") or []:
        if not isinstance(seg, dict):
            continue
        off = seg.get("offsets") or {}
        ini, fin = _ms(off.get("from")), _ms(off.get("to"))
        texto = (seg.get("text") or "").strip()
        palabras = _palabras_de_tokens(seg.get("tokens") or []) if word_level else []
        if not texto and not palabras:
            continue
        if not texto and palabras:
            texto = " ".join(p["texto"] for p in palabras)
        segmentos.append(
            {"inicio_ms": ini, "fin_ms": max(ini, fin), "texto": texto, "palabras": palabras}
        )
    return segmentos


def _transcribir_whisper_json(
    datos: bytes, *, ext: str, idioma: str = _IDIOMA, word_level: bool = False
) -> dict[str, Any]:
    """Transcribe bytes de audio/video a segmentos CON TIMESTAMPS: ffmpeg + whisper-cli `-ojf`.

    Mismo motor whisper.cpp + modelo `v3 turbo` que el flujo clip-a-copy, pero pidiendo JSON con
    offsets en milisegundos. Devuelve `{"texto": <texto plano>, "segmentos": [...]}`. Trabaja en un
    temporal con nombres generados por nosotros (uuid), nunca el del cliente.
    """
    modelo = _exigir_dependencias()
    with tempfile.TemporaryDirectory(prefix="keni-transcripcion-") as tmp:
        base = Path(tmp) / uuid.uuid4().hex
        entrada = base.with_suffix(f".{ext}")
        wav = base.with_suffix(".wav")
        entrada.write_bytes(datos)

        _extraer_audio_wav(entrada, wav, timeout=_TIMEOUT_LARGO)
        # whisper-cli: JSON full (`-ojf -of <base>` -> <base>.json) con offsets en ms y tokens.
        _ejecutar(
            [
                "whisper-cli",
                "-m", str(modelo),
                "-f", str(wav),
                "-l", _codigo_idioma(idioma),
                "-ojf",
                "-of", str(base),
            ],
            etapa="whisper-cli",
            timeout=_TIMEOUT_LARGO,
        )
        salida = base.with_suffix(".json")
        try:
            data = json.loads(salida.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError) as e:
            raise TranscripcionError("No se pudo leer la transcripción generada.") from e

    segmentos = parsear_whispercpp(data, word_level=word_level)
    texto = " ".join(s["texto"] for s in segmentos).strip()
    return {"texto": texto, "segmentos": segmentos}


# Punto INYECTABLE: lo unico que toca whisper/ffmpeg reales. Los tests lo parchean.
_TRANSCRIPTOR = _transcribir_whisper
# Punto INYECTABLE del camino con timestamps (gestor de audio + ASR de video). Los tests lo parchean.
_TRANSCRIPTOR_JSON = _transcribir_whisper_json


def transcribir_datos(
    datos: bytes, *, ext: str, idioma: str = _IDIOMA, word_level: bool = False
) -> dict[str, Any]:
    """Transcribe bytes de audio/video a `{"texto", "segmentos"}` con timestamps (motor compartido).

    Entrada del gestor de audio y del motor de subtitulos de video. Delega en `_TRANSCRIPTOR_JSON`
    (parcheable en tests; NUNCA invoca whisper real ahi). `word_level=True` ademas trocea cada
    segmento en palabras (para el karaoke del video).
    """
    return _TRANSCRIPTOR_JSON(datos, ext=ext, idioma=idioma, word_level=word_level)


async def transcribir_subida(archivo, *, content_type: str | None = None) -> str:  # noqa: ANN001
    """Lee un `UploadFile` de video/audio y devuelve su TRANSCRIPCION (texto) en local.

    - Acepta SOLO mimes/extensiones de video/audio (`ext_de_subida`); cualquier otra cosa ->
      `TranscripcionError`.
    - Lee en trozos MIDIENDO el tamano; si supera `LIMITE_CLIP`, aborta antes de transcribir.
    - Delega en `_TRANSCRIPTOR` (parcheable en tests; NUNCA invoca whisper real ahi).

    Devuelve el texto transcrito (puede ser "" si el clip no tenia habla). Lanza
    `TranscripcionError` (en espanol) ante formato no soportado, clip vacio o demasiado grande,
    o si la transcripcion local no esta disponible.
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

    return _TRANSCRIPTOR(b"".join(trozos), ext=ext)
