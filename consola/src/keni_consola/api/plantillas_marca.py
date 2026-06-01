"""API Plantilla de marca: leer/editar el estampado determinista por marca (Estudio).

El compositor del Estudio (`motores/estudio_imagen/componer.py`) estampa logo + pleca +
titular por marca. Esta API expone la "Plantilla de marca" EDITABLE: el equipo ajusta
colores, pleca por defecto, flags de titular, posicion y wordmark, y referencia el LOGO
real (subido aparte). La verdad vive en fichero (`plantillas_marca.py`, file-as-truth), un
override por marca fusionado con sus defaults.

Endpoints:
  - `GET  /api/plantillas-marca`          -> {plantillas:{<marca>:{...campos, logo_url}}}
  - `GET  /api/plantillas-marca/{marca}`  -> {plantilla:{...campos, logo_url}}
  - `PUT  /api/plantillas-marca/{marca}`  (JSON con campos editables) -> {plantilla:{...}}

El LOGO se sube con el endpoint EXISTENTE `POST /api/media` (multipart) que devuelve
`{id, url}`; el frontend luego hace `PUT` con `logo: <id>`. NO hay endpoint de subida nuevo.

SEGURIDAD: entradas validadas en el store (hex, posicion, flags) antes de persistir;
errores en espanol sin tracebacks.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import plantillas_marca  # intra-app (shell store): permitido
from .._http_json import leer_json


def _con_logo_url(plantilla: dict[str, Any]) -> dict[str, Any]:
    """Anade `logo_url` (sirve el logo via `/api/media/<id>`; "" si no hay logo)."""
    logo = plantilla.get("logo") or ""
    return {**plantilla, "logo_url": f"/api/media/{logo}" if logo else ""}


async def listar(request: Request) -> Response:
    """Todas las plantillas efectivas por marca -> `{plantillas:{<marca>:{...}}}`."""
    plantillas = {
        marca: _con_logo_url(datos) for marca, datos in plantillas_marca.listar().items()
    }
    return JSONResponse({"plantillas": plantillas})


async def obtener(request: Request) -> Response:
    """Plantilla efectiva de una marca -> `{plantilla:{...}}` (404 si la marca no existe)."""
    marca = request.path_params["marca"]
    try:
        plantilla = plantillas_marca.obtener(marca)
    except plantillas_marca.PlantillaMarcaError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    return JSONResponse({"plantilla": _con_logo_url(plantilla)})


async def guardar(request: Request) -> Response:
    """Edita la plantilla de una marca (campos editables) -> `{plantilla:{...}}`.

    Validacion (hex, posicion, flags) en el store; un error sale como 400 en espanol.
    """
    marca = request.path_params["marca"]
    datos = await leer_json(request)
    try:
        plantilla = plantillas_marca.guardar(marca, datos)
    except plantillas_marca.PlantillaMarcaError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"plantilla": _con_logo_url(plantilla)})


RUTAS = [
    Route("/api/plantillas-marca", listar, methods=["GET"]),
    Route("/api/plantillas-marca/{marca}", obtener, methods=["GET"]),
    Route("/api/plantillas-marca/{marca}", guardar, methods=["PUT"]),
]
