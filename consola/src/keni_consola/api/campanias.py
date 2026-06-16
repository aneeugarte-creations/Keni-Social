"""API Campañas: agrupan piezas YA publicadas por uno o varios hashtags.

Una campaña define un FILTRO (marcas + hashtags); su analítica (KPIs, tendencia, tabla de
piezas, comparativa) se computa AL VUELO en `consola.campanias` sobre el listado de Métricas.
Este módulo solo es la frontera HTTP.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import campanias, marcas, redes
from .._http_json import leer_json

_MARCAS_IDS = {mid for mid, _ in marcas.opciones()}


async def opciones(request: Request) -> Response:
    """Catálogos para los selects del SPA al crear/editar una campaña: marcas y redes."""
    return JSONResponse(
        {
            "marcas": [{"id": mid, "nombre": nombre} for mid, nombre in marcas.opciones()],
            "redes": redes.opciones(),
        }
    )


# --------------------------------------------------------------------------- #
# Campañas (agrupan piezas por hashtag; analítica al vuelo)                     #
# --------------------------------------------------------------------------- #


def _leer_hashtags(valor: Any) -> tuple[list[str] | None, str | None]:
    """Acepta lista de strings o un string con hashtags separados por espacios/comas."""
    if isinstance(valor, str):
        valor = [t for t in valor.replace(",", " ").split() if t]
    if not isinstance(valor, list) or not all(isinstance(t, str) for t in valor):
        return None, "Los hashtags deben ser una lista de texto."
    return valor, None


async def listar_campanias(request: Request) -> Response:
    """Campañas, opcionalmente filtradas por `?marca=`."""
    marca = request.query_params.get("marca") or None
    if marca and marca not in _MARCAS_IDS:
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    return JSONResponse(
        {
            "campanias": campanias.listar_campanias(marca=marca),
            "fuente": campanias.fuente_actual(),
        }
    )


def _leer_marcas(valor: Any) -> tuple[list[str] | None, str | None]:
    """Acepta una lista de ids de marca (o un string único, retrocompat). Valida allowlist."""
    if isinstance(valor, str):
        valor = [valor] if valor else []
    if not isinstance(valor, list) or not all(isinstance(m, str) for m in valor):
        return None, "Las marcas deben ser una lista de ids."
    if not valor:
        return None, "Elige al menos una marca."
    if any(m not in _MARCAS_IDS for m in valor):
        return None, "Marca no permitida."
    return valor, None


async def crear_campania(request: Request) -> Response:
    """Crea una campaña (multimarca): `{marcas: [...], nombre, hashtags: [...]}`."""
    datos = await leer_json(request)
    # `marcas` (lista) es la forma actual; se acepta `marca` (string) por retrocompat.
    marcas_ids, error = _leer_marcas(datos.get("marcas", datos.get("marca")))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    nombre = datos.get("nombre")
    if not isinstance(nombre, str):
        return JSONResponse({"error": "El nombre debe ser texto."}, status_code=400)
    tags, error = _leer_hashtags(datos.get("hashtags"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    try:
        cam = campanias.crear_campania(marcas_ids=marcas_ids, nombre=nombre, hashtags=tags)
    except campanias.CampaniaInvalida as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"campania": cam}, status_code=201)


async def detalle_campania(request: Request) -> Response:
    cam = campanias.obtener_campania(request.path_params["campania_id"])
    if cam is None:
        return JSONResponse({"error": "Esa campaña ya no existe."}, status_code=404)
    return JSONResponse({"campania": cam})


async def actualizar_campania(request: Request) -> Response:
    """Edición parcial: `{nombre?, marcas?, hashtags?, activa?}`; 404 si no existe."""
    campania_id = request.path_params["campania_id"]
    datos = await leer_json(request)
    campos: dict[str, Any] = {}
    if "nombre" in datos:
        if not isinstance(datos["nombre"], str):
            return JSONResponse({"error": "El nombre debe ser texto."}, status_code=400)
        campos["nombre"] = datos["nombre"]
    if "marcas" in datos:
        marcas_ids, error = _leer_marcas(datos.get("marcas"))
        if error is not None:
            return JSONResponse({"error": error}, status_code=400)
        campos["marcas"] = marcas_ids
    if "hashtags" in datos:
        tags, error = _leer_hashtags(datos.get("hashtags"))
        if error is not None:
            return JSONResponse({"error": error}, status_code=400)
        campos["hashtags"] = tags
    if "activa" in datos:
        campos["activa"] = bool(datos["activa"])
    try:
        cam = campanias.actualizar_campania(campania_id, campos)
    except campanias.CampaniaInvalida as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if cam is None:
        return JSONResponse({"error": "Esa campaña ya no existe."}, status_code=404)
    return JSONResponse({"campania": cam})


async def eliminar_campania(request: Request) -> Response:
    if not campanias.borrar_campania(request.path_params["campania_id"]):
        return JSONResponse({"error": "Esa campaña ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Campaña eliminada."})


async def analitica_campania(request: Request) -> Response:
    """Analítica de una campaña en un periodo: `?rango=` (def `mes`). 404 si no existe."""
    campania_id = request.path_params["campania_id"]
    rango = request.query_params.get("rango") or campanias.RANGO_DEF
    try:
        datos = await campanias.analitica_campania(campania_id, rango)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if datos is None:
        return JSONResponse({"error": "Esa campaña ya no existe."}, status_code=404)
    return JSONResponse(datos)


RUTAS = [
    Route("/api/campanias/opciones", opciones, methods=["GET"]),
    Route("/api/campanias", listar_campanias, methods=["GET"]),
    Route("/api/campanias", crear_campania, methods=["POST"]),
    Route("/api/campanias/{campania_id}", detalle_campania, methods=["GET"]),
    Route("/api/campanias/{campania_id}", actualizar_campania, methods=["PUT"]),
    Route("/api/campanias/{campania_id}", eliminar_campania, methods=["DELETE"]),
    Route(
        "/api/campanias/{campania_id}/analitica",
        analitica_campania,
        methods=["GET"],
    ),
]
