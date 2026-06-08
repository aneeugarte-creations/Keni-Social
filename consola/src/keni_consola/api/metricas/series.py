"""Endpoints de series temporales / desglose del periodo.

  - `tendencia`: serie diaria (visualizaciones + interacciones).
  - `seguidores`: serie de seguidores (total + por red).
  - `desglose`: desglose de interacciones por marca×red.
  - `crosstab`: rendimiento cruzado marca×red×formato.
  - `correlacion`: seguidores ganados ↔ piezas publicadas.

Todos comparten la misma forma: validan rango+marca, leen de cache (lazy fill) y
añaden `etiqueta_rango` + `generado_en` al payload.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ._comun import (
    _etiqueta_rango,
    _gate_marca_metricas,
    _log,
    _validar_rango,
    metricas_cache,
)

__all__ = ["tendencia", "seguidores", "desglose", "crosstab", "correlacion"]


async def tendencia(request: Request) -> Response:
    """GET /api/metricas/tendencia: serie diaria del periodo (visualizaciones + interacciones).

    `?marca=` acota el ámbito (suma de sus cuentas); sin marca, todas. Servido desde
    cache (lazy fill). `puntos` vacío = la fuente activa no expone serie diaria.
    """
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca, rechazo = _gate_marca_metricas(request, request.query_params.get("marca") or None)
    if rechazo is not None:
        return rechazo
    try:
        payload, generado_en = await metricas_cache.tendencia_async(rango, marca)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        _log.exception("Fallo al generar la tendencia (rango=%s, marca=%s).", rango, marca or "todas")
        return JSONResponse({"error": "No se pudo generar la tendencia."}, status_code=500)
    return JSONResponse({**payload, "etiqueta_rango": _etiqueta_rango(rango), "generado_en": generado_en})


async def seguidores(request: Request) -> Response:
    """GET /api/metricas/seguidores: serie de seguidores del periodo (total + por red).

    `?marca=` acota el ámbito; sin marca, todas. Servido desde cache (lazy fill).
    `puntos` vacío = la fuente activa no expone serie de seguidores (degradación honesta).
    """
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca, rechazo = _gate_marca_metricas(request, request.query_params.get("marca") or None)
    if rechazo is not None:
        return rechazo
    try:
        payload, generado_en = await metricas_cache.seguidores_async(rango, marca)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        _log.exception("Fallo al generar la serie de seguidores (rango=%s, marca=%s).", rango, marca or "todas")
        return JSONResponse({"error": "No se pudo generar la serie de seguidores."}, status_code=500)
    return JSONResponse({**payload, "etiqueta_rango": _etiqueta_rango(rango), "generado_en": generado_en})


async def desglose(request: Request) -> Response:
    """GET /api/metricas/desglose: desglose de interacciones por marca×red.

    `?marca=` acota a una marca; sin marca, todas. Servido desde cache (lazy fill).
    """
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca, rechazo = _gate_marca_metricas(request, request.query_params.get("marca") or None)
    if rechazo is not None:
        return rechazo
    try:
        payload, generado_en = await metricas_cache.desglose_async(rango, marca)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        _log.exception("Fallo al generar el desglose (rango=%s, marca=%s).", rango, marca or "todas")
        return JSONResponse({"error": "No se pudo generar el desglose de interacciones."}, status_code=500)
    return JSONResponse({**payload, "etiqueta_rango": _etiqueta_rango(rango), "generado_en": generado_en})


async def crosstab(request: Request) -> Response:
    """GET /api/metricas/crosstab: rendimiento cruzado marca×red×formato.

    `?marca=` acota a una marca; sin marca, todas. Servido desde cache (lazy fill).
    """
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca, rechazo = _gate_marca_metricas(request, request.query_params.get("marca") or None)
    if rechazo is not None:
        return rechazo
    try:
        payload, generado_en = await metricas_cache.crosstab_async(rango, marca)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        _log.exception("Fallo al generar el crosstab (rango=%s, marca=%s).", rango, marca or "todas")
        return JSONResponse({"error": "No se pudo generar el crosstab."}, status_code=500)
    return JSONResponse({**payload, "etiqueta_rango": _etiqueta_rango(rango), "generado_en": generado_en})


async def correlacion(request: Request) -> Response:
    """GET /api/metricas/correlacion: correlación seguidores ganados ↔ piezas publicadas.

    `?marca=` acota a una marca; sin marca, todas. Servido desde cache (lazy fill).
    """
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca, rechazo = _gate_marca_metricas(request, request.query_params.get("marca") or None)
    if rechazo is not None:
        return rechazo
    try:
        payload, generado_en = await metricas_cache.correlacion_async(rango, marca)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        _log.exception("Fallo al generar la correlación (rango=%s, marca=%s).", rango, marca or "todas")
        return JSONResponse({"error": "No se pudo generar la correlación de seguidores."}, status_code=500)
    return JSONResponse({**payload, "etiqueta_rango": _etiqueta_rango(rango), "generado_en": generado_en})
