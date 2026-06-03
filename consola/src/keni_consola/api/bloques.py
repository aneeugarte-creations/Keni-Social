"""API Almacén de BLOQUES: grupos de capas reutilizables (editor profesional).

Un bloque es un conjunto de capas con sentido propio (lower-third, módulo de infografía, pleca de
marca) que se guarda una vez y se suelta en cualquier documento. Se etiqueta por `marca` y `lineas`
(ids de `etiquetas` clase=vertical).

  - `GET    /api/bloques`        lista (filtros `?marca=&q=`).
  - `POST   /api/bloques`        crea un bloque a partir de una lista de capas (validadas).
  - `GET    /api/bloques/{id}`   un bloque (con sus capas listas para insertar).
  - `PATCH  /api/bloques/{id}`   edita nombre/capas/lineas/miniatura.
  - `DELETE /api/bloques/{id}`   borra.

SEGURIDAD: `marca` (si llega) del catálogo único; las `capas` se validan en el dominio
(`estudio_imagen.validar_capas`) antes de persistir; errores en español, sin tracebacks.
"""

from __future__ import annotations

import json

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import marcas, repos
from .._http_json import leer_json
from ..dominio import estudio_imagen
from ..seguridad import autor_de_peticion

_MAX_NOMBRE = 120
_MAX_LINEAS = 24


def _validar_marca(marca: object) -> tuple[str | None, str | None]:
    if marca in (None, ""):
        return "", None
    if not isinstance(marca, str) or not marcas.es_marca(marca):
        return None, "Marca no permitida."
    return marca, None


def _normalizar_lineas(valor: object) -> list[str]:
    if not isinstance(valor, list):
        return []
    vistas: list[str] = []
    for item in valor:
        if isinstance(item, str) and item.strip() and item.strip() not in vistas:
            vistas.append(item.strip())
        if len(vistas) >= _MAX_LINEAS:
            break
    return vistas


def _bloque_a_dict(item: dict) -> dict:
    try:
        capas = json.loads(item.get("capas") or "[]")
    except (ValueError, TypeError):
        capas = []
    if not isinstance(capas, list):
        capas = []
    try:
        lineas = json.loads(item.get("lineas") or "[]")
    except (ValueError, TypeError):
        lineas = []
    if not isinstance(lineas, list):
        lineas = []
    miniatura = item.get("miniatura") or ""
    return {
        **item,
        "capas": capas,
        "lineas": [x for x in lineas if isinstance(x, str)],
        "miniatura_url": f"/api/media/{miniatura}" if miniatura else "",
        "marca_nombre": marcas.etiqueta_de(item["marca"]) if item.get("marca") else "",
    }


async def listar(request: Request) -> Response:
    """GET /api/bloques: bloques (mas recientes primero), filtros `marca`/`q` opcionales."""
    q = request.query_params
    bloques = [_bloque_a_dict(item) for item in repos.listar_bloques(marca=q.get("marca") or None)]
    busqueda = (q.get("q") or "").strip().lower()
    if busqueda:
        bloques = [b for b in bloques if busqueda in (b.get("nombre") or "").lower()]
    return JSONResponse({"bloques": bloques})


async def crear(request: Request) -> Response:
    """POST /api/bloques: crea un bloque desde una lista de capas (validadas). -> `{bloque}` | 400."""
    datos = await leer_json(request)
    if not isinstance(datos, dict):
        return JSONResponse({"error": "Cuerpo JSON inválido."}, status_code=400)

    capas = datos.get("capas")
    if not isinstance(capas, list) or not capas:
        return JSONResponse({"error": "Un bloque necesita al menos una capa."}, status_code=400)
    try:
        capas_ok = estudio_imagen.validar_capas(capas)
    except estudio_imagen.EstudioError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    marca, err = _validar_marca(datos.get("marca"))
    if err:
        return JSONResponse({"error": err}, status_code=400)

    nombre = (datos.get("nombre") or "").strip()[:_MAX_NOMBRE]
    miniatura = (datos.get("miniatura") or "").strip() if isinstance(datos.get("miniatura"), str) else ""
    lineas = _normalizar_lineas(datos.get("lineas"))

    bloque = repos.crear_bloque(
        marca=marca or "",
        nombre=nombre,
        capas=json.dumps(capas_ok, ensure_ascii=False),
        lineas=json.dumps(lineas, ensure_ascii=False),
        miniatura=miniatura,
        autor=autor_de_peticion(request),
    )
    return JSONResponse({"bloque": _bloque_a_dict(bloque)})


async def obtener(request: Request) -> Response:
    """GET /api/bloques/{id}: un bloque con sus capas listas para insertar. -> 404 si no existe."""
    item = repos.obtener_bloque(request.path_params["bloque_id"])
    if item is None:
        return JSONResponse({"error": "Ese bloque no existe."}, status_code=404)
    return JSONResponse({"bloque": _bloque_a_dict(item)})


async def actualizar(request: Request) -> Response:
    """PATCH /api/bloques/{id}: edita nombre/capas/lineas/miniatura. -> `{bloque}` | 400/404."""
    bloque_id = request.path_params["bloque_id"]
    datos = await leer_json(request)
    if not isinstance(datos, dict):
        return JSONResponse({"error": "Cuerpo JSON inválido."}, status_code=400)

    campos: dict[str, object] = {}
    if "nombre" in datos:
        campos["nombre"] = (datos.get("nombre") or "").strip()[:_MAX_NOMBRE]
    if "miniatura" in datos:
        campos["miniatura"] = (datos.get("miniatura") or "").strip()
    if "lineas" in datos:
        campos["lineas"] = json.dumps(_normalizar_lineas(datos.get("lineas")), ensure_ascii=False)
    if "capas" in datos:
        if not isinstance(datos["capas"], list) or not datos["capas"]:
            return JSONResponse({"error": "Un bloque necesita al menos una capa."}, status_code=400)
        try:
            capas_ok = estudio_imagen.validar_capas(datos["capas"])
        except estudio_imagen.EstudioError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        campos["capas"] = json.dumps(capas_ok, ensure_ascii=False)

    bloque = repos.actualizar_bloque(bloque_id, campos)
    if bloque is None:
        return JSONResponse({"error": "Ese bloque no existe."}, status_code=404)
    return JSONResponse({"bloque": _bloque_a_dict(bloque)})


async def borrar(request: Request) -> Response:
    """DELETE /api/bloques/{id}: borra el bloque. -> `{mensaje}` | 404."""
    item = repos.borrar_bloque(request.path_params["bloque_id"])
    if item is None:
        return JSONResponse({"error": "Ese bloque ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Bloque borrado."})


RUTAS = [
    Route("/api/bloques", listar, methods=["GET"]),
    Route("/api/bloques", crear, methods=["POST"]),
    Route("/api/bloques/{bloque_id}", obtener, methods=["GET"]),
    Route("/api/bloques/{bloque_id}", actualizar, methods=["PATCH"]),
    Route("/api/bloques/{bloque_id}", borrar, methods=["DELETE"]),
]
