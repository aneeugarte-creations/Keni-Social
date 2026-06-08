"""Limites de caracteres por red — api/limites.py / limites_plataforma.py."""

from __future__ import annotations

from typing import TypedDict

__all__ = [
    "LimiteRed",
    "RespuestaLimites",
]


class LimiteRed(TypedDict):
    """Limite de caracteres canonico de una red (fuente unica, `GET /api/limites`).

    `limite` es `null` si la red no tiene tope tecnico practico (Facebook/YouTube).
    """

    id: str
    nombre: str
    limite: int | None


class RespuestaLimites(TypedDict):
    """Respuesta de `GET /api/limites`: los limites por red, en orden fijo."""

    limites: list[LimiteRed]
