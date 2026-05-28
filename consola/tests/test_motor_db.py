"""Tests del motor de persistencia (`keni_consola.motor_db`): traduccion de dialecto +
contrato de `conectar_cruda` (Postgres obligatorio, ADR 0004).

OFFLINE en su mayor parte: la traduccion `?`->`%s` y `INSERT OR IGNORE`->`ON CONFLICT DO
NOTHING` es logica pura sin DB; el contrato de "sin DATABASE_URL falla con un mensaje
claro" tambien se prueba sin abrir Postgres. La conexion REAL a Postgres se prueba en
`test_db_postgres.py` (skip si no hay Postgres).
"""

from __future__ import annotations

import sqlite3

import pytest

from keni_consola import motor_db


# --------------------------------------------------------------------------- #
# Contrato: DATABASE_URL es OBLIGATORIA (ADR 0004)                            #
# --------------------------------------------------------------------------- #


def test_conectar_cruda_sin_database_url_falla_con_mensaje_accionable(monkeypatch):
    """Sin `DATABASE_URL`, `conectar_cruda` lanza `RuntimeError` con el one-liner de docker.

    No es un fallback a SQLite ni un traceback opaco: es un error de arranque accionable.
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)
    for var in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB",
                "POSTGRES_HOST", "POSTGRES_PORT"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(RuntimeError) as exc:
        motor_db.conectar_cruda()
    mensaje = str(exc.value)
    assert "DATABASE_URL" in mensaje
    assert "docker compose" in mensaje or "docker" in mensaje
    assert "postgres" in mensaje.lower()


def test_database_url_vacia_es_como_ausente(monkeypatch):
    """Una `DATABASE_URL` vacia/espacios cuenta como AUSENTE (no como URL rota)."""
    monkeypatch.setenv("DATABASE_URL", "   ")
    for var in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB",
                "POSTGRES_HOST", "POSTGRES_PORT"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(RuntimeError):
        motor_db.conectar_cruda()


# --------------------------------------------------------------------------- #
# Traduccion de dialecto                                                      #
# --------------------------------------------------------------------------- #


def test_traduce_marcadores_posicionales():
    sql = "SELECT * FROM tareas WHERE id = ? AND proyecto = ?"
    assert motor_db._traducir_sql(sql) == "SELECT * FROM tareas WHERE id = %s AND proyecto = %s"


def test_traduce_insert_or_ignore_a_on_conflict():
    sql = "INSERT OR IGNORE INTO tareas (id, titulo) VALUES (?, ?)"
    salida = motor_db._traducir_sql(sql)
    assert salida.startswith("INSERT INTO tareas (id, titulo) VALUES (%s, %s)")
    assert salida.rstrip().endswith("ON CONFLICT DO NOTHING")
    assert "OR IGNORE" not in salida


def test_traduce_insert_normal_no_anade_on_conflict():
    sql = "INSERT INTO tareas (id, titulo) VALUES (?, ?)"
    salida = motor_db._traducir_sql(sql)
    assert "ON CONFLICT" not in salida
    assert salida == "INSERT INTO tareas (id, titulo) VALUES (%s, %s)"


def test_traduce_insert_or_ignore_insensible_a_mayusculas():
    sql = "insert or ignore into comercial_snapshots (id, ts) values (?, ?)"
    salida = motor_db._traducir_sql(sql)
    assert salida.rstrip().endswith("ON CONFLICT DO NOTHING")
    assert "or ignore" not in salida.lower()


def test_integrity_error_es_neutra():
    """El tipo que se relanza desde el wrapper es `motor_db.IntegrityError`.

    Por compatibilidad con el codigo y los tests historicos sigue siendo el tipo de sqlite3
    (`sqlite3.IntegrityError`); ningun SQLite operacional se abre ya (ADR 0004).
    """
    assert motor_db.IntegrityError is sqlite3.IntegrityError
