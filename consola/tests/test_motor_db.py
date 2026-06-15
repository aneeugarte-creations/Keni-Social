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
    """El tipo que se relanza desde el wrapper es `motor_db.IntegrityError` (alias sqlite3.IntegrityError).

    Ningún SQLite operacional se abre ya (ADR 0004).
    """
    assert motor_db.IntegrityError is sqlite3.IntegrityError


# --------------------------------------------------------------------------- #
# Robustez: `?` dentro de literales de string NO es un marcador               #
# --------------------------------------------------------------------------- #


def test_no_traduce_marcadores_dentro_de_literales():
    """Un `?` dentro de comillas simples (p.ej. el cuantificador de una regex inline) se
    respeta; solo los `?` FUERA de literales se traducen a `%s`."""
    sql = r"UPDATE t SET col = left(col, ?) WHERE col ~ '^\d+?$' AND id = ?"
    salida = motor_db._traducir_sql(sql)
    assert salida == r"UPDATE t SET col = left(col, %s) WHERE col ~ '^\d+?$' AND id = %s"


def test_no_traduce_dentro_de_literal_con_comilla_escapada():
    """El escape SQL `''` (comilla duplicada) no rompe la particion: el `?` del literal
    sigue intacto y el de fuera se traduce."""
    sql = "UPDATE t SET nota = 'que ''pasa?'' aqui' WHERE id = ?"
    salida = motor_db._traducir_sql(sql)
    assert salida == "UPDATE t SET nota = 'que ''pasa?'' aqui' WHERE id = %s"


def test_traduce_varios_literales_y_marcadores_mezclados():
    sql = "SELECT '?' AS a, ? AS b, 'x?y' AS c, ? AS d"
    salida = motor_db._traducir_sql(sql)
    assert salida == "SELECT '?' AS a, %s AS b, 'x?y' AS c, %s AS d"


# --------------------------------------------------------------------------- #
# Mapeo de violaciones de integridad: FK / NOT NULL / CHECK -> IntegrityError #
# --------------------------------------------------------------------------- #


class _CursorQueExplota:
    """Cursor falso cuyo `execute` lanza la excepcion configurada (sin Postgres real)."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def execute(self, sql, params=()):  # noqa: ANN001 -- firma minima
        raise self._exc


class _ConQueExplota:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.rollbacks = 0

    def cursor(self, row_factory=None):  # noqa: ANN001 -- firma minima
        return _CursorQueExplota(self._exc)

    def rollback(self) -> None:
        self.rollbacks += 1


@pytest.mark.parametrize(
    "nombre_error",
    ["UniqueViolation", "ForeignKeyViolation", "NotNullViolation", "CheckViolation"],
)
def test_violaciones_de_integridad_se_mapean_a_integrity_error(nombre_error):
    """TODAS las violaciones de integridad de psycopg (no solo UNIQUE) salen como la
    excepcion neutra `motor_db.IntegrityError`, con rollback de la transaccion."""
    psycopg = pytest.importorskip("psycopg")
    exc = getattr(psycopg.errors, nombre_error)("boom")
    con_falsa = _ConQueExplota(exc)
    wrapper = motor_db._ConexionPg(con_falsa, dict_row=None, pool=None)
    with pytest.raises(motor_db.IntegrityError):
        wrapper.execute("INSERT INTO t (id) VALUES (?)", ("x",))
    assert con_falsa.rollbacks == 1


def test_otros_errores_de_psycopg_no_se_enmascaran():
    """Un error que NO es de integridad (p.ej. sintaxis) NO se convierte en IntegrityError."""
    psycopg = pytest.importorskip("psycopg")
    exc = psycopg.errors.SyntaxError("mal sql")
    wrapper = motor_db._ConexionPg(_ConQueExplota(exc), dict_row=None, pool=None)
    with pytest.raises(psycopg.errors.SyntaxError):
        wrapper.execute("SELECT ?", ("x",))
