"""Repositorio — dominio metricas. Implementación de repos.py (ver barrel `repos.py`)."""
from __future__ import annotations

from ._repos_comun import (
    Any,
    db,
)

# --------------------------------------------------------------------------- #
# Histórico de metricas POR PIEZA (serie temporal general; ADR 0007)            #
# --------------------------------------------------------------------------- #


def registrar_snapshot_pieza(
    pieza_id: str,
    marca: str,
    red: str,
    formato: str,
    ts: str,
    metricas: dict[str, Any],
) -> bool:
    return db.registrar_snapshot_pieza(pieza_id, marca, red, formato, ts, metricas)


def serie_pieza(pieza_id: str, *, limite: int | None = None) -> list[dict[str, Any]]:
    return db.serie_pieza(pieza_id, limite=limite)


def listar_snapshots_piezas(
    marca: str | None = None,
    red: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
    *,
    limite: int | None = None,
) -> list[dict[str, Any]]:
    return db.listar_snapshots_piezas(
        marca=marca, red=red, desde=desde, hasta=hasta, limite=limite
    )


def purgar_snapshots_piezas(retencion_dias: int, ahora_iso: str) -> int:
    return db.purgar_snapshots_piezas(retencion_dias, ahora_iso)



# --------------------------------------------------------------------------- #
# Cache de metricas (OPERACIONAL: Postgres via db.py; lo orquesta metricas_cache.py) #
# --------------------------------------------------------------------------- #


def leer_metricas_cache(clave: str) -> dict[str, Any] | None:
    return db.leer_metricas_cache(clave)


def listar_metricas_cache_por_tipo(tipos: tuple[str, ...]) -> list[dict[str, Any]]:
    return db.listar_metricas_cache_por_tipo(tipos)


def guardar_metricas_cache(
    clave: str,
    tipo: str,
    rango: str,
    marca: str,
    payload: dict[str, Any],
    fuente: str,
    generado_en: str,
) -> None:
    return db.guardar_metricas_cache(
        clave, tipo, rango, marca, payload, fuente, generado_en
    )


def purgar_metricas_cache(
    prefijo_vigente: str, corte_rangos_adhoc: str, tipos: tuple[str, ...]
) -> int:
    return db.purgar_metricas_cache(prefijo_vigente, corte_rangos_adhoc, tipos)
