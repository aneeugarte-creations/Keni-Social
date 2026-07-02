"""API Almacén de BLOQUES: grupos de capas reutilizables (editor profesional).

Un bloque es un conjunto de capas con sentido propio (lower-third, módulo de infografía, pleca de
marca) que se guarda una vez y se suelta en cualquier documento. Se etiqueta por `marca` y
`categorias` (ids de `etiquetas` clase=categoria).

  - `GET    /api/bloques`        lista (filtros `?marca=&q=`).
  - `POST   /api/bloques`        crea un bloque a partir de una lista de capas (validadas).
  - `GET    /api/bloques/{id}`   un bloque (con sus capas listas para insertar).
  - `PATCH  /api/bloques/{id}`   edita nombre/capas/categorias/miniatura.
  - `DELETE /api/bloques/{id}`   borra.

SEGURIDAD: `marca` (si llega) del catálogo único; las `capas` se validan en el dominio
(`estudio_imagen.validar_capas`) antes de persistir; errores en español, sin tracebacks.
"""

from __future__ import annotations

import json

from keni_shared import marcas
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import repos
from .._http_json import leer_json
from ..dominio import estudio_imagen
from ..seguridad import autor_de_peticion

_MAX_NOMBRE = 120
_MAX_CATEGORIAS = 24


def _validar_marca(marca: object) -> tuple[str | None, str | None]:
    if marca in (None, ""):
        return "", None
    if not isinstance(marca, str) or not marcas.es_marca(marca):
        return None, "Marca no permitida."
    return marca, None


def _normalizar_categorias(valor: object) -> list[str]:
    if not isinstance(valor, list):
        return []
    vistas: list[str] = []
    for item in valor:
        if isinstance(item, str) and item.strip() and item.strip() not in vistas:
            vistas.append(item.strip())
        if len(vistas) >= _MAX_CATEGORIAS:
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
        categorias = json.loads(item.get("categorias") or "[]")
    except (ValueError, TypeError):
        categorias = []
    if not isinstance(categorias, list):
        categorias = []
    miniatura = item.get("miniatura") or ""
    return {
        **item,
        "capas": capas,
        "categorias": [x for x in categorias if isinstance(x, str)],
        "miniatura_url": f"/api/media/{miniatura}" if miniatura else "",
        "marca_nombre": marcas.etiqueta_de(item["marca"]) if item.get("marca") else "",
    }


def _listar(marca: str | None, busqueda: str) -> dict:
    bloques = [_bloque_a_dict(item) for item in repos.listar_bloques(marca=marca)]
    if busqueda:
        bloques = [b for b in bloques if busqueda in (b.get("nombre") or "").lower()]
    return {"bloques": bloques}


async def listar(request: Request) -> Response:
    """GET /api/bloques: bloques (mas recientes primero), filtros `marca`/`q` opcionales."""
    q = request.query_params
    busqueda = (q.get("q") or "").strip().lower()
    cuerpo = await run_in_threadpool(_listar, q.get("marca") or None, busqueda)
    return JSONResponse(cuerpo)


def _crear(*, marca: str, nombre: str, capas: str, categorias: str, miniatura: str, autor: object) -> dict:
    bloque = repos.crear_bloque(
        marca=marca,
        nombre=nombre,
        capas=capas,
        categorias=categorias,
        miniatura=miniatura,
        autor=autor,
    )
    return {"bloque": _bloque_a_dict(bloque)}


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
    categorias = _normalizar_categorias(datos.get("categorias"))

    cuerpo = await run_in_threadpool(
        _crear,
        marca=marca or "",
        nombre=nombre,
        capas=json.dumps(capas_ok, ensure_ascii=False),
        categorias=json.dumps(categorias, ensure_ascii=False),
        miniatura=miniatura,
        autor=autor_de_peticion(request),
    )
    return JSONResponse(cuerpo)


def _obtener(bloque_id: str) -> tuple[int, dict]:
    item = repos.obtener_bloque(bloque_id)
    if item is None:
        return 404, {"error": "Ese bloque no existe."}
    return 200, {"bloque": _bloque_a_dict(item)}


async def obtener(request: Request) -> Response:
    """GET /api/bloques/{id}: un bloque con sus capas listas para insertar. -> 404 si no existe."""
    status, cuerpo = await run_in_threadpool(_obtener, request.path_params["bloque_id"])
    return JSONResponse(cuerpo, status_code=status)


def _actualizar(bloque_id: str, campos: dict) -> tuple[int, dict]:
    bloque = repos.actualizar_bloque(bloque_id, campos)
    if bloque is None:
        return 404, {"error": "Ese bloque no existe."}
    return 200, {"bloque": _bloque_a_dict(bloque)}


async def actualizar(request: Request) -> Response:
    """PATCH /api/bloques/{id}: edita nombre/capas/categorias/miniatura. -> `{bloque}` | 400/404."""
    bloque_id = request.path_params["bloque_id"]
    datos = await leer_json(request)
    if not isinstance(datos, dict):
        return JSONResponse({"error": "Cuerpo JSON inválido."}, status_code=400)

    campos: dict[str, object] = {}
    if "nombre" in datos:
        campos["nombre"] = (datos.get("nombre") or "").strip()[:_MAX_NOMBRE]
    if "miniatura" in datos:
        campos["miniatura"] = (datos.get("miniatura") or "").strip()
    if "categorias" in datos:
        campos["categorias"] = json.dumps(_normalizar_categorias(datos.get("categorias")), ensure_ascii=False)
    if "capas" in datos:
        if not isinstance(datos["capas"], list) or not datos["capas"]:
            return JSONResponse({"error": "Un bloque necesita al menos una capa."}, status_code=400)
        try:
            capas_ok = estudio_imagen.validar_capas(datos["capas"])
        except estudio_imagen.EstudioError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        campos["capas"] = json.dumps(capas_ok, ensure_ascii=False)

    status, cuerpo = await run_in_threadpool(_actualizar, bloque_id, campos)
    return JSONResponse(cuerpo, status_code=status)


def _borrar(bloque_id: str) -> tuple[int, dict]:
    item = repos.borrar_bloque(bloque_id)
    if item is None:
        return 404, {"error": "Ese bloque ya no existe."}
    return 200, {"mensaje": "Bloque borrado."}


async def borrar(request: Request) -> Response:
    """DELETE /api/bloques/{id}: borra el bloque. -> `{mensaje}` | 404."""
    status, cuerpo = await run_in_threadpool(_borrar, request.path_params["bloque_id"])
    return JSONResponse(cuerpo, status_code=status)


RUTAS = [
    Route("/api/bloques", listar, methods=["GET"]),
    Route("/api/bloques", crear, methods=["POST"]),
    Route("/api/bloques/{bloque_id}", obtener, methods=["GET"]),
    Route("/api/bloques/{bloque_id}", actualizar, methods=["PATCH"]),
    Route("/api/bloques/{bloque_id}", borrar, methods=["DELETE"]),
]
