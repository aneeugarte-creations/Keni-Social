"""Interfaces comunes: una fuente de metricas y un adaptador por plataforma.

`FuenteMetricas` es lo que consumen las tools del MCP. Hay dos implementaciones:
- `FuenteMuestra` (datos offline, para tests y para usar mientras llegan los permisos
  reales de cada plataforma).
- `FuenteCompuesta` (en `agregador.py`), que combina varios `AdaptadorPlataforma`
  reales por marca.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from ..schema import Cuenta, MetricaPlataforma, Pieza, Plataforma, ResumenMetricas


@runtime_checkable
class FuenteMetricas(Protocol):
    """Origen de metricas que las tools del MCP consultan."""

    nombre: str

    def cuentas(self) -> list[Cuenta]: ...

    def resumen(self, cuenta_id: str, rango: str) -> ResumenMetricas: ...

    def mejores_piezas(self, cuenta_id: str, rango: str, n: int) -> list[Pieza]: ...


@runtime_checkable
class AdaptadorPlataforma(Protocol):
    """Lee metricas de UNA plataforma para un handle/id de cuenta concreto."""

    plataforma: Plataforma

    def disponible(self) -> bool:
        """True si hay credenciales suficientes para operar (si no, se omite)."""
        ...

    def metricas(self, handle: str, desde: date, hasta: date) -> MetricaPlataforma | None: ...

    def piezas(self, handle: str, desde: date, hasta: date, n: int) -> list[Pieza]: ...


class CuentaNoEncontrada(Exception):
    """La cuenta solicitada no existe en la fuente activa."""
