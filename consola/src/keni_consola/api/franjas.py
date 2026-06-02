"""API Franjas: colas de publicacion (franjas horarias) CRUD + calculo de hueco.

Una FRANJA es una plantilla de hueco recurrente: (marca?, red?, dia_semana, hora).
Las publicaciones se ENCOLAN buscando el proximo hueco futuro de las franjas que
apliquen a su (marca, red). El calculo del hueco es una funcion PURA y DETERMINISTA
(`proximo_hueco`) que recibe "ahora" inyectado para poder testearla sin reloj real.

dia_semana: 0=lunes .. 6=domingo (igual que `datetime.weekday()`).
hora:       "HH:MM" en 24h.

SEGURIDAD / VALIDACION:
  - `marca` (si viene) SOLO del catalogo unico (por su id canonico); `red` (si viene)
    SOLO una red canonica. dia_semana 0..6; hora "HH:MM" valida.
  - SQL parametrizado en `consola.db`; errores en espanol, sin tracebacks.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import marcas, redes, repos
from .._http_json import leer_json

# La logica de scheduling (PURA y testeable) vive en el dominio `dominio.franjas`. Se
# RE-EXPORTA aqui para no romper a quien la importe como `api.franjas.X` (en particular
# `api/publicaciones.py` y `api/sugerencias_hora.py`, que hacen
# `from . import franjas as api_franjas; api_franjas.proximo_hueco(...)`).
from ..dominio.franjas import (  # noqa: F401  (re-export para compatibilidad)
    franjas_aplicables,
    proximo_hueco,
)
from ..dominio.franjas import hora_valida

# Marcas validas: TODAS las del catalogo unico (por su id canonico). Mismo criterio
# que publicaciones.
_MARCAS: tuple[tuple[str, str], ...] = tuple(marcas.opciones())
_MARCAS_IDS = {m[0] for m in _MARCAS}


def _franja_a_dict(franja: dict[str, Any]) -> dict[str, Any]:
    """Serializa una franja resolviendo nombres legibles de marca y red."""
    return {
        "id": franja["id"],
        "marca": franja["marca"],
        "marca_nombre": marcas.etiqueta_de(franja["marca"]) if franja["marca"] else "",
        "red": franja["red"],
        "red_nombre": redes.nombre_por_id(franja["red"]) if franja["red"] else "",
        "dia_semana": franja["dia_semana"],
        "hora": franja["hora"],
    }


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


async def listar(request: Request) -> Response:
    """Listado de franjas."""
    franjas = repos.listar_franjas()
    return JSONResponse({"franjas": [_franja_a_dict(f) for f in franjas]})


async def crear(request: Request) -> Response:
    """Crea una franja `{dia_semana, hora, marca?, red?}` -> `{franja}`."""
    datos = await leer_json(request)
    dia = datos.get("dia_semana")
    if not isinstance(dia, int) or isinstance(dia, bool) or not (0 <= dia <= 6):
        return JSONResponse(
            {"error": "El día de la semana debe ser un número de 0 (lunes) a 6 (domingo)."},
            status_code=400,
        )
    hora = datos.get("hora")
    if not hora_valida(hora):
        return JSONResponse(
            {"error": "La hora debe tener el formato HH:MM (24 horas)."}, status_code=400
        )
    marca = datos.get("marca", "")
    if marca is None:
        marca = ""
    if not isinstance(marca, str):
        return JSONResponse({"error": "La marca debe ser texto."}, status_code=400)
    if marca and marca not in _MARCAS_IDS:
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    red = datos.get("red", "")
    if red is None:
        red = ""
    if not isinstance(red, str):
        return JSONResponse({"error": "La red debe ser texto."}, status_code=400)
    if red and not redes.es_red(red):
        return JSONResponse({"error": "Red no permitida."}, status_code=400)

    franja = repos.crear_franja(dia, hora, marca=marca, red=red)
    return JSONResponse({"franja": _franja_a_dict(franja)})


async def borrar(request: Request) -> Response:
    franja_id = request.path_params["franja_id"]
    if not repos.borrar_franja(franja_id):
        return JSONResponse({"error": "Esa franja ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Franja borrada."})


RUTAS = [
    Route("/api/franjas", listar, methods=["GET"]),
    Route("/api/franjas", crear, methods=["POST"]),
    Route("/api/franjas/{franja_id}", borrar, methods=["DELETE"]),
]
