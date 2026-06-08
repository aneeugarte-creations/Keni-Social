"""Configuracion — api/config.py."""

from __future__ import annotations

from typing import TypedDict

from ._base import MarcaDisponible

__all__ = [
    "CredencialesPresentes",
    "RespuestaConfig",
    "CuerpoGuardarConfig",
]


class CredencialesPresentes(TypedDict):
    meta: bool
    youtube: bool
    x: bool
    tiktok: bool


class RespuestaConfig(TypedDict):
    fuente: str
    fuentes_validas: list[str]
    marcas: list[str]
    marcas_disponibles: list[MarcaDisponible]
    credenciales_presentes: CredencialesPresentes


class CuerpoGuardarConfig(TypedDict):
    fuente: str
    marcas: list[str]
