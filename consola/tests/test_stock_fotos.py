"""Tests UNITARIOS de los buscadores de fotos de stock (Pexels/Pixabay/Wikimedia/NASA/Openverse).

OFFLINE, sin red. Cubre la lógica PURA (normalizadores tolerantes a la forma de cada API),
la degradación honesta (gating por credencial de Pexels/Pixabay) y que `buscar`/`buscar_todos`
descargan via el `_DESCARGADOR` inyectable de `api.rss` (parcheado, sin tocar la red).
"""

from __future__ import annotations

import pytest

from keni_consola import stock_fotos


@pytest.fixture(autouse=True)
def _sin_claves(monkeypatch):
    """Por defecto NO hay claves: Pexels/Pixabay quedan apagados salvo que un test las ponga."""
    monkeypatch.delenv("KENI_PEXELS_API_KEY", raising=False)
    monkeypatch.delenv("KENI_PIXABAY_API_KEY", raising=False)


@pytest.fixture
def _sin_ssrf(monkeypatch):
    """Neutraliza el guard SSRF (que resuelve DNS) para que el fetch sea OFFLINE y determinista."""
    monkeypatch.setattr(stock_fotos.rss, "validar_url", lambda url: (url, None))


# --------------------------------------------------------------------------- #
# Normalizadores (PUROS, tolerantes a la forma)                                #
# --------------------------------------------------------------------------- #


def test_normalizar_pexels_extrae_forma_normalizada():
    datos = {
        "photos": [
            {
                "src": {"original": "https://p/orig.jpg", "medium": "https://p/med.jpg"},
                "photographer": "Ana Foto",
                "url": "https://pexels.com/photo/1",
                "alt": "Estadio lleno",
            }
        ]
    }
    cands = stock_fotos.normalizar_pexels(datos)
    assert len(cands) == 1
    c = cands[0]
    assert c == {
        "proveedor": "pexels",
        "url": "https://p/orig.jpg",
        "thumb": "https://p/med.jpg",
        "autor": "Ana Foto",
        "licencia": "Pexels License",
        "credito_url": "https://pexels.com/photo/1",
        "titulo": "Estadio lleno",
    }


def test_normalizar_pexels_omite_sin_url():
    assert stock_fotos.normalizar_pexels({"photos": [{"photographer": "X"}]}) == []


def test_normalizar_pexels_thumb_cae_a_url():
    datos = {"photos": [{"src": {"original": "https://p/o.jpg"}, "photographer": "Y"}]}
    cands = stock_fotos.normalizar_pexels(datos)
    assert cands[0]["thumb"] == "https://p/o.jpg"


def test_normalizar_pixabay_extrae_forma_normalizada():
    datos = {
        "hits": [
            {
                "largeImageURL": "https://px/large.jpg",
                "webformatURL": "https://px/web.jpg",
                "user": "fotografo_mx",
                "pageURL": "https://pixabay.com/photos/1",
                "tags": "futbol, balón",
            }
        ]
    }
    cands = stock_fotos.normalizar_pixabay(datos)
    assert cands[0]["url"] == "https://px/large.jpg"
    assert cands[0]["thumb"] == "https://px/web.jpg"
    assert cands[0]["autor"] == "fotografo_mx"
    assert cands[0]["licencia"] == "Pixabay Content License"
    assert cands[0]["credito_url"] == "https://pixabay.com/photos/1"
    assert cands[0]["titulo"] == "futbol, balón"


def test_normalizar_wikimedia_pages_dict_con_extmetadata():
    datos = {
        "query": {
            "pages": {
                "123": {
                    "title": "File:Estadio.jpg",
                    "imageinfo": [
                        {
                            "url": "https://upload.wikimedia.org/estadio.jpg",
                            "thumburl": "https://upload.wikimedia.org/thumb.jpg",
                            "descriptionurl": "https://commons.wikimedia.org/wiki/File:Estadio.jpg",
                            "extmetadata": {
                                "Artist": {"value": "<a href='x'>Juan</a>"},
                                "LicenseShortName": {"value": "CC BY-SA 4.0"},
                            },
                        }
                    ],
                }
            }
        }
    }
    cands = stock_fotos.normalizar_wikimedia(datos)
    assert len(cands) == 1
    c = cands[0]
    assert c["proveedor"] == "wikimedia"
    assert c["url"] == "https://upload.wikimedia.org/estadio.jpg"
    assert c["thumb"] == "https://upload.wikimedia.org/thumb.jpg"
    assert c["autor"] == "Juan"  # HTML quitado por _limpiar_resumen
    assert c["licencia"] == "CC BY-SA 4.0"
    assert c["credito_url"] == "https://commons.wikimedia.org/wiki/File:Estadio.jpg"
    assert c["titulo"] == "File:Estadio.jpg"


def test_normalizar_wikimedia_omite_sin_url():
    datos = {"query": {"pages": {"1": {"title": "File:x", "imageinfo": [{}]}}}}
    assert stock_fotos.normalizar_wikimedia(datos) == []


def test_normalizar_nasa_extrae_forma_normalizada():
    datos = {
        "collection": {
            "items": [
                {
                    "links": [{"href": "https://images.nasa.gov/thumb.jpg"}],
                    "data": [
                        {
                            "title": "Galaxia",
                            "description": "Una galaxia espiral",
                            "photographer": "NASA/JPL",
                        }
                    ],
                }
            ]
        }
    }
    cands = stock_fotos.normalizar_nasa(datos)
    assert cands[0]["url"] == "https://images.nasa.gov/thumb.jpg"
    assert cands[0]["thumb"] == "https://images.nasa.gov/thumb.jpg"
    assert cands[0]["autor"] == "NASA/JPL"
    assert cands[0]["licencia"] == "NASA (dominio público)"
    assert cands[0]["titulo"] == "Galaxia"


def test_normalizar_nasa_omite_sin_links():
    datos = {"collection": {"items": [{"data": [{"title": "X"}]}]}}
    assert stock_fotos.normalizar_nasa(datos) == []


def test_normalizar_openverse_extrae_forma_normalizada():
    datos = {
        "results": [
            {
                "url": "https://ov/img.jpg",
                "thumbnail": "https://ov/thumb.jpg",
                "creator": "Autor Libre",
                "license": "by-nc",
                "foreign_landing_url": "https://flickr.com/photo/1",
                "title": "Paisaje",
            }
        ]
    }
    cands = stock_fotos.normalizar_openverse(datos)
    assert cands[0]["url"] == "https://ov/img.jpg"
    assert cands[0]["thumb"] == "https://ov/thumb.jpg"
    assert cands[0]["autor"] == "Autor Libre"
    assert cands[0]["licencia"] == "by-nc"
    assert cands[0]["credito_url"] == "https://flickr.com/photo/1"
    assert cands[0]["titulo"] == "Paisaje"


def test_normalizadores_toleran_basura():
    for fn in (
        stock_fotos.normalizar_pexels,
        stock_fotos.normalizar_pixabay,
        stock_fotos.normalizar_wikimedia,
        stock_fotos.normalizar_nasa,
        stock_fotos.normalizar_openverse,
    ):
        assert fn(None) == []
        assert fn({}) == []
        assert fn([]) == []


# --------------------------------------------------------------------------- #
# Degradación honesta (gating por credencial)                                  #
# --------------------------------------------------------------------------- #


def test_estado_pexels_pendiente_sin_clave():
    estado = stock_fotos.estado_fuente("pexels")
    assert estado["disponible"] is False
    assert estado["requiere_clave"] is True
    assert "Sistema → Proveedores" in estado["motivo"]


def test_estado_pixabay_pendiente_sin_clave():
    estado = stock_fotos.estado_fuente("pixabay")
    assert estado["disponible"] is False
    assert "Pixabay" in estado["motivo"]


def test_estado_pexels_disponible_con_clave(monkeypatch):
    monkeypatch.setenv("KENI_PEXELS_API_KEY", "k")
    estado = stock_fotos.estado_fuente("pexels")
    assert estado["disponible"] is True
    assert estado["motivo"] == ""


@pytest.mark.parametrize("proveedor", ["wikimedia", "nasa", "openverse"])
def test_estado_sin_clave_siempre_disponible(proveedor):
    estado = stock_fotos.estado_fuente(proveedor)
    assert estado["disponible"] is True
    assert estado["requiere_clave"] is False


def test_estado_proveedor_desconocido():
    estado = stock_fotos.estado_fuente("inexistente")
    assert estado["disponible"] is False


def test_proveedores_disponibles_sin_claves():
    disp = stock_fotos.proveedores_disponibles()
    assert "pexels" not in disp
    assert "pixabay" not in disp
    assert set(disp) == {"wikimedia", "nasa", "openverse"}


# --------------------------------------------------------------------------- #
# Por marca: clave propia + toggle de fuentes habilitadas                      #
# --------------------------------------------------------------------------- #


def test_clave_pexels_por_marca_hace_disponible(monkeypatch):
    # La clave existe SOLO para 'unotv': disponible para esa marca, no para otra ni global.
    monkeypatch.setattr(
        stock_fotos.config,
        "pexels_api_key",
        lambda marca="": "k" if marca == "unotv" else None,
    )
    assert stock_fotos.estado_fuente("pexels", "unotv")["disponible"] is True
    assert stock_fotos.estado_fuente("pexels", "claro-sports")["disponible"] is False
    assert stock_fotos.estado_fuente("pexels", "")["disponible"] is False


def test_estado_incluye_activa_segun_toggle(monkeypatch):
    # Toggle por marca: solo wikimedia+openverse habilitadas; nasa queda activa=False.
    monkeypatch.setattr(
        stock_fotos.config,
        "fuentes_stock_activas",
        lambda marca="": {"wikimedia", "openverse"} if marca == "unotv" else None,
    )
    assert stock_fotos.estado_fuente("wikimedia", "unotv")["activa"] is True
    nasa = stock_fotos.estado_fuente("nasa", "unotv")
    assert nasa["disponible"] is True and nasa["activa"] is False


def test_proveedores_disponibles_respeta_toggle(monkeypatch):
    monkeypatch.setattr(
        stock_fotos.config,
        "fuentes_stock_activas",
        lambda marca="": {"openverse"} if marca == "unotv" else None,
    )
    assert stock_fotos.proveedores_disponibles("unotv") == ["openverse"]


def test_buscar_todos_omite_fuente_desactivada(monkeypatch, _sin_ssrf):
    # 'nasa' desactivada por toggle: aunque responda, buscar_todos no la consulta.
    monkeypatch.setattr(
        stock_fotos.config,
        "fuentes_stock_activas",
        lambda marca="": {"openverse"},
    )
    monkeypatch.setattr(
        stock_fotos.rss,
        "_DESCARGADOR",
        lambda url: '{"results": [{"url": "https://ov/i.jpg", "creator": "C", "license": "cc0"}]}',
    )
    cands = stock_fotos.buscar_todos("tema", marca="unotv")
    assert {c["proveedor"] for c in cands} == {"openverse"}


def test_buscar_pexels_sin_clave_devuelve_vacio_sin_red():
    assert stock_fotos.buscar("estadio", "pexels") == []


def test_buscar_query_vacio_devuelve_vacio():
    assert stock_fotos.buscar("", "wikimedia") == []


# --------------------------------------------------------------------------- #
# Fetch via el _DESCARGADOR inyectable (sin red real)                          #
# --------------------------------------------------------------------------- #


def test_buscar_wikimedia_usa_descargador_inyectable(monkeypatch, _sin_ssrf):
    payload = (
        '{"query": {"pages": {"7": {"title": "File:Gol.jpg", '
        '"imageinfo": [{"url": "https://upload.wikimedia.org/gol.jpg", '
        '"extmetadata": {"LicenseShortName": {"value": "CC0"}}}]}}}}'
    )
    monkeypatch.setattr(stock_fotos.rss, "_DESCARGADOR", lambda url: payload)
    cands = stock_fotos.buscar("gol", "wikimedia")
    assert len(cands) == 1
    assert cands[0]["url"] == "https://upload.wikimedia.org/gol.jpg"
    assert cands[0]["licencia"] == "CC0"


def test_buscar_pexels_con_clave_usa_descargador(monkeypatch, _sin_ssrf):
    monkeypatch.setenv("KENI_PEXELS_API_KEY", "k")
    monkeypatch.setattr(
        stock_fotos.rss,
        "_DESCARGADOR",
        lambda url: '{"photos": [{"src": {"original": "https://p/o.jpg"}, "photographer": "A"}]}',
    )
    cands = stock_fotos.buscar("playa", "pexels")
    assert cands[0]["url"] == "https://p/o.jpg"
    assert cands[0]["proveedor"] == "pexels"


def test_buscar_propaga_rsserror(monkeypatch, _sin_ssrf):
    def _boom(url):
        raise stock_fotos.rss.RSSError("falló la descarga")

    monkeypatch.setattr(stock_fotos.rss, "_DESCARGADOR", _boom)
    with pytest.raises(stock_fotos.rss.RSSError):
        stock_fotos.buscar("x", "nasa")


def test_buscar_todos_tolera_proveedor_que_lanza(monkeypatch, _sin_ssrf):
    # NASA falla, Openverse responde: buscar_todos sigue con el siguiente y devuelve lo bueno.
    def _descargador(url):
        if "images-api.nasa.gov" in url:
            raise stock_fotos.rss.RSSError("nasa caída")
        return '{"results": [{"url": "https://ov/i.jpg", "creator": "C", "license": "cc0"}]}'

    monkeypatch.setattr(stock_fotos.rss, "_DESCARGADOR", _descargador)
    cands = stock_fotos.buscar_todos("tema", proveedores=["nasa", "openverse"])
    assert [c["proveedor"] for c in cands] == ["openverse"]
    assert cands[0]["url"] == "https://ov/i.jpg"


def test_buscar_todos_solo_disponibles(monkeypatch, _sin_ssrf):
    # Sin claves, pedir pexels (no disponible) no llama a red; wikimedia sí.
    monkeypatch.setattr(
        stock_fotos.rss,
        "_DESCARGADOR",
        lambda url: '{"query": {"pages": {"1": {"title": "File:a", '
        '"imageinfo": [{"url": "https://w/a.jpg"}]}}}}',
    )
    cands = stock_fotos.buscar_todos("t", proveedores=["pexels", "wikimedia"])
    assert {c["proveedor"] for c in cands} == {"wikimedia"}


def test_buscar_todos_query_vacio():
    assert stock_fotos.buscar_todos("") == []
