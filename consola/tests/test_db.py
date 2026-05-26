"""Tests de la capa SQLite (`keni_consola.db`): dato OPERACIONAL. OFFLINE, base en tmp.

Tras la consolidacion de persistencia (E5/H2), SQLite solo guarda lo operacional:
`tareas` y el apartado `comercial`. El CONTENIDO editorial (publicaciones, historial
de skills, etc.) vive en YAML (`ficheros.py`) y se prueba en `test_ficheros.py`.

Aqui se cubre: creacion on-demand del esquema, CRUD de tareas y la migracion
idempotente del viejo tareas.json a SQLite. El comercial tiene su propio test
(`test_comercial.py`, `test_api_comercial.py`).
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from keni_consola import db


@pytest.fixture
def base(monkeypatch, tmp_path):
    """Aisla la DB (y el tareas.json de migracion) en tmp."""
    monkeypatch.setenv("KENI_CONSOLA_DB", str(tmp_path / "consola.db"))
    monkeypatch.setenv("KENI_CONSOLA_TAREAS", str(tmp_path / "tareas.json"))
    return tmp_path


# --------------------------------------------------------------------------- #
# Esquema on-demand                                                            #
# --------------------------------------------------------------------------- #


def test_esquema_se_crea_on_demand(base):
    # Una primera operacion crea el archivo y las tablas operacionales.
    assert db.listar_tareas() == []
    ruta = db.ruta_db()
    assert ruta.is_file()
    con = sqlite3.connect(str(ruta))
    try:
        tablas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()
    # Solo dato operacional: tareas + comercial. El contenido ya NO vive en SQLite.
    assert {"tareas", "comercial_publicaciones", "comercial_snapshots"} <= tablas
    # Las tablas de CONTENIDO se retiraron del esquema (viven en YAML).
    assert "publicaciones" not in tablas
    assert "skill_historial" not in tablas


def test_ruta_db_respeta_env(base, tmp_path):
    assert db.ruta_db() == tmp_path / "consola.db"


# --------------------------------------------------------------------------- #
# Tareas: CRUD                                                                 #
# --------------------------------------------------------------------------- #


def test_crear_y_listar_tarea(base):
    t = db.crear_tarea("proj1", "Una tarea", "detalle")
    assert t["id"]
    assert t["estado"] == "pendiente"
    assert t["fecha"]
    listadas = db.listar_tareas()
    assert len(listadas) == 1
    assert listadas[0]["titulo"] == "Una tarea"
    assert listadas[0]["detalle"] == "detalle"


def test_obtener_tarea(base):
    t = db.crear_tarea("proj1", "Buscar esta")
    assert db.obtener_tarea(t["id"])["titulo"] == "Buscar esta"
    assert db.obtener_tarea("noexiste") is None


def test_actualizar_estado(base):
    t = db.crear_tarea("proj1", "Cambiar estado")
    actualizada = db.actualizar_estado_tarea(t["id"], "hecha")
    assert actualizada["estado"] == "hecha"
    assert db.obtener_tarea(t["id"])["estado"] == "hecha"
    # Una tarea inexistente devuelve None.
    assert db.actualizar_estado_tarea("noexiste", "hecha") is None


def test_borrar_tarea(base):
    t = db.crear_tarea("proj1", "Borrar")
    assert db.borrar_tarea(t["id"]) is True
    assert db.obtener_tarea(t["id"]) is None
    # Borrar de nuevo: False (ya no existia).
    assert db.borrar_tarea(t["id"]) is False


def test_sql_parametrizado_no_inyectable(base):
    """Un titulo con sintaxis SQL se guarda LITERAL (consultas parametrizadas)."""
    malicioso = "'; DROP TABLE tareas; --"
    t = db.crear_tarea("proj1", malicioso)
    # La tabla sigue viva y el titulo se guardo tal cual.
    assert db.obtener_tarea(t["id"])["titulo"] == malicioso
    assert len(db.listar_tareas()) == 1


# --------------------------------------------------------------------------- #
# Migracion del viejo tareas.json                                              #
# --------------------------------------------------------------------------- #


def _escribir_json(ruta, tareas):
    ruta.write_text(json.dumps({"tareas": tareas}, ensure_ascii=False), encoding="utf-8")


def test_migracion_de_tareas_json(base, tmp_path):
    _escribir_json(
        tmp_path / "tareas.json",
        [
            {
                "id": "abc123",
                "proyecto": "proj1",
                "titulo": "Tarea migrada",
                "detalle": "del json",
                "estado": "hecha",
                "fecha": "2026-05-01",
            }
        ],
    )
    # La primera conexion dispara la migracion.
    tareas = db.listar_tareas()
    assert len(tareas) == 1
    assert tareas[0]["id"] == "abc123"
    assert tareas[0]["titulo"] == "Tarea migrada"
    assert tareas[0]["estado"] == "hecha"


def test_migracion_idempotente(base, tmp_path):
    _escribir_json(
        tmp_path / "tareas.json",
        [{"id": "x1", "proyecto": "p", "titulo": "Una", "estado": "pendiente", "fecha": "2026-01-01"}],
    )
    db.listar_tareas()  # migra
    db.listar_tareas()  # migra de nuevo: no debe duplicar
    assert len(db.listar_tareas()) == 1


def test_migracion_json_invalido_no_crashea(base, tmp_path):
    (tmp_path / "tareas.json").write_text("no es json", encoding="utf-8")
    # No debe lanzar; simplemente no migra nada.
    assert db.listar_tareas() == []


def test_migracion_descarta_entradas_invalidas(base, tmp_path):
    _escribir_json(
        tmp_path / "tareas.json",
        [
            {"id": "ok1", "proyecto": "p", "titulo": "Valida", "estado": "pendiente", "fecha": "2026-01-01"},
            {"id": "", "proyecto": "p", "titulo": "sin id"},  # invalida
            {"titulo": "sin proyecto ni id"},  # invalida
        ],
    )
    tareas = db.listar_tareas()
    assert len(tareas) == 1
    assert tareas[0]["id"] == "ok1"


def test_sin_tareas_json_no_pasa_nada(base):
    # No hay tareas.json: listar devuelve vacio sin error.
    assert db.listar_tareas() == []
