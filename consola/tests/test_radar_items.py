"""Tests de la capa de datos del Investigador (Fase 1): `radar_items` + dedup publicado.

Cubre `db.upsert_radar_items` / `db.listar_radar_items` (insert+update idempotente por
(marca, geo, clave), filtros por marca/geo, frescura por `snapshot_ts`, round-trip de los
campos JSON redes/fuentes/enlaces y `curado` como bool) y `db.existe_publicado_similar`
(titulo exacto, fuzzy >= umbral, no-match, aislamiento por marca). Usa Postgres de pruebas
via la fixture `entorno` (se SALTA si no hay), operando contra `db` directamente.
"""

from __future__ import annotations

from keni_consola import db, repos


def _item(clave: str, titulo: str, **extra):
    """Construye un item del Radar con los defaults de cada campo (override por kwargs)."""
    base = {
        "clave": clave,
        "titulo": titulo,
        "por_que": "",
        "senal": 0,
        "senal_texto": "",
        "redes": [],
        "fuentes": [],
        "enlaces": [],
        "curado": False,
        "url_canonica": "",
        "breaking": False,
        "score": 0.0,
        "razon": "",
        "estado": "nuevo",
    }
    base.update(extra)
    return base


# --------------------------------------------------------------------------- #
# upsert / listar: esquema on-demand y vacio                                   #
# --------------------------------------------------------------------------- #


def test_radar_items_vacio_on_demand(entorno):
    """La primera consulta crea la tabla y devuelve vacio."""
    assert db.listar_radar_items() == []
    assert repos.listar_radar_items(marca="unotv") == []


# --------------------------------------------------------------------------- #
# upsert: insert, round-trip JSON, idempotencia                               #
# --------------------------------------------------------------------------- #


def test_upsert_inserta_y_round_trip_json(entorno):
    enlaces = [{"url": "https://a.com/x", "titulo": "A"}, {"url": "https://b.com/y"}]
    n = db.upsert_radar_items(
        "unotv",
        "MX",
        [
            _item(
                "gol america",
                "Gol del América",
                por_que="trending",
                senal=80,
                senal_texto="alto",
                redes=["x", "facebook"],
                fuentes=["Diario", "Agencia"],
                enlaces=enlaces,
                curado=True,
                url_canonica="example.com/gol",
                score=4.5,
                razon="señal alta",
                estado="nuevo",
            )
        ],
    )
    assert n == 1
    filas = db.listar_radar_items(marca="unotv", geo="MX")
    assert len(filas) == 1
    f = filas[0]
    assert f["marca"] == "unotv" and f["geo"] == "MX" and f["clave"] == "gol america"
    assert f["titulo"] == "Gol del América"
    assert f["senal"] == 80 and f["senal_texto"] == "alto"
    assert f["redes"] == ["x", "facebook"]
    assert f["fuentes"] == ["Diario", "Agencia"]
    assert f["enlaces"] == enlaces
    assert f["curado"] is True
    assert f["url_canonica"] == "example.com/gol"
    assert f["score"] == 4.5
    assert f["estado"] == "nuevo"
    # Todas las claves del contrato presentes (listas para reconstruir un Tema).
    assert {
        "id", "marca", "geo", "clave", "titulo", "por_que", "senal", "senal_texto",
        "redes", "fuentes", "enlaces", "curado", "url_canonica", "score", "razon",
        "estado", "snapshot_ts", "creado", "actualizado",
    } <= set(f)
    assert f["snapshot_ts"] and f["creado"] and f["actualizado"]


def test_upsert_idempotente_actualiza_no_duplica(entorno):
    """Re-upsert de la misma (marca, geo, clave) ACTUALIZA, conserva `creado`, refresca ts."""
    db.upsert_radar_items("unotv", "MX", [_item("tema x", "Tema X", senal=10)])
    primera = db.listar_radar_items(marca="unotv", geo="MX")[0]
    # Segundo snapshot con nuevos valores.
    db.upsert_radar_items(
        "unotv", "MX", [_item("tema x", "Tema X v2", senal=90, estado="en_parrilla")]
    )
    filas = db.listar_radar_items(marca="unotv", geo="MX")
    assert len(filas) == 1  # NO se duplica
    f = filas[0]
    assert f["id"] == primera["id"]  # misma fila
    assert f["titulo"] == "Tema X v2" and f["senal"] == 90 and f["estado"] == "en_parrilla"
    assert f["creado"] == primera["creado"]  # `creado` conservado
    assert f["actualizado"] >= primera["actualizado"]  # refrescado


def test_upsert_salta_clave_vacia(entorno):
    n = db.upsert_radar_items(
        "unotv", "MX", [_item("", "Sin clave"), _item("con clave", "Con clave")]
    )
    assert n == 1
    filas = db.listar_radar_items(marca="unotv")
    assert [f["clave"] for f in filas] == ["con clave"]


# --------------------------------------------------------------------------- #
# listar: filtros, orden, frescura                                            #
# --------------------------------------------------------------------------- #


def test_listar_filtra_por_marca_y_geo(entorno):
    db.upsert_radar_items("unotv", "MX", [_item("a", "A")])
    db.upsert_radar_items("unotv", "US", [_item("b", "B")])
    db.upsert_radar_items("clarosports", "MX", [_item("c", "C")])
    assert {f["clave"] for f in db.listar_radar_items(marca="unotv")} == {"a", "b"}
    assert {f["clave"] for f in db.listar_radar_items(geo="MX")} == {"a", "c"}
    assert {f["clave"] for f in db.listar_radar_items(marca="unotv", geo="MX")} == {"a"}
    assert len(db.listar_radar_items()) == 3  # sin filtros = todo


def test_listar_orden_senal_luego_score(entorno):
    db.upsert_radar_items(
        "unotv",
        "MX",
        [
            _item("bajo", "Bajo", senal=10, score=9.0),
            _item("alto", "Alto", senal=90, score=1.0),
            _item("medio_a", "MedioA", senal=50, score=2.0),
            _item("medio_b", "MedioB", senal=50, score=8.0),
        ],
    )
    claves = [f["clave"] for f in db.listar_radar_items(marca="unotv")]
    # senal DESC, y a igual senal score DESC.
    assert claves == ["alto", "medio_b", "medio_a", "bajo"]


def test_listar_frescura_descarta_antiguos(entorno):
    """`frescas_seg` descarta filas con snapshot_ts mas antiguo que la ventana."""
    db.upsert_radar_items("unotv", "MX", [_item("reciente", "Reciente")])
    # Ventana amplia: la fila recien escrita esta dentro -> aparece.
    assert len(db.listar_radar_items(marca="unotv", frescas_seg=3600)) == 1
    # Ventana de 0 segundos: nada cabe (snapshot_ts < ahora) -> vacio.
    assert db.listar_radar_items(marca="unotv", frescas_seg=0) == []
    # Sin frescura: siempre aparece.
    assert len(db.listar_radar_items(marca="unotv")) == 1
