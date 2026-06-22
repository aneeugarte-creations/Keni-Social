"""Router del PREVIEW navegable de una propuesta del carril de auto-desarrollo.

El worker construye el frontend de la rama de una sugerencia y sube el bundle al almacen de
media bajo `previews/sug-<id>/...`. Este router lo sirve en `/api/preview/<id>/` (bajo `/api`
para reusar el enrutado Traefik->back; `/preview` a secas iria al SPA):

  - `/api/preview/<id>/api/<path>`  -> proxy de SOLO LECTURA a la API real. Las rutas se
    declaran SOLO con GET, asi que cualquier mutacion (POST/PUT/PATCH/DELETE) responde 405
    sin tocar nada: el preview se puede explorar/ensenar sin riesgo sobre datos reales.
  - `/api/preview/<id>/<path>`      -> assets estaticos del bundle desde el almacen, con
    fallback a `index.html` (rutas del cliente del SPA).

El bundle se compila con `base=/api/preview/<id>/`, asi que sus assets y su cliente API
cuelgan ya de ese prefijo. La limpieza del bundle (al promover/descartar) vive en
`worker_dev._teardown` + `almacen_media.borrar_prefijo`.
"""

from __future__ import annotations

import logging

import httpx
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import almacen_media, config

_log = logging.getLogger("keni_consola.api.preview")

# Content-Type por extension para servir el bundle. Lo desconocido cae a octet-stream.
_TIPOS: dict[str, str] = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".css": "text/css",
    ".map": "application/json",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".txt": "text/plain; charset=utf-8",
}


def _content_type(path: str) -> str:
    punto = path.rfind(".")
    ext = path[punto:].lower() if punto != -1 else ""
    return _TIPOS.get(ext, "application/octet-stream")


async def proxy_api(request: Request) -> Response:
    """GET de SOLO LECTURA a la API real (`/api/<path>`), reenviando cookie/authorization.

    La ruta solo admite GET (las mutaciones caen en 405 por metodo), asi que el preview nunca
    escribe sobre produccion. Reenvia al propio back por loopback; 502 si no responde.
    """
    path = request.path_params.get("path", "")
    destino = f"http://127.0.0.1:{config.port()}/api/{path}"
    cabeceras = {h: v for h in ("cookie", "authorization") if (v := request.headers.get(h))}
    try:
        async with httpx.AsyncClient(timeout=30.0) as cliente:
            r = await cliente.get(destino, params=dict(request.query_params), headers=cabeceras)
    except httpx.HTTPError as e:
        _log.warning("preview: no se pudo proxear %s: %s", destino, e)
        return JSONResponse(
            {"error": "No se pudo contactar la API para el preview."}, status_code=502
        )
    return Response(
        content=r.content,
        status_code=r.status_code,
        media_type=r.headers.get("content-type"),
    )


async def servir_asset(request: Request) -> Response:
    """Sirve un asset del bundle `previews/sug-<id>/<path>`; fallback a `index.html` (SPA)."""
    sid = request.path_params["sugerencia_id"]
    path = (request.path_params.get("path") or "").strip("/") or "index.html"
    datos = await run_in_threadpool(almacen_media.leer_crudo, f"previews/sug-{sid}/{path}")
    if datos is None:
        # Ruta del cliente (SPA) o asset ausente: cae al index para que el router del bundle resuelva.
        path = "index.html"
        datos = await run_in_threadpool(almacen_media.leer_crudo, f"previews/sug-{sid}/index.html")
        if datos is None:
            return JSONResponse({"error": "No hay preview para esta sugerencia."}, status_code=404)
    return Response(content=datos, media_type=_content_type(path))


# El proxy de API se declara ANTES del catch-all de assets para que `/api/preview/<id>/api/...`
# no lo capture el de assets. Ambos SOLO-GET: el preview es de lectura.
RUTAS = [
    Route("/api/preview/{sugerencia_id}/api/{path:path}", proxy_api, methods=["GET"]),
    Route("/api/preview/{sugerencia_id}", servir_asset, methods=["GET"]),
    Route("/api/preview/{sugerencia_id}/{path:path}", servir_asset, methods=["GET"]),
]
