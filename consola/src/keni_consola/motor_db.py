"""Motor de persistencia operacional: Postgres, un solo backend (ADR 0004).

Toda la persistencia OPERACIONAL (tareas, comercial, rota, usuarios, sesiones, jobs) pasa
por `conectar_cruda()`, que abre Postgres usando `DATABASE_URL`. Antes (ADR 0002/#130) el
backend se elegia segun la presencia de esa var: SIN `DATABASE_URL` -> SQLite local; CON
ella -> Postgres. La ADR 0004 retira ese SQLite operacional: ahora `DATABASE_URL` es
REQUERIDA (un Postgres, local o hosted). Asi desaparece el drift SQLite<->Postgres que
causaba bugs (p. ej. columnas que solo migraban en un backend). Ver `docs/adr/0004`.

La privacidad del perfil local se preserva apuntando `DATABASE_URL` a un Postgres LOCAL
(ningun dato sale de la maquina). Lo que se pierde es el "cero-config / offline por
defecto". En desarrollo no se usa Postgres local: la ejecucion/validacion se hace en el
server (CI Woodpecker / hosted); quien necesite correr en local provee su propio
`DATABASE_URL` apuntando a un Postgres que el mismo gestione.

POR QUE UN WRAPPER (y no SQLAlchemy): la capa de auth (`auth/usuarios.py`,
`auth/sesiones.py`, `auth/bootstrap.py`) y `db.py` operan DIRECTAMENTE sobre la conexion
(`con.execute(sql, params)`, `fila["col"]`, `cur.rowcount`, `con.commit()`), con SQL
parametrizado y unas pocas construcciones estilo SQLite (`?`, `INSERT OR IGNORE`). Cuando
ambos backends coexistian, reescribirlo a un ORM habria sido invasivo y arriesgado en un
servicio LIVE; el wrapper IMITA la API de `sqlite3.Connection` que esos modulos ya usan,
pero por debajo habla Postgres. Aunque ya solo quede Postgres, MANTENEMOS el wrapper: los
cientos de call sites siguen usando `?` y `fila["col"]` sin cambios. Asi:

  - La FACHADA (`repos.py`/`db.conectar`) y las firmas publicas NO cambian.
  - Los call sites de auth/db NO cambian (siguen usando `?` y `fila["col"]`).
  - El unico ajuste de los call sites (ya hecho) es capturar `motor_db.IntegrityError`
    (neutro) en vez de `sqlite3.IntegrityError`.

NORMALIZACION DE DIALECTO (lo unico que el wrapper traduce):
  - Placeholders `?` -> `%s` (psycopg). Solo `?`; NUNCA se interpolan datos.
  - `INSERT OR IGNORE` -> `INSERT ... ON CONFLICT DO NOTHING`.
  - Filas accesibles por NOMBRE (como `sqlite3.Row`): en Postgres via `dict_row`.

SEGURIDAD: igual que antes, SIEMPRE consultas parametrizadas; el wrapper solo cambia el
estilo del marcador, nunca inyecta datos en el SQL.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from . import config


# --------------------------------------------------------------------------- #
# Excepcion neutra de integridad (UNIQUE/PK duplicada)                         #
# --------------------------------------------------------------------------- #
#
# auth/usuarios.py captura el duplicado de `usuario UNIQUE`. Captura
# `motor_db.IntegrityError`, que mapeamos desde la `UniqueViolation` de psycopg (ver
# `_ConexionPg.execute`). Se mantiene como `sqlite3.IntegrityError` por compatibilidad de
# tipo con el codigo y los tests historicos: es solo el TIPO que se relanza, ningun SQLite
# operacional se abre ya.
IntegrityError = sqlite3.IntegrityError


# --------------------------------------------------------------------------- #
# Backend Postgres (unico). Wrapper que imita la API de sqlite3 que usan los    #
# call sites. Importacion DIFERIDA de psycopg (extra `postgres`).               #
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
    se re-lanzan como `motor_db.IntegrityError` para que `auth` las capture (paridad con el
    contrato historico).
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
            # Mapeo a la excepcion neutra que captura auth.
            self._con.rollback()
            raise IntegrityError(str(e)) from e
        return _CursorPg(cur)

    def commit(self) -> None:
        self._con.commit()

    def close(self) -> None:
        self._con.close()


def _mensaje_sin_url() -> str:
    """Mensaje accionable cuando falta `DATABASE_URL` (Postgres es obligatorio, ADR 0004)."""
    return (
        "DATABASE_URL no esta fijada y es OBLIGATORIA: la Consola persiste en Postgres "
        "(ya no hay backend SQLite, ver docs/adr/0004). En desarrollo no se usa Postgres "
        "local: la ejecucion/validacion se hace en el server (CI Woodpecker / hosted). Si "
        "necesitas correr en local, provee tu propio Postgres y exporta su URL, p. ej.:\n\n"
        "    export DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/keni_social\n\n"
        "(En hosted la fija deploy/docker-compose.yml.)"
    )


def conectar_cruda() -> _ConexionPg:
    """Conexion al Postgres operacional SIN crear esquema (lo hace `db._conectar`).

    Exige `DATABASE_URL` (obligatoria, ADR 0004): si falta, lanza un `RuntimeError` con el
    one-liner para arrancar un Postgres local. La eleccion/lectura se hace en tiempo de
    LLAMADA (no al importar), para que los tests aislen el backend con env vars.

    `autocommit=False` (los call sites hacen `commit()` explicito). Filas como dict
    (`dict_row`) para que `fila["col"]` funcione como con `sqlite3.Row`. Importacion
    DIFERIDA de psycopg: solo se necesita en runtime (extra `postgres`).
    """
    url = config.database_url()
    if url is None:
        raise RuntimeError(_mensaje_sin_url())
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as e:  # pragma: no cover -- solo si falta el extra
        raise RuntimeError(
            "DATABASE_URL esta fijada pero falta el driver de Postgres. Instala el extra "
            "`postgres` (psycopg[binary]) en el entorno del back."
        ) from e
    con = psycopg.connect(url, autocommit=False)
    return _ConexionPg(con, dict_row)
