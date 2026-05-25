"""Tests de la capa SQLite de plantillas, fuentes_rss y la columna `evergreen`.

OFFLINE, base en tmp. Cubre: creacion on-demand de las tablas, CRUD de plantillas y
fuentes RSS, y la migracion/serializacion del `evergreen` en publicaciones.
"""

from __future__ import annotations

import sqlite3

import pytest

from keni_consola import db


@pytest.fixture
def base(monkeypatch, tmp_path):
    """Aisla la DB en tmp (y el tareas.json de migracion, para no tocar el real)."""
    monkeypatch.setenv("KENI_CONSOLA_DB", str(tmp_path / "consola.db"))
    monkeypatch.setenv("KENI_CONSOLA_TAREAS", str(tmp_path / "tareas.json"))
    return tmp_path


# --------------------------------------------------------------------------- #
# Tablas nuevas se crean on-demand                                            #
# --------------------------------------------------------------------------- #


def test_tablas_nuevas_se_crean_on_demand(base):
    assert db.listar_plantillas() == []
    assert db.listar_fuentes_rss() == []
    con = sqlite3.connect(str(db.ruta_db()))
    try:
        tablas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()
    assert "plantillas" in tablas
    assert "fuentes_rss" in tablas


# --------------------------------------------------------------------------- #
# Plantillas CRUD                                                             #
# --------------------------------------------------------------------------- #


def test_plantilla_crear_y_listar(base):
    p = db.crear_plantilla("Saludo", marca="unotv", red="x", contenido="Hola {x}")
    assert p["id"]
    assert p["fecha"]
    leida = db.obtener_plantilla(p["id"])
    assert leida["nombre"] == "Saludo"
    assert leida["marca"] == "unotv"
    assert leida["red"] == "x"
    assert leida["contenido"] == "Hola {x}"
    assert len(db.listar_plantillas()) == 1


def test_plantilla_actualizar_parcial(base):
    p = db.crear_plantilla("Vieja", contenido="c")
    act = db.actualizar_plantilla(p["id"], {"nombre": "Nueva", "campo_raro": "z"})
    assert act["nombre"] == "Nueva"
    assert act["contenido"] == "c"  # intacto


def test_plantilla_actualizar_sin_campos_devuelve_misma(base):
    p = db.crear_plantilla("X")
    act = db.actualizar_plantilla(p["id"], {"campo_raro": "z"})
    assert act is not None
    assert act["nombre"] == "X"


def test_plantilla_actualizar_inexistente(base):
    assert db.actualizar_plantilla("noexiste", {"nombre": "x"}) is None


def test_plantilla_borrar(base):
    p = db.crear_plantilla("X")
    assert db.borrar_plantilla(p["id"]) is True
    assert db.obtener_plantilla(p["id"]) is None
    assert db.borrar_plantilla(p["id"]) is False


def test_plantilla_sql_parametrizado(base):
    malicioso = "'; DROP TABLE plantillas; --"
    p = db.crear_plantilla(malicioso, contenido=malicioso)
    assert db.obtener_plantilla(p["id"])["nombre"] == malicioso
    assert len(db.listar_plantillas()) == 1


# --------------------------------------------------------------------------- #
# Fuentes RSS CRUD                                                            #
# --------------------------------------------------------------------------- #


def test_fuente_crear_y_listar(base):
    f = db.crear_fuente_rss("Diario", "https://example.com/feed.xml", marca="unotv")
    assert f["id"]
    leida = db.obtener_fuente_rss(f["id"])
    assert leida["nombre"] == "Diario"
    assert leida["url"] == "https://example.com/feed.xml"
    assert leida["marca"] == "unotv"
    assert len(db.listar_fuentes_rss()) == 1


def test_fuente_borrar(base):
    f = db.crear_fuente_rss("Diario", "https://example.com/feed.xml")
    assert db.borrar_fuente_rss(f["id"]) is True
    assert db.obtener_fuente_rss(f["id"]) is None
    assert db.borrar_fuente_rss(f["id"]) is False


# --------------------------------------------------------------------------- #
# Columna evergreen en publicaciones                                          #
# --------------------------------------------------------------------------- #


def test_evergreen_existe_y_default_false(base):
    # fuerza la creacion del esquema y comprueba la columna (PRAGMA: r[1] = name)
    assert db.listar_publicaciones() == []
    con = sqlite3.connect(str(db.ruta_db()))
    cols = {r[1] for r in con.execute("PRAGMA table_info(publicaciones)")}
    con.close()
    assert "evergreen" in cols

    p = db.crear_publicacion("unotv", "x", titulo="T")
    assert p["evergreen"] is False
    assert db.obtener_publicacion(p["id"])["evergreen"] is False


def test_evergreen_se_crea_true(base):
    p = db.crear_publicacion("unotv", "x", evergreen=True)
    assert p["evergreen"] is True
    assert db.obtener_publicacion(p["id"])["evergreen"] is True


def test_evergreen_actualizar(base):
    p = db.crear_publicacion("unotv", "x")
    act = db.actualizar_publicacion(p["id"], {"evergreen": True})
    assert act["evergreen"] is True
    act = db.actualizar_publicacion(p["id"], {"evergreen": False})
    assert act["evergreen"] is False


def test_evergreen_filtro(base):
    db.crear_publicacion("unotv", "x", evergreen=True)
    db.crear_publicacion("unotv", "x", evergreen=False)
    assert len(db.listar_publicaciones(evergreen=True)) == 1
    assert len(db.listar_publicaciones(evergreen=False)) == 1
    assert len(db.listar_publicaciones()) == 2


def test_evergreen_migracion_idempotente_base_antigua(base):
    """Una base SIN la columna evergreen recibe el ALTER TABLE al conectar (idempotente)."""
    ruta = str(db.ruta_db())
    con = sqlite3.connect(ruta)
    # Crea una tabla 'publicaciones' antigua: con imagen pero SIN evergreen.
    con.execute(
        """
        CREATE TABLE publicaciones (
            id TEXT PRIMARY KEY, titulo TEXT, marca TEXT, red TEXT, contenido TEXT,
            estado TEXT, veredicto TEXT, fecha_creacion TEXT, fecha_actualizacion TEXT,
            fecha_programada TEXT, origen TEXT, imagen TEXT
        )
        """
    )
    con.commit()
    con.close()
    # Una operacion normal dispara _conectar -> _crear_esquema -> migracion.
    assert db.listar_publicaciones() == []
    con = sqlite3.connect(ruta)
    cols = {r[1] for r in con.execute("PRAGMA table_info(publicaciones)")}
    con.close()
    assert "evergreen" in cols
    # Idempotente: volver a conectar no rompe.
    assert db.listar_publicaciones() == []
