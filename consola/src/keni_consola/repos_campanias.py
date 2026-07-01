"""Repositorio — dominio Campañas (filtro por hashtag). Implementación de repos.py.

Una campaña define un filtro (marcas + hashtags) sobre las piezas ya publicadas; su
analítica se computa al vuelo en `campanias.py`. La fachada delega 1:1 en db.py.
"""
from __future__ import annotations

from ._repos_comun import (
    Any,
    db,
)


def crear_campania(
    *,
    marcas: list[str],
    nombre: str,
    hashtags: list[str],
    etiqueta_web: str = "",
    precio_venta: float = 0.0,
    margen_objetivo_pct: float = 40.0,
    activa: bool = True,
) -> dict[str, Any]:
    return db.crear_campania(
        marcas=marcas,
        nombre=nombre,
        hashtags=hashtags,
        etiqueta_web=etiqueta_web,
        precio_venta=precio_venta,
        margen_objetivo_pct=margen_objetivo_pct,
        activa=activa,
    )


def listar_campanias(marca: str | None = None) -> list[dict[str, Any]]:
    return db.listar_campanias(marca=marca)


def obtener_campania(campania_id: str) -> dict[str, Any] | None:
    return db.obtener_campania(campania_id)


def actualizar_campania(
    campania_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_campania(campania_id, campos)


def borrar_campania(campania_id: str) -> bool:
    return db.borrar_campania(campania_id)
