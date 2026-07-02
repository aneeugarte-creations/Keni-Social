"""API Franjas: colas de pieza (franjas horarias) CRUD + calculo de hueco.

Una FRANJA es una plantilla de hueco recurrente: (marca?, red?, dia_semana, hora).
Las piezas se ENCOLAN buscando el proximo hueco futuro de las franjas que
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

from keni_shared import marcas
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import bootstrap_categorias, redes, repos
from .._http_json import leer_json

# La logica de scheduling (PURA y testeable) vive en el dominio `dominio.franjas`. Se
# RE-EXPORTA aqui para no romper a quien la importe como `api.franjas.X` (en particular
# `api/piezas.py` y `api/sugerencias_hora.py`, que hacen
# `from . import franjas as api_franjas; api_franjas.proximo_hueco(...)`).
from ..dominio.franjas import (  # noqa: F401  (re-export para compatibilidad)
    franjas_aplicables,
    hora_valida,
    proximo_hueco,
)

# Marcas validas: TODAS las del catalogo unico (por su id canonico). Mismo criterio
# que piezas.
_MARCAS: tuple[tuple[str, str], ...] = tuple(marcas.opciones())
_MARCAS_IDS = {m[0] for m in _MARCAS}


def _label_linea(categoria: str, lineas: dict[str, str]) -> str:
    """Nombre legible de la línea de una franja: id -> su nombre; señales con su rótulo; '' = genérica."""
    return bootstrap_categorias.etiqueta_categoria(categoria, lineas)


def _franja_a_dict(franja: dict[str, Any], etiqueta: str = "") -> dict[str, Any]:
    """Serializa una franja resolviendo nombres legibles de marca, red y LÍNEA."""
    return {
        "id": franja["id"],
        "marca": franja["marca"],
        "marca_nombre": marcas.etiqueta_de(franja["marca"]) if franja["marca"] else "",
        "red": franja["red"],
        "red_nombre": redes.nombre_por_id(franja["red"]) if franja["red"] else "",
        "dia_semana": franja["dia_semana"],
        "hora": franja["hora"],
        # LÍNEA del plan a la que sirve la franja (id de etiqueta categoria; '' = genérica).
        "categoria": franja.get("categoria", ""),
        # Nombre legible de esa línea (o "Última hora"/"Evergreen"); '' si es genérica.
        "etiqueta": etiqueta,
    }


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


def _listar() -> dict:
    franjas = repos.listar_franjas()
    # Mapa id de línea -> nombre (una lectura) para rotular sin N consultas.
    lineas = {e["id"]: e["nombre"] for e in repos.listar_etiquetas(clase="categoria")}
    return {
        "franjas": [_franja_a_dict(f, _label_linea(f.get("categoria", ""), lineas)) for f in franjas]
    }


async def listar(request: Request) -> Response:
    """Listado de franjas (con el nombre legible de su línea)."""
    cuerpo = await run_in_threadpool(_listar)
    return JSONResponse(cuerpo)


def _crear(dia: int, hora: str, marca: str, red: str, categoria: str) -> dict:
    franja = repos.crear_franja(dia, hora, marca=marca, red=red, categoria=categoria)
    return {"franja": _franja_a_dict(franja)}


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

    categoria = datos.get("categoria", "")
    if categoria is None:
        categoria = ""
    if not isinstance(categoria, str) or len(categoria) > 40:
        return JSONResponse({"error": "La categoría debe ser texto corto."}, status_code=400)

    cuerpo = await run_in_threadpool(
        _crear, dia, hora, marca, red, categoria.strip().lower()
    )
    return JSONResponse(cuerpo)


def _borrar(franja_id: str) -> tuple[int, dict]:
    if not repos.borrar_franja(franja_id):
        return 404, {"error": "Esa franja ya no existe."}
    return 200, {"mensaje": "Franja borrada."}


async def borrar(request: Request) -> Response:
    franja_id = request.path_params["franja_id"]
    status, cuerpo = await run_in_threadpool(_borrar, franja_id)
    return JSONResponse(cuerpo, status_code=status)


RUTAS = [
    Route("/api/franjas", listar, methods=["GET"]),
    Route("/api/franjas", crear, methods=["POST"]),
    Route("/api/franjas/{franja_id}", borrar, methods=["DELETE"]),
]
