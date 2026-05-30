"""API Plantillas (LEGADO): adaptador de SOLO-MODO-PLANO sobre el catálogo unificado.

El concepto de "plantilla de copy plano" (un texto reutilizable por marca/red) se FUSIONÓ
en el catálogo unificado `plantilla_contenido` (ver `api/plantillas_contenido.py`), donde una
plantilla plana es simplemente `modo='plano'` con su texto en `contenido`. Este módulo se
mantiene SOLO como adaptador retrocompatible para clientes viejos que aún llamen a
`/api/plantillas`: traduce la forma legada `{nombre, marca, red, contenido}` a/desde el
catálogo unificado y filtra a las plantillas planas. No persiste nada propio.

NO crees plantillas nuevas por aquí desde la UI: usa `/api/plantillas-contenido`. Este
adaptador se podrá retirar cuando ningún cliente lo consuma.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import marcas, redes, repos
from .._http_json import leer_json
from ..seguridad import autor_de_peticion

# Marcas validas: TODAS las del catalogo unico (por su id canonico).
_MARCAS_IDS = {m[0] for m in marcas.opciones()}


def _plantilla_a_dict(p: dict[str, Any]) -> dict[str, Any]:
    """Serializa una plantilla plana en la forma LEGADA `{id,nombre,marca,red,contenido}`."""
    return {
        "id": p["id"],
        "nombre": p["nombre"],
        "marca": p["marca"],
        "marca_nombre": marcas.etiqueta_de(p["marca"]) if p["marca"] else "",
        "red": p["red"],
        "red_nombre": redes.nombre_por_id(p["red"]) if p["red"] else "",
        "contenido": p.get("contenido", "") or "",
    }


def _es_plana(p: dict[str, Any]) -> bool:
    return (p.get("modo") or "estructura") == "plano"


def _validar_marca(marca: Any) -> tuple[str | None, str | None]:
    if marca is None:
        marca = ""
    if not isinstance(marca, str):
        return None, "La marca debe ser texto."
    if marca and marca not in _MARCAS_IDS:
        return None, "Marca no permitida."
    return marca, None


def _validar_red(red: Any) -> tuple[str | None, str | None]:
    if red is None:
        red = ""
    if not isinstance(red, str):
        return None, "La red debe ser texto."
    if red and not redes.es_red(red):
        return None, "Red no permitida."
    return red, None


def _obtener_plana(plantilla_id: str) -> dict[str, Any] | None:
    """Una plantilla por id SOLO si es plana (las de estructura no las gestiona el adaptador)."""
    p = repos.obtener_plantilla_contenido(plantilla_id)
    if p is None or not _es_plana(p):
        return None
    return p


# --------------------------------------------------------------------------- #
# Endpoints (adaptan al catálogo unificado, filtrando a modo='plano')          #
# --------------------------------------------------------------------------- #


async def listar(request: Request) -> Response:
    """Listado de plantillas PLANAS (forma legada)."""
    plantillas = [p for p in repos.listar_plantillas_contenido() if _es_plana(p)]
    return JSONResponse({"plantillas": [_plantilla_a_dict(p) for p in plantillas]})


async def crear(request: Request) -> Response:
    """Crea una plantilla plana `{nombre, marca?, red?, contenido}` -> `{plantilla}`."""
    datos = await leer_json(request)
    nombre = datos.get("nombre")
    if not isinstance(nombre, str) or not nombre.strip():
        return JSONResponse({"error": "El nombre de la plantilla es obligatorio."}, status_code=400)
    marca, error = _validar_marca(datos.get("marca", ""))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    red, error = _validar_red(datos.get("red", ""))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    contenido = datos.get("contenido", "")
    if not isinstance(contenido, str):
        return JSONResponse({"error": "El contenido debe ser texto."}, status_code=400)

    autor = autor_de_peticion(request) or {}
    plantilla = repos.crear_plantilla_contenido(
        nombre=nombre.strip(),
        modo="plano",
        marca=marca,
        red=red,
        contenido=contenido,
        autor=autor,
    )
    return JSONResponse({"plantilla": _plantilla_a_dict(plantilla)})


async def actualizar(request: Request) -> Response:
    """Edicion PARCIAL `{nombre?, marca?, red?, contenido?}` -> `{plantilla}` | 404."""
    plantilla_id = request.path_params["plantilla_id"]
    if _obtener_plana(plantilla_id) is None:
        return JSONResponse({"error": "Esa plantilla ya no existe."}, status_code=404)
    datos = await leer_json(request)
    campos: dict[str, Any] = {}
    if "nombre" in datos:
        nombre = datos.get("nombre")
        if not isinstance(nombre, str) or not nombre.strip():
            return JSONResponse(
                {"error": "El nombre de la plantilla es obligatorio."}, status_code=400
            )
        campos["nombre"] = nombre.strip()
    if "marca" in datos:
        marca, error = _validar_marca(datos.get("marca"))
        if error is not None:
            return JSONResponse({"error": error}, status_code=400)
        campos["marca"] = marca
    if "red" in datos:
        red, error = _validar_red(datos.get("red"))
        if error is not None:
            return JSONResponse({"error": error}, status_code=400)
        campos["red"] = red
    if "contenido" in datos:
        contenido = datos.get("contenido")
        if not isinstance(contenido, str):
            return JSONResponse({"error": "El contenido debe ser texto."}, status_code=400)
        campos["contenido"] = contenido
    if not campos:
        return JSONResponse(
            {"error": "No hay nada que actualizar (nombre, marca, red o contenido)."},
            status_code=400,
        )

    plantilla = repos.actualizar_plantilla_contenido(plantilla_id, campos)
    if plantilla is None:
        return JSONResponse({"error": "Esa plantilla ya no existe."}, status_code=404)
    return JSONResponse({"plantilla": _plantilla_a_dict(plantilla)})


async def borrar(request: Request) -> Response:
    plantilla_id = request.path_params["plantilla_id"]
    if _obtener_plana(plantilla_id) is None:
        return JSONResponse({"error": "Esa plantilla ya no existe."}, status_code=404)
    if not repos.borrar_plantilla_contenido(plantilla_id):
        return JSONResponse({"error": "Esa plantilla ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Plantilla borrada."})


RUTAS = [
    Route("/api/plantillas", listar, methods=["GET"]),
    Route("/api/plantillas", crear, methods=["POST"]),
    Route("/api/plantillas/{plantilla_id}", actualizar, methods=["PUT"]),
    Route("/api/plantillas/{plantilla_id}", borrar, methods=["DELETE"]),
]
