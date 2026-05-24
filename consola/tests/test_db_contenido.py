"""Tests de la capa SQLite de las features nuevas: imagen en publicaciones, grupos
de hashtags y franjas. OFFLINE, base en tmp.
"""

from __future__ import annotations

import sqlite3

import pytest

from keni_consola import db


@pytest.fixture
def base(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_CONSOLA_DB", str(tmp_path / "consola.db"))
    monkeypatch.setenv("KENI_CONSOLA_TAREAS", str(tmp_path / "tareas.json"))
    return tmp_path


# --------------------------------------------------------------------------- #
# Columna imagen en publicaciones                                             #
# --------------------------------------------------------------------------- #


def test_publicacion_imagen_default_vacia(base):
    p = db.crear_publicacion("unotv", "x", titulo="T")
    assert p["imagen"] == ""
    assert db.obtener_publicacion(p["id"])["imagen"] == ""


def test_publicacion_imagen_se_guarda(base):
    p = db.crear_publicacion("unotv", "x", imagen="abc.png")
    assert db.obtener_publicacion(p["id"])["imagen"] == "abc.png"


def test_publicacion_imagen_editable(base):
    p = db.crear_publicacion("unotv", "x")
    act = db.actualizar_publicacion(p["id"], {"imagen": "nueva.webp"})
    assert act["imagen"] == "nueva.webp"


def test_migracion_columna_imagen_en_base_vieja(base):
    """Una base sin la columna `imagen` se migra con ALTER TABLE de forma idempotente."""
    ruta = db.ruta_db()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(ruta))
    try:
        # Tabla "vieja" sin la columna imagen.
        con.execute(
            "CREATE TABLE publicaciones (id TEXT PRIMARY KEY, titulo TEXT, marca TEXT, "
            "red TEXT, contenido TEXT, estado TEXT, veredicto TEXT, fecha_creacion TEXT, "
            "fecha_actualizacion TEXT, fecha_programada TEXT, origen TEXT)"
        )
        con.execute(
            "INSERT INTO publicaciones (id, marca, red) VALUES ('viejo', 'unotv', 'x')"
        )
        con.commit()
    finally:
        con.close()
    # Al usar db (que conecta -> crea esquema -> migra), la columna aparece.
    pub = db.obtener_publicacion("viejo")
    assert pub is not None
    assert pub["imagen"] == ""


# --------------------------------------------------------------------------- #
# Grupos de hashtags                                                          #
# --------------------------------------------------------------------------- #


def test_grupos_hashtags_se_crean_on_demand(base):
    assert db.listar_grupos_hashtags() == []
    con = sqlite3.connect(str(db.ruta_db()))
    try:
        tablas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()
    assert "grupos_hashtags" in tablas
    assert "franjas" in tablas


def test_crear_y_listar_grupo_hashtags(base):
    g = db.crear_grupo_hashtags("Deportes", marca="unotv", hashtags=["#gol", "#liga"])
    assert g["id"]
    assert g["hashtags"] == ["#gol", "#liga"]
    leido = db.obtener_grupo_hashtags(g["id"])
    assert leido["nombre"] == "Deportes"
    assert leido["marca"] == "unotv"
    assert leido["hashtags"] == ["#gol", "#liga"]


def test_grupo_hashtags_filtra_no_strings(base):
    g = db.crear_grupo_hashtags("X", hashtags=["#a", 5, None, "#b"])  # type: ignore[list-item]
    assert g["hashtags"] == ["#a", "#b"]


def test_actualizar_grupo_hashtags_parcial(base):
    g = db.crear_grupo_hashtags("Viejo", marca="unotv", hashtags=["#a"])
    act = db.actualizar_grupo_hashtags(g["id"], {"nombre": "Nuevo", "hashtags": ["#x", "#y"]})
    assert act["nombre"] == "Nuevo"
    assert act["hashtags"] == ["#x", "#y"]
    assert act["marca"] == "unotv"  # no tocado


def test_actualizar_grupo_inexistente(base):
    assert db.actualizar_grupo_hashtags("noexiste", {"nombre": "Z"}) is None


def test_borrar_grupo_hashtags(base):
    g = db.crear_grupo_hashtags("Borrar")
    assert db.borrar_grupo_hashtags(g["id"]) is True
    assert db.obtener_grupo_hashtags(g["id"]) is None
    assert db.borrar_grupo_hashtags(g["id"]) is False


# --------------------------------------------------------------------------- #
# Franjas                                                                     #
# --------------------------------------------------------------------------- #


def test_crear_y_listar_franja(base):
    f = db.crear_franja(2, "09:00", marca="unotv", red="x")
    assert f["id"]
    assert f["dia_semana"] == 2
    assert f["hora"] == "09:00"
    franjas = db.listar_franjas()
    assert len(franjas) == 1
    assert franjas[0]["marca"] == "unotv"
    assert franjas[0]["red"] == "x"


def test_listar_franjas_orden_determinista(base):
    db.crear_franja(4, "08:00")
    db.crear_franja(1, "12:00")
    db.crear_franja(1, "09:00")
    orden = [(f["dia_semana"], f["hora"]) for f in db.listar_franjas()]
    assert orden == [(1, "09:00"), (1, "12:00"), (4, "08:00")]


def test_borrar_franja(base):
    f = db.crear_franja(0, "10:00")
    assert db.borrar_franja(f["id"]) is True
    assert db.borrar_franja(f["id"]) is False
