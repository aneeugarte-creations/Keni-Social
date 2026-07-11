"""Endpoint de análisis del periodo: `analisis` (lectura multi-dimensión "qué pasó y por qué").

Ensambla reporte + picos + series en una lectura accionable de HALLAZGOS jerarquizados
+ siguiente paso. Los helpers de serialización viven aquí.
"""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ...tiempo import ahora_iso
from ._comun import (
    _etiqueta_rango,
    _gate_marca_metricas,
    _log,
    _nombre_marca_id,
    _validar_rango,
    _validar_redes,
    metricas_cache,
    servicio,
)

__all__ = ["analisis"]


def _pieza_serializable(pieza: dict | None) -> dict | None:
    """Forma JSON mínima de una pieza para el SPA (la que explica un hallazgo)."""
    if not pieza:
        return None
    return {
        "titulo": pieza.get("titulo", ""),
        "plataforma": pieza.get("plataforma", ""),
        "engagement_pct": pieza.get("engagement_pct", 0.0),
        "url": pieza.get("url"),
    }


def _hallazgo_serializable(hallazgo: dict) -> dict:
    """Un hallazgo (dimensión + frase + dirección + ancla + grupo + pieza) para el SPA."""
    return {
        "dimension": hallazgo.get("dimension", ""),
        "texto": hallazgo.get("texto", ""),
        "direccion": hallazgo.get("direccion", "estable"),
        # Dato ANCLA ya formateado + su nombre en una palabra (None en los hallazgos de
        # contexto, que llevan las cifras dentro de la propia frase).
        "cifra": hallazgo.get("cifra"),
        "etiqueta": hallazgo.get("etiqueta"),
        # Reparto del panel: "positivo" | "vigilar" | "contexto".
        "grupo": hallazgo.get("grupo", "contexto"),
        # `pieza` se normaliza a None cuando el hallazgo no apunta a una pieza (el motor
        # omite la clave); el contrato la emite siempre (nullable) para el SPA.
        "pieza": _pieza_serializable(hallazgo.get("pieza")),
    }


def _analisis_serializable(analisis: dict, rango: str, marca: str | None) -> dict:
    """Forma JSON del análisis del periodo para el SPA: hallazgos + paso.

    Resuelve los nombres de marca con el catálogo de la Consola y mantiene `fuente`
    (procedencia de las cifras). El texto narrativo (render Markdown) NO se incluye: el
    SPA pinta su propia tarjeta a partir de los campos estructurados.
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
        "hallazgos": [_hallazgo_serializable(h) for h in analisis.get("hallazgos", [])],
        "cobertura_parcial": [
            _nombre_marca_id(c, nombres)
            for c in (analisis.get("cobertura") or {}).get("cuentas_parciales", [])
        ],
        "siguiente_paso": paso_out,
    }


async def analisis(request: Request) -> Response:
    """GET /api/metricas/analisis: lectura multi-dimensión del periodo.

    `?rango=` (preset o token), `?marca=` (en forma `id_metricas`; sin marca, todas) y
    `?red=a,b` acotan la lectura. Sin `red` se sirve de cache (lazy fill); con `red` se
    recomputa al vuelo (en threadpool) acotado a esas redes — vista filtrada bajo demanda,
    no se cachea cada combinación (mismo patrón que `/piezas`).
    """
    rango = _validar_rango(request.query_params.get("rango", "semana"))
    marca, rechazo = _gate_marca_metricas(request, request.query_params.get("marca") or None)
    if rechazo is not None:
        return rechazo
    try:
        redes = _validar_redes(request.query_params.get("red"))
        if redes:
            a = await run_in_threadpool(
                servicio.construir_analisis_diario, rango, marca, redes
            )
            generado_en = ahora_iso()
        else:
            # Lee de cache (instantaneo); lazy fill (en executor) si el combo aun no esta guardado.
            a, generado_en = await metricas_cache.analisis_async(rango, marca)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        _log.exception(
            "Fallo al generar el análisis (rango=%s, marca=%s, red=%s).",
            rango, marca or "todas", ",".join(redes) or "todas",
        )
        return JSONResponse({"error": "No se pudo generar el análisis."}, status_code=500)
    salida = _analisis_serializable(a, rango, marca)
    salida["generado_en"] = generado_en
    return JSONResponse(salida)
