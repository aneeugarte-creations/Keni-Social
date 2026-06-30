"""Repositorio — uso de las cuentas de Claude (último snapshot por cuenta). Implementación de repos.py.

El muestreo de fondo escribe (`guardar_uso_cuenta`) por cuenta y el indicador/gate leen
(`leer_uso_cuenta` una cuenta, `leer_uso_cuentas` todas). La fachada delega 1:1 en db.py.
"""
from __future__ import annotations

from ._repos_comun import (
    Any,
    db,
)


def leer_uso_cuenta(cuenta: str = "a") -> dict[str, Any] | None:
    return db.leer_uso_cuenta(cuenta)


def leer_uso_cuentas() -> dict[str, dict[str, Any] | None]:
    return db.leer_uso_cuentas()


def guardar_uso_cuenta(
    *,
    cuenta: str = "a",
    conectada: bool,
    semana_pct: int | None,
    sesion_5h_pct: int | None,
    sonnet_pct: int | None,
    reset_semana_iso: str = "",
    reset_semana_txt: str = "",
    reset_sesion_iso: str = "",
    actualizado_ts: float | None = None,
    dia_utc: str | None = None,
) -> dict[str, Any]:
    return db.guardar_uso_cuenta(
        cuenta=cuenta,
        conectada=conectada,
        semana_pct=semana_pct,
        sesion_5h_pct=sesion_5h_pct,
        sonnet_pct=sonnet_pct,
        reset_semana_iso=reset_semana_iso,
        reset_semana_txt=reset_semana_txt,
        reset_sesion_iso=reset_sesion_iso,
        actualizado_ts=actualizado_ts,
        dia_utc=dia_utc,
    )
