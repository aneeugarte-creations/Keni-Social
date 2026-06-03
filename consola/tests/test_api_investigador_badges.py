"""Tests F2b: badges `estado` y `prioritario` por tema en `/api/radar` y `/api/parrilla-dia`.

El Investigador (F2b) expone, POR CADA TEMA serializado, dos campos ADITIVOS para que el
frontend pinte badges:

  - `estado`: `'nuevo' | 'en_parrilla' | 'publicado'`, calculado AL LEER cruzando el titulo del
    tema contra el estado editorial reciente de la marca (`investigador._estado_por_clave`), asi
    funciona AUNQUE el daemon del Investigador este OFF.
  - `prioritario`: `bool`, `True` si `senal >= investigador.umbral_prioritario()`
    (= `config.radar_auto_umbral()`, def 50000: el mismo umbral "muy viral" del radar-auto).

OFFLINE: el Radar descarga via `rss._DESCARGADOR` (mockeado, sin red); el cruce al tablero lee
via `repos.listar_contenido` (mockeado, sin Postgres). Cero regresion: campos ADITIVOS, los
existentes no cambian.
"""

from __future__ import annotations

import pytest

from keni_consola import config, investigador
from keni_consola import relevancia_marca as relevancia_modulo
from keni_consola import repos as repos_modulo
from keni_consola.api import rss
from keni_consola.dominio import dedup

from .conftest import _cliente  # noqa: F401  (usado por la fixture `cliente`)

# Trends con dos temas: uno MUY viral (60K, sobre el umbral 50K) y uno debil (2K).
_TRENDS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0"><channel>
  <item>
    <title>final del mundial</title><ht:approx_traffic>60K+</ht:approx_traffic>
    <ht:news_item>
      <ht:news_item_title>La gran final</ht:news_item_title>
      <ht:news_item_url>https://example.com/final</ht:news_item_url>
      <ht:news_item_source>Claro Sports</ht:news_item_source>
    </ht:news_item>
  </item>
  <item>
    <title>nota menor</title><ht:approx_traffic>2K+</ht:approx_traffic>
  </item>
</channel></rss>
"""

_MARCA = "claro-sports"


def _sin_foco(monkeypatch):
    """Anula el filtro de foco por marca: asi pasar `marca=` cruza el tablero sin descartar temas.

    El badge `estado` necesita una marca (para cruzar el tablero), pero el foco editorial
    filtraria los temas de Trends que no casan con el vocabulario de la marca. Aqui dejamos el
    vocabulario vacio (sin foco) para que TODOS los temas lleguen a la respuesta y podamos
    verificar sus badges; el cruce al tablero (que SI depende de la marca) se mantiene.
    """
    monkeypatch.setattr(relevancia_modulo, "palabras_de_marca", lambda marca: frozenset())


def _tablero(monkeypatch, items):
    """Mockea `repos.listar_contenido` (lo que lee `_estado_por_clave`) con `items` dados."""
    monkeypatch.setattr(
        repos_modulo, "listar_contenido", lambda **k: items, raising=False
    )


# --------------------------------------------------------------------------- #
# /api/radar                                                                    #
# --------------------------------------------------------------------------- #

def test_radar_cada_tema_trae_estado_y_prioritario(cliente, monkeypatch):
    monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _TRENDS_XML)
    _tablero(monkeypatch, [])
    datos = cliente.get("/api/radar?feeds=0").json()
    assert datos["temas"], "deberia haber temas"
    for tema in datos["temas"]:
        assert "estado" in tema and isinstance(tema["estado"], str)
        assert "prioritario" in tema and isinstance(tema["prioritario"], bool)


def test_radar_prioritario_respeta_el_umbral(cliente, monkeypatch):
    monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _TRENDS_XML)
    _tablero(monkeypatch, [])
    datos = cliente.get("/api/radar?feeds=0").json()
    por_titulo = {t["titulo"]: t for t in datos["temas"]}
    # 60K (>= 50K umbral) -> prioritario; 2K (< umbral) -> NO prioritario.
    assert por_titulo["final del mundial"]["prioritario"] is True
    assert por_titulo["nota menor"]["prioritario"] is False


def test_radar_sin_marca_estado_es_nuevo(cliente, monkeypatch):
    """Sin marca no hay tablero contra el que cruzar: todo cae a 'nuevo' (best-effort)."""
    monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _TRENDS_XML)
    # listar_contenido NO debe consultarse sin marca; si se llamara, devolveria estado.
    def _boom(**k):  # noqa: ANN001, ANN003
        raise AssertionError("no debe cruzar el tablero sin marca")

    monkeypatch.setattr(repos_modulo, "listar_contenido", _boom, raising=False)
    datos = cliente.get("/api/radar?feeds=0").json()
    assert all(t["estado"] == "nuevo" for t in datos["temas"])


def test_radar_estado_refleja_el_tablero(cliente, monkeypatch):
    monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _TRENDS_XML)
    _sin_foco(monkeypatch)
    # 'final del mundial' ya esta PUBLICADO; 'nota menor' esta en el tablero (no publicado).
    _tablero(monkeypatch, [
        {"titulo": "Final del Mundial", "estado": "publicado"},
        {"titulo": "Nota menor", "estado": "borrador"},
    ])
    datos = cliente.get(f"/api/radar?feeds=0&marca={_MARCA}").json()
    por_titulo = {t["titulo"]: t for t in datos["temas"]}
    assert por_titulo["final del mundial"]["estado"] == "publicado"
    assert por_titulo["nota menor"]["estado"] == "en_parrilla"


def test_radar_estado_nuevo_si_no_hay_match(cliente, monkeypatch):
    monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _TRENDS_XML)
    _sin_foco(monkeypatch)
    _tablero(monkeypatch, [{"titulo": "Tema totalmente distinto", "estado": "publicado"}])
    datos = cliente.get(f"/api/radar?feeds=0&marca={_MARCA}").json()
    assert all(t["estado"] == "nuevo" for t in datos["temas"])


def test_radar_degrada_a_nuevo_si_el_tablero_falla(cliente, monkeypatch):
    """Si el cruce al tablero lanza, el endpoint no rompe: `estado='nuevo'` (best-effort)."""
    monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _TRENDS_XML)
    _sin_foco(monkeypatch)

    def _boom(**k):  # noqa: ANN001, ANN003
        raise RuntimeError("tablero caido")

    monkeypatch.setattr(repos_modulo, "listar_contenido", _boom, raising=False)
    resp = cliente.get(f"/api/radar?feeds=0&marca={_MARCA}")
    assert resp.status_code == 200
    datos = resp.json()
    assert datos["temas"]
    assert all(t["estado"] == "nuevo" for t in datos["temas"])


# --------------------------------------------------------------------------- #
# /api/parrilla-dia                                                            #
# --------------------------------------------------------------------------- #

def _items_plan(datos):
    return [*datos["posteos"], *datos["editorial"], *datos["sobrantes"]]


def test_parrilla_cada_item_trae_estado_y_prioritario(cliente, monkeypatch):
    monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _TRENDS_XML)
    _tablero(monkeypatch, [])
    datos = cliente.get("/api/parrilla-dia").json()
    items = _items_plan(datos)
    assert items, "deberia haber items en el plan"
    for it in items:
        assert "estado" in it and isinstance(it["estado"], str)
        assert "prioritario" in it and isinstance(it["prioritario"], bool)


def test_parrilla_prioritario_respeta_el_umbral(cliente, monkeypatch):
    # Temas por body con señales a ambos lados del umbral (sin red para el Radar).
    _tablero(monkeypatch, [])
    body = {
        "temas": [
            {"titulo": "Tema muy viral", "senal": 70000},
            {"titulo": "Tema flojo", "senal": 1000},
        ]
    }
    datos = cliente.post("/api/parrilla-dia", json=body).json()
    por_titulo = {it["titulo"]: it for it in _items_plan(datos)}
    assert por_titulo["Tema muy viral"]["prioritario"] is True
    assert por_titulo["Tema flojo"]["prioritario"] is False


def test_parrilla_estado_refleja_el_tablero(cliente, monkeypatch):
    _sin_foco(monkeypatch)
    _tablero(monkeypatch, [
        {"titulo": "Tema A", "estado": "publicado"},
        {"titulo": "Tema B", "estado": "programado"},
    ])
    body = {
        "marca": _MARCA,
        "temas": [
            {"titulo": "Tema A", "senal": 5000},
            {"titulo": "Tema B", "senal": 5000},
            {"titulo": "Tema C nuevo", "senal": 5000},
        ],
    }
    datos = cliente.post("/api/parrilla-dia", json=body).json()
    por_titulo = {it["titulo"]: it for it in _items_plan(datos)}
    assert por_titulo["Tema A"]["estado"] == "publicado"
    assert por_titulo["Tema B"]["estado"] == "en_parrilla"
    assert por_titulo["Tema C nuevo"]["estado"] == "nuevo"


def test_parrilla_degrada_a_nuevo_si_el_tablero_falla(cliente, monkeypatch):
    _sin_foco(monkeypatch)

    def _boom(**k):  # noqa: ANN001, ANN003
        raise RuntimeError("tablero caido")

    monkeypatch.setattr(repos_modulo, "listar_contenido", _boom, raising=False)
    body = {"marca": _MARCA, "temas": [{"titulo": "Tema X", "senal": 5000}]}
    resp = cliente.post("/api/parrilla-dia", json=body)
    assert resp.status_code == 200
    items = _items_plan(resp.json())
    assert items and all(it["estado"] == "nuevo" for it in items)


# --------------------------------------------------------------------------- #
# Umbral: fuente backend (radar-auto) y respuesta a config                      #
# --------------------------------------------------------------------------- #

def test_umbral_prioritario_es_el_del_radar_auto(monkeypatch):
    """El umbral de `prioritario` REUSA `config.radar_auto_umbral()` (un solo numero backend)."""
    monkeypatch.setattr(config, "radar_auto_umbral", lambda: 12345)
    assert investigador.umbral_prioritario() == 12345
    assert investigador.prioritario_de_senal(12345) is True
    assert investigador.prioritario_de_senal(12344) is False
    # Tipos raros no rompen (best-effort).
    assert investigador.prioritario_de_senal("no-num") is False


def test_anotar_es_aditivo_y_una_sola_query(monkeypatch):
    """`anotar_estado_prioritario` cruza el tablero UNA vez y no toca los campos existentes."""
    llamadas = {"n": 0}

    def _listar(**k):  # noqa: ANN001, ANN003
        llamadas["n"] += 1
        return [{"titulo": "Tema uno", "estado": "publicado"}]

    monkeypatch.setattr(repos_modulo, "listar_contenido", _listar, raising=False)
    temas = [
        {"titulo": "Tema uno", "senal": 99999, "razon": "x"},
        {"titulo": "Tema dos", "senal": 1, "razon": "y"},
    ]
    investigador.anotar_estado_prioritario(temas, _MARCA)
    # UNA sola query al tablero para todos los temas (no N+1).
    assert llamadas["n"] == 1
    # Campos existentes intactos.
    assert temas[0]["razon"] == "x" and temas[1]["razon"] == "y"
    assert dedup.clave("Tema uno")  # sanity: la clave no es vacia
    assert temas[0]["estado"] == "publicado"
    assert temas[1]["estado"] == "nuevo"
