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
# _dimensiones_imagen: medir el lado por la cabecera (sin Pillow)             #
# --------------------------------------------------------------------------- #


def _png_dim(ancho: int, alto: int) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\x0dIHDR"
        + ancho.to_bytes(4, "big")
        + alto.to_bytes(4, "big")
        + b"\x08\x06\x00\x00\x00"
    )


def _jpg_dim(ancho: int, alto: int) -> bytes:
    return (
        b"\xff\xd8"
        + b"\xff\xc0\x00\x11\x08"
        + alto.to_bytes(2, "big")
        + ancho.to_bytes(2, "big")
        + b"\x00" * 6
    )


def _gif_dim(ancho: int, alto: int) -> bytes:
    return b"GIF89a" + ancho.to_bytes(2, "little") + alto.to_bytes(2, "little") + b"\x00" * 3


def _webp_vp8x_dim(ancho: int, alto: int) -> bytes:
    return (
        b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"VP8X"
        + b"\x00\x00\x00\x0a" + b"\x00\x00\x00\x00"
        + (ancho - 1).to_bytes(3, "little")
        + (alto - 1).to_bytes(3, "little")
    )


def test_dimensiones_imagen_por_formato():
    assert extraccion_url._dimensiones_imagen(_png_dim(640, 480)) == (640, 480)
    assert extraccion_url._dimensiones_imagen(_jpg_dim(640, 480)) == (640, 480)
    assert extraccion_url._dimensiones_imagen(_gif_dim(640, 480)) == (640, 480)
    assert extraccion_url._dimensiones_imagen(_webp_vp8x_dim(640, 480)) == (640, 480)


def test_dimensiones_imagen_no_medible_none():
    # No es imagen reconocible -> None.
    assert extraccion_url._dimensiones_imagen(b"<html>") is None
    # PNG con firma valida pero cabecera truncada (no llega al IHDR) -> None (no medible).
    assert extraccion_url._dimensiones_imagen(b"\x89PNG\r\n\x1a\n" + b"\x00\x00") is None


# --------------------------------------------------------------------------- #
# descargar_imagen_a_media: filtro de tamano minimo (min_lado)                #
# --------------------------------------------------------------------------- #


def test_descargar_rechaza_imagen_pequena(almacen_disco, monkeypatch):
    """`min_lado` rechaza la basura diminuta (p. ej. el emoji-fallback 72x72)."""
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", lambda url: _png_dim(72, 72))
    with pytest.raises(extraccion_url.ExtraccionError):
        extraccion_url.descargar_imagen_a_media("https://example.com/emoji.png", min_lado=320)


def test_descargar_acepta_imagen_grande(almacen_disco, monkeypatch):
    """Una imagen que supera `min_lado` se guarda con normalidad."""
    grande = _png_dim(800, 600)
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", lambda url: grande)
    nombre = extraccion_url.descargar_imagen_a_media("https://example.com/foto.png", min_lado=320)
    assert nombre.startswith("fotos/") and nombre.endswith(".png")
    assert media.leer_media(nombre) == grande


def test_descargar_sin_min_lado_no_filtra(almacen_disco, monkeypatch):
    """`min_lado=0` (por defecto) NO filtra por tamano: los callers manuales no cambian."""
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", lambda url: _png_dim(10, 10))
    nombre = extraccion_url.descargar_imagen_a_media("https://example.com/x.png")
    assert nombre.startswith("fotos/")


def test_descargar_no_medible_no_se_bloquea(almacen_disco, monkeypatch):
    """Si la cabecera no es medible, `min_lado` NO bloquea (no rechazamos lo que no medimos)."""
    indeterminada = b"\x89PNG\r\n\x1a\n" + b"\x00\x00"  # PNG valido pero sin IHDR completo
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", lambda url: indeterminada)
    nombre = extraccion_url.descargar_imagen_a_media("https://example.com/x.png", min_lado=320)
    assert nombre.startswith("fotos/")


# --------------------------------------------------------------------------- #
# descargar_imagen_a_media: camino feliz (guardado + lectura)                 #
# --------------------------------------------------------------------------- #


def test_descargar_imagen_a_media_png_guarda_y_es_legible(almacen_disco, monkeypatch):
    """Bytes PNG validos => key `fotos/<uuid>.png` y el objeto se lee con `media.leer_media`."""
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", lambda url: _PNG)
    nombre = extraccion_url.descargar_imagen_a_media("https://example.com/x.png")
    assert nombre.endswith(".png")
    # La foto original va a la carpeta `fotos/` (key con prefijo de categoria).
    assert nombre.startswith("fotos/")
    # El nombre plano lo generamos nosotros (uuid hex de 32), NO viene de la URL.
    stem = nombre.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    assert len(stem) == 32 and all(c in "0123456789abcdef" for c in stem)
    assert media.leer_media(nombre) == _PNG


def test_descargar_imagen_a_media_jpg_extension(almacen_disco, monkeypatch):
    """Bytes JPG => la extension del objeto guardado es `.jpg` (no se fia del nombre de URL)."""
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", lambda url: _JPG)
    nombre = extraccion_url.descargar_imagen_a_media("https://example.com/foto.png")
    assert nombre.endswith(".jpg")
    assert media.leer_media(nombre) == _JPG


def test_descargar_imagen_a_media_categoria_copyright(almacen_disco, monkeypatch):
    """`categoria='copyright'` => key `copyright/<uuid>` (stock sin licencia aislado de `fotos/`)."""
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", lambda url: _PNG)
    nombre = extraccion_url.descargar_imagen_a_media(
        "https://example.com/x.png", categoria="copyright"
    )
    assert nombre.startswith("copyright/")
    assert media.leer_media(nombre) == _PNG


# --------------------------------------------------------------------------- #
# es_url_icono: descarta emojis/iconos/favicons por la ruta                   #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "url",
    [
        "https://s.w.org/images/core/emoji/17.0.2/72x72/1f514.png",  # 🔔 bell de WordPress
        "https://s.w.org/images/core/emoji/17.0.2/72x72/2714.png",   # ✔️ check
        "https://cdn.site.com/assets/emoji/smile.png",
        "https://site.com/favicon.ico",
        "https://site.com/apple-touch-icon.png",
        "https://www.gravatar.com/avatar/abc.png",
        "https://site.com/logo.ICO",
    ],
)
def test_es_url_icono_detecta(url):
    assert extraccion_url.es_url_icono(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://cdn.amxinfra.com/uploads/2026/06/nota-portada.jpg",
        "https://sm.ign.com/ign_mx/screenshot/foto.png",
        "https://site.com/articulo/imagen-grande.webp",
        "",
    ],
)
def test_es_url_icono_no_falso_positivo(url):
    assert extraccion_url.es_url_icono(url) is False


def test_descargar_rechaza_url_icono_sin_tocar_red(almacen_disco, monkeypatch):
    """Una URL de emoji/icono => ExtraccionError ANTES de descargar (no llama al descargador)."""
    llamado = {"n": 0}

    def descargador_espia(url):  # noqa: ANN001
        llamado["n"] += 1
        return _PNG

    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", descargador_espia)
    with pytest.raises(extraccion_url.ExtraccionError):
        extraccion_url.descargar_imagen_a_media(
            "https://s.w.org/images/core/emoji/17.0.2/72x72/1f514.png"
        )
    assert llamado["n"] == 0


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

    def revienta(datos, *, ext="png", categoria="fotos"):  # noqa: ANN001
        raise media.MediaError("La imagen generada es demasiado grande.")

    monkeypatch.setattr(media, "guardar_bytes", revienta)
    with pytest.raises(extraccion_url.ExtraccionError):
        extraccion_url.descargar_imagen_a_media("https://example.com/x.png")
