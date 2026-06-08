"""Config — accesores del dominio video. Parte de config.py (ver barrel)."""
from __future__ import annotations

from ._config_comun import (
    ENV_FFMPEG_BIN,
    ENV_VIDEO_RENDER_TIMEOUT,
    ENV_WHISPER_MODELO,
    FFMPEG_BIN_DEF,
    VIDEO_RENDER_TIMEOUT_DEF,
    WHISPER_MODELO_DEF,
    _crudo,
    _entero,
)

# --------------------------------------------------------------------------- #
# Accesores: motor de VIDEO (Ola VIDEO)                                         #
# --------------------------------------------------------------------------- #


def whisper_modelo() -> str:
    """Modelo de faster-whisper para el ASR (`KENI_WHISPER_MODELO`, def "medium")."""
    return _crudo(ENV_WHISPER_MODELO) or WHISPER_MODELO_DEF


def ffmpeg_bin() -> str:
    """Binario de ffmpeg a invocar (`KENI_FFMPEG_BIN`, def "ffmpeg" — se resuelve en PATH)."""
    return _crudo(ENV_FFMPEG_BIN) or FFMPEG_BIN_DEF


def video_render_timeout() -> int:
    """Wall-timeout (s) del render de un video (`KENI_VIDEO_RENDER_TIMEOUT`, def 1800, min 1)."""
    return _entero(ENV_VIDEO_RENDER_TIMEOUT, VIDEO_RENDER_TIMEOUT_DEF, minimo=1)
