"""Tests UNITARIOS del radar de tendencias (`keni_consola.radar`). OFFLINE, sin red.

Cubre la logica PURA: parseo del feed de Google Trends (namespace `ht:`), traduccion
de `approx_traffic` a un entero comparable, dedup + prioridad por señal al consolidar,
conversion de items de feeds RSS del equipo, y las fuentes PENDIENTES (degradacion).
"""

from __future__ import annotations

import pytest

from keni_consola import radar
from keni_consola.api import rss

# Feed de Google Trends MINIMO pero realista (dos terminos con ht:approx_traffic + notas).
_TRENDS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0">
  <channel>
    <title>Daily Search Trends</title>
    <item>
      <title>junior h</title>
      <ht:approx_traffic>2K+</ht:approx_traffic>
      <pubDate>Wed, 27 May 2026 10:50:00 -0700</pubDate>
      <ht:news_item>
        <ht:news_item_title>Junior H anuncia gira en México</ht:news_item_title>
        <ht:news_item_url>https://example.com/junior-h</ht:news_item_url>
        <ht:news_item_source>Billboard</ht:news_item_source>
      </ht:news_item>
      <ht:news_item>
        <ht:news_item_title>Concierto de Junior H agota entradas</ht:news_item_title>
        <ht:news_item_url>https://example.com/junior-h-2</ht:news_item_url>
        <ht:news_item_source>Las Estrellas</ht:news_item_source>
      </ht:news_item>
    </item>
    <item>
      <title>fichajes</title>
      <ht:approx_traffic>100+</ht:approx_traffic>
      <ht:news_item>
        <ht:news_item_title>Liga MX: rumores de fichajes</ht:news_item_title>
        <ht:news_item_url>https://example.com/fichajes</ht:news_item_url>
        <ht:news_item_source>ESPN</ht:news_item_source>
      </ht:news_item>
    </item>
  </channel>
</rss>
"""


# --------------------------------------------------------------------------- #
# traduce_trafico (funcion pura)                                               #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "crudo,esperado",
    [
        ("100+", 100),
        ("2K+", 2000),
        ("50 mil+", 50_000),
        ("1M+", 1_000_000),
        ("2 millones+", 2_000_000),
        ("1 millón+", 1_000_000),
        ("1,000+", 1000),
        ("", 0),
        ("sin numero", 0),
    ],
)
def test_traduce_trafico(crudo, esperado):
    assert radar.traduce_trafico(crudo) == esperado


# --------------------------------------------------------------------------- #
# parsear_trends (namespace ht:, tolerante)                                    #
# --------------------------------------------------------------------------- #


def test_parsear_trends_basico():
    temas = radar.parsear_trends(_TRENDS_XML, geo="MX")
    assert len(temas) == 2
    junior = next(t for t in temas if t.titulo == "junior h")
    assert junior.senal == 2000
    assert junior.senal_texto == "2K+"
    assert junior.redes == {"busquedas-mx"}
    assert junior.fuentes == {"Google Trends"}
    assert len(junior.enlaces) == 2
    assert junior.enlaces[0].url == "https://example.com/junior-h"
    assert junior.enlaces[0].fuente == "Billboard"
    # "Por que sube" = señal real + la nota mas relevante (sin inventar la causa).
    assert "2K+" in junior.por_que
    assert "México" in junior.por_que
    assert "Junior H anuncia gira" in junior.por_que


def test_parsear_trends_xml_invalido_lanza():
    with pytest.raises(rss.RSSError):
        radar.parsear_trends("<<<no es xml", geo="MX")


def test_parsear_trends_item_sin_titulo_se_omite():
    xml = """<rss xmlns:ht="https://trends.google.com/trending/rss"><channel>
      <item><ht:approx_traffic>9K+</ht:approx_traffic></item>
      <item><title>válido</title><ht:approx_traffic>1+</ht:approx_traffic></item>
    </channel></rss>"""
    temas = radar.parsear_trends(xml, geo="MX")
    assert [t.titulo for t in temas] == ["válido"]


def test_parsear_trends_sin_trafico_senal_cero():
    xml = """<rss xmlns:ht="https://trends.google.com/trending/rss"><channel>
      <item><title>sin trafico</title></item>
    </channel></rss>"""
    temas = radar.parsear_trends(xml, geo="MX")
    assert temas[0].senal == 0
    assert temas[0].senal_texto == ""
    # No inventa un "por que" cuando no hay ni trafico ni notas.
    assert temas[0].por_que == ""


# --------------------------------------------------------------------------- #
# temas_de_feeds (señal cualitativa)                                           #
# --------------------------------------------------------------------------- #


def test_temas_de_feeds():
    items = [
        {"titulo": "Nota A", "resumen": "resumen A", "enlace": "https://x/a", "fuente_nombre": "Diario"},
        {"titulo": "", "resumen": "sin titulo", "enlace": "https://x/b", "fuente_nombre": "Diario"},
    ]
    temas = radar.temas_de_feeds(items)
    assert len(temas) == 1  # el de titulo vacio se omite
    assert temas[0].titulo == "Nota A"
    assert temas[0].redes == {"rss"}
    assert temas[0].fuentes == {"Diario"}
    assert temas[0].senal == radar._SENAL_FEED
    assert temas[0].enlaces[0].url == "https://x/a"


# --------------------------------------------------------------------------- #
# consolidar: dedup + prioridad por señal                                      #
# --------------------------------------------------------------------------- #


def test_consolidar_ordena_por_senal_desc():
    temas = radar.parsear_trends(_TRENDS_XML, geo="MX")
    cons = radar.consolidar(temas)
    assert [t.titulo for t in cons] == ["junior h", "fichajes"]  # 2000 antes que 100


def test_consolidar_deduplica_y_funde_fuentes_y_redes():
    trends = radar.parsear_trends(_TRENDS_XML, geo="MX")
    # Un feed del equipo trae el MISMO tema "Junior H" (clave normalizada igual).
    feed = radar.temas_de_feeds(
        [{"titulo": "Junior H", "resumen": "r", "enlace": "https://x/jh", "fuente_nombre": "Mediotiempo"}]
    )
    cons = radar.consolidar(trends, feed)
    # Sigue habiendo 2 temas (junior h fusionado), no 3.
    assert len(cons) == 2
    junior = next(t for t in cons if radar._normalizar_clave(t.titulo) == "junior h")
    # Se queda la señal mas alta (la de Trends) y une redes + fuentes.
    assert junior.senal == 2000
    assert junior.redes == {"busquedas-mx", "rss"}
    assert {"Google Trends", "Mediotiempo"} <= junior.fuentes
    # El enlace del feed se añadio (dedup por URL).
    assert any(e.url == "https://x/jh" for e in junior.enlaces)


def test_consolidar_ignora_titulos_vacios():
    t = radar.Tema(titulo="   ")
    assert radar.consolidar([t]) == []


def test_normalizar_clave():
    assert radar._normalizar_clave("Junior H!") == radar._normalizar_clave("junior   h")
    assert radar._normalizar_clave("¡Hola, México!") == "hola méxico"


# --------------------------------------------------------------------------- #
# Geos + fuentes pendientes                                                    #
# --------------------------------------------------------------------------- #


def test_es_geo():
    assert radar.es_geo("MX") is True
    assert radar.es_geo("XX") is False
    assert radar.es_geo(None) is False


def test_url_trends_usa_geo():
    assert radar._url_trends("MX").endswith("geo=MX")


def test_fuentes_pendientes_documentan_redes_sin_inventar():
    pend = radar.fuentes_pendientes()
    redes = {p["red"] for p in pend}
    assert {"tiktok", "instagram", "x", "youtube"} <= redes
    # Cada pendiente trae un motivo legible (no datos inventados).
    assert all(p["motivo"] for p in pend)
    assert all(p["nombre"] for p in pend)
