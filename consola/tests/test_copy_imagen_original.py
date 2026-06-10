"""La foto ORIGINAL de fuente propia se CATALOGA en la Biblioteca y se inyecta a la pieza.

Cuando `crear_publicaciones_desde_piezas` recibe `imagen_fuente` (og:image de un RSS de marca
propia), descarga la foto, la promueve a la carpeta protegida `artes`, la registra en el
catálogo de media con `tipo="original"` (así APARECE en la Galería de Artes bajo "Originales" y
el GC no la borra) y la pieza nace con ESA key como imagen del feed.

OFFLINE: backend de media en DISCO (S3_* borradas) y descarga binaria parcheada; DB en el
Postgres de pruebas vía la fixture `entorno`.
"""

from __future__ import annotations

from keni_consola import almacen_media, repos
from keni_consola.dominio import copy as dom_copy
from keni_consola.dominio import extraccion_url

_MARCA = "unotv"
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x01\x02\x03" * 4


def _almacen_disco(monkeypatch):
    """Fuerza backend de media en DISCO (sin S3 ni red), como en test_extraccion_imagen."""
    for var in ("S3_ENDPOINT", "S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_REGION", "S3_BUCKET"):
        monkeypatch.delenv(var, raising=False)
    almacen_media._resetear_cliente_s3()


def test_imagen_fuente_se_cataloga_como_original_y_se_inyecta(entorno, monkeypatch):
    _almacen_disco(monkeypatch)
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", lambda url: _PNG)

    creadas = dom_copy.crear_publicaciones_desde_piezas(
        [{"red": "x", "contenido": "Hola", "copy_in": ""}],
        marca=_MARCA,
        titulo="Nota propia",
        verdicto="",
        origen="hist-1",
        imagen_fuente="https://example.com/foto.png",
        tipo_contenido="fuente",
    )

    # La pieza nace con la foto en la carpeta protegida `artes` (auto-inyectada al feed).
    assert len(creadas) == 1
    imagen = str(creadas[0].get("imagen") or "")
    assert imagen.startswith("artes/")

    # Y queda CATALOGADA en la Biblioteca con tipo="original" y marca de la pieza.
    catalogo = repos.listar_media_catalogo()
    fila = next((c for c in catalogo if (c.get("objeto") or "") == imagen), None)
    assert fila is not None
    assert fila.get("tipo") == dom_copy.TIPO_ARTE_ORIGINAL
    assert fila.get("marca") == _MARCA


def test_sin_imagen_fuente_no_cataloga_ni_pone_imagen(entorno, monkeypatch):
    _almacen_disco(monkeypatch)

    creadas = dom_copy.crear_publicaciones_desde_piezas(
        [{"red": "x", "contenido": "Hola", "copy_in": ""}],
        marca=_MARCA,
        titulo="Sin foto",
        verdicto="",
        origen="hist-2",
    )

    assert len(creadas) == 1
    assert str(creadas[0].get("imagen") or "") == ""
    assert repos.listar_media_catalogo() == []
