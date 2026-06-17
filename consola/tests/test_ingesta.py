"""Tests PUROS (sin DB ni red) del dominio de ingesta (`dominio.ingesta`).

Cubre `url_canonica` (delega en dedup), la `clave` de dedup (url canónica o hash del título) e
`items_de_feed` con un FETCHER FALSO inyectado: nunca se toca la red. Verifica el mapeo de
campos, el idioma (del feed vs heurístico), `publicado_en` normalizado, el descarte de items
sin identidad estable y la degradación honesta cuando el feed falla.
"""

from __future__ import annotations

import pytest

from keni_consola.dominio import dedup, ingesta

# IP pública literal: pasa el guard SSRF de http_feed sin tocar DNS.
_URL_FEED = "https://93.184.216.34/feed.xml"

_FEED_ES = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>El presidente anuncia una nueva reforma para los estados</title>
    <description>La noticia detalla los cambios en la ley general del país.</description>
    <link>https://example.com/nota-1?utm_source=tw&amp;id=9</link>
    <guid>g1</guid>
    <pubDate>Mon, 02 Jun 2025 10:00:00 GMT</pubDate>
  </item>
  <item>
    <title>The market reacts to the new policy with strong gains today</title>
    <description>Investors and traders welcomed the change in the economy.</description>
    <link>https://example.com/nota-2</link>
    <guid>g2</guid>
  </item>
</channel></rss>
"""


def _feed(**extra):
    base = {"id": "f1", "nombre": "Fuente Demo", "url": _URL_FEED, "categoria": "mx", "marca": "unotv"}
    base.update(extra)
    return base


# --------------------------------------------------------------------------- #
# url_canonica + clave de dedup                                                #
# --------------------------------------------------------------------------- #


def test_url_canonica_delega_en_dedup():
    assert ingesta.url_canonica("https://www.Example.com/Nota/?utm_source=x") == "example.com/Nota"


def test_clave_usa_url_canonica_cuando_hay_url():
    items, _ = ingesta.items_de_feed(_feed(), fetcher=lambda _u: _FEED_ES)
    # La clave del primer item es su url canónica (sin utm, conserva id real).
    primero = next(it for it in items if it["fuente_id"] == "f1" and it["url"].endswith("id=9"))
    assert primero["clave"] == "example.com/nota-1?id=9"
    assert primero["url_canonica"] == "example.com/nota-1?id=9"


def test_clave_cae_a_hash_de_titulo_sin_url():
    feed_sin_url = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title>Una noticia sin enlace pero con título</title><guid></guid></item>
</channel></rss>"""
    items, salud = ingesta.items_de_feed(_feed(), fetcher=lambda _u: feed_sin_url)
    assert salud["error"] == ""
    assert len(items) == 1
    # Sin url: la clave es el hash del título normalizado (prefijo "t:").
    assert items[0]["clave"].startswith("t:")
    assert items[0]["url"] == ""


def test_item_sin_url_ni_titulo_se_descarta():
    feed_vacio = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title></title><link></link><guid></guid></item>
</channel></rss>"""
    items, _ = ingesta.items_de_feed(_feed(), fetcher=lambda _u: feed_vacio)
    assert items == []  # sin identidad estable: no se archiva


# --------------------------------------------------------------------------- #
# Mapeo de campos + idioma + fecha                                             #
# --------------------------------------------------------------------------- #


def test_items_de_feed_mapea_campos_de_la_fuente():
    items, salud = ingesta.items_de_feed(_feed(), fetcher=lambda _u: _FEED_ES)
    assert salud == {"conteo": 2, "error": ""}
    assert len(items) == 2
    it = items[0]
    assert it["fuente_id"] == "f1"
    assert it["fuente_nombre"] == "Fuente Demo"
    assert it["categoria"] == "mx"
    assert it["marca"] == "unotv"
    assert it["estado"] == "nuevo"
    assert it["titulo"].startswith("El presidente")


def test_idioma_del_feed_gana_a_la_heuristica():
    # El feed declara idioma 'fr'; aunque el texto sea español, se respeta el del feed.
    items, _ = ingesta.items_de_feed(_feed(idioma="fr"), fetcher=lambda _u: _FEED_ES)
    assert all(it["idioma"] == "fr" for it in items)


def test_deteccion_idioma_en_la_ingesta_es_en():
    """Sin idioma declarado en el feed, cada item DETECTA su idioma del texto (es/en)."""
    items, _ = ingesta.items_de_feed(_feed(idioma=""), fetcher=lambda _u: _FEED_ES)
    por_clave = {it["titulo"][:5]: it["idioma"] for it in items}
    assert por_clave["El pr"] == "es"
    assert por_clave["The m"] == "en"


def test_detectar_idioma_extranjero_no_es():
    """Lo que importa aguas abajo: el español sale "es" y lo EXTRANJERO no empieza por "es" (-> entra
    a Traducir). `langdetect` distingue varios idiomas en titulares cortos, no solo es/en."""
    pytest.importorskip("langdetect")
    assert ingesta.detectar_idioma("El gobierno de México anuncia nuevas medidas hoy").startswith("es")
    assert not ingesta.detectar_idioma("The government announces new measures today").startswith("es")
    assert not ingesta.detectar_idioma("Top Gear's Jeremy Clarkson diagnosed with cancer").startswith("es")
    assert not ingesta.detectar_idioma("Tu przeniosą się Lewandowscy, mocny komentarz Bońka").startswith("es")


def test_idioma_por_palabras_fallback():
    """El fallback por palabras funcionales (sin la lib) sigue dando es/en; "" sin señal clara."""
    assert ingesta._idioma_por_palabras("the minister of the city") == "en"
    assert ingesta._idioma_por_palabras("el presidente de la ciudad") == "es"
    assert ingesta._idioma_por_palabras("Lewandowski") == ""


def test_items_heredan_el_peso_de_la_fuente():
    # El peso editorial del feed viaja DENORMALIZADO en cada item (el clustering es puro).
    items, _ = ingesta.items_de_feed(_feed(peso=2.0), fetcher=lambda _u: _FEED_ES)
    assert all(it["fuente_peso"] == 2.0 for it in items)


def test_items_sin_peso_declarado_caen_a_normal():
    items, _ = ingesta.items_de_feed(_feed(), fetcher=lambda _u: _FEED_ES)
    assert all(it["fuente_peso"] == 1.0 for it in items)


def test_items_con_peso_invalido_caen_a_normal():
    items, _ = ingesta.items_de_feed(_feed(peso="potente"), fetcher=lambda _u: _FEED_ES)
    assert all(it["fuente_peso"] == 1.0 for it in items)


def test_publicado_en_normaliza_rfc822_a_iso():
    items, _ = ingesta.items_de_feed(_feed(), fetcher=lambda _u: _FEED_ES)
    con_fecha = next(it for it in items if it["url"].endswith("id=9"))
    assert con_fecha["publicado_en"].startswith("2025-06-02T10:00:00")
    # El item sin pubDate parseable queda con publicado_en vacío.
    sin_fecha = next(it for it in items if it["url"].endswith("nota-2"))
    assert sin_fecha["publicado_en"] == ""


# --------------------------------------------------------------------------- #
# Degradación honesta                                                          #
# --------------------------------------------------------------------------- #


def test_feed_xml_invalido_devuelve_error_sin_lanzar():
    items, salud = ingesta.items_de_feed(_feed(), fetcher=lambda _u: "no soy xml")
    assert items == []
    assert salud["conteo"] == 0
    assert salud["error"]  # mensaje en español, no excepción


def test_fetcher_que_lanza_no_aborta():
    def explota(_u):
        raise RuntimeError("boom")

    items, salud = ingesta.items_de_feed(_feed(), fetcher=explota)
    assert items == []
    assert salud["error"]


def test_max_items_acota_el_numero_de_items():
    items, _ = ingesta.items_de_feed(_feed(), max_items=1, fetcher=lambda _u: _FEED_ES)
    assert len(items) == 1


def test_clave_misma_para_url_equivalente_con_tracking():
    # Dos enlaces a la misma nota con distinto utm canonizan igual -> misma clave de dedup.
    a = dedup.url_canonica("https://example.com/x?utm_source=a")
    b = dedup.url_canonica("https://example.com/x?utm_source=b")
    assert a == b == "example.com/x"


# --------------------------------------------------------------------------- #
# Filtro de relevancia en la ENTRADA (`filtrar_por_vocabulario`)                #
# --------------------------------------------------------------------------- #


def _item_pool(titulo, resumen=""):
    return {"titulo": titulo, "resumen": resumen, "clave": titulo.lower()}


def test_filtrar_por_vocabulario_separa_aptos_y_descartados():
    pal = frozenset({"sismo", "cdmx"})
    items = [
        _item_pool("Sismo de 6.1 esta mañana"),
        _item_pool("Celebrity gossip news"),
        _item_pool("Tránsito complicado", resumen="cierres en la CDMX"),  # casa por resumen
    ]
    aptos, descartados = ingesta.filtrar_por_vocabulario(items, pal)
    assert [it["titulo"] for it in aptos] == ["Sismo de 6.1 esta mañana", "Tránsito complicado"]
    assert [it["titulo"] for it in descartados] == ["Celebrity gossip news"]


def test_filtrar_por_vocabulario_vacio_no_filtra_nada():
    # Sin agenda definida no hay criterio: se archiva todo (honesto).
    items = [_item_pool("Cualquier cosa"), _item_pool("Otra cosa")]
    aptos, descartados = ingesta.filtrar_por_vocabulario(items, frozenset())
    assert aptos == items
    assert descartados == []


def test_filtrar_por_vocabulario_normaliza_acentos_y_puntuacion():
    pal = frozenset({"mexico"})
    aptos, descartados = ingesta.filtrar_por_vocabulario(
        [_item_pool("México: arranca la jornada electoral")], pal
    )
    assert len(aptos) == 1 and descartados == []
