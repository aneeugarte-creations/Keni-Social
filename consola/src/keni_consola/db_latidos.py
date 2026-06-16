"""Persistencia — dominio latidos de daemons (observabilidad). Implementación de db.py.

Una fila por daemon de fondo en `daemon_latidos` (ver DDL en `_db_core`). Los daemons
NO llaman aquí directamente: pasan por la fachada best-effort `latidos.py`, que captura
cualquier fallo de BD (un latido jamás debe romper un barrido). Aquí las operaciones son
normales (propagan excepciones), como el resto de `db_<dominio>`.
"""
from __future__ import annotations

import uuid
from typing import Any

from ._db_comun import _conectar
from .tiempo import ahora_iso

# Tope defensivo del texto de error persistido (un traceback entero no aporta en el panel).
_MAX_ERROR_TXT = 500
# Tope del `resumen` (texto corto de qué hizo el barrido / nº items): el panel muestra una línea.
_MAX_RESUMEN = 300
# COTA dura del historial por daemon (`daemon_barridos`): se recorta a los N barridos mas recientes
# en cada insercion, asi la tabla no crece sin limite (un daemon barre cada pocos minutos).
_MAX_BARRIDOS_POR_DAEMON = 50


def latido_ciclo(daemon: str, *, activo: bool, intervalo_seg: float, tick_seg: float) -> None:
    """Registra que el BUCLE del daemon dio una iteración (vivo), corra o no el sweep.

    Upsert de `visto`/`activo`/`intervalo_seg`/`tick_seg`; no toca los campos de barrido.
    """
    ahora = ahora_iso()
    con = _conectar()
    try:
        con.execute(
            "INSERT INTO daemon_latidos (daemon, visto, activo, intervalo_seg, tick_seg) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (daemon) DO UPDATE SET "
            "visto = EXCLUDED.visto, activo = EXCLUDED.activo, "
            "intervalo_seg = EXCLUDED.intervalo_seg, tick_seg = EXCLUDED.tick_seg",
            (daemon, ahora, 1 if activo else 0, float(intervalo_seg), float(tick_seg)),
        )
        con.commit()
    finally:
        con.close()


def latido_barrido(
    daemon: str,
    *,
    ok: bool,
    intervalo_seg: float,
    tick_seg: float,
    duracion_ms: int = 0,
    error_txt: str = "",
    resumen: str = "",
) -> None:
    """Registra el RESULTADO de un barrido ejecutado (ok o error) + contadores.

    `resumen` (texto corto de qué hizo / nº items) se guarda como `ultimo_resumen` para que
    el panel distinga "corre y TRABAJA" de "corre EN VACIO" sin abrir el historial. En un
    barrido con error se conserva el resumen previo (no se pisa con '').
    """
    ahora = ahora_iso()
    err = (error_txt or "")[:_MAX_ERROR_TXT]
    res = (resumen or "")[:_MAX_RESUMEN]
    con = _conectar()
    try:
        if ok:
            con.execute(
                "INSERT INTO daemon_latidos (daemon, visto, activo, intervalo_seg, tick_seg, "
                "ultimo_barrido, ultimo_ok, duracion_ms, barridos, ultimo_resumen) "
                "VALUES (?, ?, 1, ?, ?, ?, ?, ?, 1, ?) "
                "ON CONFLICT (daemon) DO UPDATE SET "
                "visto = EXCLUDED.visto, activo = 1, "
                "intervalo_seg = EXCLUDED.intervalo_seg, tick_seg = EXCLUDED.tick_seg, "
                "ultimo_barrido = EXCLUDED.ultimo_barrido, ultimo_ok = EXCLUDED.ultimo_ok, "
                "duracion_ms = EXCLUDED.duracion_ms, "
                "ultimo_resumen = EXCLUDED.ultimo_resumen, "
                "barridos = daemon_latidos.barridos + 1",
                (daemon, ahora, float(intervalo_seg), float(tick_seg), ahora, ahora,
                 int(duracion_ms), res),
            )
        else:
            con.execute(
                "INSERT INTO daemon_latidos (daemon, visto, activo, intervalo_seg, tick_seg, "
                "ultimo_barrido, ultimo_error, error_txt, duracion_ms, barridos, errores) "
                "VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, 1, 1) "
                "ON CONFLICT (daemon) DO UPDATE SET "
                "visto = EXCLUDED.visto, activo = 1, "
                "intervalo_seg = EXCLUDED.intervalo_seg, tick_seg = EXCLUDED.tick_seg, "
                "ultimo_barrido = EXCLUDED.ultimo_barrido, "
                "ultimo_error = EXCLUDED.ultimo_error, error_txt = EXCLUDED.error_txt, "
                "duracion_ms = EXCLUDED.duracion_ms, "
                "barridos = daemon_latidos.barridos + 1, "
                "errores = daemon_latidos.errores + 1",
                (daemon, ahora, float(intervalo_seg), float(tick_seg), ahora, ahora, err,
                 int(duracion_ms)),
            )
        con.commit()
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Historial por barrido (`daemon_barridos`): una fila por sweep + recorte con cota #
# --------------------------------------------------------------------------- #


def registrar_barrido(
    daemon: str,
    *,
    ok: bool,
    ts_inicio: str = "",
    duracion_ms: int = 0,
    resumen: str = "",
    error_txt: str = "",
) -> None:
    """Inserta UNA fila de historial por el barrido de `daemon` y recorta el exceso.

    `ts_inicio` es el instante (ISO canon) del barrido; por defecto el actual (los sweeps son
    cortos, asi que `ahora` ≈ inicio). Tras insertar se RECORTA el daemon a sus
    `_MAX_BARRIDOS_POR_DAEMON` barridos mas recientes (cota dura, en la misma conexion). `id`
    es un uuid (como el resto del esquema); `resumen`/`error_txt` se truncan defensivamente.
    """
    bid = uuid.uuid4().hex
    ts = ts_inicio or ahora_iso()
    res = (resumen or "")[:_MAX_RESUMEN]
    err = (error_txt or "")[:_MAX_ERROR_TXT]
    con = _conectar()
    try:
        con.execute(
            "INSERT INTO daemon_barridos (id, daemon, ts_inicio, duracion_ms, ok, resumen, "
            "error_txt) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (bid, daemon, ts, int(duracion_ms), 1 if ok else 0, res, err),
        )
        # Recorte: conserva solo los N mas recientes de ESTE daemon (recientes primero, desempate
        # por id para un orden estable cuando el ts coincide al segundo).
        con.execute(
            "DELETE FROM daemon_barridos WHERE daemon = ? AND id NOT IN ("
            "SELECT id FROM daemon_barridos WHERE daemon = ? "
            "ORDER BY ts_inicio DESC, id DESC LIMIT ?)",
            (daemon, daemon, _MAX_BARRIDOS_POR_DAEMON),
        )
        con.commit()
    finally:
        con.close()


def listar_barridos(daemon: str, limite: int = _MAX_BARRIDOS_POR_DAEMON) -> list[dict[str, Any]]:
    """Barridos recientes de `daemon` (nuevo primero), acotado a `limite` (tope = la cota dura)."""
    limite = max(1, min(int(limite or _MAX_BARRIDOS_POR_DAEMON), _MAX_BARRIDOS_POR_DAEMON))
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT id, daemon, ts_inicio, duracion_ms, ok, resumen, error_txt "
            "FROM daemon_barridos WHERE daemon = ? ORDER BY ts_inicio DESC, id DESC LIMIT ?",
            (daemon, limite),
        ).fetchall()
    finally:
        con.close()
    return [
        {
            "id": f["id"],
            "daemon": f["daemon"],
            "ts_inicio": f["ts_inicio"],
            "duracion_ms": int(f["duracion_ms"]),
            "ok": bool(f["ok"]),
            "resumen": f["resumen"],
            "error_txt": f["error_txt"],
        }
        for f in filas
    ]


def listar_latidos() -> list[dict[str, Any]]:
    """Todas las filas de `daemon_latidos`, ordenadas por nombre (para el panel Sistema)."""
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT daemon, visto, activo, intervalo_seg, tick_seg, ultimo_barrido, "
            "ultimo_ok, ultimo_error, error_txt, duracion_ms, barridos, errores, "
            "barrido_solicitado, ultimo_resumen "
            "FROM daemon_latidos ORDER BY daemon"
        ).fetchall()
    finally:
        con.close()
    return [
        {
            "daemon": f["daemon"],
            "visto": f["visto"],
            "activo": bool(f["activo"]),
            "intervalo_seg": float(f["intervalo_seg"]),
            "tick_seg": float(f["tick_seg"]),
            "ultimo_barrido": f["ultimo_barrido"],
            "ultimo_ok": f["ultimo_ok"],
            "ultimo_error": f["ultimo_error"],
            "error_txt": f["error_txt"],
            "duracion_ms": int(f["duracion_ms"]),
            "barridos": int(f["barridos"]),
            "errores": int(f["errores"]),
            # ISO de la solicitud de barrido forzado pendiente, o '' (el panel puede pintar
            # "barrido solicitado" hasta que el daemon la consuma en su siguiente tick).
            "barrido_solicitado": f["barrido_solicitado"],
            # Resumen del último barrido (qué hizo / nº items), o '' si no aportó: el panel lo
            # muestra para ver de un vistazo si el daemon TRABAJA o corre EN VACIO.
            "ultimo_resumen": f["ultimo_resumen"],
        }
        for f in filas
    ]


# --------------------------------------------------------------------------- #
# Barrido FORZADO (flag cross-proceso back -> daemons)                         #
# --------------------------------------------------------------------------- #


def solicitar_barrido(daemon: str) -> bool:
    """Marca la solicitud de barrido inmediato del daemon (escribe el ISO actual).

    Solo sobre filas EXISTENTES (un daemon que nunca latio no esta registrado): devuelve
    False si no hay fila, True si quedo solicitada (idempotente: re-solicitar refresca el
    timestamp; el daemon la consumira una sola vez).
    """
    con = _conectar()
    try:
        cur = con.execute(
            "UPDATE daemon_latidos SET barrido_solicitado = ? WHERE daemon = ?",
            (ahora_iso(), daemon),
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def consumir_solicitud_barrido(daemon: str) -> bool:
    """Consume (limpia) la solicitud de barrido pendiente del daemon, si la hay.

    ATOMICO (UPDATE condicionado): si dos consumidores compitieran, solo uno ve
    `rowcount == 1`; la solicitud dispara EXACTAMENTE un barrido. True si habia solicitud.
    """
    con = _conectar()
    try:
        cur = con.execute(
            "UPDATE daemon_latidos SET barrido_solicitado = '' "
            "WHERE daemon = ? AND barrido_solicitado <> ''",
            (daemon,),
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()
