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


# --------------------------------------------------------------------------- #
# Tareas: tablero compartido (#145 F5) - responsable, enlace, estado, filtro    #
# --------------------------------------------------------------------------- #


def test_crear_tarea_con_responsable_y_enlace(base):
    """Una tarea nace con responsable (id+nombre) y enlace de accion; persisten."""
    t = db.crear_tarea(
        "proj1",
        "Asignada",
        responsable={"id": "u1", "usuario": "ana"},
        enlace="/asistente?skill=copy",
    )
    assert t["responsable_id"] == "u1"
    assert t["responsable_nombre"] == "ana"
    assert t["enlace"] == "/asistente?skill=copy"
    releida = db.obtener_tarea(t["id"])
    assert releida["responsable_nombre"] == "ana"
    assert releida["enlace"] == "/asistente?skill=copy"


def test_crear_tarea_sin_responsable_queda_sin_asignar(base):
    """Sin responsable/enlace, los campos quedan vacios (sin asignar)."""
    t = db.crear_tarea("proj1", "Suelta")
    assert t["responsable_id"] == ""
    assert t["responsable_nombre"] == ""
    assert t["enlace"] == ""


def test_actualizar_estado_en_curso(base):
    """El ciclo de vida admite el estado intermedio 'en_curso' (#145)."""
    assert "en_curso" in db.ESTADOS_TAREA
    t = db.crear_tarea("proj1", "Avanza")
    actualizada = db.actualizar_tarea(t["id"], {"estado": "en_curso"})
    assert actualizada["estado"] == "en_curso"


def test_actualizar_tarea_reasigna_responsable_y_enlace(base):
    """`actualizar_tarea` cambia responsable y enlace; vaciar limpia las columnas."""
    t = db.crear_tarea("proj1", "Reasignar")
    asignada = db.actualizar_tarea(
        t["id"],
        {"responsable_id": "u2", "responsable_nombre": "luis", "enlace": "/x"},
    )
    assert asignada["responsable_nombre"] == "luis"
    assert asignada["enlace"] == "/x"
    # Desasignar: ambos campos vuelven a vacio.
    limpia = db.actualizar_tarea(
        t["id"], {"responsable_id": "", "responsable_nombre": "", "enlace": ""}
    )
    assert limpia["responsable_id"] == ""
    assert limpia["responsable_nombre"] == ""
    assert limpia["enlace"] == ""


def test_actualizar_tarea_ignora_columnas_arbitrarias(base):
    """`actualizar_tarea` solo escribe campos de la allowlist (no columnas arbitrarias)."""
    t = db.crear_tarea("proj1", "Titulo original")
    # Intentar reescribir 'titulo'/'proyecto' (no editables) se ignora silenciosamente.
    db.actualizar_tarea(t["id"], {"titulo": "hackeado", "proyecto": "otro", "estado": "hecha"})
    releida = db.obtener_tarea(t["id"])
    assert releida["titulo"] == "Titulo original"
    assert releida["proyecto"] == "proj1"
    assert releida["estado"] == "hecha"  # el campo valido si se aplico


def test_actualizar_tarea_inexistente_devuelve_none(base):
    assert db.actualizar_tarea("noexiste", {"estado": "hecha"}) is None


def test_listar_tareas_filtra_por_proyecto(base):
    """`listar_tareas(proyecto_id)` acota al proyecto (acotado por marca/proyecto, #145)."""
    db.crear_tarea("proj1", "De A")
    db.crear_tarea("proj2", "De B")
    solo_a = db.listar_tareas("proj1")
    assert len(solo_a) == 1
    assert solo_a[0]["titulo"] == "De A"
    assert len(db.listar_tareas()) == 2


def test_migracion_columnas_tablero_en_bd_vieja(base):
    """Una BD con `tareas` SIN responsable/enlace se ALTERa (idempotente) y se lee vacia."""
    ruta = db.ruta_db()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(ruta))
    # Esquema previo a #145 (con autor de #130 pero sin responsable/enlace).
    con.execute(
        "CREATE TABLE tareas (id TEXT PRIMARY KEY, proyecto TEXT NOT NULL, titulo TEXT NOT NULL, "
        "detalle TEXT NOT NULL DEFAULT '', estado TEXT NOT NULL DEFAULT 'pendiente', "
        "fecha TEXT NOT NULL DEFAULT '', autor_id TEXT NOT NULL DEFAULT '', "
        "autor_nombre TEXT NOT NULL DEFAULT '')"
    )
    con.execute("INSERT INTO tareas (id, proyecto, titulo) VALUES ('vieja', 'p', 'Tarea vieja')")
    con.commit()
    con.close()
    # Cualquier operacion dispara la migracion idempotente.
    t = db.obtener_tarea("vieja")
    assert t is not None
    assert t["responsable_id"] == ""
    assert t["responsable_nombre"] == ""
    assert t["enlace"] == ""
    # Y la columna queda disponible para nuevas filas.
    nueva = db.crear_tarea("p", "Nueva", responsable={"id": "u1", "usuario": "ana"})
    assert nueva["responsable_nombre"] == "ana"


def test_migracion_columnas_eventos_rota_en_bd_vieja(base):
    """Un `rota_eventos` SIN cobertura/prioridad/cambiado/actualizado se ALTERa idempotente."""
    ruta = db.ruta_db()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(ruta))
    # Esquema previo a la ola B (solo los campos originales del evento).
    con.execute(
        "CREATE TABLE rota_eventos (id TEXT PRIMARY KEY, titulo TEXT NOT NULL, "
        "fecha TEXT NOT NULL DEFAULT '', hora TEXT NOT NULL DEFAULT '', "
        "contenido TEXT NOT NULL DEFAULT '', nota TEXT NOT NULL DEFAULT '', "
        "creado TEXT NOT NULL DEFAULT '')"
    )
    con.execute(
        "INSERT INTO rota_eventos (id, titulo, fecha) VALUES ('viejo', 'Partido', '2026-05-30')"
    )
    con.commit()
    con.close()
    # Cualquier operacion dispara la migracion idempotente; el evento legado queda con
    # los valores por defecto sensatos (transmision/media/sin reprogramar).
    ev = db.obtener_evento_rota("viejo")
    assert ev is not None
    assert ev["tipo_cobertura"] == "transmision"
    assert ev["prioridad"] == "media"
    assert ev["cambiado"] is False
    assert ev["actualizado"] == ""
    # Y las columnas quedan disponibles para nuevas filas.
    nuevo = db.crear_evento_rota("Nuevo", fecha="2026-05-30", tipo_cobertura="imagenes")
    assert nuevo["tipo_cobertura"] == "imagenes"


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
