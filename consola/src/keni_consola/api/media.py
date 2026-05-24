"""API Media: subir imagenes, servirlas y generarlas con IA (si hay proveedor).

El SPA adjunta imagenes a las publicaciones. Esta API:
  - `POST /api/media`        guarda una imagen subida (multipart `archivo`).
  - `GET  /api/media/{n}`    sirve una imagen del dir de media (anti-traversal).
  - `POST /api/media/generar` genera una imagen con IA si HAY proveedor configurado;
    si no, responde 400 con un mensaje claro (la clave del proveedor no se commitea).

SEGURIDAD: el nombre en disco lo genera el servidor (uuid); el GET valida que el
nombre pedido no escape del dir (anti-traversal). Errores en espanol, sin tracebacks.
El proveedor de imagen y su clave viven en `consola.media` y son mockeables: los
tests NUNCA tocan la red.
"""

from __future__ import annotations

from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Route

from .. import media
from .._http_json import leer_json


async def subir(request: Request) -> Response:
    """Guarda una imagen subida (multipart `archivo`) -> `{id, url}`."""
    try:
        form = await request.form()
    except Exception:  # noqa: BLE001 -- multipart malformado => mensaje claro, sin traza
        return JSONResponse({"error": "No se pudo leer la imagen subida."}, status_code=400)
    archivo = form.get("archivo")
    if not isinstance(archivo, UploadFile):
        return JSONResponse({"error": "No se recibió ninguna imagen."}, status_code=400)
    try:
        nombre = await media.guardar_subida(archivo)
    except media.MediaError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        return JSONResponse({"error": "No se pudo guardar la imagen."}, status_code=500)
    return JSONResponse({"id": nombre, "url": f"/api/media/{nombre}"})


async def servir(request: Request) -> Response:
    """Sirve una imagen del dir de media por nombre (404 si falta; anti-traversal)."""
    nombre = request.path_params["nombre"]
    destino = media.resolver_media(nombre)
    if destino is None or not destino.is_file():
        return JSONResponse({"error": "Esa imagen no existe."}, status_code=404)
    return FileResponse(destino, media_type=media.mime_de(nombre))


async def generar(request: Request) -> Response:
    """Genera una imagen con IA (JSON `{prompt}`) -> `{id, url}`; 400 si no hay proveedor."""
    datos = await leer_json(request)
    prompt = datos.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return JSONResponse({"error": "Falta el texto (prompt) para generar la imagen."}, status_code=400)
    if not media.proveedor_configurado():
        return JSONResponse(
            {
                "error": "La generación de imagen no está configurada. Añade una clave "
                "de proveedor de imagen para activarla."
            },
            status_code=400,
        )
    try:
        crudos = media.generar_imagen(prompt)
        nombre = media.guardar_bytes(crudos, ext="png")
    except media.MediaError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        return JSONResponse({"error": "No se pudo generar la imagen."}, status_code=500)
    return JSONResponse({"id": nombre, "url": f"/api/media/{nombre}"})


RUTAS = [
    Route("/api/media", subir, methods=["POST"]),
    Route("/api/media/generar", generar, methods=["POST"]),
    Route("/api/media/{nombre}", servir, methods=["GET"]),
]
