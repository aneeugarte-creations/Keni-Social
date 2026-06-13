"""Piezas COMUNES del dominio STREAM: excepcion de generacion y conversiones numericas.

Base sin dependencias internas que comparten el resto de areas del paquete
(`invocacion`/`parser`/`texto`): la excepcion `GeneracionError` (mensaje ya en espanol)
y las conversiones numericas tolerantes `_entero`/`_flotante` que usa el parseo de
metricas y el acumulador del stream.
"""

from __future__ import annotations


class GeneracionError(RuntimeError):
    """Error de ejecucion con mensaje ya en espanol, apto para mostrar al usuario."""


def _entero(valor: object) -> int | None:
    """Convierte `valor` a int si es un numero; None en cualquier otro caso."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float):
        return int(valor)
    return None


def _flotante(valor: object) -> float | None:
    """Convierte `valor` a float si es un numero; None en cualquier otro caso."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    return None
