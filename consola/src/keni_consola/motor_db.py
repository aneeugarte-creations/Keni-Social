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

import atexit
import logging
import re
import sqlite3
import threading
from typing import Any

from . import config

_log = logging.getLogger("keni_consola.motor_db")


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


_RE_INSERT_OR_IGNORE = re.compile(r"\bINSERT\s+OR\s+IGNORE\b", re.IGNORECASE)


def _sustituir_marcadores(sql: str) -> str:
    """Sustituye `?` -> `%s` SOLO fuera de literales de string (comillas simples).

    Un `?` dentro de un literal (p. ej. el cuantificador de una REGEX pasada inline en el
    SQL) NO es un marcador y corromperia la sentencia si se tradujera. Partimos por `'`:
    los segmentos PARES estan fuera de comillas (se traduce) y los IMPARES dentro (se
    respeta). El escape SQL `''` (comilla duplicada) produce segmentos vacios que alternan
    la paridad de forma correcta, asi que tambien se maneja bien.
    """
    partes = sql.split("'")
    for i in range(0, len(partes), 2):
        partes[i] = partes[i].replace("?", "%s")
    return "'".join(partes)


def _traducir_sql(sql: str) -> str:
    """Normaliza SQL de dialecto SQLite a Postgres (solo marcadores y OR IGNORE).

    - `?` -> `%s` (psycopg usa %s para parametros posicionales), respetando los
      literales de string (un `?` entre comillas simples NO se toca).
    - `INSERT OR IGNORE INTO t (...)` -> `INSERT INTO t (...) ... ON CONFLICT DO NOTHING`.

    El `ON CONFLICT DO NOTHING` se ANEXA al final (Postgres lo admite tras los VALUES) en
    vez de inline, porque la clausula va despues de los VALUES. Es seguro para las dos
    sentencias que lo usan (tareas por PK `id`, snapshots por indice UNIQUE (pub, ts)):
    en ambas el unico conflicto posible es la clave que queremos ignorar.
    """
    tenia_or_ignore = bool(_RE_INSERT_OR_IGNORE.search(sql))
    if tenia_or_ignore:
        sql = _RE_INSERT_OR_IGNORE.sub("INSERT", sql)
    sql = _sustituir_marcadores(sql)
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

    def __init__(self, conexion: Any, dict_row: Any, pool: Any = None) -> None:
        self._con = conexion
        self._dict_row = dict_row
        # Si `pool` no es None, esta conexion es una LEASE del pool: `close()` la DEVUELVE
        # (putconn) en vez de cerrar el socket. Si es None, es una conexion dedicada (camino
        # fallback) y `close()` la cierra de verdad. None tras devolverla (idempotencia).
        self._pool = pool

    def execute(self, sql: str, params: Any = ()) -> _CursorPg:
        import psycopg

        cur = self._con.cursor(row_factory=self._dict_row)
        try:
            cur.execute(_traducir_sql(sql), tuple(params))
        except (
            # TODAS las violaciones de integridad (UNIQUE/PK, FK, NOT NULL, CHECK) se mapean a
            # la excepcion neutra: antes solo UniqueViolation y las demas salian como psycopg
            # crudo, que ningun call site capturaba (500 en vez de un error de dominio).
            psycopg.errors.UniqueViolation,
            psycopg.errors.ForeignKeyViolation,
            psycopg.errors.NotNullViolation,
            psycopg.errors.CheckViolation,
        ) as e:
            self._con.rollback()
            raise IntegrityError(str(e)) from e
        return _CursorPg(cur)

    def commit(self) -> None:
        self._con.commit()

    def rollback(self) -> None:
        """Deshace la transaccion abierta (para migraciones defensivas que absorben fallos).

        Los call sites historicos no lo usan (el shim hace rollback solo al mapear una
        violacion de integridad), pero las migraciones best-effort de `_db_core` lo
        necesitan: tras un fallo NO mapeado la transaccion queda abortada y, sin rollback,
        envenenaria todas las sentencias siguientes de la misma conexion.
        """
        self._con.rollback()

    def descartar(self) -> None:
        """DESCARTA la conexion (cierra el socket) en vez de devolverla sana al pool.

        Para conexiones cuyo ESTADO DE SESION quedo sucio sin remedio: p. ej. un advisory
        lock de sesion que no se pudo soltar (`lock_barrido`/lock de esquema). Devolver esa
        conexion al pool dejaria el lock pegado y todos los `pg_try_advisory_lock` futuros
        devolverian False hasta el reciclado (~1 h): el single-flight quedaria envenenado.
        Cerrar el socket libera los locks de sesion en el servidor; `putconn` de una
        conexion CERRADA hace que el pool la deseche y reponga una fresca. Idempotente, y
        deja `close()` posterior como no-op.
        """
        pool, self._pool = self._pool, None
        con, self._con = self._con, None
        if con is None:
            return
        try:
            con.close()
        except Exception:  # noqa: BLE001 -- cerrar es best-effort
            pass
        if pool is not None:
            try:
                pool.putconn(con)  # cerrada -> el pool la descarta y repone
            except Exception:  # noqa: BLE001 -- descartar es best-effort
                pass

    def close(self) -> None:
        """Cierra la conexion. Si vino del pool, la DEVUELVE; si no, cierra el socket.

        Idempotente (varios `close()` no rompen). En el camino pooled devolvemos la conexion
        en estado IDLE (rollback previo) y `putconn` del `psycopg_pool` la reencola o la
        DESCARTA si esta rota (no la devuelve poisoned); si `putconn` fallara (conexion
        inservible), la cerramos para no filtrar la lease.

        El rollback previo NO cambia el comportamiento (putconn haria el mismo rollback) pero
        evita el WARNING que `psycopg_pool` emite en CADA retorno de una conexion con
        transaccion abierta ("rolling back returned connection"): toda LECTURA bajo
        autocommit=False deja la conexion INTRANS (un SELECT abre transaccion y los call sites
        de lectura no commitean), asi que sin esto el log se llena con ~1 linea por request.
        `rollback()` es no-op si la conexion ya esta IDLE (p. ej. tras un `commit()`).
        """
        pool, self._pool = self._pool, None
        con, self._con = self._con, None
        if con is None:
            return  # ya cerrada
        if pool is None:
            con.close()
            return
        try:
            con.rollback()  # devolver IDLE: sin transaccion abierta -> putconn no avisa
        except Exception:  # noqa: BLE001 -- inservible: que putconn/check la descarte.
            pass
        try:
            pool.putconn(con)
        except Exception:  # noqa: BLE001 -- devolver es best-effort; si falla, cerramos.
            _log.warning("No se pudo devolver la conexion al pool; se cierra.", exc_info=True)
            try:
                con.close()
            except Exception:  # noqa: BLE001
                pass

    def __del__(self) -> None:
        """Red de seguridad ANTI-FUGA de leases del pool.

        Casi todas las funciones de `db.py` hacen `con = _conectar(); ... ; con.close()` SIN
        `try/finally`. Si la funcion lanza ANTES del `con.close()` (un `IntegrityError`, un
        retry, cualquier error), la lease del pool NO se devolveria. Sin pool eso era inocuo
        (el socket lo cerraba el GC); CON pool, cada fuga deja una conexion prestada para
        siempre y, tras `max_size` fugas, todo `getconn()` se cuelga 30 s -> `PoolTimeout` ->
        la app entera se cuelga. Aqui: cuando el `con` local cae de scope sin `close()`, el
        refcount de CPython dispara `__del__` al instante y devolvemos la lease.

        Tras un `close()` explicito esto es un NO-OP (close() ya dejo `_con`/`_pool` en None),
        asi que el camino feliz no paga nada. `__del__` JAMAS propaga (contrato de Python):
        absorbe todo, incluido el shutdown del interprete (pool/logging a medio desmontar).
        """
        try:
            pool, self._pool = self._pool, None
            con, self._con = self._con, None
            if con is None or pool is None:
                return  # ya devuelta por close(), o conexion dedicada (su GC cierra el socket)
            # Lease POOLED fugada: scrub antes de reciclar. `rollback()` suelta locks de
            # transaccion/fila; `pg_advisory_unlock_all()` suelta los de SESION (un rollback NO
            # lo hace), si no una conexion reciclada arrastraria el advisory lock de
            # `lock_barrido` y romperia el single-flight de los barridos.
            try:
                con.rollback()
                con.execute("SELECT pg_advisory_unlock_all()")
                con.commit()
            except Exception:  # noqa: BLE001 -- inservible: que putconn/check la descarte.
                pass
            try:
                pool.putconn(con)
            except Exception:  # noqa: BLE001 -- best-effort; si falla, cerramos para no filtrar.
                try:
                    con.close()
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001 -- __del__ jamas propaga.
            pass


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


# --------------------------------------------------------------------------- #
# Pool de conexiones (psycopg_pool). UNO por proceso, lazy y thread-safe.       #
# --------------------------------------------------------------------------- #
#
# El camino caliente (cientos de call sites) abria una conexion nueva por operacion (TCP +
# handshake de auth de Postgres) y la cerraba: bajo carga, la latencia DOMINANTE y un riesgo de
# tocar `max_connections`. El pool reutiliza conexiones fisicas: `conectar_cruda` toma una en
# prestamo (lease) y `close()` la DEVUELVE en vez de cerrar el socket.
#
# FALLBACK de un solo flag (`KENI_DB_POOL=0`) o si el pool no arranca: se vuelve al camino
# historico de "una conexion por operacion" (ver `_conectar_directa`). Asi un mal comportamiento
# en prod se revierte con UNA env var, sin tocar codigo.

_pool: Any = None  # psycopg_pool.ConnectionPool, o None si no inicializado / fallback
_pool_url: str | None = None  # URL con la que se construyo el pool (rehacer si cambia, p. ej. tests)
_pool_lock = threading.Lock()  # protege el check-then-act de inicializacion del pool
_modo_logueado = False  # log "pool ON/OFF" una sola vez por proceso


def _configurar_conexion(con: Any) -> None:
    """Setup por-conexion del pool: REPLICA lo que aplicaba `psycopg.connect(..., autocommit=False)`.

    El pool crea las conexiones por su cuenta; este `configure` se ejecuta una vez por
    conexion fisica al crearla, de modo que toda conexion prestada llega con `autocommit=False`
    (los call sites hacen `commit()` explicito), igual que el camino directo. El `row_factory`
    NO se fija aqui: se pasa por cursor en `_ConexionPg.execute` (paridad con el camino directo).
    """
    con.autocommit = False


def _crear_pool(url: str) -> Any:
    """Construye el `ConnectionPool` (no abre conexiones aun: `open=False`, se abre en `.open()`)."""
    from psycopg_pool import ConnectionPool

    minimo = config.db_pool_min()
    maximo = config.db_pool_max()
    pool = ConnectionPool(
        conninfo=url,
        min_size=minimo,
        max_size=maximo,
        # `timeout`: segundos que un lease espera por una conexion libre antes de fallar con
        # `PoolTimeout` (mejor un error claro que colgarse para siempre si el MAX se queda corto).
        timeout=30.0,
        # Reciclado: cierra conexiones ociosas mas de `max_idle` y recrea las que superen
        # `max_lifetime`, para no arrastrar conexiones eternas (server reinicia, NAT, etc.).
        max_idle=300.0,
        max_lifetime=3600.0,
        kwargs={"autocommit": False},
        configure=_configurar_conexion,
        # `check`: el pool valida la conexion al PRESTARLA y en `putconn`; una conexion rota se
        # DESCARTA y se recrea en vez de devolverse poisoned al call site siguiente.
        check=ConnectionPool.check_connection,
        open=False,
        name="keni-consola-db",
    )
    pool.open()
    return pool


def _obtener_pool() -> Any:
    """Devuelve el pool del proceso (lo crea lazy y thread-safe), o None si hay que ir directo.

    None significa "usa el camino directo": flag OFF, falta el driver, o el pool no arranco
    (se loguea y se cae al fallback). Si la URL cambio respecto al pool actual (caso de tests
    que reapuntan `DATABASE_URL`), se cierra el viejo y se crea uno nuevo.
    """
    global _pool, _pool_url, _modo_logueado
    if not config.db_pool_activado():
        if not _modo_logueado:
            _log.info("Pool de conexiones Postgres DESACTIVADO (KENI_DB_POOL=0): una conexion por operacion.")
            _modo_logueado = True
        return None
    url = config.database_url()
    if url is None:
        raise RuntimeError(_mensaje_sin_url())
    pool = _pool
    if pool is not None and _pool_url == url:
        return pool
    with _pool_lock:
        if _pool is not None and _pool_url == url:
            return _pool
        # URL distinta (o primer arranque): cierra el pool previo si lo habia.
        if _pool is not None and _pool_url != url:
            try:
                _pool.close()
            except Exception:  # noqa: BLE001
                pass
            _pool = None
            _pool_url = None
        try:
            _pool = _crear_pool(url)
            _pool_url = url
            _log.info(
                "Pool de conexiones Postgres ACTIVADO (min=%s max=%s).",
                config.db_pool_min(), config.db_pool_max(),
            )
            _modo_logueado = True
            return _pool
        except Exception:  # noqa: BLE001 -- fallback: sin pool, una conexion por operacion.
            _log.warning(
                "No se pudo inicializar el pool de conexiones; fallback a una conexion por "
                "operacion.", exc_info=True,
            )
            _modo_logueado = True
            return None


def cerrar_pool() -> None:
    """Cierra el pool del proceso si esta abierto (hook de shutdown; evita filtrar conexiones)."""
    global _pool, _pool_url
    with _pool_lock:
        if _pool is not None:
            try:
                _pool.close()
            except Exception:  # noqa: BLE001
                pass
            _pool = None
            _pool_url = None


# Cierre del pool al terminar el proceso (back/worker/daemons). Es lazy y best-effort: el SO
# reclama los sockets igual, pero cerrar limpio evita warnings de psycopg_pool al salir.
atexit.register(cerrar_pool)


def _conectar_directa(url: str, dict_row: Any) -> _ConexionPg:
    """Camino historico (fallback): UNA conexion psycopg por operacion (`close()` cierra el socket)."""
    import psycopg

    con = psycopg.connect(url, autocommit=False)
    return _ConexionPg(con, dict_row, pool=None)


def conectar_cruda() -> _ConexionPg:
    """Conexion al Postgres operacional SIN crear esquema (lo hace `db._conectar`).

    Exige `DATABASE_URL` (obligatoria, ADR 0004): si falta, lanza un `RuntimeError` con el
    one-liner para arrancar un Postgres local. La eleccion/lectura se hace en tiempo de
    LLAMADA (no al importar), para que los tests aislen el backend con env vars.

    Por defecto toma una conexion en PRESTAMO del pool del proceso (reutiliza el socket; el
    `close()` del call site la devuelve). Con `KENI_DB_POOL=0` o si el pool no arranca, cae al
    camino directo (`_conectar_directa`): una conexion por operacion, identica al comportamiento
    historico. En ambos casos: `autocommit=False` (los call sites hacen `commit()` explicito) y
    filas como dict (`dict_row`) para que `fila["col"]` funcione como con `sqlite3.Row`.
    Importacion DIFERIDA de psycopg/psycopg_pool: solo se necesitan en runtime (extra `postgres`).
    """
    url = config.database_url()
    if url is None:
        raise RuntimeError(_mensaje_sin_url())
    try:
        import psycopg  # noqa: F401 -- valida que el driver este presente
        from psycopg.rows import dict_row
    except ImportError as e:  # pragma: no cover -- solo si falta el extra
        raise RuntimeError(
            "DATABASE_URL esta fijada pero falta el driver de Postgres. Instala el extra "
            "`postgres` (psycopg[binary]) en el entorno del back."
        ) from e
    pool = _obtener_pool()
    if pool is None:
        return _conectar_directa(url, dict_row)
    con = pool.getconn()
    return _ConexionPg(con, dict_row, pool=pool)
