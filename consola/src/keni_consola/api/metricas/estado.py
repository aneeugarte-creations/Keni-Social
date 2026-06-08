"""Endpoints de estado del refresco: `estado` y `refrescar`."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ._comun import _rango_opcional, metricas_cache

__all__ = ["estado", "refrescar"]


async def estado(request: Request) -> Response:
    """GET /api/metricas/estado: estado del refresco + `generado_en` del combo.

    `?rango=` y `?marca=` (opcionales) acotan el `generado_en` que devuelve (el del
    reporte cacheado de ese combo, "" si aun no hay). La UI lo usa para "Actualizado
    hace X" y para saber cuando dejar de pollear (`corriendo` -> false).
    """
    rango = _rango_opcional(request.query_params.get("rango"))
    marca = request.query_params.get("marca") or None
    return JSONResponse(metricas_cache.estado(rango, marca))


async def refrescar(request: Request) -> Response:
    """POST /api/metricas/refrescar: dispara un refresco en 2o plano (idempotente).

    Prioriza el combo `?rango=&marca=` que se esta viendo (se recalcula primero) y
    sigue con el resto en segundo plano. Si ya hay un refresco corriendo, NO arranca
    otro: devuelve el estado actual. Responde 202 (aceptado, trabajo en curso).
    """
    rango = _rango_opcional(request.query_params.get("rango"))
    marca = request.query_params.get("marca") or None
    estado_actual = metricas_cache.disparar_refresco(rango, marca)
    return JSONResponse(estado_actual, status_code=202)
