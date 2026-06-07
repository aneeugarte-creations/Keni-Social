"""Tests de la subida de VIDEO (`media.guardar_video_subida`). OFFLINE, backend DISCO.

Cubre: aceptacion de mimes de video (por content-type y por nombre), rechazo de mimes no-video,
limite de tamano (`KENI_VIDEO_MAX_MB`), video vacio, y dedup content-addressed (`videos/<sha256>`).
No toca Postgres: solo el almacen de media en disco (aislado en tmp).
"""

from __future__ import annotations

import asyncio

import pytest

from keni_consola import almacen_media, media


class _FakeUpload:
    """Minimo `UploadFile` para tests: nombre, content_type y `await read(n)` por trozos."""

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


@pytest.fixture
def disco(monkeypatch, tmp_path):
    """Aisla el dir de media en tmp y BORRA cualquier S3_* (=> backend disco)."""
    for var in ("S3_ENDPOINT", "S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_REGION", "S3_BUCKET"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("KENI_CONSOLA_MEDIA", str(tmp_path / "media"))
    almacen_media._resetear_cliente_s3()
    return tmp_path


def test_categoria_videos_en_almacen():
    """La categoria `videos` esta en el catalogo del almacen (subcarpeta valida)."""
    assert "videos" in almacen_media.CATEGORIAS


def test_subir_video_ok(disco):
    """Un mp4 valido se guarda en `videos/<sha256>.mp4` (nombre content-addressed)."""
    up = _FakeUpload(b"datos-de-video", filename="clip.mp4", content_type="video/mp4")
    clave = _correr(media.guardar_video_subida(up))
    assert clave.startswith("videos/")
    assert clave.endswith(".mp4")
    assert "clip.mp4" not in clave  # el nombre es un hash, no el del cliente


def test_subir_video_por_nombre_sin_content_type(disco):
    """Sin content-type fiable, la extension del nombre decide (mov -> .mov)."""
    up = _FakeUpload(b"clip", filename="grabacion.MOV", content_type=None)
    clave = _correr(media.guardar_video_subida(up))
    assert clave.endswith(".mov")


def test_subir_video_dedup(disco):
    """El mismo contenido subido dos veces guarda UN solo objeto (misma key)."""
    a = _FakeUpload(b"identico", filename="a.mp4", content_type="video/mp4")
    b = _FakeUpload(b"identico", filename="otro.webm", content_type="video/webm")
    clave_a = _correr(media.guardar_video_subida(a))
    clave_b = _correr(media.guardar_video_subida(b))
    # Mismo contenido -> mismo sha256; la extension depende del mime, asi que comparamos el hash.
    assert clave_a.rsplit(".", 1)[0] == clave_b.rsplit(".", 1)[0]


def test_subir_no_video_rechaza(disco):
    """Un mime de imagen/texto no se acepta como video -> MediaError."""
    up = _FakeUpload(b"hola", filename="nota.txt", content_type="text/plain")
    with pytest.raises(media.MediaError):
        _correr(media.guardar_video_subida(up))


def test_subir_video_vacio_rechaza(disco):
    up = _FakeUpload(b"", filename="vacio.mp4", content_type="video/mp4")
    with pytest.raises(media.MediaError):
        _correr(media.guardar_video_subida(up))


def test_subir_video_demasiado_grande(disco, monkeypatch):
    """Supera `KENI_VIDEO_MAX_MB` -> MediaError (limite configurable)."""
    monkeypatch.setenv("KENI_VIDEO_MAX_MB", "1")  # 1 MB
    grande = b"x" * (2 * 1024 * 1024)  # 2 MB
    up = _FakeUpload(grande, filename="grande.mp4", content_type="video/mp4")
    with pytest.raises(media.MediaError):
        _correr(media.guardar_video_subida(up))


def test_mime_de_video():
    """`mime_de` resuelve el content-type de un video por su extension."""
    assert media.mime_de("videos/abc.mp4") == "video/mp4"
    assert media.mime_de("videos/abc.webm") == "video/webm"
    assert media.mime_de("videos/abc.mov") == "video/quicktime"
