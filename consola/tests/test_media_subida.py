"""Tests de la subida de IMAGEN (`media.guardar_subida`). OFFLINE, backend DISCO.

Cubre: una foto pequeña se guarda intacta; una subida pesada NO se rechaza, se recomprime a JPEG
bajo el objetivo; y solo el techo anti-OOM (`LIMITE_SUBIDA_IMAGEN`) rechaza un peso absurdo. No
toca Postgres: solo el almacen de media en disco (aislado en tmp).
"""

from __future__ import annotations

import asyncio
import io

import pytest
from PIL import Image

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


def _jpeg_grande(lado: int = 2400) -> bytes:
    """Un JPEG grande pero COMPRIMIBLE: degradado vertical suave (baja frecuencia)."""
    img = Image.new("RGB", (lado, lado))
    pix = img.load()
    for y in range(lado):
        v = (y * 255) // lado
        row = (v, (v * 7) // 10, 255 - v)
        for x in range(lado):
            pix[x, y] = row
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=98)
    return buf.getvalue()


def test_subida_pequena_se_guarda_intacta(disco):
    """Una imagen por debajo del objetivo NO se recomprime: conserva su extensión y sus bytes."""
    img = Image.new("RGB", (32, 32), (10, 20, 30))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    crudo = buf.getvalue()
    up = _FakeUpload(crudo, filename="chica.png", content_type="image/png")
    clave = _correr(media.guardar_subida(up))
    assert clave.startswith("fotos/") and clave.endswith(".png")
    assert almacen_media.leer_objeto(clave) == crudo


def test_subida_pesada_se_recomprime_a_jpeg(disco, monkeypatch):
    """Una subida que supera el objetivo se admite y se RECOMPRIME a JPEG bajo ese objetivo."""
    crudo = _jpeg_grande()
    objetivo = 80 * 1024
    monkeypatch.setattr(media, "OBJETIVO_COMPRESION_IMAGEN", objetivo)
    assert len(crudo) > objetivo  # de partida pesa más que el objetivo
    up = _FakeUpload(crudo, filename="afp.jpg", content_type="image/jpeg")
    clave = _correr(media.guardar_subida(up))
    assert clave.endswith(".jpg")
    guardado = almacen_media.leer_objeto(clave)
    assert guardado is not None
    assert len(guardado) <= objetivo
    assert len(guardado) < len(crudo)


def test_subida_grande_no_se_rechaza_por_peso(disco):
    """Sin tocar el objetivo, una foto de ~varios MB pasa sin error (no hay límite de producto)."""
    up = _FakeUpload(_jpeg_grande(), filename="afp.jpg", content_type="image/jpeg")
    clave = _correr(media.guardar_subida(up))
    assert clave.startswith("fotos/")


def test_subida_por_encima_del_techo_anti_oom_se_rechaza(disco, monkeypatch):
    """El único tope es el techo anti-OOM: por encima de él se rechaza en español."""
    monkeypatch.setattr(media, "LIMITE_SUBIDA_IMAGEN", 4 * 1024 * 1024)
    enorme = b"\xff\xd8\xff" + b"\0" * (5 * 1024 * 1024)  # > techo: se corta en la lectura
    up = _FakeUpload(enorme, filename="enorme.jpg", content_type="image/jpeg")
    with pytest.raises(media.MediaError):
        _correr(media.guardar_subida(up))
