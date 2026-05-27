"""Tests del motor de persistencia (`keni_consola.motor_db`): seleccion de backend +
traduccion de dialecto SQLite->Postgres. OFFLINE: no abre Postgres (solo la logica pura).

Lo que cubre SIN Postgres:
  - `es_postgres()` segun `DATABASE_URL`.
  - `_traducir_sql`: `?`->`%s`, `INSERT OR IGNORE`->`ON CONFLICT DO NOTHING`.
  - `conectar_cruda()` devuelve SQLite cuando no hay `DATABASE_URL`.
La conexion REAL a Postgres se prueba en `test_db_postgres.py` (skip si no hay Postgres).
"""

from __future__ import annotations

import sqlite3

import pytest

from keni_consola import motor_db


@pytest.fixture
def base(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("KENI_CONSOLA_DB", str(tmp_path / "consola.db"))
    return tmp_path


# --------------------------------------------------------------------------- #
# Seleccion de backend                                                        #
# --------------------------------------------------------------------------- #


def test_es_postgres_falso_sin_database_url(base, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert motor_db.es_postgres() is False


def test_es_postgres_verdadero_con_database_url(base, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x:y@db:5432/keni")
    assert motor_db.es_postgres() is True


def test_database_url_vacia_es_sqlite(base, monkeypatch):
    # Una var vacia/espacios cuenta como AUSENTE (perfil local), no como Postgres roto.
    monkeypatch.setenv("DATABASE_URL", "   ")
    assert motor_db.es_postgres() is False


def test_conectar_cruda_es_sqlite_sin_database_url(base):
    con = motor_db.conectar_cruda()
    try:
        assert isinstance(con, sqlite3.Connection)
    finally:
        con.close()


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
    # En local ES la de sqlite3; el contrato es que `auth` capture `motor_db.IntegrityError`.
    assert motor_db.IntegrityError is sqlite3.IntegrityError
