"""Tests PUROS de descargar la imagen original de una URL a media (S3/disco).

OFFLINE: NUNCA se toca la red. El punto de descarga binaria vive detras de
`extraccion_url._DESCARGADOR_BYTES`, que aqui se PARCHEA para devolver bytes canned;
asi se cubre `descargar_imagen_a_media` (validacion SSRF + magic bytes + guardado a
media) sin httpx real ni S3 real.

ALMACEN: backend DISCO en un dir temporal (`KENI_CONSOLA_MEDIA` -> tmp + S3_* borradas),
mismo patron que la fixture `disco` de `test_almacen_media.py`. Asi `media.guardar_bytes`
escribe a disco temporal y `media.leer_media` lo lee de vuelta, SIN Postgres ni S3.
"""

from __future__ import annotations

import pytest

from keni_consola import almacen_media, media
from keni_consola.dominio import extraccion_url

# Bytes canned por formato: solo necesitan los magic bytes correctos (el resto da igual:
# `descargar_imagen_a_media` no decodifica la imagen, solo deduce la extension).
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x01\x02\x03" * 4
_JPG = b"\xff\xd8\xff\xe0" + b"\x00\x10JFIF" + b"\x00" * 8
_GIF = b"GIF89a" + b"\x01\x00\x01\x00\x00\x00\x00"
_WEBP = b"RIFF" + b"\x24\x00\x00\x00" + b"WEBP" + b"VP8 " + b"\x00" * 8


@pytest.fixture
def almacen_disco(monkeypatch, tmp_path):
    """Aisla el dir de media en tmp y BORRA S3_* => backend DISCO (sin red, sin Postgres).

    Mismo patron que `disco` en `test_almacen_media.py`: `media.guardar_bytes` escribe a
    `tmp_path/media` y `media.leer_media` lee de ahi.
    """
    for var in ("S3_ENDPOINT", "S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_REGION", "S3_BUCKET"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("KENI_CONSOLA_MEDIA", str(tmp_path / "media"))
    almacen_media._resetear_cliente_s3()
    return tmp_path


# --------------------------------------------------------------------------- #
# _ext_imagen: deteccion por magic bytes                                      #
# --------------------------------------------------------------------------- #


def test_ext_imagen_detecta_formatos():
    assert extraccion_url._ext_imagen(_PNG) == "png"
    assert extraccion_url._ext_imagen(_JPG) == "jpg"
    assert extraccion_url._ext_imagen(_GIF) == "gif"
    assert extraccion_url._ext_imagen(_WEBP) == "webp"


def test_ext_imagen_gif87a():
    # Ambas firmas GIF se aceptan (GIF87a y GIF89a).
    assert extraccion_url._ext_imagen(b"GIF87a" + b"\x00" * 8) == "gif"


def test_ext_imagen_no_imagen_none():
    assert extraccion_url._ext_imagen(b"nope") is None
    assert extraccion_url._ext_imagen(b"<html><body>error</body></html>") is None
    assert extraccion_url._ext_imagen(b"") is None
    # RIFF sin WEBP en el offset 8 NO es webp.
    assert extraccion_url._ext_imagen(b"RIFF\x00\x00\x00\x00AVI ") is None


# --------------------------------------------------------------------------- #
# descargar_imagen_a_media: camino feliz (guardado + lectura)                 #
# --------------------------------------------------------------------------- #


def test_descargar_imagen_a_media_png_guarda_y_es_legible(almacen_disco, monkeypatch):
    """Bytes PNG validos => nombre `<uuid>.png` y el objeto se lee con `media.leer_media`."""
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", lambda url: _PNG)
    nombre = extraccion_url.descargar_imagen_a_media("https://example.com/x.png")
    assert nombre.endswith(".png")
    # El nombre lo generamos nosotros (uuid hex), NO viene de la URL.
    stem = nombre.rsplit(".", 1)[0]
    assert len(stem) == 32 and all(c in "0123456789abcdef" for c in stem)
    assert media.leer_media(nombre) == _PNG


def test_descargar_imagen_a_media_jpg_extension(almacen_disco, monkeypatch):
    """Bytes JPG => la extension del objeto guardado es `.jpg` (no se fia del nombre de URL)."""
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", lambda url: _JPG)
    nombre = extraccion_url.descargar_imagen_a_media("https://example.com/foto.png")
    assert nombre.endswith(".jpg")
    assert media.leer_media(nombre) == _JPG


# --------------------------------------------------------------------------- #
# descargar_imagen_a_media: errores controlados (ExtraccionError)             #
# --------------------------------------------------------------------------- #


def test_descargar_contenido_no_imagen_error(almacen_disco, monkeypatch):
    """Si lo descargado NO es una imagen soportada => ExtraccionError (no se guarda nada)."""
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", lambda url: b"<html>error</html>")
    with pytest.raises(extraccion_url.ExtraccionError):
        extraccion_url.descargar_imagen_a_media("https://example.com/x.png")


def test_descargar_vacio_error(almacen_disco, monkeypatch):
    """Descarga vacia (0 bytes) => ExtraccionError."""
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", lambda url: b"")
    with pytest.raises(extraccion_url.ExtraccionError):
        extraccion_url.descargar_imagen_a_media("https://example.com/x.png")


def test_descargar_url_insegura_no_descarga(almacen_disco, monkeypatch):
    """URL privada/loopback => el guard SSRF la rechaza ANTES de descargar.

    Verifica que `_DESCARGADOR_BYTES` NO se llamo (la defensa ocurre antes de tocar red).
    """
    llamado = {"n": 0}

    def descargador_espia(url):  # noqa: ANN001
        llamado["n"] += 1
        return _PNG

    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", descargador_espia)
    for url in ("http://127.0.0.1/x.png", "http://localhost/x.png"):
        with pytest.raises(extraccion_url.ExtraccionError):
            extraccion_url.descargar_imagen_a_media(url)
    assert llamado["n"] == 0


def test_descargar_url_vacia_error(almacen_disco, monkeypatch):
    """URL vacia/no-string => ExtraccionError sin descargar."""
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", lambda url: _PNG)
    with pytest.raises(extraccion_url.ExtraccionError):
        extraccion_url.descargar_imagen_a_media("")


def test_descargar_esquema_no_http_error(almacen_disco, monkeypatch):
    """Esquema distinto de http/https => ExtraccionError (gate de validar_url)."""
    llamado = {"n": 0}

    def descargador_espia(url):  # noqa: ANN001
        llamado["n"] += 1
        return _PNG

    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", descargador_espia)
    with pytest.raises(extraccion_url.ExtraccionError):
        extraccion_url.descargar_imagen_a_media("ftp://example.com/x.png")
    assert llamado["n"] == 0


def test_descargar_media_error_se_envuelve(almacen_disco, monkeypatch):
    """Un `media.MediaError` (p.ej. imagen demasiado grande) se traduce a ExtraccionError."""
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", lambda url: _PNG)

    def revienta(datos, *, ext="png"):  # noqa: ANN001
        raise media.MediaError("La imagen generada es demasiado grande.")

    monkeypatch.setattr(media, "guardar_bytes", revienta)
    with pytest.raises(extraccion_url.ExtraccionError):
        extraccion_url.descargar_imagen_a_media("https://example.com/x.png")
