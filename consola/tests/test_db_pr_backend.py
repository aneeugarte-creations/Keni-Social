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


# --------------------------------------------------------------------------- #
# Fuentes RSS v2: columnas nuevas, edicion parcial, salud, migracion          #
# --------------------------------------------------------------------------- #

_COLS_FUENTE_V2 = {
    "activo",
    "incluir",
    "excluir",
    "redes_def",
    "ultima_actualizacion",
    "ultimo_error",
    "ultimo_conteo",
}


def test_fuente_v2_columnas_existen(base):
    assert db.listar_fuentes_rss() == []
    con = sqlite3.connect(str(db.ruta_db()))
    cols = {r[1] for r in con.execute("PRAGMA table_info(fuentes_rss)")}
    con.close()
    assert _COLS_FUENTE_V2 <= cols


def test_fuente_crear_defaults_v2(base):
    f = db.crear_fuente_rss("Diario", "https://example.com/feed.xml")
    assert f["activo"] is True
    assert f["incluir"] == ""
    assert f["excluir"] == ""
    assert f["redes_def"] == ""
    assert f["ultima_actualizacion"] == ""
    assert f["ultimo_error"] == ""
    assert f["ultimo_conteo"] == 0
    leida = db.obtener_fuente_rss(f["id"])
    assert leida["activo"] is True


def test_fuente_crear_con_filtros_y_redes(base):
    f = db.crear_fuente_rss(
        "Diario", "https://x/y", incluir="ia, agentes", excluir="rumor", redes_def='["x"]'
    )
    leida = db.obtener_fuente_rss(f["id"])
    assert leida["incluir"] == "ia, agentes"
    assert leida["excluir"] == "rumor"
    assert leida["redes_def"] == '["x"]'


def test_fuente_actualizar_parcial(base):
    f = db.crear_fuente_rss("Vieja", "https://x/y", marca="unotv")
    act = db.actualizar_fuente_rss(
        f["id"], {"nombre": "Nueva", "activo": False, "incluir": "gol", "campo_raro": "z"}
    )
    assert act["nombre"] == "Nueva"
    assert act["activo"] is False
    assert act["incluir"] == "gol"
    assert act["marca"] == "unotv"  # intacto
    assert act["url"] == "https://x/y"  # intacto


def test_fuente_actualizar_sin_campos_devuelve_misma(base):
    f = db.crear_fuente_rss("X", "https://x/y")
    act = db.actualizar_fuente_rss(f["id"], {"campo_raro": "z"})
    assert act is not None
    assert act["nombre"] == "X"


def test_fuente_actualizar_inexistente(base):
    assert db.actualizar_fuente_rss("noexiste", {"nombre": "x"}) is None


def test_fuente_registrar_salud(base):
    f = db.crear_fuente_rss("X", "https://x/y")
    db.registrar_salud_fuente_rss(f["id"], conteo=5, error="")
    leida = db.obtener_fuente_rss(f["id"])
    assert leida["ultimo_conteo"] == 5
    assert leida["ultimo_error"] == ""
    assert leida["ultima_actualizacion"]  # fecha no vacia
    db.registrar_salud_fuente_rss(f["id"], conteo=0, error="No se pudo contactar con el feed.")
    leida = db.obtener_fuente_rss(f["id"])
    assert leida["ultimo_conteo"] == 0
    assert leida["ultimo_error"] == "No se pudo contactar con el feed."


def test_fuente_v2_migracion_idempotente_base_antigua(base):
    """Una base con `fuentes_rss` antigua (5 cols) recibe los ALTER al conectar."""
    ruta = str(db.ruta_db())
    con = sqlite3.connect(ruta)
    con.execute(
        "CREATE TABLE fuentes_rss (id TEXT PRIMARY KEY, nombre TEXT, url TEXT, "
        "marca TEXT, fecha TEXT)"
    )
    con.execute(
        "INSERT INTO fuentes_rss (id, nombre, url, marca, fecha) VALUES "
        "('viejo', 'Antigua', 'https://x/y', '', '2026-01-01')"
    )
    con.commit()
    con.close()
    # Conectar dispara la migracion idempotente.
    leida = db.obtener_fuente_rss("viejo")
    assert leida is not None
    assert leida["activo"] is True  # default 1: las preexistentes quedan activas
    assert leida["incluir"] == ""
    con = sqlite3.connect(ruta)
    cols = {r[1] for r in con.execute("PRAGMA table_info(fuentes_rss)")}
    con.close()
    assert _COLS_FUENTE_V2 <= cols


# --------------------------------------------------------------------------- #
# Items RSS vistos (dedup / marcar usado)                                     #
# --------------------------------------------------------------------------- #


def test_marcar_item_y_claves_vistas(base):
    assert db.claves_vistas("f1") == set()
    db.marcar_item("f1", "guid-1", True)
    db.marcar_item("f1", "guid-2", True)
    db.marcar_item("f2", "guid-1", True)  # otra fuente, misma clave
    assert db.claves_vistas("f1") == {"guid-1", "guid-2"}
    assert db.claves_vistas("f2") == {"guid-1"}


def test_marcar_item_idempotente(base):
    db.marcar_item("f1", "guid-1", True)
    db.marcar_item("f1", "guid-1", True)  # repetir no duplica (indice UNICO)
    assert db.claves_vistas("f1") == {"guid-1"}


def test_desmarcar_item(base):
    db.marcar_item("f1", "guid-1", True)
    db.marcar_item("f1", "guid-1", False)
    assert db.claves_vistas("f1") == set()
    # desmarcar algo que no existe no rompe
    db.marcar_item("f1", "inexistente", False)


def test_borrar_fuente_limpia_items_vistos(base):
    f = db.crear_fuente_rss("X", "https://x/y")
    db.marcar_item(f["id"], "guid-1", True)
    assert db.claves_vistas(f["id"]) == {"guid-1"}
    db.borrar_fuente_rss(f["id"])
    assert db.claves_vistas(f["id"]) == set()
