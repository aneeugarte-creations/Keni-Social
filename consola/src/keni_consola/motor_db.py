"""Motor de persistencia operacional: SQLite (local) o Postgres (hosted), un solo codigo.

Esta capa es el punto de extension que el ADR 0001/0002 dejaba reservado en `db.py`:
toda la persistencia OPERACIONAL (tareas, comercial, rota, usuarios, sesiones) pasa por
`conectar()`, y aqui se elige el backend SEGUN `DATABASE_URL`:

  - SIN `DATABASE_URL`  -> SQLite local (perfil privado/local de ADR 0001/0002). Es el
    comportamiento HISTORICO: ninguna fila sale de la maquina. No se toca.
  - CON `DATABASE_URL`  -> Postgres (perfil hosted multiusuario). La var ya esta cableada
    en `deploy/docker-compose.yml`; el codigo la consume ahora.

POR QUE UN WRAPPER (y no SQLAlchemy): la capa de auth (`auth/usuarios.py`,
`auth/sesiones.py`, `auth/bootstrap.py`) y `db.py` operan DIRECTAMENTE sobre la conexion
(`con.execute(sql, params)`, `fila["col"]`, `cur.rowcount`, `con.commit()`), con SQL
parametrizado y unas pocas construcciones SQLite (`?`, `INSERT OR IGNORE`). Reescribir
todo eso a un ORM seria un cambio invasivo y arriesgado en un servicio LIVE. En su lugar,
`conectar()` devuelve una conexion que IMITA la API de `sqlite3.Connection` que esos
modulos ya usan, pero por debajo habla SQLite o Postgres. Asi:

  - La FACHADA (`repos.py`/`db.conectar`) y las firmas publicas NO cambian.
  - Los call sites de auth/db NO cambian (siguen usando `?` y `fila["col"]`).
  - El unico ajuste en los call sites es capturar `motor_db.IntegrityError` (neutro) en
    vez de `sqlite3.IntegrityError` (especifico de un backend).

NORMALIZACION DE DIALECTO (lo unico que el wrapper traduce, en Postgres):
  - Placeholders `?` -> `%s` (psycopg). Solo `?`; NUNCA se interpolan datos.
  - `INSERT OR IGNORE` -> `INSERT ... ON CONFLICT DO NOTHING`.
  - `INTEGER PRIMARY KEY`/`AUTOINCREMENT`/pragmas: NO se usan en el esquema operacional
    (los ids son TEXT generados por la app), asi que el DDL es portable salvo detalles
    que `db.py` ya resuelve por backend (`_crear_esquema`).
  - Filas accesibles por NOMBRE (como `sqlite3.Row`): en Postgres via `dict_row`.

SEGURIDAD: igual que antes, SIEMPRE consultas parametrizadas; el wrapper solo cambia el
estilo del marcador, nunca inyecta datos en el SQL.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import config, rutas

if TYPE_CHECKING:  # pragma: no cover -- solo para tipos; psycopg es opcional en local
    pass

# Espera (ms) ante contencion antes de fallar con `database is locked` (#130, SQLite).
_BUSY_TIMEOUT_MS = 5000


# --------------------------------------------------------------------------- #
# Excepcion neutra de integridad (UNIQUE/PK duplicada)                         #
# --------------------------------------------------------------------------- #
#
# auth/usuarios.py captura el duplicado de `usuario UNIQUE`. Antes capturaba
# `sqlite3.IntegrityError`; ahora captura `motor_db.IntegrityError`, que ES la de sqlite3
# en local y la mapeamos desde psycopg en hosted (ver `_ConexionPg.execute`).
IntegrityError = sqlite3.IntegrityError


def es_postgres() -> bool:
    """True si el backend operacional es Postgres (`DATABASE_URL` presente)."""
    return config.database_url() is not None


# --------------------------------------------------------------------------- #
# Backend SQLite (local; comportamiento historico intacto)                     #
# --------------------------------------------------------------------------- #


def ruta_db() -> Path:
    """Ruta del consola.db (SQLite). Solo aplica en perfil local (sin `DATABASE_URL`).

    `KENI_CONSOLA_DB` la sobreescribe (override de maxima prioridad; tests). Si no,
    cuelga de la raiz de estado unica (`rutas.dir_config()`).
    """
    if (p := config.override_ruta(config.ENV_DB)) is not None:
        return p
    return rutas.dir_config() / "consola.db"


def _conectar_sqlite() -> sqlite3.Connection:
    """Conexion SQLite con WAL/busy_timeout (concurrencia de una replica, #130).

    El esquema NO se crea aqui: lo crea `db._crear_esquema` (que recibe la conexion), para
    que la creacion del esquema sea responsabilidad de `db.py` en ambos backends.
    """
    ruta = ruta_db()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(ruta), timeout=_BUSY_TIMEOUT_MS / 1000)
    con.row_factory = sqlite3.Row
    con.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")
    return con


# --------------------------------------------------------------------------- #
# Backend Postgres (hosted; wrapper que imita la API de sqlite3 que usan los    #
# call sites). Importacion DIFERIDA de psycopg: en local no es necesaria.       #
# --------------------------------------------------------------------------- #


_RE_MARCADOR = re.compile(r"\?")
_RE_INSERT_OR_IGNORE = re.compile(r"\bINSERT\s+OR\s+IGNORE\b", re.IGNORECASE)


def _traducir_sql(sql: str) -> str:
    """Normaliza SQL de dialecto SQLite a Postgres (solo marcadores y OR IGNORE).

    - `?` -> `%s` (psycopg usa %s para parametros posicionales).
    - `INSERT OR IGNORE INTO t (...)` -> `INSERT INTO t (...) ... ON CONFLICT DO NOTHING`.

    El `ON CONFLICT DO NOTHING` se ANEXA al final (Postgres lo admite tras los VALUES) en
    vez de inline, porque la clausula va despues de los VALUES. Es seguro para las dos
    sentencias que lo usan (tareas por PK `id`, snapshots por indice UNIQUE (pub, ts)):
    en ambas el unico conflicto posible es la clave que queremos ignorar.
    """
    tenia_or_ignore = bool(_RE_INSERT_OR_IGNORE.search(sql))
    if tenia_or_ignore:
        sql = _RE_INSERT_OR_IGNORE.sub("INSERT", sql)
    sql = _RE_MARCADOR.sub("%s", sql)
    if tenia_or_ignore:
        sql = sql.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    return sql


class _CursorPg:
    """Cursor que imita lo que los call sites usan de un cursor sqlite3.

    Expone `fetchone()`, `fetchall()` (filas como dict accesibles por `fila["col"]`,
    igual que `sqlite3.Row`) y `rowcount`. Lo devuelve `_ConexionPg.execute`.
    """

    def __init__(self, cursor: Any) -> None:
        self._cur = cursor

    def fetchone(self) -> Any:
        return self._cur.fetchone()

    def fetchall(self) -> list[Any]:
        return self._cur.fetchall()

    @property
    def rowcount(self) -> int:
        return self._cur.rowcount


class _ConexionPg:
    """Conexion Postgres que imita la superficie de `sqlite3.Connection` usada en el repo.

    Metodos soportados (los unicos que los call sites usan): `execute(sql, params=())`,
    `commit()`, `close()`. `execute` traduce el dialecto, ejecuta y devuelve un `_CursorPg`
    cuyas filas se leen por nombre (`fila["col"]`). Las violaciones de UNIQUE/PK de psycopg
    se re-lanzan como `motor_db.IntegrityError` para que `auth` las capture igual que en
    SQLite.
    """

    def __init__(self, conexion: Any, dict_row: Any) -> None:
        self._con = conexion
        self._dict_row = dict_row

    def execute(self, sql: str, params: Any = ()) -> _CursorPg:
        import psycopg

        cur = self._con.cursor(row_factory=self._dict_row)
        try:
            cur.execute(_traducir_sql(sql), tuple(params))
        except psycopg.errors.UniqueViolation as e:
            # Mapeo a la excepcion neutra que captura auth (paridad con sqlite3).
            self._con.rollback()
            raise IntegrityError(str(e)) from e
        return _CursorPg(cur)

    def commit(self) -> None:
        self._con.commit()

    def close(self) -> None:
        self._con.close()


def _conectar_postgres() -> _ConexionPg:
    """Abre Postgres con `DATABASE_URL` (autocommit OFF; los call sites hacen commit()).

    Filas como dict (`dict_row`) para que `fila["col"]` funcione como con `sqlite3.Row`.
    Importacion DIFERIDA: psycopg solo es necesaria en hosted (extra `postgres`).
    """
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as e:  # pragma: no cover -- solo si falta el extra en hosted
        raise RuntimeError(
            "DATABASE_URL esta fijado pero falta el driver de Postgres. Instala el extra "
            "`postgres` (psycopg[binary]) en la imagen del back."
        ) from e
    url = config.database_url()
    con = psycopg.connect(url, autocommit=False)
    return _ConexionPg(con, dict_row)


# --------------------------------------------------------------------------- #
# Punto de entrada unico                                                       #
# --------------------------------------------------------------------------- #


def conectar_cruda() -> Any:
    """Conexion al backend operacional SIN crear esquema (lo hace `db._conectar`).

    SQLite si no hay `DATABASE_URL`; Postgres si lo hay. La eleccion se hace en tiempo de
    LLAMADA (no al importar), para que los tests aislen el backend con env vars.
    """
    if es_postgres():
        return _conectar_postgres()
    return _conectar_sqlite()
