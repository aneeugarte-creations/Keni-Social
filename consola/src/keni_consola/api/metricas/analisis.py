"""Endpoint de análisis diario: `analisis` ("qué cambió y por qué" + siguiente paso).

Ensambla reporte + picos en una lectura accionable. Los helpers de
serialización de la pieza, el movimiento y el análisis viven aquí.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ._comun import (
    _etiqueta_rango,
    _gate_marca_metricas,
    _log,
    _nombre_marca_id,
    _validar_rango,
    metricas_cache,
)

__all__ = ["analisis"]


def _pieza_serializable(pieza: dict | None) -> dict | None:
    """Forma JSON mínima de una pieza para el SPA (la que explica un movimiento)."""
    if not pieza:
        return None
    return {
        "titulo": pieza.get("titulo", ""),
        "plataforma": pieza.get("plataforma", ""),
        "engagement_pct": pieza.get("engagement_pct", 0.0),
        "url": pieza.get("url"),
    }


def _movimiento_serializable(mov: dict, nombres: dict[str, str]) -> dict:
    """Un movimiento (qué se movió y la pieza que lo explica) con nombre resuelto."""
    cid = mov.get("marca_id", "")
    return {
        "marca_id": cid,
        # El catálogo de marcas de la Consola tiene prioridad sobre el nombre de la
        # fuente (mismo criterio que /reporte): resuelve el id_metricas a etiqueta.
        "marca": _nombre_marca_id(cid, nombres),
        "variacion_vis_pct": mov.get("variacion_vis_pct", 0.0),
        "direccion": mov.get("direccion", "estable"),
        "visualizaciones": mov.get("visualizaciones", 0),
        "engagement_pct": mov.get("engagement_pct"),
        "pieza": _pieza_serializable(mov.get("pieza")),
    }


def _analisis_serializable(analisis: dict, rango: str, marca: str | None) -> dict:
    """Forma JSON del análisis diario para el SPA: lectura + movimientos + paso.

    Resuelve los nombres de marca con el catálogo de la Consola y mantiene
    `fuente` (procedencia de las cifras). El texto narrativo (render
    Markdown) NO se incluye: el SPA pinta su propia tarjeta a partir de los
    campos estructurados.
    """
    nombres = analisis.get("nombres") or {}
    paso = analisis.get("siguiente_paso")
    paso_out = None
    if paso is not None:
        cid = paso.get("marca_id", "")
        paso_out = {
            "marca_id": cid,
            "marca": _nombre_marca_id(cid, nombres),
            "engagement_pct": paso.get("engagement_pct"),
            "pieza": _pieza_serializable(paso.get("pieza")),
            "texto": paso.get("texto", ""),
        }
    return {
        "rango": rango,
        "etiqueta_rango": _etiqueta_rango(rango),
        "marca": marca or "",
        # Procedencia: nombre de la fuente de los datos.
        "fuente": analisis.get("fuente") or "",
        "movimientos": [
            _movimiento_serializable(m, nombres) for m in analisis.get("movimientos", [])
        ],
        "movimientos_resto": analisis.get("movimientos_resto", 0),
        "marcas_estables": analisis.get("marcas_estables", 0),
        "cobertura_parcial": [
            _nombre_marca_id(c, nombres)
            for c in (analisis.get("cobertura") or {}).get("cuentas_parciales", [])
        ],
        "siguiente_paso": paso_out,
    }


async def analisis(request: Request) -> Response:
    rango = _validar_rango(request.query_params.get("rango", "semana"))
    marca, rechazo = _gate_marca_metricas(request, request.query_params.get("marca") or None)
    if rechazo is not None:
        return rechazo
    try:
        # Lee de cache (instantaneo); lazy fill (en executor) si el combo aun no esta guardado.
        a, generado_en = await metricas_cache.analisis_async(rango, marca)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        _log.exception("Fallo al generar el análisis (rango=%s, marca=%s).", rango, marca or "todas")
        return JSONResponse({"error": "No se pudo generar el análisis."}, status_code=500)
    salida = _analisis_serializable(a, rango, marca)
    salida["generado_en"] = generado_en
    return JSONResponse(salida)
