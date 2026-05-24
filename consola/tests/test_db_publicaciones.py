"""Tests de la capa SQLite de publicaciones (`keni_consola.db`). OFFLINE, base en tmp.

Cubre: creacion on-demand de la tabla, CRUD, creacion en lote, filtros del listado,
edicion parcial (solo campos editables + fecha_actualizacion) y SQL parametrizado.
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


def test_tabla_publicaciones_se_crea_on_demand(base):
    assert db.listar_publicaciones() == []
    con = sqlite3.connect(str(db.ruta_db()))
    try:
        tablas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()
    assert "publicaciones" in tablas


def test_crear_y_listar(base):
    p = db.crear_publicacion("unotv", "x", titulo="Hola", contenido="texto")
    assert p["id"]
    assert p["marca"] == "unotv"
    assert p["red"] == "x"
    assert p["estado"] == "borrador"  # default
    assert p["fecha_creacion"]
    assert p["fecha_actualizacion"] == p["fecha_creacion"]
    listadas = db.listar_publicaciones()
    assert len(listadas) == 1
    assert listadas[0]["titulo"] == "Hola"
    assert listadas[0]["contenido"] == "texto"


def test_crear_con_todos_los_campos(base):
    p = db.crear_publicacion(
        "piso-15",
        "instagram",
        titulo="T",
        contenido="C",
        estado="aprobado",
        veredicto="listo",
        fecha_programada="2026-06-01",
        origen="skill:copy-desde-nota",
    )
    leida = db.obtener_publicacion(p["id"])
    assert leida["estado"] == "aprobado"
    assert leida["veredicto"] == "listo"
    assert leida["fecha_programada"] == "2026-06-01"
    assert leida["origen"] == "skill:copy-desde-nota"


def test_obtener_inexistente(base):
    assert db.obtener_publicacion("noexiste") is None


def test_crear_lote(base):
    creadas = db.crear_publicaciones(
        [
            {"marca": "unotv", "red": "x", "contenido": "a"},
            {"marca": "unotv", "red": "instagram", "contenido": "b"},
        ]
    )
    assert len(creadas) == 2
    # ids distintos
    assert creadas[0]["id"] != creadas[1]["id"]
    assert len(db.listar_publicaciones()) == 2


def test_crear_lote_vacio_no_toca_base(base):
    assert db.crear_publicaciones([]) == []
    assert db.listar_publicaciones() == []


def test_filtros_listado(base):
    db.crear_publicacion("unotv", "x", estado="borrador")
    db.crear_publicacion("unotv", "instagram", estado="aprobado")
    db.crear_publicacion("piso-15", "x", estado="borrador")
    assert len(db.listar_publicaciones(marca="unotv")) == 2
    assert len(db.listar_publicaciones(red="x")) == 2
    assert len(db.listar_publicaciones(estado="aprobado")) == 1
    assert len(db.listar_publicaciones(marca="unotv", red="x")) == 1
    assert len(db.listar_publicaciones(marca="piso-15", estado="aprobado")) == 0


def test_actualizar_parcial_toca_solo_editables(base):
    p = db.crear_publicacion("unotv", "x", titulo="Viejo", contenido="c", estado="borrador")
    creacion = p["fecha_creacion"]
    actualizada = db.actualizar_publicacion(
        p["id"],
        {
            "titulo": "Nuevo",
            "estado": "aprobado",
            # campos NO editables: deben ignorarse
            "marca": "piso-15",
            "red": "youtube",
            "veredicto": "hackeado",
            "fecha_creacion": "1999-01-01",
        },
    )
    assert actualizada["titulo"] == "Nuevo"
    assert actualizada["estado"] == "aprobado"
    # los no-editables intactos
    assert actualizada["marca"] == "unotv"
    assert actualizada["red"] == "x"
    assert actualizada["veredicto"] == ""
    assert actualizada["fecha_creacion"] == creacion
    # fecha_actualizacion se toca (puesta a hoy)
    assert actualizada["fecha_actualizacion"]


def test_actualizar_inexistente(base):
    assert db.actualizar_publicacion("noexiste", {"titulo": "x"}) is None


def test_actualizar_sin_campos_editables_solo_fecha(base):
    """Sin campos editables, solo se actualiza fecha_actualizacion (no falla el SQL)."""
    p = db.crear_publicacion("unotv", "x", titulo="T")
    actualizada = db.actualizar_publicacion(p["id"], {"campo_raro": "z"})
    assert actualizada is not None
    assert actualizada["titulo"] == "T"


def test_borrar(base):
    p = db.crear_publicacion("unotv", "x")
    assert db.borrar_publicacion(p["id"]) is True
    assert db.obtener_publicacion(p["id"]) is None
    assert db.borrar_publicacion(p["id"]) is False


def test_sql_parametrizado_no_inyectable(base):
    malicioso = "'; DROP TABLE publicaciones; --"
    p = db.crear_publicacion("unotv", "x", titulo=malicioso)
    assert db.obtener_publicacion(p["id"])["titulo"] == malicioso
    assert len(db.listar_publicaciones()) == 1
