"""Persistencia — dominio latidos de daemons (observabilidad). Implementación de db.py.

Una fila por daemon de fondo en `daemon_latidos` (ver DDL en `_db_core`). Los daemons
NO llaman aquí directamente: pasan por la fachada best-effort `latidos.py`, que captura
cualquier fallo de BD (un latido jamás debe romper un barrido). Aquí las operaciones son
normales (propagan excepciones), como el resto de `db_<dominio>`.
"""
from __future__ import annotations

from typing import Any

from ._db_comun import _conectar
from .tiempo import ahora_iso

# Tope defensivo del texto de error persistido (un traceback entero no aporta en el panel).
_MAX_ERROR_TXT = 500


def latido_ciclo(daemon: str, *, activo: bool, intervalo_seg: float, tick_seg: float) -> None:
    """Registra que el BUCLE del daemon dio una vuelta (vivo), corra o no el sweep.

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
) -> None:
    """Registra el RESULTADO de un barrido ejecutado (ok o error) + contadores."""
    ahora = ahora_iso()
    err = (error_txt or "")[:_MAX_ERROR_TXT]
    con = _conectar()
    try:
        if ok:
            con.execute(
                "INSERT INTO daemon_latidos (daemon, visto, activo, intervalo_seg, tick_seg, "
                "ultimo_barrido, ultimo_ok, duracion_ms, barridos) "
                "VALUES (?, ?, 1, ?, ?, ?, ?, ?, 1) "
                "ON CONFLICT (daemon) DO UPDATE SET "
                "visto = EXCLUDED.visto, activo = 1, "
                "intervalo_seg = EXCLUDED.intervalo_seg, tick_seg = EXCLUDED.tick_seg, "
                "ultimo_barrido = EXCLUDED.ultimo_barrido, ultimo_ok = EXCLUDED.ultimo_ok, "
                "duracion_ms = EXCLUDED.duracion_ms, "
                "barridos = daemon_latidos.barridos + 1",
                (daemon, ahora, float(intervalo_seg), float(tick_seg), ahora, ahora,
                 int(duracion_ms)),
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


def listar_latidos() -> list[dict[str, Any]]:
    """Todas las filas de `daemon_latidos`, ordenadas por nombre (para el panel Sistema)."""
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT daemon, visto, activo, intervalo_seg, tick_seg, ultimo_barrido, "
            "ultimo_ok, ultimo_error, error_txt, duracion_ms, barridos, errores "
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
        }
        for f in filas
    ]
