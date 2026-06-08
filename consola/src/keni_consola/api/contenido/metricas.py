"""Handler de métricas REALES por pieza publicada del tablero (`/api/contenido/metricas`)."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ._comun import _enfocar_items_por_marca, metricas_pieza, repos


async def metricas(request: Request) -> Response:
    """GET /api/contenido/metricas: rendimiento REAL por pieza publicada (Metricool).

    Para cada fila por plataforma del tablero que tiene `id_post_metricool`, devuelve su
    rendimiento (visualizaciones/interacciones/engagement) leido de la fuente activa
    (Metricool de pago en prod; muestra en demo) y cacheado por pieza. La UI lo pinta en
    cada tarjeta. Las filas sin `id_post_metricool` se omiten (la UI no muestra nada).

    Forma: `{"metricas": {"<contenido_plataforma.id>": {<MetricaPieza>, generado_en}}}`.
    Acepta los mismos filtros que `GET /api/contenido` para acotar el universo.
    """
    q = request.query_params
    items = repos.listar_contenido(
        clase=q.get("clase") or None,
        flujo=q.get("flujo") or None,
        marca=q.get("marca") or None,
        responsable_id=q.get("responsable_id") if "responsable_id" in q else None,
        estado=q.get("estado") or None,
        desde=q.get("desde") or None,
        hasta=q.get("hasta") or None,
    )
    # FOCO POR DEFECTO (ver `listar`): sin marca explicita, la sesion se enfoca en sus marcas
    # preferentes (post-filtrado en memoria). Sobreescribible con `?marca=` (cualquiera). No bloquea.
    items = _enfocar_items_por_marca(request, items, q.get("marca") or None)
    por_contenido: dict[str, list[dict]] = {}
    for plat in repos.listar_contenido_plataforma():
        por_contenido.setdefault(plat["contenido_id"], []).append(plat)
    contenidos = [
        {"marca": it.get("marca", ""), "plataformas": por_contenido.get(it["id"], [])}
        for it in items
    ]
    return JSONResponse({"metricas": metricas_pieza.rendimiento_de_tablero(contenidos)})
