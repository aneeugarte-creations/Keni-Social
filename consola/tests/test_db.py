"""Tests de la capa SQLite (`keni_consola.db`). Todo OFFLINE, base en tmp.

Cubre: creacion on-demand del esquema, CRUD de tareas, CRUD del historial de
skills, y la migracion idempotente del viejo tareas.json a SQLite.
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
    # Una primera operacion crea el archivo y las tablas.
    assert db.listar_tareas() == []
    ruta = db.ruta_db()
    assert ruta.is_file()
    con = sqlite3.connect(str(ruta))
    try:
        tablas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()
    assert {"tareas", "skill_historial"} <= tablas


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
# Historial de skills                                                          #
# --------------------------------------------------------------------------- #


def test_registrar_y_listar_historial(base):
    hid = db.registrar_historial_skill("copy-desde-nota", "unotv", "BORRADOR")
    assert hid
    entradas = db.listar_historial_skills()
    assert len(entradas) == 1
    assert entradas[0]["skill"] == "copy-desde-nota"
    assert entradas[0]["marca"] == "unotv"
    assert entradas[0]["resultado"] == "BORRADOR"


def test_obtener_historial_por_id(base):
    hid = db.registrar_historial_skill("clip-a-copy", "piso-15", "RESULTADO completo")
    entrada = db.obtener_historial_skill(hid)
    assert entrada["resultado"] == "RESULTADO completo"
    assert db.obtener_historial_skill("noexiste") is None


def test_historial_recientes_primero(base):
    h1 = db.registrar_historial_skill("copy-desde-nota", "unotv", "primero")
    h2 = db.registrar_historial_skill("copy-desde-nota", "unotv", "segundo")
    ids = [e["id"] for e in db.listar_historial_skills()]
    # El mas reciente (h2) va primero.
    assert ids[0] == h2
    assert ids[1] == h1


def test_historial_guarda_y_devuelve_piezas_y_titulo(base):
    piezas = [
        {"red": "x", "contenido": "tw", "caracteres": 2},
        {"red": "instagram", "contenido": "ig", "caracteres": 2},
    ]
    hid = db.registrar_historial_skill(
        "copy-desde-nota", "unotv", "RES", piezas=piezas, titulo="Mi titulo"
    )
    entrada = db.obtener_historial_skill(hid)
    assert entrada["titulo"] == "Mi titulo"
    assert entrada["piezas"] == piezas
    # El listado tambien las devuelve (parseadas a lista).
    listado = db.listar_historial_skills()
    assert listado[0]["piezas"] == piezas
    assert listado[0]["titulo"] == "Mi titulo"


def test_historial_sin_piezas_devuelve_lista_vacia(base):
    hid = db.registrar_historial_skill("copy-desde-nota", "unotv", "RES")
    entrada = db.obtener_historial_skill(hid)
    assert entrada["piezas"] == []
    assert entrada["titulo"] == ""
    assert entrada["metricas"] is None


def test_historial_guarda_y_devuelve_metricas(base):
    metricas = {
        "tokens_in": 130, "tokens_out": 50, "num_turns": 3,
        "total_cost_usd": 0.0123, "duration_ms": 4200, "modelo": "claude-opus-4-7",
    }
    hid = db.registrar_historial_skill(
        "copy-desde-nota", "unotv", "RES", metricas=metricas
    )
    entrada = db.obtener_historial_skill(hid)
    assert entrada["metricas"] == metricas
    # El listado tambien las devuelve (parseadas a dict).
    assert db.listar_historial_skills()[0]["metricas"] == metricas


def test_historial_filas_antiguas_sin_columnas_devuelven_defaults(base):
    """Una fila preexistente sin piezas/titulo (base antigua) no debe romper la lectura."""
    # Simula una base antigua: tabla sin las columnas nuevas + una fila.
    ruta = db.ruta_db()
    con = sqlite3.connect(str(ruta))
    try:
        con.execute(
            "CREATE TABLE skill_historial ("
            "id TEXT PRIMARY KEY, skill TEXT NOT NULL, marca TEXT NOT NULL, "
            "fecha TEXT NOT NULL DEFAULT '', resultado TEXT NOT NULL DEFAULT '')"
        )
        con.execute(
            "INSERT INTO skill_historial (id, skill, marca, fecha, resultado) "
            "VALUES ('viejo1', 'copy-desde-nota', 'unotv', '2020-01-01', 'antiguo')"
        )
        con.commit()
    finally:
        con.close()
    # La primera conexion via db.* migra las columnas (idempotente) y lee defaults.
    entrada = db.obtener_historial_skill("viejo1")
    assert entrada["resultado"] == "antiguo"
    assert entrada["piezas"] == []
    assert entrada["titulo"] == ""
    # La columna `metricas` se migra (idempotente) y una fila vieja la lee como None.
    assert entrada["metricas"] is None


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
