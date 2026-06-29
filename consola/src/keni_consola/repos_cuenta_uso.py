"""Repositorio — uso de la cuenta de Claude (último snapshot). Implementación de repos.py.

El muestreo de fondo escribe (`guardar_uso_cuenta`) y el endpoint admin lee (`leer_uso_cuenta`).
La fachada delega 1:1 en db.py.
"""
from __future__ import annotations

from ._repos_comun import (
    Any,
    db,
)


def leer_uso_cuenta() -> dict[str, Any] | None:
    return db.leer_uso_cuenta()


def guardar_uso_cuenta(
    *,
    conectada: bool,
    semana_pct: int | None,
    sesion_5h_pct: int | None,
    sonnet_pct: int | None,
    reset_semana_iso: str = "",
    reset_semana_txt: str = "",
    actualizado_ts: float | None = None,
    dia_utc: str | None = None,
) -> dict[str, Any]:
    return db.guardar_uso_cuenta(
        conectada=conectada,
        semana_pct=semana_pct,
        sesion_5h_pct=sesion_5h_pct,
        sonnet_pct=sonnet_pct,
        reset_semana_iso=reset_semana_iso,
        reset_semana_txt=reset_semana_txt,
        actualizado_ts=actualizado_ts,
        dia_utc=dia_utc,
    )
