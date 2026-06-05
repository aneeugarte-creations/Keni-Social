"""API Cadencias: scheduling por MARGEN entre posts, por (marca?, red?).

Una CADENCIA define, para una (marca, red): el MARGEN (minutos entre posts), la VENTANA
horaria activa (`hora_inicio`..`hora_fin`, 24h) y los DÍAS activos (0=lunes..6=domingo). El
repartidor (`api/publicaciones.calcular_hueco_para`) la prefiere a las franjas-caja para
escalar a alto volumen: coloca cada pieza en el próximo hueco libre espaciado por el margen.

`marca=''`/`red=''` = comodín (aplica a todas). UNIQUE(marca, red): una cadencia por par.
La lógica PURA (validación + cálculo de hueco) vive en `dominio/cadencia.py`.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import marcas, redes, repos
from .._http_json import leer_json
from ..dominio import cadencia as dom_cadencia

# Marcas validas: TODAS las del catalogo unico (por su id canonico).
_MARCAS_IDS = {m[0] for m in marcas.opciones()}


def _cadencia_a_dict(c: dict[str, Any]) -> dict[str, Any]:
    """Serializa una cadencia resolviendo nombres legibles de marca y red."""
    return {
        "id": c["id"],
        "marca": c["marca"],
        "marca_nombre": marcas.etiqueta_de(c["marca"]) if c["marca"] else "",
        "red": c["red"],
        "red_nombre": redes.nombre_por_id(c["red"]) if c["red"] else "",
        "margen_min": c["margen_min"],
        "hora_inicio": c["hora_inicio"],
        "hora_fin": c["hora_fin"],
        "dias": c["dias"],
        "activo": c["activo"],
    }


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


async def listar(request: Request) -> Response:
    """Listado de cadencias."""
    return JSONResponse({"cadencias": [_cadencia_a_dict(c) for c in repos.listar_cadencias()]})


async def guardar(request: Request) -> Response:
    """UPSERT de la cadencia de `(marca?, red?)` -> `{cadencia}`.

    Cuerpo: `{marca?, red?, margen_min, hora_inicio, hora_fin, dias:[0..6], activo?}`.
    """
    datos = await leer_json(request)

    marca = datos.get("marca", "") or ""
    if not isinstance(marca, str):
        return JSONResponse({"error": "La marca debe ser texto."}, status_code=400)
    if marca and marca not in _MARCAS_IDS:
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)

    red = datos.get("red", "") or ""
    if not isinstance(red, str):
        return JSONResponse({"error": "La red debe ser texto."}, status_code=400)
    if red and not redes.es_red(red):
        return JSONResponse({"error": "Red no permitida."}, status_code=400)

    margen = datos.get("margen_min")
    if not isinstance(margen, int) or isinstance(margen, bool) or margen <= 0:
        return JSONResponse(
            {"error": "El margen (minutos entre posts) debe ser un entero mayor que 0."},
            status_code=400,
        )

    dias = datos.get("dias")
    if not isinstance(dias, list) or not dias or not all(
        isinstance(d, int) and not isinstance(d, bool) and 0 <= d <= 6 for d in dias
    ):
        return JSONResponse(
            {"error": "Indica los días activos como una lista de 0 (lunes) a 6 (domingo)."},
            status_code=400,
        )
    dias = sorted(set(dias))

    candidata = {
        "margen_min": margen,
        "hora_inicio": datos.get("hora_inicio"),
        "hora_fin": datos.get("hora_fin"),
        "dias": dias,
    }
    if not dom_cadencia.cadencia_valida(candidata):
        return JSONResponse(
            {"error": "Revisa la ventana: horas HH:MM válidas y fin posterior al inicio."},
            status_code=400,
        )

    activo = datos.get("activo", True)
    if not isinstance(activo, bool):
        return JSONResponse({"error": "El campo activo debe ser verdadero o falso."}, status_code=400)

    guardada = repos.guardar_cadencia(
        marca=marca,
        red=red,
        margen_min=margen,
        hora_inicio=datos["hora_inicio"],
        hora_fin=datos["hora_fin"],
        dias=dias,
        activo=activo,
    )
    return JSONResponse({"cadencia": _cadencia_a_dict(guardada)})


async def borrar(request: Request) -> Response:
    cadencia_id = request.path_params["cadencia_id"]
    if not repos.borrar_cadencia(cadencia_id):
        return JSONResponse({"error": "Esa cadencia ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Cadencia borrada."})


RUTAS = [
    Route("/api/cadencias", listar, methods=["GET"]),
    Route("/api/cadencias", guardar, methods=["PUT"]),
    Route("/api/cadencias/{cadencia_id}", borrar, methods=["DELETE"]),
]
