"""API HISTORIAL de generaciones: listado, detalle y "guardar como publicación".

El historial es el registro DURADERO de las generaciones de copy/documento (lo escribe el
post-procesado vía `repos.registrar_historial_skill`). Lo consumen TODAS las generaciones
(copy, termómetro, QA…), no solo la antigua página de skills, por eso vive en su propio
módulo NEUTRO (al retirar el sistema de skills). Mantiene los paths `/api/skills/historial*`
para no romper el frontend.

  - `GET  /api/skills/historial`               -> listado (metadatos + preview).
  - `GET  /api/skills/historial/{id}`          -> detalle (resultado completo).
  - `POST /api/skills/historial/{id}/guardar`  -> crea publicaciones (borradores) desde la
                                                  entrada (una por pieza, o una con `red`).
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import marcas, redes, repos
from .._http_json import leer_json
from ..dominio import copy as dom_copy
from ..dominio import publicaciones as dom_publicaciones
from ..dominio import stream
from ..seguridad import autor_de_peticion

# Longitud del preview del resultado en el listado (chars).
_PREVIEW_CHARS = 140

# Mapa id->nombre de marca (catálogo único) para enriquecer el listado.
_MARCA_NOMBRE: dict[str, str] = dict(marcas.opciones())


def _preview(resultado: str) -> str:
    """Primeros ~140 chars del resultado para el listado del historial."""
    resultado = (resultado or "").strip()
    if len(resultado) <= _PREVIEW_CHARS:
        return resultado
    return resultado[:_PREVIEW_CHARS].rstrip() + "…"


def _nombre(skill: str) -> str:
    """Nombre legible de la generación de origen (sin catálogo: prettify del id)."""
    return (skill or "").replace("-", " ").strip().capitalize() or skill


async def historial(request: Request) -> Response:
    """`GET /api/skills/historial` -> listado (metadatos + preview), recientes primero."""
    entradas = repos.listar_historial_skills()
    salida = [
        {
            "id": e["id"],
            "skill": e["skill"],
            "skill_nombre": _nombre(e["skill"]),
            "marca": e["marca"],
            "marca_nombre": _MARCA_NOMBRE.get(e["marca"], e["marca"]),
            "fecha": e["fecha"],
            "titulo": e["titulo"],
            "preview": _preview(e["resultado"]),
            "piezas": e["piezas"],
            "metricas": e.get("metricas"),
            "autor_id": e.get("autor_id", "") or "",
            "autor_nombre": e.get("autor_nombre", "") or "",
        }
        for e in entradas
    ]
    return JSONResponse({"historial": salida})


async def historial_detalle(request: Request) -> Response:
    """`GET /api/skills/historial/{id}` -> detalle con el resultado completo (404)."""
    entrada = repos.obtener_historial_skill(request.path_params["historial_id"])
    if entrada is None:
        return JSONResponse({"error": "No se encontró ese borrador en el historial."}, status_code=404)
    return JSONResponse(
        {
            "id": entrada["id"],
            "skill": entrada["skill"],
            "marca": entrada["marca"],
            "fecha": entrada["fecha"],
            "titulo": entrada["titulo"],
            "resultado": entrada["resultado"],
            "piezas": entrada["piezas"],
            "metricas": entrada.get("metricas"),
            "autor_id": entrada.get("autor_id", "") or "",
            "autor_nombre": entrada.get("autor_nombre", "") or "",
        }
    )


async def historial_guardar(request: Request) -> Response:
    """`POST /api/skills/historial/{id}/guardar` -> crea publicaciones (borradores).

    Con piezas: una publicación por pieza (filtradas a `redes` si se pasa). Sin piezas
    (entradas antiguas): requiere `red` ∈ redes canónicas. 404 si la entrada no existe.
    """
    historial_id = request.path_params["historial_id"]
    entrada = repos.obtener_historial_skill(historial_id)
    if entrada is None:
        return JSONResponse({"error": "No se encontró ese borrador en el historial."}, status_code=404)

    datos = await leer_json(request)
    titulo_dado = datos.get("titulo")
    titulo_dado = titulo_dado.strip() if isinstance(titulo_dado, str) else ""
    crudas = datos.get("redes")
    redes_filtro: set[str] | None = None
    if isinstance(crudas, list):
        redes_filtro = {r for r in crudas if isinstance(r, str) and redes.es_red(r)}

    marca = entrada["marca"]
    verdicto = stream.derivar_verdicto(entrada["resultado"])
    titulo = titulo_dado or entrada["titulo"] or stream.derivar_titulo(entrada["resultado"])
    piezas = entrada["piezas"]

    autor = autor_de_peticion(request)
    if piezas:
        publicaciones = dom_copy.crear_publicaciones_desde_piezas(
            piezas, marca=marca, titulo=titulo, verdicto=verdicto, origen=historial_id,
            redes_filtro=redes_filtro, autor=autor,
        )
        return JSONResponse({"publicaciones": publicaciones})

    # Entrada antigua sin piezas: requiere una red explícita.
    red = datos.get("red")
    if not isinstance(red, str) or not redes.es_red(red):
        return JSONResponse(
            {"error": "Indica la red para guardar este borrador como publicación."}, status_code=400
        )
    if redes_filtro is not None and red not in redes_filtro:
        return JSONResponse(
            {"error": "La red indicada no está entre las redes pedidas."}, status_code=400
        )
    pub = dom_publicaciones.crear_borrador(
        marca, red, titulo=titulo, contenido=entrada["resultado"], veredicto=verdicto,
        origen=historial_id, autor=autor,
    )
    return JSONResponse({"publicaciones": [pub]})


RUTAS = [
    Route("/api/skills/historial", historial, methods=["GET"]),
    Route("/api/skills/historial/{historial_id}/guardar", historial_guardar, methods=["POST"]),
    Route("/api/skills/historial/{historial_id}", historial_detalle, methods=["GET"]),
]
