"""Repositorio — dominio Campañas (filtro por hashtag). Implementación de repos.py.

Una campaña define un filtro (marcas + hashtags) sobre las piezas ya publicadas; su
analítica se computa al vuelo en `campanias.py`. La fachada delega 1:1 en db.py.
"""
from __future__ import annotations

from ._repos_comun import (
    Any,
    db,
)


def crear_campania_comercial(
    *, marcas: list[str], nombre: str, hashtags: list[str], activa: bool = True
) -> dict[str, Any]:
    return db.crear_campania_comercial(
        marcas=marcas, nombre=nombre, hashtags=hashtags, activa=activa
    )


def listar_campanias_comerciales(marca: str | None = None) -> list[dict[str, Any]]:
    return db.listar_campanias_comerciales(marca=marca)


def obtener_campania_comercial(campania_id: str) -> dict[str, Any] | None:
    return db.obtener_campania_comercial(campania_id)


def actualizar_campania_comercial(
    campania_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_campania_comercial(campania_id, campos)


def borrar_campania_comercial(campania_id: str) -> bool:
    return db.borrar_campania_comercial(campania_id)
