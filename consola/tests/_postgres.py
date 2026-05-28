"""Ayuda compartida de los tests con backend POSTGRES (skip si no hay Postgres).

CONTRATO de CI (lo importante): los tests de Postgres SE SALTAN con un mensaje claro si no
hay un Postgres disponible, de modo que un CI SIN Postgres sigue verde y, donde SI lo haya
(servicio `postgres` del runner), se ejecutan de verdad.

COMO se decide "hay Postgres": la env var `KENI_TEST_DATABASE_URL` apunta al Postgres de
pruebas. Si esta, los tests la usan (la copian a `DATABASE_URL`, que es lo que `motor_db`
lee). Si NO esta, `requiere_postgres()` hace `pytest.skip`.

  # local (con un contenedor):
  #   docker run -d --name pg -e POSTGRES_PASSWORD=x -p 55432:5432 postgres:16
  #   export KENI_TEST_DATABASE_URL=postgresql://postgres:x@127.0.0.1:55432/postgres
  #   pytest consola/tests/test_db_postgres.py
  # CI: arranca un service `postgres` y exporta KENI_TEST_DATABASE_URL apuntandolo.

AISLAMIENTO: `limpiar_postgres()` hace TRUNCATE de las tablas operacionales entre tests
(rapido y sin recrear el esquema). El esquema se crea on-demand al primera conexion.
"""

from __future__ import annotations

import os

import pytest

# Nombre de la env var que activa los tests de Postgres (apunta al Postgres de pruebas).
ENV_TEST_DATABASE_URL = "KENI_TEST_DATABASE_URL"

# Tablas operacionales que se truncan entre tests (todas las del esquema de `db.py`).
_TABLAS = (
    "sesiones",
    "usuarios",
    "tareas",
    "comercial_snapshots",
    "comercial_publicaciones",
    "rota_turnos",
    "rota_ausencias",
    "rota_piezas",
    "rota_programas",
    "rota_eventos",
    "rota_swaps_turno",
    "jobs",
)


def url_postgres_de_pruebas() -> str | None:
    """URL del Postgres de pruebas (`KENI_TEST_DATABASE_URL`), o None si no esta."""
    return os.environ.get(ENV_TEST_DATABASE_URL) or None


def requiere_postgres() -> str:
    """Devuelve la URL de pruebas o hace `pytest.skip` con un mensaje claro si no hay.

    Usar al inicio de cada test de Postgres (o via la fixture `pg`). El skip es el
    comportamiento esperado en CI sin Postgres.
    """
    url = url_postgres_de_pruebas()
    if not url:
        pytest.skip(
            f"sin Postgres de pruebas: exporta {ENV_TEST_DATABASE_URL} para ejecutar los "
            "tests del backend Postgres (CI sin Postgres los salta)."
        )
    return url


def limpiar_postgres(url: str) -> None:
    """TRUNCATE de todas las tablas operacionales (aislamiento entre tests).

    Tolerante a tablas inexistentes (primer uso, antes de crear el esquema).
    """
    import psycopg

    with psycopg.connect(url, autocommit=True) as con:
        for tabla in _TABLAS:
            try:
                con.execute(f"TRUNCATE TABLE {tabla} CASCADE")  # noqa: S608 -- allowlist fija
            except psycopg.errors.UndefinedTable:
                pass


@pytest.fixture
def pg(monkeypatch):
    """Activa el Postgres de pruebas para el test (o lo salta si no hay Postgres).

    Fija `DATABASE_URL` (lo que lee `motor_db`) al Postgres de pruebas, limpia las tablas
    antes del test y las vuelve a limpiar despues. Devuelve la URL.

    Tras la ADR 0004 la fixture `entorno` tambien fija `DATABASE_URL`; `pg` se mantiene como
    fixture mas LIGERA (sin tocar el resto de env vars de la app) util para los tests del
    backend de DB puro (`test_db_postgres.py`, `test_migracion.py`).
    """
    url = requiere_postgres()
    limpiar_postgres(url)
    monkeypatch.setenv("DATABASE_URL", url)
    yield url
    limpiar_postgres(url)
