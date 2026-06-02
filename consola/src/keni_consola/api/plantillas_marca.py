"""API Plantilla de marca: leer/editar el estampado determinista por marca (Estudio).

El compositor del Estudio (`motores/estudio_imagen/render_node`) estampa logo + pleca +
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
from ..dominio import estudio_imagen


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


async def obtener_spec(request: Request) -> Response:
    """SPEC de capas EFECTIVO de una marca (editor visual) -> `{spec:{...}}` (404 si no existe)."""
    marca = request.path_params["marca"]
    try:
        spec = plantillas_marca.obtener_spec(marca)
    except plantillas_marca.PlantillaMarcaError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    return JSONResponse({"spec": spec})


async def guardar_spec(request: Request) -> Response:
    """Guarda el SPEC de capas de una marca (validado en el store) -> `{spec:{...}}` | 400 | 404."""
    marca = request.path_params["marca"]
    datos = await leer_json(request)
    spec = datos.get("spec") if isinstance(datos, dict) and "spec" in datos else datos
    try:
        guardado = plantillas_marca.guardar_spec(marca, spec)
    except plantillas_marca.PlantillaMarcaError as e:
        # Marca desconocida -> 404; spec inválido -> 400.
        codigo = 404 if str(e).startswith("Marca desconocida") else 400
        return JSONResponse({"error": str(e)}, status_code=codigo)
    return JSONResponse({"spec": guardado})


async def previsualizar(request: Request) -> Response:
    """Renderiza el SPEC EN EDICIÓN (sin guardar) para la vista previa del editor.

    `POST /api/plantillas-marca/{marca}/preview {spec, formato, titular?}` -> `{id, url}`.
    Render determinista (placeholder) del spec recibido; 400 si el spec o el formato no valen.
    """
    datos = await leer_json(request)
    spec = datos.get("spec") if isinstance(datos, dict) else None
    formato = datos.get("formato") if isinstance(datos, dict) else None
    if not isinstance(spec, dict) or not isinstance(formato, str):
        return JSONResponse({"error": "Faltan 'spec' y 'formato'."}, status_code=400)
    titular = datos.get("titular") if isinstance(datos.get("titular"), str) else ""
    etiqueta = datos.get("etiqueta") if isinstance(datos.get("etiqueta"), str) else ""
    try:
        res = estudio_imagen.previsualizar_spec(spec, formato, titular=titular, etiqueta_default=etiqueta)
    except estudio_imagen.EstudioError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse(res)


RUTAS = [
    Route("/api/plantillas-marca", listar, methods=["GET"]),
    Route("/api/plantillas-marca/{marca}", obtener, methods=["GET"]),
    Route("/api/plantillas-marca/{marca}", guardar, methods=["PUT"]),
    Route("/api/plantillas-marca/{marca}/spec", obtener_spec, methods=["GET"]),
    Route("/api/plantillas-marca/{marca}/spec", guardar_spec, methods=["PUT"]),
    Route("/api/plantillas-marca/{marca}/preview", previsualizar, methods=["POST"]),
]
