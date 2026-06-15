"""Pool único (Ola E): los `procesar` de cajones e investigación ALSO escriben `noticias_items`.

PURO: no toca BD. Parchea los repos (insumo/candidato/noticias) para capturar las inserciones y
verifica que AMBAS tablas reciben filas a partir de la salida del worker. Cubre además los
constructores puros de fila de pool (incl. la exclusión de EVENTOS y la clave de dedup).
"""

from __future__ import annotations

import json

from keni_consola import repos
from keni_consola.dominio import ingesta as dom_ingesta
from keni_consola.dominio import recibir_parse

# --------------------------------------------------------------------------- #
# Constructores puros de fila de pool                                          #
# --------------------------------------------------------------------------- #


def test_noticia_item_de_insumo_basico():
    fila = dom_ingesta.noticia_item_de_insumo({
        "cajon": "portal",
        "marca": "unotv",
        "titulo": "Sismo en CDMX",
        "resumen": "Detalle",
        "linea": "ultima-hora",
        "idioma": "es",
        "fecha": "2026-06-05",
        "tipo": "nota",
    })
    assert fila is not None
    assert fila["fuente_id"] == "cajon-portal"
    assert fila["marca"] == "unotv"
    assert fila["titulo"] == "Sismo en CDMX"
    assert fila["senal"] == dom_ingesta.SENAL_CURADO
    assert fila["clave"]  # hash de título (no vacío)


def test_noticia_item_de_insumo_evento_no_entra():
    assert dom_ingesta.noticia_item_de_insumo({
        "cajon": "eventos_claro", "titulo": "Partido", "tipo": "evento",
    }) is None


def test_noticia_item_de_insumo_sin_titulo_no_entra():
    assert dom_ingesta.noticia_item_de_insumo({"cajon": "portal", "titulo": "  ", "tipo": "nota"}) is None


# --------------------------------------------------------------------------- #
# procesar de CAJONES escribe AMBAS tablas                                     #
# --------------------------------------------------------------------------- #


def _capturas(monkeypatch):
    """Parchea los repos para capturar las inserciones (sin BD). Devuelve los buffers."""
    insumos: list[list[dict]] = []
    noticias: list[list[dict]] = []
    lotes: list[tuple] = []
    monkeypatch.setattr(repos, "crear_insumo_items", lambda items: (insumos.append(items) or items))
    monkeypatch.setattr(repos, "crear_noticias_items", lambda items: (noticias.append(items) or len(items)))
    monkeypatch.setattr(repos, "actualizar_insumo_lote", lambda lote_id, campos: lotes.append((lote_id, campos)))
    return {"insumos": insumos, "noticias": noticias, "lotes": lotes}


def test_procesar_cajon_escribe_insumos_y_noticias(monkeypatch):
    cap = _capturas(monkeypatch)
    salida = json.dumps({"items": [
        {"titulo": "Nota A", "marca": "unotv", "tipo": "nota", "resumen": "r"},
        {"titulo": "Partido X", "marca": "claro-sports", "tipo": "evento"},
    ]})
    procesar = recibir_parse.construir_procesar_insumos(
        lote_id="l1", cajon="portal", fecha="2026-06-05"
    )
    res = procesar(salida, None)
    assert res["estado"] == "listo"
    # insumos_item: ambas (nota + evento) entran a su tabla propia
    assert len(cap["insumos"]) == 1
    assert len(cap["insumos"][0]) == 2
    # noticias_items: SOLO la nota (el evento NO entra al pool)
    assert len(cap["noticias"]) == 1
    pool = cap["noticias"][0]
    assert len(pool) == 1
    assert pool[0]["titulo"] == "Nota A"
    assert pool[0]["fuente_id"] == "cajon-portal"


def test_procesar_cajon_salida_basura_no_escribe_pool(monkeypatch):
    cap = _capturas(monkeypatch)
    procesar = recibir_parse.construir_procesar_insumos(
        lote_id="l2", cajon="portal", fecha="2026-06-05"
    )
    res = procesar("lo siento, nada", None)
    assert res["estado"] == "error"
    assert cap["noticias"] == []  # sin items, no se vuelca al pool


