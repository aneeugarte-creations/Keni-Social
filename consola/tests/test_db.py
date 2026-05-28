"""Tests del CRUD de tareas (`keni_consola.db`): dato OPERACIONAL.

Tras la ADR 0004 la operacional vive en POSTGRES. La fixture `entorno` apunta a un
Postgres de pruebas (o salta si no hay). Estos tests cubren el tablero compartido (#145
F5): responsable, enlace, ciclo de estado intermedio, filtro por proyecto, allowlist de
campos editables. El CRUD basico y la inyeccion SQL se prueban en `test_db_postgres.py`
(paridad backend); aqui evitamos duplicar y nos quedamos con los casos de tablero.
"""

from __future__ import annotations

from keni_consola import db


# --------------------------------------------------------------------------- #
# Esquema on-demand                                                            #
# --------------------------------------------------------------------------- #


def test_esquema_se_crea_on_demand(entorno):
    """La primera operacion crea el esquema en Postgres y devuelve vacio."""
    assert db.listar_tareas() == []


# --------------------------------------------------------------------------- #
# Tareas: tablero compartido (#145 F5) - responsable, enlace, estado, filtro    #
# --------------------------------------------------------------------------- #


def test_crear_tarea_con_responsable_y_enlace(entorno):
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


def test_crear_tarea_sin_responsable_queda_sin_asignar(entorno):
    """Sin responsable/enlace, los campos quedan vacios (sin asignar)."""
    t = db.crear_tarea("proj1", "Suelta")
    assert t["responsable_id"] == ""
    assert t["responsable_nombre"] == ""
    assert t["enlace"] == ""


def test_actualizar_estado_en_curso(entorno):
    """El ciclo de vida admite el estado intermedio 'en_curso' (#145)."""
    assert "en_curso" in db.ESTADOS_TAREA
    t = db.crear_tarea("proj1", "Avanza")
    actualizada = db.actualizar_tarea(t["id"], {"estado": "en_curso"})
    assert actualizada["estado"] == "en_curso"


def test_actualizar_tarea_reasigna_responsable_y_enlace(entorno):
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


def test_actualizar_tarea_ignora_columnas_arbitrarias(entorno):
    """`actualizar_tarea` solo escribe campos de la allowlist (no columnas arbitrarias)."""
    t = db.crear_tarea("proj1", "Titulo original")
    # Intentar reescribir 'titulo'/'proyecto' (no editables) se ignora silenciosamente.
    db.actualizar_tarea(t["id"], {"titulo": "hackeado", "proyecto": "otro", "estado": "hecha"})
    releida = db.obtener_tarea(t["id"])
    assert releida["titulo"] == "Titulo original"
    assert releida["proyecto"] == "proj1"
    assert releida["estado"] == "hecha"  # el campo valido si se aplico


def test_actualizar_tarea_inexistente_devuelve_none(entorno):
    assert db.actualizar_tarea("noexiste", {"estado": "hecha"}) is None


def test_listar_tareas_filtra_por_proyecto(entorno):
    """`listar_tareas(proyecto_id)` acota al proyecto (acotado por marca/proyecto, #145)."""
    db.crear_tarea("proj1", "De A")
    db.crear_tarea("proj2", "De B")
    solo_a = db.listar_tareas("proj1")
    assert len(solo_a) == 1
    assert solo_a[0]["titulo"] == "De A"
    assert len(db.listar_tareas()) == 2
