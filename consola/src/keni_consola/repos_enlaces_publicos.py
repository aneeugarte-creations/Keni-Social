"""Repositorio — enlaces PÚBLICOS de campaña. Implementación de repos.py.

Capability-URL de solo lectura: un token indescifrable mapea a UNA campaña y un periodo+modo
congelados. La fachada delega 1:1 en db.py; la validez (caducidad/revocación) la decide
`campanias.py`.
"""
from __future__ import annotations

from ._repos_comun import (
    Any,
    db,
)


def crear_enlace_publico(
    *, campania_id: str, token: str, rango: str, ocultar_ads: bool, expira: str
) -> dict[str, Any]:
    return db.crear_enlace_publico(
        campania_id=campania_id, token=token, rango=rango, ocultar_ads=ocultar_ads, expira=expira
    )


def obtener_enlace_por_token(token: str) -> dict[str, Any] | None:
    return db.obtener_enlace_por_token(token)


def listar_enlaces_de_campania(campania_id: str) -> list[dict[str, Any]]:
    return db.listar_enlaces_de_campania(campania_id)


def desactivar_enlace_publico(enlace_id: str, campania_id: str) -> bool:
    return db.desactivar_enlace_publico(enlace_id, campania_id)
