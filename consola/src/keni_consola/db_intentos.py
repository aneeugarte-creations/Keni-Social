"""Persistencia — contador de intentos por etapa del pipeline. Implementación de db.py (ver barrel `db.py`)."""
from __future__ import annotations

from ._db_comun import (
    _conectar,
)
from .tiempo import ahora_iso, iso_o_vacio

# --------------------------------------------------------------------------- #
# Contador de intentos por ETAPA (anti reintento desbocado)                     #
# --------------------------------------------------------------------------- #
#
# Una fila por `(sujeto, etapa)` con el nº de intentos consumidos de esa fase y el instante del
# ultimo. `sujeto` es el `publicacion_id` (tema) o el `cluster_id` (verificacion pre-tablero,
# antes de que exista tema); `etapa` es el nombre estable de la fase. El contador vive en su
# PROPIA tabla (no en `copy_pendiente`) para SOBREVIVIR a la purga de la cola y a un "exito
# vacio" que limpiaria el pendiente. Al ÉXITO de la etapa la fila se BORRA (`reset_intentos_etapa`).


def intentos_etapa(sujeto: str, etapa: str) -> int:
    """Intentos ya consumidos de la `etapa` para el `sujeto`. 0 si no hay fila."""
    if not sujeto or not etapa:
        return 0
    con = _conectar()
    try:
        fila = con.execute(
            "SELECT n FROM intentos_etapa WHERE sujeto = ? AND etapa = ?",
            (sujeto, etapa),
        ).fetchone()
    finally:
        con.close()
    return int(fila["n"]) if fila is not None else 0


def anotar_intento_etapa(sujeto: str, etapa: str) -> int:
    """Suma 1 al contador de la `etapa` del `sujeto` y devuelve el nuevo valor (UPSERT atomico).

    Un solo `INSERT ... ON CONFLICT DO UPDATE`: crea la fila con `n=1` o incrementa `n=n+1`,
    refrescando `actualizado=now()` (el instante del ultimo intento, base del backoff). Devuelve
    el `n` resultante. 0 si faltan `sujeto`/`etapa` (no se anota nada).
    """
    if not sujeto or not etapa:
        return 0
    ahora = ahora_iso()
    con = _conectar()
    try:
        fila = con.execute(
            "INSERT INTO intentos_etapa (sujeto, etapa, n, actualizado) VALUES (?, ?, 1, ?) "
            "ON CONFLICT (sujeto, etapa) DO UPDATE SET "
            "n = intentos_etapa.n + 1, actualizado = EXCLUDED.actualizado "
            "RETURNING n",
            (sujeto, etapa, ahora),
        ).fetchone()
        con.commit()
    finally:
        con.close()
    return int(fila["n"]) if fila is not None else 0


def intento_ts(sujeto: str, etapa: str) -> str | None:
    """Instante (ISO) del ultimo intento de la `etapa` del `sujeto`, o None si no hay fila.

    Lo usa el backoff creciente entre reintentos (`actualizado` es timestamptz, se re-emite al
    canon ISO). None = aun no se ha anotado ningun intento (no hay espera que aplicar).
    """
    if not sujeto or not etapa:
        return None
    con = _conectar()
    try:
        fila = con.execute(
            "SELECT actualizado FROM intentos_etapa WHERE sujeto = ? AND etapa = ?",
            (sujeto, etapa),
        ).fetchone()
    finally:
        con.close()
    if fila is None:
        return None
    return iso_o_vacio(fila["actualizado"]) or None


def reset_intentos_etapa(sujeto: str, etapa: str) -> None:
    """Borra la fila de intentos de la `etapa` del `sujeto`. Se llama al ÉXITO de la etapa. Idempotente."""
    if not sujeto or not etapa:
        return
    con = _conectar()
    try:
        con.execute(
            "DELETE FROM intentos_etapa WHERE sujeto = ? AND etapa = ?",
            (sujeto, etapa),
        )
        con.commit()
    finally:
        con.close()
