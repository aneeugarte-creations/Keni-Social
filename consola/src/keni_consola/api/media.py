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
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import generaciones, media
from .._http_json import leer_json
from ..dominio import extraccion_url
from ..seguridad import autor_de_peticion


# Carpetas en las que el CLIENTE puede pedir guardar una subida (allowlist publica). Las demas
# categorias (logos/biblioteca/render/generadas/documentos) las asigna el server por su flujo;
# el cliente solo distingue una foto de pieza (`fotos`) de un asset del editor de plantillas.
_CATEGORIAS_SUBIDA = {"fotos", "plantillas"}


async def subir(request: Request) -> Response:
    """Guarda una imagen subida (multipart `archivo`; opcional `categoria`) -> `{id, url}`."""
    try:
        form = await request.form()
    except Exception:  # noqa: BLE001 -- multipart malformado => mensaje claro, sin traza
        return JSONResponse({"error": "No se pudo leer la imagen subida."}, status_code=400)
    archivo = form.get("archivo")
    if not isinstance(archivo, UploadFile):
        return JSONResponse({"error": "No se recibió ninguna imagen."}, status_code=400)
    categoria = form.get("categoria")
    categoria = categoria if categoria in _CATEGORIAS_SUBIDA else "fotos"
    try:
        nombre = await media.guardar_subida(archivo, categoria=categoria)
    except media.MediaError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        return JSONResponse({"error": "No se pudo guardar la imagen."}, status_code=500)
    return JSONResponse({"id": nombre, "url": f"/api/media/{nombre}"})


async def servir(request: Request) -> Response:
    """Sirve una imagen del almacen de media por nombre (404 si falta; anti-traversal).

    Camino backend-NEUTRAL: `media.leer_media` lee del disco (con anti-traversal) o del
    bucket S3 segun el backend activo, y devolvemos los bytes con el mime de la extension.
    """
    nombre = request.path_params["nombre"]
    datos = media.leer_media(nombre)
    if datos is None:
        return JSONResponse({"error": "Esa imagen no existe."}, status_code=404)
    return Response(datos, media_type=media.mime_de(nombre))


async def generar(request: Request) -> Response:
    """Genera una imagen con IA EN SEGUNDO PLANO (JSON `{prompt}`) -> `{generacion}`.

    400 inmediato si no hay proveedor configurado (no se crea trabajo). Si lo hay, lanza
    un trabajo (tipo "imagen") que no bloquea; el frontend sondea
    `GET /api/generaciones/{id}` y, al completarse, recoge `resultado = {id, url}`.
    """
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
    prompt = prompt.strip()

    def _generar() -> dict[str, object]:
        crudos = media.generar_imagen(prompt)
        nombre = media.guardar_bytes(crudos, ext="png")
        return {"id": nombre, "url": f"/api/media/{nombre}"}

    # Atribucion por usuario (#130 Fase 1): la imagen la genera el usuario de la peticion.
    autor = autor_de_peticion(request) or {}
    gen = generaciones.crear(
        {
            "tipo": "imagen",
            "marca": "",
            "etiqueta": f"Imagen · {prompt[:40]}",
            "autor_id": autor.get("id", ""),
            "autor_nombre": autor.get("usuario", ""),
        }
    )
    try:
        generaciones.lanzar_job_imagen(gen["id"], generar=_generar)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo; reflejamos error en el registro
        generaciones.actualizar(
            gen["id"],
            {"estado": generaciones.ESTADO_ERROR, "error": "No se pudo generar la imagen.",
             "fecha_fin": generaciones.ahora_iso()},
        )
    return JSONResponse({"generacion": generaciones.obtener(gen["id"]) or gen})


async def desde_url(request: Request) -> Response:
    """Descarga una imagen desde una URL externa al almacén -> `{id, url}`.

    Reutiliza la imagen ORIGINAL de un artículo (p.ej. de un RSS de marca propia) como un
    asset PROPIO y publicable. Guard SSRF + tope de tamaño + validación de que el contenido
    sea realmente una imagen (en `extraccion_url.descargar_imagen_a_media`).
    """
    datos = await leer_json(request)
    url = datos.get("url")
    if not isinstance(url, str) or not url.strip():
        return JSONResponse({"error": "Falta la URL de la imagen."}, status_code=400)
    try:
        nombre = extraccion_url.descargar_imagen_a_media(url.strip())
    except extraccion_url.ExtraccionError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        return JSONResponse({"error": "No se pudo descargar la imagen."}, status_code=500)
    return JSONResponse({"id": nombre, "url": f"/api/media/{nombre}"})


RUTAS = [
    Route("/api/media", subir, methods=["POST"]),
    Route("/api/media/desde-url", desde_url, methods=["POST"]),
    Route("/api/media/generar", generar, methods=["POST"]),
    Route("/api/media/{nombre:path}", servir, methods=["GET"]),
]
