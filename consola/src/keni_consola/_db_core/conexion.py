"""Conexion a Postgres, asegurado de esquema una-vez-por-proceso y advisory locks.

Extraido de `_db_core.py` al trocearlo por areas (refactor de pura reubicacion). El asegurado
de esquema invoca `_crear_esquema` (modulo `esquema`) via import perezoso para romper el ciclo
conexion<->esquema. Acoplamiento hacia abajo: `config`/`motor_db` + `_comun` + stdlib.
"""
from __future__ import annotations

import hashlib
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from .. import config, motor_db
from ._comun import _log

# URLs de BD cuyo esquema YA aseguramos en ESTE proceso. El DDL (idempotente, ~89 sentencias
# `CREATE ... IF NOT EXISTS` + `ALTER ... ADD COLUMN IF NOT EXISTS`) NO necesita re-ejecutarse en
# CADA conexion: como no hay pool y cada operacion abre su propia conexion, hacerlo en cada
# `_conectar` significaba barrer el catalogo de Postgres en CADA request -> coste real en prod y,
# x16k conexiones, el coste DOMINANTE de la suite (medido: con memo la suite cae ~3.5x). Se asegura
# UNA vez por proceso y URL; tras un deploy el proceso reinicia -> el set se vacia -> se re-crea/migra.
# En tests, un fixture autouse lo limpia por test, de modo que la PRIMERA conexion de cada test
# re-asegura el esquema (preserva la auto-curacion que ejercitan los tests de "BD vieja"/on-demand).
_esquemas_asegurados: set[str] = set()
# Protege el check-then-act sobre `_esquemas_asegurados`: varios hilos daemon (refrescos,
# worker, scanners) abren su PRIMERA conexion casi a la vez al arrancar y correrian el DDL en
# paralelo. El DDL es idempotente (riesgo bajo), pero el lock evita el doble trabajo y deja el
# "asegurar una vez por proceso/URL" limpio y determinista.
_lock_esquemas = threading.Lock()


def _conectar() -> Any:
    """Abre la conexion a Postgres y asegura el esquema UNA vez por proceso/URL.

    `motor_db.conectar_cruda()` abre Postgres con `DATABASE_URL` (obligatoria, ADR 0004) y
    devuelve una conexion que IMITA la API de `sqlite3.Connection` que usan los call sites
    (`execute(sql, params)` con `?`, filas por nombre, `rowcount`, commit/close).

    El esquema (idempotente) se crea/migra la PRIMERA vez que este proceso ve una URL dada; las
    siguientes conexiones a la misma BD se saltan el DDL (ver `_esquemas_asegurados`).
    """
    con = motor_db.conectar_cruda()
    url = config.database_url() or ""
    # Lock de modulo: el check-then-act corre en varios hilos daemon al arranque (ver
    # `_lock_esquemas`). Doble-check dentro del lock para asegurar el esquema UNA sola vez.
    if url not in _esquemas_asegurados:
        # Import perezoso: `esquema` depende de `conexion` (advisory locks), asi que el ciclo
        # se rompe difiriendo este import al primer `_conectar` (no al cargar el modulo).
        from .esquema import _crear_esquema

        try:
            with _lock_esquemas:
                if url not in _esquemas_asegurados:
                    _crear_esquema(con)
                    _esquemas_asegurados.add(url)
        except Exception:  # noqa: BLE001 -- limpiar y re-lanzar: la conexion no debe fugarse
            # Si una migracion lanza, la conexion recien abierta NO debe fugarse: se descarta
            # (cierra el socket; el servidor suelta cualquier lock de sesion) antes de propagar.
            descartar = getattr(con, "descartar", None)
            if descartar is not None:
                descartar()
            else:
                con.close()
            raise
    return con


def conectar() -> Any:
    """Conexion publica al backend (mismo `_conectar`, expuesto para `auth/`).

    El esquema de `usuarios`/`sesiones` se crea aqui igual que el resto de tablas, de modo
    que `auth/` puede operar sin duplicar la creacion del esquema. Cada operacion
    abre/cierra su propia conexion.
    """
    return _conectar()


# --------------------------------------------------------------------------- #
# Locks de aplicacion CROSS-PROCESO (Postgres advisory locks)                  #
# --------------------------------------------------------------------------- #
# Sin pool de conexiones, cada operacion abre su propia conexion: el unico mutex que cruza
# procesos (back, worker, daemons, replicas) es un advisory lock de Postgres. Lo usamos para
# el SINGLE-FLIGHT de los barridos (radar/autogen/pipeline): un segundo barrido concurrente
# (deploy solapado, admin pulsando "ejecutar" mientras corre el daemon) NO debe duplicar
# items del tablero ni runs de `claude -p`, porque su dedup es leer-luego-escribir en Python.
# `pg_try_advisory_lock` es NO bloqueante: si otro ya lo tiene, devolvemos False y el segundo
# barrido sale de inmediato (no encola, no espera). El lock se suelta al cerrar la conexion
# (o explicitamente con `pg_advisory_unlock`).

# Espacio de nombres (clave alta de 32 bits del par de claves int) para no colisionar con
# advisory locks de otros subsistemas. Arbitrario pero estable.
_LOCK_NS_BARRIDO = 0x4B53  # 'KS'


def _clave_lock(nombre: str) -> int:
    """Deriva una clave estable de 32 bits (con signo) para un advisory lock a partir de texto."""
    h = int.from_bytes(hashlib.blake2b(nombre.encode("utf-8"), digest_size=4).digest(), "big")
    # Postgres usa bigint con signo; `pg_*_advisory_lock(int4, int4)` toma int de 32 bits.
    return h - 0x1_0000_0000 if h >= 0x8000_0000 else h


@contextmanager
def lock_barrido(nombre: str) -> Iterator[bool]:
    """Single-flight CROSS-PROCESO de un barrido. `with lock_barrido("autogen") as ok:`.

    Intenta tomar un advisory lock de Postgres (`pg_try_advisory_lock`, NO bloqueante) keyed
    en `nombre`. `ok` es True si ESTE proceso lo obtuvo (debe ejecutar el barrido) o False si
    otro lo retiene ahora mismo (debe abortar sin hacer nada). El lock se mantiene mientras
    dure el `with` y se suelta SIEMPRE al salir (incluso ante excepcion), sobre una conexion
    propia dedicada que no se reusa para el trabajo. Es no-op-friendly: el caller solo
    comprueba `ok`.
    """
    clave = _clave_lock(nombre)
    con = _conectar()
    obtenido = False
    try:
        fila = con.execute(
            "SELECT pg_try_advisory_lock(?, ?) AS ok", (_LOCK_NS_BARRIDO, clave)
        ).fetchone()
        con.commit()
        obtenido = bool(fila["ok"]) if fila is not None else False
        yield obtenido
    finally:
        if obtenido:
            try:
                con.execute(
                    "SELECT pg_advisory_unlock(?, ?)", (_LOCK_NS_BARRIDO, clave)
                )
                con.commit()
            except Exception:  # noqa: BLE001 -- soltar fallo: DESCARTAR la conexion (no reciclarla).
                # CRITICO con pool: si el unlock falla y la conexion VOLVIERA al pool, el lock de
                # SESION seguiria pegado a ese socket reciclado y TODOS los `lock_barrido`
                # posteriores verian ok=False hasta el reciclado (~1 h): single-flight envenenado.
                # `descartar()` cierra el socket (el servidor libera los locks de sesion) y deja
                # que el pool reponga una conexion fresca. El `close()` de abajo queda como no-op.
                _log.warning(
                    "No se pudo soltar el advisory lock de barrido %s; se descarta la conexion.",
                    nombre,
                )
                descartar = getattr(con, "descartar", None)
                if descartar is not None:
                    descartar()
        con.close()
