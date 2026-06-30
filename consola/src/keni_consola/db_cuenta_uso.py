"""Persistencia — ULTIMO snapshot del uso de las cuentas de Claude. Implementación de db.py.

Una fila POR CUENTA de Claude (`cuenta` = 'a'|'b'): el muestreo de fondo (`cuenta_uso_daemon`)
corre `claude -p /usage` por cuenta y deja aquí su última lectura, para que el indicador de la
barra lateral y el gate diario lean de la BD sin ejecutar `claude`. `cuenta` es la clave lógica
(índice único + target del UPSERT); `id` la espeja por compat de PK.

Además del snapshot, se mantiene —POR CUENTA— el `semana_pct` Y el `sonnet_pct` AL INICIO DEL DÍA
CDMX (`*_pct_inicio_dia`) para derivar el "consumo de HOY" de cada límite (= `*_pct` actual −
`*_pct_inicio_dia`): los medidores son acumulativos y solo resetean su ventana semanal, así que
dentro de un día crecen de forma monótona. Cada línea base se RUEDA en la primera escritura de cada
día CDMX (se hereda la última lectura del día anterior como valor de medianoche) y se reajusta a la
baja si la ventana semanal resetea a mitad del día (el porcentaje cae), para que el consumo de hoy
nunca sea negativo.
La jornada del equipo es la mexicana: el rollover en la medianoche de México (no la de UTC) evita
que la base se reancle a media tarde y vacíe el consumo del día en plena operación. La columna
`dia_utc` guarda ese día-bucket (ya en jornada CDMX).
"""
from __future__ import annotations

from ._db_comun import (
    Any,
    _conectar,
)
from .tiempo import dia_cdmx

_COLS = (
    "id",
    "cuenta",
    "conectada",
    "semana_pct",
    "sesion_5h_pct",
    "sonnet_pct",
    "reset_semana_iso",
    "reset_semana_txt",
    "semana_pct_inicio_dia",
    "sonnet_pct_inicio_dia",
    "dia_utc",
    "actualizado_ts",
)
_SELECT = f"SELECT {', '.join(_COLS)} FROM cuenta_uso WHERE cuenta = ?"
_SELECT_TODAS = f"SELECT {', '.join(_COLS)} FROM cuenta_uso"


def _normalizar_cuenta(cuenta: str | None) -> str:
    """Selector de cuenta -> 'a'|'b' validado (def 'a'). Contrato `jobspec.CUENTAS`."""
    from .dominio import jobspec

    c = (cuenta or jobspec.CUENTA_A).strip().lower()
    return c if c in jobspec.CUENTAS else jobspec.CUENTA_A


def _fila_a_uso(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `cuenta_uso` en dict (los `*_pct` pueden ser None)."""
    return {col: fila[col] for col in _COLS}


def leer_uso_cuenta(cuenta: str = "a") -> dict[str, Any] | None:
    """El último snapshot del uso de una cuenta de Claude (None si aún no se muestreó nunca)."""
    c = _normalizar_cuenta(cuenta)
    con = _conectar()
    try:
        fila = con.execute(_SELECT, (c,)).fetchone()
    finally:
        con.close()
    return _fila_a_uso(fila) if fila is not None else None


def leer_uso_cuentas() -> dict[str, dict[str, Any] | None]:
    """El último snapshot de TODAS las cuentas: `{'a': {...}|None, 'b': {...}|None}`.

    Una sola lectura de la tabla; cada cuenta sin fila (cold start / nunca logueada) va como None.
    """
    from .dominio import jobspec

    con = _conectar()
    try:
        filas = con.execute(_SELECT_TODAS).fetchall()
    finally:
        con.close()
    por_cuenta = {_normalizar_cuenta(f["cuenta"]): _fila_a_uso(f) for f in filas}
    return {c: por_cuenta.get(c) for c in jobspec.CUENTAS}


def _baseline_col(
    previa: dict[str, Any] | None, dia: str, pct: int | None, k_pct: str, k_base: str
) -> int | None:
    """Línea base del consumo de HOY de UN medidor (`k_pct` actual, `k_base` base del día).

    PURA (sin reloj ni BD): dado el snapshot previo, el día CDMX actual y el `pct` recién leído,
    decide la base del día del medidor. Reglas:
      - Día NUEVO (o sin fila previa): la base es el `pct` del cierre del día anterior (la última
        lectura ≈ el valor de medianoche); si no hay previa, la lectura actual.
      - Mismo día: conserva la base previa, salvo que la ventana semanal haya reseteado a mitad
        del día (`pct` actual < base) — entonces la base baja al valor actual.
    """
    if previa is None or previa.get("dia_utc") != dia:
        base = previa.get(k_pct) if previa else None
        if base is None:
            base = pct
        return base
    base = previa.get(k_base)
    if pct is not None and base is not None and pct < base:
        base = pct
    return base


def _baseline_dia(
    previa: dict[str, Any] | None, dia: str, semana_pct: int | None
) -> tuple[int | None, str]:
    """Base del día del medidor SEMANAL (all-models): `(semana_pct_inicio_dia, dia_utc)`. Envoltura
    fina de `_baseline_col` con las claves del semanal (la fuente del corte por defecto)."""
    return _baseline_col(previa, dia, semana_pct, "semana_pct", "semana_pct_inicio_dia"), dia


def guardar_uso_cuenta(
    *,
    cuenta: str = "a",
    conectada: bool,
    semana_pct: int | None,
    sesion_5h_pct: int | None,
    sonnet_pct: int | None,
    reset_semana_iso: str = "",
    reset_semana_txt: str = "",
    actualizado_ts: float | None = None,
    dia_utc: str | None = None,
) -> dict[str, Any]:
    """Persiste (UPSERT) el último snapshot del uso de una cuenta y devuelve la fila guardada.

    Rueda la línea base del día (`_baseline_dia`) leyendo el snapshot previo DE ESA CUENTA en la
    misma conexión. `dia_utc` (opcional) fija el día-bucket en tests; por defecto se toma el día
    CDMX de hoy (`dia_cdmx()`). NO ejecuta `claude` (eso es del daemon): solo escribe lo ya leído.
    """
    c = _normalizar_cuenta(cuenta)
    dia = dia_utc if dia_utc is not None else dia_cdmx()
    con = _conectar()
    try:
        prev = con.execute(_SELECT, (c,)).fetchone()
        previa = _fila_a_uso(prev) if prev is not None else None
        base, dia = _baseline_dia(previa, dia, semana_pct)
        base_sonnet = _baseline_col(previa, dia, sonnet_pct, "sonnet_pct", "sonnet_pct_inicio_dia")
        fila = {
            "id": c,
            "cuenta": c,
            "conectada": 1 if conectada else 0,
            "semana_pct": semana_pct,
            "sesion_5h_pct": sesion_5h_pct,
            "sonnet_pct": sonnet_pct,
            "reset_semana_iso": reset_semana_iso or "",
            "reset_semana_txt": reset_semana_txt or "",
            "semana_pct_inicio_dia": base,
            "sonnet_pct_inicio_dia": base_sonnet,
            "dia_utc": dia,
            "actualizado_ts": actualizado_ts,
        }
        asignaciones = ", ".join(f"{col} = EXCLUDED.{col}" for col in _COLS if col != "cuenta")
        con.execute(
            f"INSERT INTO cuenta_uso ({', '.join(_COLS)}) "
            f"VALUES ({', '.join('?' for _ in _COLS)}) "
            f"ON CONFLICT (cuenta) DO UPDATE SET {asignaciones}",
            tuple(fila[col] for col in _COLS),
        )
        con.commit()
    finally:
        con.close()
    return fila
