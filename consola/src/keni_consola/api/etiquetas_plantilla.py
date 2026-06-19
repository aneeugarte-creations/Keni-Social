"""API HTTP — catálogo de ETIQUETAS de plantilla, editable POR MARCA.

Una etiqueta es el rótulo LEGIBLE de una categoría de plantilla (`plantillas_diseno.categoria`, texto
libre normalizado a slug). Renombrar una etiqueta cambia SOLO su rótulo visible para esa marca y
conserva el slug: NO mueve plantillas. La identidad es `(marca, slug)`.

  - `GET    /api/etiquetas-plantilla`               lista (filtro `?marca=`); rótulos personalizados.
  - `PUT    /api/etiquetas-plantilla/{marca}/{slug}` crea/renombra el rótulo (cuerpo `{etiqueta}`).
  - `DELETE /api/etiquetas-plantilla/{marca}/{slug}` borra el rótulo (409 si alguna plantilla lo usa).

El catálogo de rótulos POR DEFECTO (y la lista de categorías presentes) vive en el frontend
(`lib/categoriasPlantilla.ts`): aquí solo se guardan los OVERRIDES que el equipo pone al renombrar.
"""
from __future__ import annotations

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import marcas, repos
from .._http_json import leer_json
from .plantillas_diseno import _normalizar_categoria as _normalizar_slug

_MAX_ETIQUETA = 60


def _etiqueta_a_dict(item: dict) -> dict:
    """Serializa una etiqueta a la forma pública (sin id ni timestamps internos)."""
    return {"marca": item["marca"], "slug": item["slug"], "etiqueta": item["etiqueta"]}


def _validar_marca(marca: object) -> tuple[str | None, str | None]:
    """Marca válida y permitida, o (None, error)."""
    if not isinstance(marca, str) or not marcas.es_marca(marca):
        return None, "Marca no permitida."
    return marca, None


def _listar(marca_q: str | None) -> dict:
    etiquetas = [_etiqueta_a_dict(e) for e in repos.listar_etiquetas_plantilla(marca=marca_q)]
    return {"etiquetas": etiquetas}


async def listar(request: Request) -> Response:
    """GET /api/etiquetas-plantilla: rótulos personalizados, filtrables por marca."""
    marca_q = (request.query_params.get("marca") or "").strip() or None
    cuerpo = await run_in_threadpool(_listar, marca_q)
    return JSONResponse(cuerpo)


def _guardar(marca: str, slug: str, etiqueta: str) -> dict:
    item = repos.upsert_etiqueta_plantilla(marca=marca, slug=slug, etiqueta=etiqueta)
    return {"etiqueta": _etiqueta_a_dict(item)}


async def guardar(request: Request) -> Response:
    """PUT /api/etiquetas-plantilla/{marca}/{slug}: crea o renombra el rótulo de una categoría."""
    marca, err = _validar_marca(request.path_params.get("marca"))
    if err:
        return JSONResponse({"error": err}, status_code=400)
    slug = _normalizar_slug(request.path_params.get("slug"))
    if not slug:
        return JSONResponse({"error": "Etiqueta no válida."}, status_code=400)
    datos = await leer_json(request)
    if not isinstance(datos, dict):
        return JSONResponse({"error": "Cuerpo JSON inválido."}, status_code=400)
    etiqueta = (datos.get("etiqueta") if isinstance(datos.get("etiqueta"), str) else "").strip()[
        :_MAX_ETIQUETA
    ]
    cuerpo = await run_in_threadpool(_guardar, marca, slug, etiqueta)
    return JSONResponse(cuerpo)


def _borrar(marca: str, slug: str) -> tuple[int, dict]:
    en_uso = len(repos.listar_plantillas_diseno(marca=marca, categoria=slug))
    if en_uso:
        return 409, {"error": f"{en_uso} plantilla(s) usan esta etiqueta.", "en_uso": en_uso}
    repos.borrar_etiqueta_plantilla(marca=marca, slug=slug)
    return 200, {"mensaje": "Etiqueta eliminada."}


async def borrar(request: Request) -> Response:
    """DELETE /api/etiquetas-plantilla/{marca}/{slug}: borra el rótulo (409 si está en uso)."""
    marca, err = _validar_marca(request.path_params.get("marca"))
    if err:
        return JSONResponse({"error": err}, status_code=400)
    slug = _normalizar_slug(request.path_params.get("slug"))
    if not slug:
        return JSONResponse({"error": "Etiqueta no válida."}, status_code=400)
    status, cuerpo = await run_in_threadpool(_borrar, marca, slug)
    return JSONResponse(cuerpo, status_code=status)


RUTAS = [
    Route("/api/etiquetas-plantilla", listar, methods=["GET"]),
    Route("/api/etiquetas-plantilla/{marca}/{slug}", guardar, methods=["PUT"]),
    Route("/api/etiquetas-plantilla/{marca}/{slug}", borrar, methods=["DELETE"]),
]
