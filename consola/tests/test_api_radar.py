"""Tests de la API del Radar de tendencias (/api/radar). OFFLINE: NUNCA se toca la red.

El radar descarga via `rss._DESCARGADOR` (el mismo punto inyectable del RSS del equipo);
aqui lo parcheamos para NO tocar la red. Cubre:
  - GET radar: consolida Trends + feeds, ordena por señal, marca estado por fuente.
  - Degradacion HONESTA: si Trends falla, sale `disponible=false` con motivo, sin inventar.
  - geo: allowlist (geo invalido cae a MX); `feeds=0` omite los feeds del equipo.
  - fuentes_pendientes siempre presentes (redes aun no cubiertas).
"""

from __future__ import annotations

from keni_consola.api import radar as api_radar
from keni_consola.api import rss

from .conftest import _cliente  # noqa: F401  (usado por la fixture `cliente`)

# IP publica literal: pasa el guard SSRF de las fuentes RSS sin tocar DNS.
_URL_OK = "https://93.184.216.34/feed.xml"

_TRENDS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0"><channel>
  <item>
    <title>junior h</title><ht:approx_traffic>2K+</ht:approx_traffic>
    <ht:news_item>
      <ht:news_item_title>Junior H anuncia gira</ht:news_item_title>
      <ht:news_item_url>https://example.com/jh</ht:news_item_url>
      <ht:news_item_source>Billboard</ht:news_item_source>
    </ht:news_item>
  </item>
  <item>
    <title>fichajes</title><ht:approx_traffic>100+</ht:approx_traffic>
  </item>
</channel></rss>
"""

# Feed RSS 2.0 normal (formato del RSS del equipo): un item.
_FEED_XML = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>Nota del equipo</title>
    <description>resumen de la nota</description>
    <link>https://example.com/nota</link>
    <guid>nota-1</guid>
  </item>
</channel></rss>
"""


def test_radar_solo_trends_sin_feeds(cliente, monkeypatch):
    monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _TRENDS_XML)
    datos = cliente.get("/api/radar?feeds=0").json()
    assert datos["geo"] == "MX"
    # Ordenado por señal desc: junior h (2000) antes que fichajes (100).
    assert [t["titulo"] for t in datos["temas"]] == ["junior h", "fichajes"]
    assert datos["total"] == 2
    # Una sola fuente consultada (Trends), disponible, con su conteo.
    assert len(datos["fuentes"]) == 1
    assert datos["fuentes"][0]["disponible"] is True
    assert datos["fuentes"][0]["conteo"] == 2
    assert datos["fuentes"][0]["red"] == "busquedas-mx"
    # El "por que sube" sale de datos reales del feed.
    junior = datos["temas"][0]
    assert "2K+" in junior["por_que"]
    assert junior["enlaces"][0]["url"] == "https://example.com/jh"
    # Pendientes SIEMPRE presentes (degradacion documentada).
    redes_pend = {p["red"] for p in datos["fuentes_pendientes"]}
    assert {"tiktok", "instagram", "x", "youtube"} <= redes_pend


def test_radar_consolida_trends_y_feeds(cliente, monkeypatch):
    # Da de alta un feed del equipo; el descargador devuelve XML segun la URL.
    cliente.post("/api/rss/fuentes", json={"nombre": "Diario", "url": _URL_OK})

    def fake(url):  # noqa: ANN001
        return _FEED_XML if url == _URL_OK else _TRENDS_XML

    monkeypatch.setattr(rss, "_DESCARGADOR", fake)
    datos = cliente.get("/api/radar").json()  # feeds incluidos por defecto
    titulos = {t["titulo"] for t in datos["temas"]}
    assert {"junior h", "fichajes", "Nota del equipo"} <= titulos
    # Clases de fuente: Trends + el feed del equipo (ambas disponibles) + las agencias
    # (Reuters/AFP, gateadas: aparecen como NO disponibles sin credencial, sin romper nada).
    nombres = {f["nombre"] for f in datos["fuentes"]}
    assert "Diario" in nombres
    assert any(f["red"] == "busquedas-mx" for f in datos["fuentes"])
    # Trends y el feed del equipo SI disponibles (las agencias no, por falta de credencial).
    no_agencias = [f for f in datos["fuentes"] if f["red"] not in ("reuters", "afp")]
    assert all(f["disponible"] for f in no_agencias)
    # Las agencias salen en el listado, gateadas (sin credencial en el entorno de test).
    agencias_red = {f["red"] for f in datos["fuentes"] if f["red"] in ("reuters", "afp")}
    assert agencias_red == {"reuters", "afp"}


def test_radar_trends_caido_degrada_honesto(cliente, monkeypatch):
    def fake(url):  # noqa: ANN001
        raise rss.RSSError("No se pudo contactar con el feed.")

    monkeypatch.setattr(rss, "_DESCARGADOR", fake)
    datos = cliente.get("/api/radar?feeds=0").json()
    # Sin inventar: temas vacio y la fuente lo dice con su motivo.
    assert datos["temas"] == []
    assert datos["total"] == 0
    fuente = datos["fuentes"][0]
    assert fuente["disponible"] is False
    assert "No se pudo contactar" in fuente["motivo"]


def test_radar_feed_caido_no_rompe_trends(cliente, monkeypatch):
    cliente.post("/api/rss/fuentes", json={"nombre": "Roto", "url": _URL_OK})

    def fake(url):  # noqa: ANN001
        if url == _URL_OK:
            raise rss.RSSError("El feed tardó demasiado y se canceló.")
        return _TRENDS_XML

    monkeypatch.setattr(rss, "_DESCARGADOR", fake)
    datos = cliente.get("/api/radar").json()
    # Trends sigue dando temas aunque el feed del equipo falle.
    assert [t["titulo"] for t in datos["temas"]] == ["junior h", "fichajes"]
    roto = next(f for f in datos["fuentes"] if f["nombre"] == "Roto")
    assert roto["disponible"] is False
    assert roto["motivo"]


def test_radar_geo_invalido_cae_a_mx(cliente, monkeypatch):
    monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _TRENDS_XML)
    datos = cliente.get("/api/radar?geo=ZZ&feeds=0").json()
    assert datos["geo"] == "MX"


def test_radar_geo_valido_se_respeta(cliente, monkeypatch):
    capturadas = []

    def fake(url):  # noqa: ANN001
        capturadas.append(url)
        return _TRENDS_XML

    monkeypatch.setattr(rss, "_DESCARGADOR", fake)
    datos = cliente.get("/api/radar?geo=US&feeds=0").json()
    assert datos["geo"] == "US"
    assert any("geo=US" in u for u in capturadas)
    assert datos["fuentes"][0]["red"] == "busquedas-us"


def test_radar_geos_disponibles_en_respuesta(cliente, monkeypatch):
    monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _TRENDS_XML)
    datos = cliente.get("/api/radar?feeds=0").json()
    ids = {g["id"] for g in datos["geos_disponibles"]}
    assert "MX" in ids and "US" in ids


def test_radar_requiere_auth(entorno):
    # Sin token => 401 (igual que el resto de la API tras #134).
    cli = _cliente(autenticar=False)
    assert cli.get("/api/radar").status_code == 401


def test_obtener_url_invalida_no_lanza(monkeypatch):
    # Defensa: si validar_url fallara, la fuente cae a no_disponible (no 500).
    monkeypatch.setattr(api_radar.rss, "validar_url", lambda url: (None, "URL mala."))
    temas, estado = api_radar._radar_trends("MX")
    assert temas == []
    assert estado["disponible"] is False
    assert estado["motivo"] == "URL mala."
