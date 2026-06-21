"""Tipos compartidos y auxiliares del contrato `/api/*`.

Modelos transversales que usan varios dominios (`MarcaDisponible`), envelopes y
respuestas genericas (`Paginacion`, `RespuestaMensaje`, `ErrorApi`) y las metricas
de un run/generacion (`MetricasRun`). Viven aqui para que cada submodulo de dominio
los importe explicitamente y el emisor de esquema resuelva sus referencias.
"""

from __future__ import annotations

from typing import NotRequired, TypedDict

__all__ = [
    "MarcaDisponible",
    "Paginacion",
    "MetricasRun",
    "RespuestaMensaje",
    "ErrorApi",
]


class MarcaDisponible(TypedDict):
    id: str
    nombre: str


class Paginacion(TypedDict):
    """Envelope ADITIVO de paginacion (offset-based).

    Lo añaden los listados pesados (piezas/runs/generaciones) junto a su
    clave de lista. `total` = filas existentes sin paginar; `limite` = tamaño de
    pagina efectivo (igual a `total` si no se paginó); `desplazamiento` = offset.

    `cursor_siguiente` (KEYSET, feed de scroll infinito): clave `"<creado>|<id>"` para
    pedir la SIGUIENTE pagina. Solo lo emite el feed cuando pagina por `?cursor=` y hay
    mas filas; se OMITE en la ultima pagina y en los modos offset/completo (opcional).
    """

    total: int
    limite: int
    desplazamiento: int
    cursor_siguiente: NotRequired[str]


class MetricasRun(TypedDict):
    """Metricas de monitorizacion de un run/generacion IA (las que reporta el CLI).

    El handler las omite (clave a `null`) si el run no produjo metricas (interactivo
    o CLI sin JSON). Cuando vienen, traen estos seis campos.
    """

    tokens_in: int
    tokens_out: int
    num_turns: int
    total_cost_usd: float
    duration_ms: int
    modelo: str


class RespuestaMensaje(TypedDict):
    mensaje: str


class ErrorApi(TypedDict):
    """Forma de error que devuelve el backend (uno u otro campo, en espanol)."""

    error: NotRequired[str]
    mensaje: NotRequired[str]
