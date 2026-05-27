"""API Panel (#9, Fase 3): dashboard ligero de un vistazo (el hueco vs Metricool/Buffer).

Una SOLA lectura agregada para la pantalla de inicio del equipo, REUTILIZANDO los
caminos de lectura existentes (no duplica logica ni toca la pagina de Metricas):

  - Resumen de metricas: total consolidado + top movimientos ("picos") del periodo,
    via `keni_metricas.servicio` (las MISMAS funciones que consume `/api/metricas/*`).
  - Cola de aprobacion: cuantas piezas esperan revision (estado `en_revision`).
  - Proximas programadas: las siguientes piezas en estado `programado`, ordenadas por
    `fecha_programada`, con su marca dry-run (`preparado_en`) si ya vencieron.

GATING (frontera del producto): el panel solo LEE. Las proximas programadas se preparan
en dry-run (el sistema no publica solo); el campo `preparado_en` lo refleja. Posteo real
GATED por #5/#8.

Solo lectura: ningun endpoint muta nada.
"""

from __future__ import annotations

from typing import Any

from keni_metricas import servicio
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import marcas, redes, repos
from ..estados import ESTADO_EN_REVISION, ESTADO_PROGRAMADO

# Cuantas piezas programadas mostrar como "proximas" (las mas inminentes). Mantiene el
# panel ligero: un vistazo, no la agenda completa.
_MAX_PROXIMAS = 8
# Cuantos movimientos ("picos") destacar en el resumen.
_MAX_PICOS = 5


def _resumen_metricas(rango: str, marca: str | None) -> dict[str, Any]:
    """Total consolidado + top movimientos del periodo (REUSA `servicio`, solo lectura).

    Best-effort: si la fuente de metricas falla, devuelve un resumen vacio marcado como
    no disponible en vez de romper el panel entero (el resto del dashboard sigue util).
    """
    try:
        rep = servicio.construir_reporte(rango, marca)
        analisis = servicio.construir_analisis_diario(rango, marca)
    except Exception:  # noqa: BLE001 -- el panel no debe caer por la fuente de metricas
        return {"disponible": False, "fuente": "muestra", "total": None, "picos": []}

    total = rep.get("total") or {}
    nombres = analisis.get("nombres") or {}
    picos = []
    for mov in (analisis.get("movimientos") or [])[:_MAX_PICOS]:
        cid = mov.get("marca_id", "")
        pieza = mov.get("pieza") or None
        picos.append(
            {
                "marca": _nombre_marca(cid, nombres),
                "direccion": mov.get("direccion", "estable"),
                "variacion_vis_pct": mov.get("variacion_vis_pct", 0.0),
                "visualizaciones": mov.get("visualizaciones", 0),
                "pieza_titulo": (pieza or {}).get("titulo", "") if pieza else "",
            }
        )
    return {
        "disponible": True,
        "rango": rango,
        # Procedencia: "muestra" (ficticios) o nombre de la fuente real. La UI pinta el
        # mismo badge de advertencia que Metricas (no se confunden muestra y reales).
        "fuente": rep.get("fuente") or "muestra",
        "total": {
            "visualizaciones": total.get("visualizaciones", 0),
            "alcance": total.get("alcance", 0),
            "interacciones": total.get("interacciones", 0),
            "engagement_pct": total.get("engagement_pct", 0.0),
        },
        "picos": picos,
    }


def _nombre_marca(cuenta_id: str, nombres: dict[str, str]) -> str:
    """Nombre legible de una cuenta de metricas (catalogo de marcas con prioridad)."""
    etiqueta = marcas.etiqueta_por_id_metricas(cuenta_id)
    if etiqueta != cuenta_id:
        return etiqueta
    return nombres.get(cuenta_id) or cuenta_id


def _proxima(pub: dict[str, Any]) -> dict[str, Any]:
    """Forma minima de una pieza programada para el panel (nombres resueltos en servidor)."""
    return {
        "id": pub["id"],
        "titulo": pub.get("titulo") or "",
        "marca": pub.get("marca") or "",
        "marca_nombre": marcas.etiqueta_de(pub["marca"]) if pub.get("marca") else "",
        "red": pub.get("red") or "",
        "red_nombre": redes.nombre_por_id(pub["red"]) if pub.get("red") else "",
        "fecha_programada": pub.get("fecha_programada") or "",
        # Marca dry-run del programador: si ya vencio y se preparo, viene el instante; ""
        # si aun no vence. La UI muestra "lista para publicar (dry-run)" cuando hay valor.
        "preparado_en": pub.get("preparado_en") or "",
    }


async def resumen(request: Request) -> Response:
    """GET /api/panel: dashboard ligero (metricas + cola de aprobacion + proximas).

    `?rango=` (def 'semana') y `?marca=` (opcional) acotan el resumen de metricas, igual
    que `/api/metricas/*`. Devuelve `{metricas, cola, proximas}`.
    """
    rango = request.query_params.get("rango") or "semana"
    if rango not in servicio.RANGOS_VALIDOS:
        rango = "semana"
    marca = request.query_params.get("marca") or None

    metricas = _resumen_metricas(rango, marca)

    pendientes = repos.listar_publicaciones(estado=ESTADO_EN_REVISION)

    programadas = repos.listar_publicaciones(estado=ESTADO_PROGRAMADO)
    # Las mas inminentes primero (por fecha_programada ascendente); las sin fecha al final.
    programadas.sort(key=lambda p: p.get("fecha_programada") or "9999")
    proximas = [_proxima(p) for p in programadas[:_MAX_PROXIMAS]]

    return JSONResponse(
        {
            "metricas": metricas,
            "cola": {"total": len(pendientes)},
            "proximas": {"items": proximas, "total": len(programadas)},
            # Aviso de frontera del producto: el panel NO publica; el posteo real esta
            # gated por #5/#8. La UI lo muestra como nota junto a las proximas.
            "gating": {
                "publicacion_real_activa": False,
                "nota": (
                    "Las piezas programadas se preparan en dry-run (lista para publicar); "
                    "el posteo real a las plataformas está pendiente de #5/#8."
                ),
            },
        }
    )


RUTAS = [
    Route("/api/panel", resumen, methods=["GET"]),
]
