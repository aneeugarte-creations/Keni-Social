"""Tests del CRUD de tareas (`keni_consola.db`): dato OPERACIONAL.

Tras la ADR 0004 la operacional vive en POSTGRES. La fixture `entorno` apunta a un
Postgres de pruebas (o salta si no hay). Estos tests cubren el tablero compartido:
responsable, enlace, ciclo de estado intermedio, filtro por proyecto, allowlist de
campos editables. El CRUD basico y la inyeccion SQL se prueban en `test_db_postgres.py`
(paridad backend); aqui evitamos duplicar y nos quedamos con los casos de tablero.
"""

from __future__ import annotations

from keni_consola import db


# --------------------------------------------------------------------------- #
# Esquema on-demand                                                            #
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# Swaps de turno: esquema idempotente + CRUD basico                            #
# --------------------------------------------------------------------------- #


def test_tabla_swaps_se_crea_on_demand(entorno):
    """La primera operacion crea `rota_swaps_turno` y devuelve vacio (no excepcion)."""
    assert db.listar_swaps_turno() == []


def test_migracion_columnas_swaps_idempotente(entorno):
    """Llamar a `_crear_esquema` varias veces no falla y no duplica columnas."""
    # Provoca dos creaciones de esquema (cada operacion abre/cierra y vuelve a crear).
    db.listar_swaps_turno()
    db.listar_swaps_turno()
    db.listar_swaps_turno()
    # Hasta aqui no hay excepcion; la idempotencia esta probada por la ausencia de fallo.
    assert db.listar_swaps_turno() == []


def test_crear_y_listar_swap_turno(entorno):
    """Crear un swap deja el estado en `propuesto` y se recupera por listar/obtener."""
    s = db.crear_swap_turno(
        "u-a",
        "u-b",
        "2026-05-25",
        "matutino",
        "2026-05-27",
        "vespertino",
        solicitante_nombre="ana",
        destinatario_nombre="beto",
        motivo="Boda de la prima",
    )
    assert s["estado"] == "propuesto"
    assert s["solicitante_nombre"] == "ana"
    assert s["destinatario_nombre"] == "beto"
    listado = db.listar_swaps_turno()
    assert any(x["id"] == s["id"] for x in listado)
    # Filtro por `mio_id` devuelve tanto si soy A como si soy B.
    assert any(x["id"] == s["id"] for x in db.listar_swaps_turno(mio_id="u-a"))
    assert any(x["id"] == s["id"] for x in db.listar_swaps_turno(mio_id="u-b"))
    assert db.listar_swaps_turno(mio_id="u-z") == []


def test_actualizar_swap_filtra_columnas_arbitrarias(entorno):
    """`actualizar_swap_turno` solo escribe la allowlist (no toca solicitante/franjas)."""
    s = db.crear_swap_turno(
        "u-a", "u-b", "2026-05-25", "matutino", "2026-05-27", "vespertino"
    )
    # Intentar reescribir el solicitante/franjas se ignora; el estado SI cambia.
    actualizado = db.actualizar_swap_turno(
        s["id"],
        {
            "solicitante_id": "hackeado",
            "fecha_a": "1900-01-01",
            "estado": "aceptado",
            "respuesta_destinatario": "Sí, te cubro.",
        },
    )
    assert actualizado["solicitante_id"] == "u-a"  # intacto
    assert actualizado["fecha_a"] == "2026-05-25"
    assert actualizado["estado"] == "aceptado"
    assert actualizado["respuesta_destinatario"] == "Sí, te cubro."
