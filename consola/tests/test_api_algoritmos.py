"""Tests de la API de Algoritmos (/api/algoritmos). OFFLINE: NUNCA se toca la red.

La ingesta descarga via `rss._DESCARGADOR` (mismo punto inyectable del RSS); aquí lo
parcheamos para no tocar la red, y usamos una URL con IP pública LITERAL para pasar el
guard SSRF sin resolver DNS. Cubre: alta de fuente, ingesta + clasificación, filtros,
propuesta a texto, archivar y la siembra de fuentes recomendadas.
"""

from __future__ import annotations

from keni_consola.api import rss

from .conftest import _cliente  # noqa: F401  (usado por la fixture `cliente`)

# IP pública literal: pasa el guard SSRF sin tocar DNS (igual que el test del Radar).
_URL_OK = "https://93.184.216.34/feed.xml"

# Feed con DOS items: uno es un cambio de algoritmo (alta) y otro una nota menor (baja).
_FEED_ALGO = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>Instagram updates its ranking algorithm: Reels reach changes</title>
    <description>The platform changes how the feed ranks Reels and distribution.</description>
    <link>https://example.com/ig-ranking</link>
    <guid>ig-ranking-1</guid>
    <pubDate>2026-05-01</pubDate>
  </item>
  <item>
    <title>Messenger gets a small design tweak</title>
    <description>A minor visual change for chats.</description>
    <link>https://example.com/messenger</link>
    <guid>messenger-1</guid>
  </item>
</channel></rss>
"""


def _alta_fuente(cliente, **extra):
    """Da de alta una fuente con URL de IP literal (SSRF-safe) y la devuelve."""
    cuerpo = {"nombre": "Agregador", "url": _URL_OK, "plataforma": "general", "tipo": "agregador"}
    cuerpo.update(extra)
    return cliente.post("/api/algoritmos/fuentes", json=cuerpo).json()["fuente"]


def test_listar_vacio_trae_vocabulario_y_pendientes(cliente):
    datos = cliente.get("/api/algoritmos").json()
    assert datos["noticias"] == []
    assert datos["fuentes"] == []
    # Vocabulario para los selectores de la UI.
    ids_plat = {p["id"] for p in datos["plataformas"]}
    assert {"instagram", "tiktok", "youtube", "general"} <= ids_plat
    assert "alta" in datos["niveles"]
    # Huecos honestos (redes sin feed oficial) siempre presentes.
    assert {p["plataforma"] for p in datos["pendientes"]} >= {"tiktok", "instagram", "x"}


def test_ingesta_clasifica_y_ordena_por_importancia(cliente, monkeypatch):
    _alta_fuente(cliente)
    monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _FEED_ALGO)

    resumen = cliente.post("/api/algoritmos/refrescar", json={}).json()["resumen"]
    assert resumen["insertadas"] == 2
    assert resumen["errores"] == []

    noticias = cliente.get("/api/algoritmos").json()["noticias"]
    assert len(noticias) == 2
    # Ordenadas por importancia desc: el cambio de algoritmo va primero.
    primera = noticias[0]
    assert "ranking algorithm" in primera["titulo"]
    assert primera["plataforma"] == "instagram"
    assert primera["nivel"] == "alta"
    assert primera["es_cambio"] is True
    assert primera["senales"]  # el "por qué" (palabras que dispararon el score)


def test_ingesta_es_idempotente_por_dedup(cliente, monkeypatch):
    _alta_fuente(cliente)
    monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _FEED_ALGO)
    cliente.post("/api/algoritmos/refrescar", json={})
    resumen = cliente.post("/api/algoritmos/refrescar", json={}).json()["resumen"]
    # Segunda pasada: misma clave => actualiza, no duplica.
    assert resumen["insertadas"] == 0
    assert resumen["actualizadas"] == 2
    assert len(cliente.get("/api/algoritmos").json()["noticias"]) == 2


def test_filtros_por_plataforma_nivel_y_solo_cambios(cliente, monkeypatch):
    _alta_fuente(cliente)
    monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _FEED_ALGO)
    cliente.post("/api/algoritmos/refrescar", json={})

    solo_ig = cliente.get("/api/algoritmos?plataforma=instagram").json()["noticias"]
    assert all(n["plataforma"] == "instagram" for n in solo_ig)
    assert len(solo_ig) == 1

    alta = cliente.get("/api/algoritmos?nivel=alta").json()["noticias"]
    assert all(n["nivel"] == "alta" for n in alta)

    cambios = cliente.get("/api/algoritmos?solo_cambios=1").json()["noticias"]
    assert cambios and all(n["es_cambio"] for n in cambios)


def test_proponer_a_texto_marca_aplicada_y_devuelve_borrador(cliente, monkeypatch):
    _alta_fuente(cliente)
    monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _FEED_ALGO)
    cliente.post("/api/algoritmos/refrescar", json={})
    noticia = cliente.get("/api/algoritmos").json()["noticias"][0]

    r = cliente.post(f"/api/algoritmos/{noticia['id']}/texto", json={}).json()
    assert r["propuesta"]  # borrador markdown no vacío
    assert noticia["titulo"] in r["propuesta"]
    assert r["noticia"]["aplicada"] is True


def test_archivar_oculta_la_noticia(cliente, monkeypatch):
    _alta_fuente(cliente)
    monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _FEED_ALGO)
    cliente.post("/api/algoritmos/refrescar", json={})
    noticia = cliente.get("/api/algoritmos").json()["noticias"][0]

    cliente.post(f"/api/algoritmos/{noticia['id']}/archivar", json={"archivada": True})
    visibles = cliente.get("/api/algoritmos").json()["noticias"]
    assert noticia["id"] not in {n["id"] for n in visibles}
    # Con incluir_archivadas=1 vuelve a aparecer.
    todas = cliente.get("/api/algoritmos?incluir_archivadas=1").json()["noticias"]
    assert noticia["id"] in {n["id"] for n in todas}


def test_fuente_crud_y_validacion_url(cliente):
    # URL inválida (esquema no http) => 400.
    bad = cliente.post(
        "/api/algoritmos/fuentes", json={"nombre": "X", "url": "ftp://x/y"}
    )
    assert bad.status_code == 400

    fuente = _alta_fuente(cliente)
    # Desactivar.
    upd = cliente.put(
        f"/api/algoritmos/fuentes/{fuente['id']}", json={"activo": False}
    ).json()["fuente"]
    assert upd["activo"] is False
    # Borrar.
    assert cliente.delete(f"/api/algoritmos/fuentes/{fuente['id']}").status_code == 200
    assert cliente.get("/api/algoritmos").json()["fuentes"] == []


def test_sembrar_crea_recomendadas_y_es_idempotente(cliente):
    creadas = cliente.post("/api/algoritmos/sembrar", json={}).json()
    assert creadas["total"] == 4
    assert len(cliente.get("/api/algoritmos").json()["fuentes"]) == 4
    # Segunda siembra no duplica (idempotente por URL).
    de_nuevo = cliente.post("/api/algoritmos/sembrar", json={}).json()
    assert de_nuevo["total"] == 0


def test_plataforma_invalida_en_filtro_da_400(cliente):
    assert cliente.get("/api/algoritmos?plataforma=myspace").status_code == 400
