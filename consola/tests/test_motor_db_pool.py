"""Tests del POOL de conexiones Postgres (`keni_consola.motor_db`).

El pool reutiliza conexiones fisicas en el camino caliente (cientos de call sites): cada
operacion hacia `_conectar()` -> `conectar_cruda()` toma una conexion en PRESTAMO y su
`close()` la DEVUELVE en vez de cerrar el socket. Aqui se prueba, SIN Postgres (pool falso
inyectado via `_crear_pool`), que:

  - el pool reutiliza conexiones (misma conexion fisica en leases secuenciales);
  - `.close()` DEVUELVE al pool (el numero de conexiones vivas se mantiene acotado en un
    bucle de N connect/close);
  - el FALLBACK (`KENI_DB_POOL=0`) usa el camino directo (una conexion por operacion);
  - una conexion ROTA no se devuelve poisoned (el pool la descarta en `putconn`).

No requiere Postgres ni `psycopg_pool` reales: se monkeypatchea `motor_db._crear_pool` para
devolver un pool falso con la misma superficie (`getconn`/`putconn`/`close`).
"""

from __future__ import annotations

import threading

import pytest

from keni_consola import motor_db


# --------------------------------------------------------------------------- #
# Dobles de prueba: conexion + pool falsos con la superficie que usa el wrapper #
# --------------------------------------------------------------------------- #


class _ConFalsa:
    """Conexion falsa: lo que el wrapper toca (`autocommit`, `close`, y en la ruta de fuga
    `rollback`/`execute`/`commit` del scrub). Registra el scrub para verificarlo."""

    _siguiente_id = 0

    def __init__(self) -> None:
        _ConFalsa._siguiente_id += 1
        self.id = _ConFalsa._siguiente_id
        self.autocommit = False
        self.closed = False
        self.rota = False  # marca de "transaccion/conexion rota" para el caso poisoned
        self.rollbacks = 0
        self.sql_ejecutado: list[str] = []

    def close(self) -> None:
        self.closed = True

    def rollback(self) -> None:
        if self.rota:
            raise RuntimeError("conexion rota")
        self.rollbacks += 1

    def execute(self, sql, params=()):  # noqa: ANN001 -- firma minima del scrub
        if self.rota:
            raise RuntimeError("conexion rota")
        self.sql_ejecutado.append(sql)

    def commit(self) -> None:
        if self.rota:
            raise RuntimeError("conexion rota")


class _PoolFalso:
    """Pool falso con `getconn`/`putconn`/`close`. Cuenta reusos y descartes.

    `putconn` imita a psycopg_pool: si la conexion esta cerrada o marcada `rota`, la DESCARTA
    (no la reencola); si esta sana, la devuelve al banco de libres para reusarla.
    """

    def __init__(self) -> None:
        self._libres: list[_ConFalsa] = []
        self._lock = threading.Lock()
        self.vivas = 0  # conexiones existentes (prestadas o en el banco)
        self.descartadas = 0
        self.closed = False

    def getconn(self) -> _ConFalsa:
        with self._lock:
            if self._libres:
                return self._libres.pop()
            con = _ConFalsa()
            self.vivas += 1
            return con

    def putconn(self, con: _ConFalsa) -> None:
        with self._lock:
            if con.closed or con.rota:
                self.vivas -= 1
                self.descartadas += 1
                return
            self._libres.append(con)

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def pool_falso(monkeypatch):
    """Activa el pool con un `_PoolFalso` inyectado y `DATABASE_URL` presente.

    Resetea el estado global del modulo (pool/url/flag de log) antes y despues, para no
    contaminar otros tests que comparten el proceso.
    """
    monkeypatch.setenv("DATABASE_URL", "postgresql://x:y@localhost:5432/keni_test")
    monkeypatch.setenv("KENI_DB_POOL", "1")  # la suite usa pool pequeño; fijamos ON explícito para aislar este test

    falso = _PoolFalso()
    monkeypatch.setattr(motor_db, "_crear_pool", lambda url: falso)
    # Estado global limpio antes de empezar.
    monkeypatch.setattr(motor_db, "_pool", None)
    monkeypatch.setattr(motor_db, "_pool_url", None)
    monkeypatch.setattr(motor_db, "_modo_logueado", False)
    yield falso
    # No dejamos el pool falso colgado en el global del modulo (monkeypatch ya revierte los
    # attrs, pero por claridad).
    motor_db.cerrar_pool()


# --------------------------------------------------------------------------- #
# Reuso: misma conexion fisica en leases secuenciales                          #
# --------------------------------------------------------------------------- #


def test_pool_reutiliza_la_conexion(pool_falso):
    con1 = motor_db.conectar_cruda()
    id1 = con1._con.id
    con1.close()  # devuelve al pool

    con2 = motor_db.conectar_cruda()
    id2 = con2._con.id
    con2.close()

    assert id1 == id2  # se reuso la MISMA conexion fisica
    assert pool_falso.vivas == 1  # nunca se creo una segunda


def test_close_devuelve_al_pool_no_cierra_socket(pool_falso):
    con = motor_db.conectar_cruda()
    fisica = con._con
    con.close()
    assert fisica.closed is False  # NO se cerro el socket: se devolvio al pool


def test_bucle_de_connect_close_acotado(pool_falso):
    # N operaciones secuenciales connect/close NO deben crear N conexiones: el pool reusa.
    for _ in range(50):
        con = motor_db.conectar_cruda()
        con.close()
    assert pool_falso.vivas == 1
    assert pool_falso.descartadas == 0


def test_close_idempotente(pool_falso):
    con = motor_db.conectar_cruda()
    con.close()
    con.close()  # segundo close: no-op, no rompe ni descarta de mas
    assert pool_falso.vivas == 1


# --------------------------------------------------------------------------- #
# Conexion rota: no se devuelve poisoned                                       #
# --------------------------------------------------------------------------- #


def test_conexion_rota_no_se_devuelve_poisoned(pool_falso):
    con = motor_db.conectar_cruda()
    con._con.rota = True  # simula transaccion/conexion en mal estado
    con.close()
    assert pool_falso.descartadas == 1
    assert pool_falso.vivas == 0  # la rota se descarto, no quedo en el banco de libres

    # La siguiente lease crea una conexion NUEVA y sana (no reusa la rota).
    con2 = motor_db.conectar_cruda()
    assert con2._con.rota is False
    con2.close()


def test_putconn_que_falla_cierra_la_conexion(pool_falso, monkeypatch):
    # Si devolver al pool lanza (conexion inservible), `close()` cierra el socket y NO filtra
    # la lease ni propaga la excepcion.
    con = motor_db.conectar_cruda()
    fisica = con._con

    def _putconn_explota(_c):
        raise RuntimeError("pool roto")

    monkeypatch.setattr(pool_falso, "putconn", _putconn_explota)
    con.close()  # no debe propagar
    assert fisica.closed is True


# --------------------------------------------------------------------------- #
# Fallback: KENI_DB_POOL=0 usa el camino directo (una conexion por operacion)  #
# --------------------------------------------------------------------------- #


def test_fallback_flag_off_usa_camino_directo(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x:y@localhost:5432/keni_test")
    monkeypatch.setenv("KENI_DB_POOL", "0")
    monkeypatch.setattr(motor_db, "_pool", None)
    monkeypatch.setattr(motor_db, "_pool_url", None)
    monkeypatch.setattr(motor_db, "_modo_logueado", False)

    # El pool NO debe construirse cuando el flag esta OFF.
    def _no_crear(url):
        raise AssertionError("no debe crearse el pool con KENI_DB_POOL=0")

    monkeypatch.setattr(motor_db, "_crear_pool", _no_crear)
    assert motor_db._obtener_pool() is None

    # Y `conectar_cruda` debe ir por el camino directo (`_conectar_directa`): lo verificamos
    # interceptandolo (no abrimos Postgres real).
    llamado = {}

    def _directa_fake(url, dict_row):
        llamado["url"] = url
        return motor_db._ConexionPg(_ConFalsa(), dict_row, pool=None)

    monkeypatch.setattr(motor_db, "_conectar_directa", _directa_fake)
    con = motor_db.conectar_cruda()
    assert llamado["url"] == "postgresql://x:y@localhost:5432/keni_test"
    assert con._pool is None  # conexion dedicada: su close() cerraria el socket
    con.close()


def test_fallback_si_pool_no_arranca(monkeypatch):
    # Si construir el pool LANZA, `_obtener_pool` cae a None (camino directo) sin propagar.
    monkeypatch.setenv("DATABASE_URL", "postgresql://x:y@localhost:5432/keni_test")
    monkeypatch.setenv("KENI_DB_POOL", "1")  # ON explícito para probar el fallback de arranque del pool
    monkeypatch.setattr(motor_db, "_pool", None)
    monkeypatch.setattr(motor_db, "_pool_url", None)
    monkeypatch.setattr(motor_db, "_modo_logueado", False)

    def _crear_explota(url):
        raise RuntimeError("psycopg_pool no disponible")

    monkeypatch.setattr(motor_db, "_crear_pool", _crear_explota)
    assert motor_db._obtener_pool() is None


def test_pool_se_rehace_si_cambia_la_url(monkeypatch):
    # Cambiar `DATABASE_URL` (caso de tests que reapuntan la BD) cierra el pool viejo y crea
    # uno nuevo para la URL nueva.
    monkeypatch.setenv("KENI_DB_POOL", "1")  # la suite usa pool pequeño; fijamos ON explícito para aislar este test
    monkeypatch.setattr(motor_db, "_pool", None)
    monkeypatch.setattr(motor_db, "_pool_url", None)
    monkeypatch.setattr(motor_db, "_modo_logueado", False)

    pools: list[_PoolFalso] = []

    def _crear(url):
        p = _PoolFalso()
        pools.append(p)
        return p

    monkeypatch.setattr(motor_db, "_crear_pool", _crear)

    monkeypatch.setenv("DATABASE_URL", "postgresql://x:y@localhost:5432/db_a")
    p1 = motor_db._obtener_pool()
    monkeypatch.setenv("DATABASE_URL", "postgresql://x:y@localhost:5432/db_b")
    p2 = motor_db._obtener_pool()

    assert p1 is not p2
    assert p1.closed is True  # el pool de la URL vieja se cerro
    assert len(pools) == 2
    motor_db.cerrar_pool()


# --------------------------------------------------------------------------- #
# Red de seguridad __del__: una lease soltada SIN close() vuelve al pool (GC)  #
# (regresion del bug de fuga que agotaba el pool -> PoolTimeout -> app colgada)#
# --------------------------------------------------------------------------- #


def test_del_devuelve_la_lease_fugada_sin_close(pool_falso):
    """Patron historico de `db.py`: `con = _conectar(); ... ; con.close()` sin try/finally.
    Si la funcion lanza antes del close(), la lease se 'fuga'. La red `__del__` la devuelve
    por GC, asi el pool NO se agota (el bug original dejaba `vivas` creciendo sin tope)."""
    import gc

    for _ in range(50):
        con = motor_db.conectar_cruda()
        del con  # se cae de scope SIN close() (simula un raise a mitad de una funcion db.py)
        gc.collect()

    assert pool_falso.vivas <= 1, f"el pool se fuga: vivas={pool_falso.vivas}"


def test_del_scrubea_la_lease_fugada_antes_de_reciclar(pool_falso):
    """En la fuga, antes de reciclar se hace rollback + `pg_advisory_unlock_all` (soltar los
    locks de SESION, que el rollback NO suelta), para no arrastrar el advisory lock de
    `lock_barrido` a la siguiente lease y romper el single-flight."""
    import gc

    wrap = motor_db.conectar_cruda()
    cruda = wrap._con  # la _ConFalsa subyacente; la mantenemos viva para inspeccionarla
    del wrap
    gc.collect()

    assert cruda.rollbacks >= 1
    assert any("pg_advisory_unlock_all" in s for s in cruda.sql_ejecutado)


def test_del_es_noop_tras_close_explicito(pool_falso):
    """Tras un `close()` explicito (camino feliz), `__del__` no hace NADA: no re-scrubea ni
    doble-devuelve (close() ya dejo `_con`/`_pool` en None)."""
    import gc

    wrap = motor_db.conectar_cruda()
    cruda = wrap._con
    wrap.close()
    rollbacks_tras_close = cruda.rollbacks
    del wrap
    gc.collect()

    assert cruda.rollbacks == rollbacks_tras_close  # __del__ fue no-op


# --------------------------------------------------------------------------- #
# Cobertura del CAMINO REAL del pool contra Postgres de CI                     #
# (la SUITE corre con pool OFF por la infra de tests; esto cubre el path prod) #
# --------------------------------------------------------------------------- #


def test_pool_real_pg_patron_de_fuga_no_agota(monkeypatch):
    """Contra la BD real de CI, fuerza el pool ON con `max_size` pequeño y ejecuta el PATRON
    DE FUGA exacto (lease + `raise` SIN `close()`) muchas mas veces que `max_size`. Solo
    sobrevive si las leases se DEVUELVEN (try/finally en los call sites + red `__del__`); si
    se fugaran, `PoolTimeout`. Skip si no hay Postgres real (`KENI_TEST_DATABASE_URL`)."""
    import os

    url = os.environ.get("KENI_TEST_DATABASE_URL")
    if not url:
        pytest.skip("sin KENI_TEST_DATABASE_URL: requiere Postgres real")
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("KENI_DB_POOL", "1")  # MAX pequeño explícito; aqui probamos el pool REAL contra Postgres
    monkeypatch.setenv("KENI_DB_POOL_MIN", "1")
    monkeypatch.setenv("KENI_DB_POOL_MAX", "6")
    monkeypatch.setattr(motor_db, "_pool", None)
    monkeypatch.setattr(motor_db, "_pool_url", None)
    monkeypatch.setattr(motor_db, "_modo_logueado", False)
    try:
        for _ in range(40):  # 40 >> max_size=6: solo pasa si cada lease vuelve al pool
            con = motor_db.conectar_cruda()
            try:
                con.execute("SELECT * FROM tabla_inexistente_para_fuga")  # lanza
                con.close()  # NUNCA se alcanza
            except Exception:
                pass  # la lease se 'fuga' aqui; debe recuperarse o el pool se agota
        # Si llegamos sin PoolTimeout, el pool no se fugó: una lease mas debe ir bien.
        con = motor_db.conectar_cruda()
        try:
            assert con.execute("SELECT 1 AS uno").fetchone()["uno"] == 1
        finally:
            con.close()
    finally:
        motor_db.cerrar_pool()
