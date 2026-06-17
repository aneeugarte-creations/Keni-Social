"""Tests de Google Trends como fuente del pool (dominio + daemon). OFFLINE.

Cubre:
  - `traduce_trafico`: "2K+"/"50 mil+" -> entero comparable; basura -> 0.
  - `parsear_trends_items`: aplana los `ht:news_item` a items de pool reales (titulo/url/
    fuente), con la señal del término y categoría 'tendencias'; dedup por clave.
  - `trends_daemon.ejecutar_barrido`: descarga (mock) + parsea + inserta en el pool.
"""

from __future__ import annotations

import pytest

from keni_consola import trends_daemon
from keni_consola.dominio import http_feed
from keni_consola.dominio import trends as dom

# Feed de Google Trends mínimo pero realista: 2 términos con ht:approx_traffic + sus noticias.
_TRENDS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0">
  <channel>
    <title>Daily Search Trends</title>
    <item>
      <title>Selección Mexicana</title>
      <ht:approx_traffic>50 mil+</ht:approx_traffic>
      <ht:news_item>
        <ht:news_item_title>El Tri convoca para el amistoso</ht:news_item_title>
        <ht:news_item_url>https://example.com/tri?utm_source=x</ht:news_item_url>
        <ht:news_item_source>ESPN</ht:news_item_source>
      </ht:news_item>
      <ht:news_item>
        <ht:news_item_title>Lista de convocados sorpresa</ht:news_item_title>
        <ht:news_item_url>https://example.com/convocados</ht:news_item_url>
        <ht:news_item_source>Récord</ht:news_item_source>
      </ht:news_item>
    </item>
    <item>
      <title>Nuevo videojuego</title>
      <ht:approx_traffic>2K+</ht:approx_traffic>
      <ht:news_item>
        <ht:news_item_title>Anuncian secuela esperada</ht:news_item_title>
        <ht:news_item_url>https://example.com/juego</ht:news_item_url>
        <ht:news_item_source>IGN</ht:news_item_source>
      </ht:news_item>
    </item>
  </channel>
</rss>
"""


@pytest.mark.parametrize(
    ("crudo", "esperado"),
    [
        ("2K+", 2_000), ("50 mil+", 50_000), ("1M+", 1_000_000), ("1,000+", 1_000),
        # Separador DECIMAL (1-2 dígitos al final): "1.5M" es 1.5 millones, NO 15 millones.
        ("1.5M+", 1_500_000), ("1,5 millones+", 1_500_000), ("2.25M+", 2_250_000),
        # Tres dígitos tras el punto = millares, como siempre.
        ("1.000+", 1_000),
        ("", 0), ("?", 0),
    ],
)
def test_traduce_trafico(crudo, esperado):
    assert dom.traduce_trafico(crudo) == esperado


def test_parsear_trends_aplana_noticias():
    items = dom.parsear_trends_items(_TRENDS_XML, geo="MX")
    # 3 noticias en total (2 del primer término + 1 del segundo).
    assert len(items) == 3
    titulos = {i["titulo"] for i in items}
    assert "El Tri convoca para el amistoso" in titulos
    assert "Anuncian secuela esperada" in titulos
    primero = next(i for i in items if i["titulo"] == "El Tri convoca para el amistoso")
    assert primero["fuente_id"] == "google-trends"
    assert primero["fuente_nombre"] == "ESPN"
    assert primero["categoria"] == "tendencias"
    assert primero["senal"] == 50_000  # tráfico del término
    assert "utm_source" not in primero["url_canonica"]  # canonizada
    assert "Selección Mexicana" in primero["resumen"]


def test_parsear_trends_dedup_por_clave():
    xml = _TRENDS_XML.replace("https://example.com/juego", "https://example.com/tri")
    items = dom.parsear_trends_items(xml, geo="MX")
    # La url repetida (tri) se deduplica: queda 1 'tri' + 1 'convocados' = 2.
    assert len(items) == 2


def test_parsear_trends_xml_invalido_lanza():
    with pytest.raises(http_feed.RSSError):
        dom.parsear_trends_items("esto no es xml <<<", geo="MX")


def test_daemon_barrido_descarga_parsea_inserta(monkeypatch):
    monkeypatch.setattr(trends_daemon, "_DESCARGADOR", lambda url: _TRENDS_XML)
    monkeypatch.setattr(http_feed, "validar_url", lambda u: (u, None))
    monkeypatch.setattr("keni_consola.repos.claves_existentes_directas", lambda *a, **k: set())
    insertados: list[list[dict]] = []
    monkeypatch.setattr(
        "keni_consola.repos.crear_noticias_items",
        lambda items: (insertados.append(items) or len(items)),
    )
    monkeypatch.setattr("keni_consola.config.trends_geos", lambda: ("MX",))
    total = trends_daemon.ejecutar_barrido()
    assert total == 3
    assert len(insertados) == 1
    assert all(i["fuente_id"] == "google-trends" for i in insertados[0])


def test_daemon_barrido_dedup_contra_rss_directo(monkeypatch):
    """Una noticia que YA está en el pool por su feed RSS directo (misma url canónica) NO se
    vuelca de nuevo desde Trends: se filtra antes de insertar (no duplica ni infla n_fuentes)."""
    monkeypatch.setattr(trends_daemon, "_DESCARGADOR", lambda url: _TRENDS_XML)
    monkeypatch.setattr(http_feed, "validar_url", lambda u: (u, None))
    monkeypatch.setattr("keni_consola.config.trends_geos", lambda: ("MX",))
    # 'example.com/tri' ya entró por un feed directo -> Trends no debe re-volcarla.
    capturado: dict[str, object] = {}
    monkeypatch.setattr(
        "keni_consola.repos.claves_existentes_directas",
        lambda claves, **kw: (capturado.update(claves=set(claves), kw=kw) or {"example.com/tri"}),
    )
    insertados: list[list[dict]] = []
    monkeypatch.setattr(
        "keni_consola.repos.crear_noticias_items",
        lambda items: (insertados.append(items) or len(items)),
    )
    total = trends_daemon.ejecutar_barrido()
    # De las 3 noticias, la 'tri' (ya en el pool por RSS) se descarta -> se insertan 2.
    assert total == 2
    claves_insertadas = {i["clave"] for i in insertados[0]}
    assert "example.com/tri" not in claves_insertadas
    assert claves_insertadas == {"example.com/convocados", "example.com/juego"}
    # El dedup excluye la propia fuente Trends (para no contarse a sí misma).
    assert capturado["kw"]["excluir_fuente"] == dom.FUENTE_ID


def test_daemon_barrido_feed_caido_no_rompe(monkeypatch):
    def explota(url):
        raise http_feed.RSSError("No se pudo contactar con el feed.")

    monkeypatch.setattr(trends_daemon, "_DESCARGADOR", explota)
    monkeypatch.setattr(http_feed, "validar_url", lambda u: (u, None))
    monkeypatch.setattr("keni_consola.config.trends_geos", lambda: ("MX",))
    assert trends_daemon.ejecutar_barrido() == 0
