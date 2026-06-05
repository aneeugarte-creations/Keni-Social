"""Pool único (Ola E): los `procesar` de cajones e investigación ALSO escriben `noticias_items`.

PURO: no toca BD. Parchea los repos (insumo/candidato/noticias) para capturar las inserciones y
verifica que AMBAS tablas reciben filas a partir de la salida del worker. Cubre además los
constructores puros de fila de pool (incl. la exclusión de EVENTOS y la clave de dedup).
"""

from __future__ import annotations

import json

from keni_consola import repos
from keni_consola.dominio import ingesta as dom_ingesta
from keni_consola.dominio import insumos_parse, investigacion_agente

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


def test_noticia_item_de_candidato_usa_url_canonica():
    fila = dom_ingesta.noticia_item_de_candidato({
        "titulo": "Nuevo fichaje",
        "enlace": "https://www.ejemplo.com/nota?utm_source=x",
        "marca": "claro-sports",
        "fecha": "2026-06-05",
        "idioma": "es",
        "fuente": "Ejemplo",
    })
    assert fila is not None
    assert fila["fuente_id"] == "investigacion"
    assert fila["url_canonica"]  # canonizada (sin utm)
    assert "utm_source" not in fila["url_canonica"]
    assert fila["clave"] == fila["url_canonica"]


def test_noticia_item_de_candidato_sin_url_usa_hash_titulo():
    fila = dom_ingesta.noticia_item_de_candidato({
        "titulo": "Historia sin enlace", "enlace": "", "marca": "unotv",
    })
    assert fila is not None
    assert fila["clave"].startswith("t:")


# --------------------------------------------------------------------------- #
# procesar de CAJONES escribe AMBAS tablas                                     #
# --------------------------------------------------------------------------- #


def _capturas(monkeypatch):
    """Parchea los repos para capturar las inserciones (sin BD). Devuelve los buffers."""
    insumos: list[list[dict]] = []
    candidatos: list[list[dict]] = []
    noticias: list[list[dict]] = []
    lotes: list[tuple] = []
    monkeypatch.setattr(repos, "crear_insumo_items", lambda items: (insumos.append(items) or items))
    monkeypatch.setattr(repos, "crear_inv_candidatos", lambda items: (candidatos.append(items) or items))
    monkeypatch.setattr(repos, "crear_noticias_items", lambda items: (noticias.append(items) or len(items)))
    monkeypatch.setattr(repos, "actualizar_insumo_lote", lambda lote_id, campos: lotes.append((lote_id, campos)))
    return {"insumos": insumos, "candidatos": candidatos, "noticias": noticias, "lotes": lotes}


def test_procesar_cajon_escribe_insumos_y_noticias(monkeypatch):
    cap = _capturas(monkeypatch)
    salida = json.dumps({"items": [
        {"titulo": "Nota A", "marca": "unotv", "tipo": "nota", "resumen": "r"},
        {"titulo": "Partido X", "marca": "claro-sports", "tipo": "evento"},
    ]})
    procesar = insumos_parse.construir_procesar_insumos(
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
    procesar = insumos_parse.construir_procesar_insumos(
        lote_id="l2", cajon="portal", fecha="2026-06-05"
    )
    res = procesar("lo siento, nada", None)
    assert res["estado"] == "error"
    assert cap["noticias"] == []  # sin items, no se vuelca al pool


# --------------------------------------------------------------------------- #
# procesar de INVESTIGACIÓN escribe AMBAS tablas                               #
# --------------------------------------------------------------------------- #


def test_procesar_investigacion_escribe_candidatos_y_noticias(monkeypatch):
    cap = _capturas(monkeypatch)
    salida = json.dumps({"candidatos": [
        {"titulo": "Tema 1", "enlace": "https://ej.com/1", "resumen": "r"},
        {"titulo": "Tema 2", "enlace": "", "resumen": "r2"},
    ]})
    brief = {"id": "b1", "marca": "claro-sports", "linea": "futbol"}
    procesar = investigacion_agente.construir_procesar_investigacion(
        brief=brief, fecha="2026-06-05"
    )
    res = procesar(salida, None)
    assert res["candidatos"] == 2
    assert len(cap["candidatos"]) == 1
    assert len(cap["candidatos"][0]) == 2
    # noticias_items: ambos candidatos (uno por url, otro por hash de título)
    assert len(cap["noticias"]) == 1
    pool = cap["noticias"][0]
    assert len(pool) == 2
    assert all(p["fuente_id"] == "investigacion" for p in pool)
    assert all(p["marca"] == "claro-sports" for p in pool)


def test_procesar_investigacion_sin_candidatos_no_escribe_pool(monkeypatch):
    cap = _capturas(monkeypatch)
    procesar = investigacion_agente.construir_procesar_investigacion(
        brief={"id": "b1", "marca": "unotv"}, fecha="2026-06-05"
    )
    res = procesar(json.dumps({"candidatos": []}), None)
    assert res["candidatos"] == 0
    assert cap["noticias"] == []
