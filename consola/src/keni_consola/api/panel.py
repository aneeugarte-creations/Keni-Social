"""API Panel (#9, Fase 3): dashboard ligero de un vistazo (el hueco vs Metricool/Buffer).

Una SOLA lectura agregada para la pantalla de inicio del equipo, REUTILIZANDO los
caminos de lectura existentes (no duplica logica ni toca la pagina de Metricas):

  - Resumen de metricas (app B): total consolidado + top movimientos ("picos") del
    periodo, via la FACHADA `keni_metricas.servicio` (B = infra de solo lectura, ADR 0005
    §Seams #6; las MISMAS funciones que consume `/api/metricas/*`). El panel NO toca los
    internals del router `metricas`: por eso `(panel, metricas)` NO es un cruce de app.
  - Cola de aprobacion (app C) + proximas programadas (app C): el panel NO consulta el
    almacen de C ni conoce sus estados internos; las pide por las funciones-CONTRATO de
    solo lectura que C expone (`dominio.publicaciones.cola_de_aprobacion` /
    `proximas_programadas`, ADR 0005 §Seams #3 — cruce shell->app legitimo, por fachada).

GATING (frontera del producto): el panel solo LEE. Las proximas programadas se preparan
en dry-run (el sistema no publica solo); el campo `preparado_en` lo refleja. Posteo real
via Metricool GATED por `KENI_PUBLICAR_REAL`.

Solo lectura: ningun endpoint muta nada.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from keni_metricas import servicio
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import marcas, metricas_cache, priorizacion, repos
from ..dominio.publicaciones import cola_de_aprobacion, proximas_programadas
from ..estados import CLASE_CONTENIDO

# Cuantas piezas programadas mostrar como "proximas" (las mas inminentes). Mantiene el
# panel ligero: un vistazo, no la agenda completa.
_MAX_PROXIMAS = 8
# Cuantos movimientos ("picos") destacar en el resumen.
_MAX_PICOS = 5
# Tope de items de la "lista del dia" (los demas cuentan en `total`, no se pintan todos).
_MAX_LISTA_DIA = 100
# Estados terminales del contenido padre: ya no son "del dia" (no hay nada que postear).
_ESTADOS_CERRADOS = ("hecha",)


def _resumen_metricas(rango: str, marca: str | None) -> dict[str, Any]:
    """Total consolidado + top movimientos del periodo (REUSA `servicio`, solo lectura).

    Best-effort: si la fuente de metricas falla, devuelve un resumen vacio marcado como
    no disponible en vez de romper el panel entero (el resto del dashboard sigue util).
    """
    try:
        # Lee de la cache de metricas (instantaneo); lazy fill si el combo aun no esta.
        rep, _gen = metricas_cache.reporte(rango, marca)
        analisis, _gen_a = metricas_cache.analisis(rango, marca)
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

    # Cola de aprobacion + proximas programadas: por el CONTRATO de lectura de C (el panel
    # no consulta el almacen ni conoce los estados internos de `publicaciones`).
    pendientes = cola_de_aprobacion()
    proximas, total_programadas = proximas_programadas(_MAX_PROXIMAS)

    return JSONResponse(
        {
            "metricas": metricas,
            "cola": {"total": len(pendientes)},
            "proximas": {"items": proximas, "total": total_programadas},
            # Aviso de frontera del producto: el panel NO publica; el posteo real (vía
            # Metricool) está gated por `KENI_PUBLICAR_REAL`. La UI lo expone como aviso.
            "gating": {
                "publicacion_real_activa": False,
                "nota": (
                    "Las piezas programadas se preparan en dry-run (lista para publicar); "
                    "el posteo real se hace vía Metricool y está gated por `KENI_PUBLICAR_REAL`."
                ),
            },
        }
    )


def _nombres_etiqueta() -> dict[str, str]:
    """Mapa id de etiqueta -> nombre (para resolver las etiquetas de cada contenido)."""
    return {e.get("id", ""): e.get("nombre", "") for e in repos.listar_etiquetas()}


def _lista_dia(marca: str | None) -> dict[str, Any]:
    """La "lista viva" del dia: contenido abierto del tablero ORDENADO por score (H3/H5).

    Reusa `repos.listar_contenido` (mismo camino que el tablero) y `priorizacion` (score
    determinista). NO cambia el orden del tablero kanban: solo ESTA vista se reordena sola.
    Best-effort: si la lectura del tablero falla, devuelve una lista vacia (el resto del
    panel sigue util). Incluye contadores por fuente (`origen`) y por estado.
    """
    try:
        items = repos.listar_contenido(marca=marca)
    except Exception:  # noqa: BLE001 -- el panel no debe caer por la lectura del tablero
        return {"items": [], "total": 0, "por_fuente": {}, "por_estado": {}}

    items = [
        it
        for it in items
        if (it.get("clase") or CLASE_CONTENIDO) == CLASE_CONTENIDO
        and (it.get("estado") or "") not in _ESTADOS_CERRADOS
    ]
    nombres_et = _nombres_etiqueta()
    etiquetas_por_item = {
        cid: [nombres_et.get(eid, "") for eid in eids]
        for cid, eids in repos.etiquetas_por_contenido().items()
    }
    hoy = date.today()
    ordenados = priorizacion.ordenar_por_score(
        items, etiquetas_por_item=etiquetas_por_item, hoy=hoy
    )
    # Una misma pieza puede existir como VARIOS temas con el mismo título: el handoff A→C
    # crea un borrador —y por tanto un tema— por red. En la lista del día solo se muestra el
    # título, así que esos temas se ven como el mismo contenido repetido N veces. Los
    # colapsamos a uno por (marca, título): como `ordenados` viene de mayor a menor score,
    # el PRIMERO de cada clave (el más prioritario) es el que se conserva. Las piezas SIN
    # título no se agrupan (cada una es única por id) para no fundir contenidos distintos.
    unicos: list[dict[str, Any]] = []
    vistos: set[tuple[str, str]] = set()
    for it in ordenados:
        titulo = (it.get("titulo") or "").strip().lower()
        clave = (it.get("marca") or "", titulo) if titulo else ("", it.get("id", ""))
        if clave in vistos:
            continue
        vistos.add(clave)
        unicos.append(it)
    nombres_marca = dict(marcas.opciones())

    por_fuente: dict[str, int] = {}
    por_estado: dict[str, int] = {}
    for it in unicos:
        por_fuente[it.get("origen") or "manual"] = por_fuente.get(it.get("origen") or "manual", 0) + 1
        por_estado[it.get("estado") or "pendiente"] = por_estado.get(it.get("estado") or "pendiente", 0) + 1

    salida: list[dict[str, Any]] = []
    for it in unicos[:_MAX_LISTA_DIA]:
        cid = it.get("id", "")
        marca_id = it.get("marca") or ""
        salida.append(
            {
                "id": cid,
                "titulo": it.get("titulo", ""),
                "marca": marca_id,
                "marca_nombre": nombres_marca.get(marca_id, marca_id),
                "estado": it.get("estado") or "pendiente",
                "prioridad": it.get("prioridad") or "media",
                "flujo": it.get("flujo") or "",
                "fecha_objetivo": it.get("fecha_objetivo") or "",
                "origen": it.get("origen") or "manual",
                "etiquetas": [e for e in etiquetas_por_item.get(cid, []) if e],
                "score": priorizacion.score_contenido(
                    it, etiquetas=etiquetas_por_item.get(cid, []), hoy=hoy
                ),
            }
        )
    return {"items": salida, "total": len(unicos), "por_fuente": por_fuente, "por_estado": por_estado}


async def lista_dia(request: Request) -> Response:
    """GET /api/panel/dia: la lista viva del dia (ordenada por score). `?marca=` opcional."""
    marca = request.query_params.get("marca") or None
    return JSONResponse(_lista_dia(marca))


RUTAS = [
    Route("/api/panel", resumen, methods=["GET"]),
    Route("/api/panel/dia", lista_dia, methods=["GET"]),
]
