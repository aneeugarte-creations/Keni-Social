"""Repositorio — dominio Vistas guardadas de Analíticas. Implementación de repos.py.

Una vista guardada es un preset nombrado del dashboard de Métricas (config de vista + marca
+ periodo). La fachada delega 1:1 en db.py.
"""
from __future__ import annotations

from ._comun import (
    Any,
    db,
)


def crear_vista(
    *,
    nombre: str,
    marca: str,
    periodo: str,
    config: dict[str, Any],
    autor_id: str = "",
    autor_nombre: str = "",
) -> dict[str, Any]:
    return db.crear_vista(
        nombre=nombre,
        marca=marca,
        periodo=periodo,
        config=config,
        autor_id=autor_id,
        autor_nombre=autor_nombre,
    )


def listar_vistas(marca: str | None = None) -> list[dict[str, Any]]:
    return db.listar_vistas(marca=marca)


def obtener_vista(vista_id: str) -> dict[str, Any] | None:
    return db.obtener_vista(vista_id)


def actualizar_vista(vista_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    return db.actualizar_vista(vista_id, campos)


def borrar_vista(vista_id: str) -> bool:
    return db.borrar_vista(vista_id)
