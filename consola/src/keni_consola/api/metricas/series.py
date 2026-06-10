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

from datetime import date

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ._comun import (
    _etiqueta_rango,
    _gate_marca_metricas,
    _log,
    _validar_rango,
    marcas,
    metricas_cache,
)

__all__ = ["tendencia", "seguidores", "desglose", "crosstab", "correlacion", "ads", "ingesta"]

# Un canal (marca×red×formato) se marca ESTANCADO si su última pieza es >= este nº de días
# MÁS VIEJA que la última pieza de su marca: el resto del feed avanza y este se quedó atrás
# (p.ej. los Reels de FB de una marca dejan de sincronizar mientras el resto entra al día).
_UMBRAL_ESTANCADO_DIAS = 7


def _fecha(s: str) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


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


async def ads(request: Request) -> Response:
    """GET /api/metricas/ads: campañas de publicidad PAGADA del periodo (Meta/TikTok Ads).

    El INORGÁNICO a nivel marca: lista de campañas (impresiones, gasto, clics) + totales.
    `?marca=` acota a una marca; sin marca, todas. Servido desde cache (lazy fill). Lista
    vacía = sin Ads conectado o sin entrega en el periodo (degradación honesta).
    """
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca, rechazo = _gate_marca_metricas(request, request.query_params.get("marca") or None)
    if rechazo is not None:
        return rechazo
    try:
        payload, generado_en = await metricas_cache.ads_async(rango, marca)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        _log.exception("Fallo al leer los ads (rango=%s, marca=%s).", rango, marca or "todas")
        return JSONResponse({"error": "No se pudieron leer las campañas de Ads."}, status_code=500)
    lista = payload.get("ads") or []
    total = {
        "visualizaciones": sum(int(a.get("impresiones") or 0) for a in lista),
        "gasto": round(sum(float(a.get("gasto") or 0.0) for a in lista), 2),
        "clics": sum(int(a.get("clics") or 0) for a in lista),
        "campanias": len(lista),
        "moneda": next((a.get("moneda") for a in lista if a.get("moneda")), ""),
    }
    return JSONResponse(
        {"ads": lista, "total": total, "etiqueta_rango": _etiqueta_rango(rango), "generado_en": generado_en}
    )


async def ingesta(request: Request) -> Response:
    """GET /api/metricas/ingesta: detecta canales (marca×red×formato) con la ingesta
    ESTANCADA — su última pieza quedó muy por detrás del resto del feed de su marca.

    Caza casos como "los Reels de Facebook de Claro Sports no entran desde el 15-mayo
    mientras el resto sí": un problema de sincronización de la fuente (Metricool) que de otro
    modo solo se descubre a mano. Se computa sobre el listado de piezas (cache, lazy fill);
    sin coste de API extra. `?marca=` acota; sin marca, todas."""
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca, rechazo = _gate_marca_metricas(request, request.query_params.get("marca") or None)
    if rechazo is not None:
        return rechazo
    try:
        payload, generado_en = await metricas_cache.piezas_listado_async(rango, marca)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        _log.exception("Fallo al evaluar la ingesta (rango=%s, marca=%s).", rango, marca or "todas")
        return JSONResponse({"error": "No se pudo evaluar la ingesta."}, status_code=500)

    piezas = payload.get("piezas") or []
    ult_combo: dict[tuple[str, str, str], date] = {}  # (cuenta, red, formato) -> última fecha
    ult_marca: dict[str, date] = {}  # cuenta -> última fecha (cualquier red/formato)
    for p in piezas:
        f = _fecha(p.get("publicado"))
        red = p.get("red") or ""
        if f is None or not red:
            continue
        cuenta = str(p.get("cuenta") or "")
        clave = (cuenta, red, str(p.get("formato") or ""))
        if f > ult_combo.get(clave, date.min):
            ult_combo[clave] = f
        if f > ult_marca.get(cuenta, date.min):
            ult_marca[cuenta] = f

    # Referencia temporal: el FIN del periodo del listado (no el reloj de pared). Si la
    # entrada de cache viene con retraso, medir contra "hoy" inflaría dias_sin_piezas con
    # días que el feed ni siquiera cubre (y acusaría a Metricool de un hueco nuestro).
    referencia = (
        _fecha((payload.get("periodo") or {}).get("hasta"))
        or max(ult_marca.values(), default=None)
        or date.today()
    )
    alertas = []
    for (cuenta, red, formato), f_combo in ult_combo.items():
        f_marca = ult_marca.get(cuenta)
        if f_marca is None:
            continue
        rezago = (f_marca - f_combo).days  # cuánto se quedó atrás vs el resto del feed
        if rezago >= _UMBRAL_ESTANCADO_DIAS:
            alertas.append({
                "marca": marcas.etiqueta_por_id_metricas(cuenta),
                "red": red,
                "formato": formato,
                "ultima_pieza": f_combo.isoformat(),
                "dias_sin_piezas": (referencia - f_combo).days,
                "rezago_dias": rezago,
            })
    alertas.sort(key=lambda a: a["rezago_dias"], reverse=True)
    return JSONResponse(
        {"alertas": alertas, "etiqueta_rango": _etiqueta_rango(rango), "generado_en": generado_en}
    )


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
