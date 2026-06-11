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


# --------------------------------------------------------------------------- #
# CARRUSEL (DOS tipos de output del pipeline): extras -> slides + flip formato  #
# --------------------------------------------------------------------------- #


def _piezas_tres_redes():
    return [
        {"red": "instagram", "contenido": "Hola", "copy_in": "T"},
        {"red": "x", "contenido": "Hola", "copy_in": "T"},
        {"red": "facebook", "contenido": "Hola", "copy_in": "T"},
    ]


def test_carrusel_extras_arman_pieza_carrusel_nidada(entorno, monkeypatch):
    """Con `carrusel_extras` y tema: flip a formato carrusel, redes IG/FB y slides en la fila."""
    import json

    from keni_consola import redes

    _almacen_disco(monkeypatch)
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", lambda url: _PNG)
    tema = repos.crear_contenido(clase="contenido", titulo="Historia", marca=_MARCA)

    creadas = dom_copy.crear_publicaciones_desde_piezas(
        _piezas_tres_redes(),
        marca=_MARCA,
        titulo="Historia",
        verdicto="",
        origen="hist-3",
        contenido_id=tema["id"],
        imagen_fuente="https://example.com/portada.png",
        tipo_contenido="fuente",
        carrusel_extras=["https://example.com/extra1.png", "https://example.com/extra2.png"],
    )

    # El FORMATO decide las redes: carrusel -> IG/FB; la pieza de X se omite.
    assert sorted(str(c["red"]) for c in creadas) == ["facebook", "instagram"]
    assert repos.obtener_contenido(tema["id"])["formato"] == redes.FORMATO_CARRUSEL
    # Cada borrador lleva los slides EXTRA en crudo (la portada va en `imagen`).
    for creada in creadas:
        slides = json.loads(str(creada.get("carrusel") or "[]"))
        assert len(slides) == 2
        assert all(s["tipo"] == "imagen" and s["objeto"].startswith("artes/") for s in slides)
        assert str(creada.get("imagen") or "").startswith("artes/")


def test_carrusel_degrada_a_post_si_extras_no_descargan(entorno, monkeypatch):
    """Si NINGUNA extra se pudo descargar, todo sigue como post de foto (sin flip ni filtro)."""
    from keni_consola import redes

    _almacen_disco(monkeypatch)

    def descarga(url):
        if "extra" in url:
            raise RuntimeError("extra rota")
        return _PNG

    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", descarga)
    tema = repos.crear_contenido(clase="contenido", titulo="Historia", marca=_MARCA)

    creadas = dom_copy.crear_publicaciones_desde_piezas(
        _piezas_tres_redes(),
        marca=_MARCA,
        titulo="Historia",
        verdicto="",
        origen="hist-4",
        contenido_id=tema["id"],
        imagen_fuente="https://example.com/portada.png",
        tipo_contenido="fuente",
        carrusel_extras=["https://example.com/extra1.png"],
    )

    assert sorted(str(c["red"]) for c in creadas) == ["facebook", "instagram", "x"]
    assert repos.obtener_contenido(tema["id"])["formato"] == redes.FORMATO_FOTO
    assert all(not str(c.get("carrusel") or "") for c in creadas)


def test_procesar_copy_arma_carrusel_si_el_modelo_lo_elige(entorno, monkeypatch):
    """Cableado parseo→depósito: la salida con `tipo: carrusel` produce la pieza carrusel."""
    import json

    from keni_consola import redes

    _almacen_disco(monkeypatch)
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", lambda url: _PNG)
    tema = repos.crear_contenido(clase="contenido", titulo="Historia", marca=_MARCA)
    fotos = ["https://example.com/portada.png", "https://example.com/extra.png"]

    procesar = dom_copy.construir_procesar_copy(
        "copy-desde-nota", _MARCA,
        redes_ids=["instagram", "x", "facebook"], titulo_dado="Historia", texto_base="nota",
        contenido_id=tema["id"], imagen_fuente=fotos[0], imagenes_fuente=fotos,
        tipo_contenido="fuente",
    )
    salida = '```json\n{"texto": "Copy", "copy_in": "T", "tipo": "carrusel"}\n```'
    resultado = procesar(salida, None)

    assert sorted(str(p["red"]) for p in resultado["publicaciones"]) == ["facebook", "instagram"]
    assert repos.obtener_contenido(tema["id"])["formato"] == redes.FORMATO_CARRUSEL
    slides = json.loads(str(resultado["publicaciones"][0].get("carrusel") or "[]"))
    assert len(slides) == 1 and slides[0]["objeto"].startswith("artes/")


def test_procesar_copy_tipo_post_no_arma_carrusel(entorno, monkeypatch):
    """Con fotos disponibles pero `tipo: post` (o sin tipo), la pieza es el post de siempre."""
    from keni_consola import redes

    _almacen_disco(monkeypatch)
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", lambda url: _PNG)
    tema = repos.crear_contenido(clase="contenido", titulo="Historia", marca=_MARCA)
    fotos = ["https://example.com/portada.png", "https://example.com/extra.png"]

    procesar = dom_copy.construir_procesar_copy(
        "copy-desde-nota", _MARCA,
        redes_ids=["instagram", "x", "facebook"], titulo_dado="Historia", texto_base="nota",
        contenido_id=tema["id"], imagen_fuente=fotos[0], imagenes_fuente=fotos,
        tipo_contenido="fuente",
    )
    salida = '```json\n{"texto": "Copy", "copy_in": "T"}\n```'
    resultado = procesar(salida, None)

    assert sorted(str(p["red"]) for p in resultado["publicaciones"]) == [
        "facebook", "instagram", "x",
    ]
    assert repos.obtener_contenido(tema["id"])["formato"] == redes.FORMATO_FOTO
    assert all(not str(p.get("carrusel") or "") for p in resultado["publicaciones"])


def test_carrusel_extras_sin_tema_se_ignoran(entorno, monkeypatch):
    """Sin `contenido_id` no hay carrusel que nidar: borradores sueltos de foto, como hoy."""
    _almacen_disco(monkeypatch)
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", lambda url: _PNG)

    creadas = dom_copy.crear_publicaciones_desde_piezas(
        _piezas_tres_redes(),
        marca=_MARCA,
        titulo="Suelta",
        verdicto="",
        origen="hist-5",
        imagen_fuente="https://example.com/portada.png",
        tipo_contenido="fuente",
        carrusel_extras=["https://example.com/extra1.png"],
    )

    assert sorted(str(c["red"]) for c in creadas) == ["facebook", "instagram", "x"]
    assert all(not str(c.get("carrusel") or "") for c in creadas)
