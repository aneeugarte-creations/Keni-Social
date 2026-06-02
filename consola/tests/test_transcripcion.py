"""Tests de la transcripción LOCAL de vídeo/audio (`keni_consola.transcripcion`).

NO invocan whisper-cli/ffmpeg reales: parchean `shutil.which`, el modelo y `subprocess.run`
(o el punto inyectable `_TRANSCRIPTOR`). Cubren: detección de formato, límite de tamaño,
degradación honesta cuando falta el toolchain, y el camino feliz (ffmpeg -> whisper -> texto).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from keni_consola import transcripcion


class _FakeUpload:
    """Mínimo `UploadFile` para los tests: nombre, content_type y `await read(n)` por trozos."""

    def __init__(self, datos: bytes, *, filename: str, content_type: str | None):
        self._datos = datos
        self._pos = 0
        self.filename = filename
        self.content_type = content_type

    async def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            trozo, self._pos = self._datos[self._pos :], len(self._datos)
            return trozo
        trozo = self._datos[self._pos : self._pos + n]
        self._pos += len(trozo)
        return trozo


def _correr(coro):
    return asyncio.run(coro)


# --- detección de formato ----------------------------------------------------


@pytest.mark.parametrize(
    "ct,nombre,esperado",
    [
        ("video/mp4", "x.mp4", "mp4"),
        ("audio/mpeg", "x.mp3", "mp3"),
        ("audio/mp4", "x.m4a", "m4a"),
        (None, "grabacion.MOV", "mov"),  # por nombre cuando no hay content-type
        ("video/mp4;codecs=avc1", "x", "mp4"),  # ignora parámetros del content-type
        ("text/plain", "notas.txt", None),  # no es vídeo/audio
        (None, "sin-extension", None),
    ],
)
def test_ext_de_subida(ct, nombre, esperado):
    assert transcripcion.ext_de_subida(ct, nombre) == esperado


# --- disponibilidad ----------------------------------------------------------


def test_disponible_true_con_todo(monkeypatch, tmp_path):
    modelo = tmp_path / "ggml.bin"
    modelo.write_bytes(b"x")
    monkeypatch.setenv(transcripcion.ENV_MODELO_WHISPER, str(modelo))
    monkeypatch.setattr(transcripcion.shutil, "which", lambda b: f"/usr/bin/{b}")
    assert transcripcion.transcripcion_disponible() is True


def test_disponible_false_sin_binarios(monkeypatch, tmp_path):
    modelo = tmp_path / "ggml.bin"
    modelo.write_bytes(b"x")
    monkeypatch.setenv(transcripcion.ENV_MODELO_WHISPER, str(modelo))
    monkeypatch.setattr(transcripcion.shutil, "which", lambda b: None)
    assert transcripcion.transcripcion_disponible() is False


def test_resolver_modelo_env_inexistente(monkeypatch):
    monkeypatch.setenv(transcripcion.ENV_MODELO_WHISPER, "/no/existe/ggml.bin")
    assert transcripcion._resolver_modelo() is None


# --- transcribir_subida (con _TRANSCRIPTOR mockeado) -------------------------


def test_transcribir_subida_formato_no_soportado():
    up = _FakeUpload(b"hola", filename="notas.txt", content_type="text/plain")
    with pytest.raises(transcripcion.TranscripcionError):
        _correr(transcripcion.transcribir_subida(up))


def test_transcribir_subida_vacio():
    up = _FakeUpload(b"", filename="x.mp4", content_type="video/mp4")
    with pytest.raises(transcripcion.TranscripcionError):
        _correr(transcripcion.transcribir_subida(up))


def test_transcribir_subida_demasiado_grande(monkeypatch):
    monkeypatch.setattr(transcripcion, "LIMITE_CLIP", 4)
    up = _FakeUpload(b"12345", filename="x.mp4", content_type="video/mp4")
    with pytest.raises(transcripcion.TranscripcionError):
        _correr(transcripcion.transcribir_subida(up))


def test_transcribir_subida_camino_feliz(monkeypatch):
    visto: dict = {}

    def fake(datos, *, ext):
        visto["datos"], visto["ext"] = datos, ext
        return "  texto transcrito  "

    monkeypatch.setattr(transcripcion, "_TRANSCRIPTOR", fake)
    up = _FakeUpload(b"clipbytes", filename="x.mp4", content_type="video/mp4")
    texto = _correr(transcripcion.transcribir_subida(up))
    assert texto == "  texto transcrito  "  # _TRANSCRIPTOR es el dueño del strip
    assert visto == {"datos": b"clipbytes", "ext": "mp4"}


# --- _transcribir_whisper (subprocess mockeado, sin tocar binarios reales) ---


def test_transcribir_whisper_invoca_ffmpeg_y_whisper(monkeypatch, tmp_path):
    modelo = tmp_path / "ggml.bin"
    modelo.write_bytes(b"x")
    monkeypatch.setenv(transcripcion.ENV_MODELO_WHISPER, str(modelo))
    monkeypatch.setattr(transcripcion.shutil, "which", lambda b: f"/usr/bin/{b}")

    llamadas: list[list[str]] = []

    def fake_run(argv, **kwargs):
        llamadas.append(argv)
        # whisper-cli escribe <base>.txt; lo simulamos a partir del `-of`.
        if argv[0] == "whisper-cli":
            of = argv[argv.index("-of") + 1]
            Path(of).with_suffix(".txt").write_text("hola mundo\n", encoding="utf-8")

        class _R:
            returncode = 0
            stdout = ""
            stderr = ""

        return _R()

    monkeypatch.setattr(transcripcion.subprocess, "run", fake_run)
    texto = transcripcion._transcribir_whisper(b"clip", ext="mp4")
    assert texto == "hola mundo"
    # Primero ffmpeg, luego whisper-cli.
    assert llamadas[0][0] == "ffmpeg"
    assert llamadas[1][0] == "whisper-cli"
    # whisper recibe el modelo resuelto y el idioma es-MX por defecto.
    assert str(modelo) in llamadas[1]
    assert "es" in llamadas[1]


def test_transcribir_whisper_sin_modelo(monkeypatch):
    monkeypatch.setattr(transcripcion, "_resolver_modelo", lambda: None)
    monkeypatch.setattr(transcripcion.shutil, "which", lambda b: f"/usr/bin/{b}")
    with pytest.raises(transcripcion.TranscripcionError):
        transcripcion._transcribir_whisper(b"clip", ext="mp4")


def test_transcribir_whisper_subproceso_falla(monkeypatch, tmp_path):
    import subprocess as sp

    modelo = tmp_path / "ggml.bin"
    modelo.write_bytes(b"x")
    monkeypatch.setenv(transcripcion.ENV_MODELO_WHISPER, str(modelo))
    monkeypatch.setattr(transcripcion.shutil, "which", lambda b: f"/usr/bin/{b}")

    def fake_run(argv, **kwargs):
        raise sp.CalledProcessError(1, argv, stderr="boom")

    monkeypatch.setattr(transcripcion.subprocess, "run", fake_run)
    with pytest.raises(transcripcion.TranscripcionError):
        transcripcion._transcribir_whisper(b"clip", ext="mp4")
