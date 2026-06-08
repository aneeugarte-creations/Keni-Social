"""Estado (autodiagnostico del sistema) — api/estado.py."""

from __future__ import annotations

from typing import Literal, TypedDict

__all__ = [
    "NivelEstado",
    "ResultadoEstado",
    "RespuestaEstado",
]

NivelEstado = Literal["ok", "aviso", "error"]


class ResultadoEstado(TypedDict):
    estado: NivelEstado
    nombre: str
    detalle: str
    icono: str


class RespuestaEstado(TypedDict):
    resultados: list[ResultadoEstado]
    resumen: str
    siguiente_paso: str
