"""API Plantillas: plantillas de post reutilizables (nombre + marca/red + contenido).

El SPA guarda plantillas de copy para arrancar publicaciones nuevas mas rapido.
Persistencia en SQLite (`consola.db`, via `consola.db`). Nada se publica aqui.

SEGURIDAD / VALIDACION (reusa las fuentes de verdad):
  - `nombre` obligatorio (no vacio).
  - `marca` (si viene) SOLO del catalogo unico (`consola.marcas`, por su id canonico).
  - `red` (si viene) SOLO una red canonica (`consola.redes`).
  - SQL parametrizado en `consola.db`; errores en espanol, sin tracebacks crudos.

`marca_nombre` y `red_nombre` se resuelven EN SERVIDOR (la UI solo muestra nombres).
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import marcas, redes, repos
from .._http_json import leer_json

# Marcas validas: TODAS las del catalogo unico (por su id canonico). Mismo criterio
# que publicaciones.
_MARCAS: tuple[tuple[str, str], ...] = tuple(marcas.opciones())
_MARCAS_IDS = {m[0] for m in _MARCAS}


def _plantilla_a_dict(plantilla: dict[str, Any]) -> dict[str, Any]:
    """Serializa una plantilla resolviendo nombres legibles de marca y red."""
    return {
        "id": plantilla["id"],
        "nombre": plantilla["nombre"],
        "marca": plantilla["marca"],
        "marca_nombre": marcas.etiqueta_de(plantilla["marca"]) if plantilla["marca"] else "",
        "red": plantilla["red"],
        "red_nombre": redes.nombre_por_id(plantilla["red"]) if plantilla["red"] else "",
        "contenido": plantilla["contenido"],
    }


def _validar_marca(marca: Any) -> tuple[str | None, str | None]:
    """Normaliza/valida una marca opcional. `(marca, None)` o `(None, mensaje)`."""
    if marca is None:
        marca = ""
    if not isinstance(marca, str):
        return None, "La marca debe ser texto."
    if marca and marca not in _MARCAS_IDS:
        return None, "Marca no permitida."
    return marca, None


def _validar_red(red: Any) -> tuple[str | None, str | None]:
    """Normaliza/valida una red opcional. `(red, None)` o `(None, mensaje)`."""
    if red is None:
        red = ""
    if not isinstance(red, str):
        return None, "La red debe ser texto."
    if red and not redes.es_red(red):
        return None, "Red no permitida."
    return red, None


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


async def listar(request: Request) -> Response:
    """Listado de plantillas."""
    plantillas = repos.listar_plantillas()
    return JSONResponse({"plantillas": [_plantilla_a_dict(p) for p in plantillas]})


async def crear(request: Request) -> Response:
    """Crea una plantilla `{nombre, marca?, red?, contenido}` -> `{plantilla}`."""
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

    plantilla = repos.crear_plantilla(nombre.strip(), marca=marca, red=red, contenido=contenido)
    return JSONResponse({"plantilla": _plantilla_a_dict(plantilla)})


async def actualizar(request: Request) -> Response:
    """Edicion PARCIAL `{nombre?, marca?, red?, contenido?}` -> `{plantilla}` | 404."""
    plantilla_id = request.path_params["plantilla_id"]
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

    plantilla = repos.actualizar_plantilla(plantilla_id, campos)
    if plantilla is None:
        return JSONResponse({"error": "Esa plantilla ya no existe."}, status_code=404)
    return JSONResponse({"plantilla": _plantilla_a_dict(plantilla)})


async def borrar(request: Request) -> Response:
    plantilla_id = request.path_params["plantilla_id"]
    if not repos.borrar_plantilla(plantilla_id):
        return JSONResponse({"error": "Esa plantilla ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Plantilla borrada."})


RUTAS = [
    Route("/api/plantillas", listar, methods=["GET"]),
    Route("/api/plantillas", crear, methods=["POST"]),
    Route("/api/plantillas/{plantilla_id}", actualizar, methods=["PUT"]),
    Route("/api/plantillas/{plantilla_id}", borrar, methods=["DELETE"]),
]
