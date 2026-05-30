"""API de ETIQUETAS editoriales del tablero (ola "organizacion").

Una etiqueta clasifica transversalmente las piezas del tablero de contenido por un EJE
(`clase`): una CAMPAÑA ("Mundial 2026"), una VERTICAL/sección editorial ("futbol") o un
TIPO de formato ("reel", "nota"). Es N:M con `contenido` (una pieza puede llevar varias).

WORKSPACES / MULTIMARCA: cada etiqueta puede ACOTARSE a una marca (`marca`) — así UnoTV
y Claro Sports tienen sus propias campañas/verticales sin pisarse — o ser GLOBAL
(`marca = ''`, visible en todas). El equipo es compartido; lo que aísla cada workspace es
la marca de las piezas y de sus etiquetas. El selector de etiquetas del tablero pide las
de la marca activa + las globales.

La asignación de etiquetas a un contenido vive en `api/contenido.py` (mismo recurso padre);
aquí se gestiona el CATÁLOGO de etiquetas (crear/editar/borrar).

SEGURIDAD:
  - Multiusuario via middleware (sesión o token). Tablero compartido (como Tareas).
  - `clase` debe ser del catálogo (`estados.CLASES_ETIQUETA`); `marca`, si llega, del
    catálogo de marcas (`consola.marcas`) o vacía (global). `color` se sanea a un token
    hex corto. Unicidad por (nombre, clase, marca). Nada se confía del cliente.
  - SQL parametrizado en `repos`/`db`.
"""

from __future__ import annotations

import re

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import marcas, repos
from .._http_json import leer_json
from ..estados import CLASE_ETIQUETA_DEFECTO, CLASES_ETIQUETA

_MAX_NOMBRE = 60
# Color como token hex (#rgb o #rrggbb). Vacío = sin color (la UI elige uno por clase).
_RE_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _etiqueta_a_dict(et: dict) -> dict:
    """Serializa una etiqueta añadiendo el nombre legible de su marca (o '' si global)."""
    return {
        **et,
        "marca_nombre": marcas.etiqueta_de(et["marca"]) if et.get("marca") else "",
    }


def _validar_marca(marca: object) -> tuple[str | None, str | None]:
    """'' (global) es válido; cualquier otra debe ser una marca del catálogo."""
    if marca in (None, ""):
        return "", None
    if not isinstance(marca, str) or not marcas.es_marca(marca):
        return None, "Marca no permitida."
    return marca, None


def _validar_color(color: object) -> str:
    if isinstance(color, str) and _RE_COLOR.match(color.strip()):
        return color.strip().lower()
    return ""


async def listar(request: Request) -> Response:
    """GET /api/etiquetas: catálogo de etiquetas.

    Filtros opcionales: `marca` (incluye las de esa marca Y las globales), `clase`,
    `activas` ("1" para excluir las ocultas).
    """
    q = request.query_params
    etiquetas = repos.listar_etiquetas(
        marca=q.get("marca") if "marca" in q else None,
        clase=q.get("clase") or None,
        solo_activas=q.get("activas") == "1",
    )
    return JSONResponse(
        {
            "etiquetas": [_etiqueta_a_dict(e) for e in etiquetas],
            "clases": list(CLASES_ETIQUETA),
            "marcas": [{"id": mid, "nombre": nombre} for mid, nombre in marcas.opciones()],
        }
    )


async def crear(request: Request) -> Response:
    """POST /api/etiquetas: crea una etiqueta. Cuerpo: `nombre` (obligatorio), `clase`,
    `marca` ('' = global), `color`."""
    datos = await leer_json(request)
    nombre = datos.get("nombre")
    if not isinstance(nombre, str) or not nombre.strip():
        return JSONResponse({"error": "La etiqueta necesita un nombre."}, status_code=400)
    nombre = nombre.strip()[:_MAX_NOMBRE]

    clase = datos.get("clase", CLASE_ETIQUETA_DEFECTO) or CLASE_ETIQUETA_DEFECTO
    if clase not in CLASES_ETIQUETA:
        return JSONResponse({"error": "Tipo de etiqueta inválido."}, status_code=400)

    marca, err = _validar_marca(datos.get("marca"))
    if err:
        return JSONResponse({"error": err}, status_code=400)

    if repos.existe_etiqueta_nombre(nombre, clase, marca):
        return JSONResponse({"error": "Ya existe una etiqueta con ese nombre."}, status_code=409)

    etiqueta = repos.crear_etiqueta(
        nombre=nombre, clase=clase, marca=marca, color=_validar_color(datos.get("color"))
    )
    return JSONResponse({"etiqueta": _etiqueta_a_dict(etiqueta)})


async def actualizar(request: Request) -> Response:
    """PATCH /api/etiquetas/{id}: edita nombre/clase/marca/color/activo (todos opcionales)."""
    etiqueta_id = request.path_params["etiqueta_id"]
    actual = repos.obtener_etiqueta(etiqueta_id)
    if actual is None:
        return JSONResponse({"error": "Esa etiqueta ya no existe."}, status_code=404)
    datos = await leer_json(request)
    campos: dict[str, object] = {}

    if "nombre" in datos:
        nombre = datos.get("nombre")
        if not isinstance(nombre, str) or not nombre.strip():
            return JSONResponse({"error": "El nombre no puede quedar vacío."}, status_code=400)
        campos["nombre"] = nombre.strip()[:_MAX_NOMBRE]
    if "clase" in datos:
        if datos["clase"] not in CLASES_ETIQUETA:
            return JSONResponse({"error": "Tipo de etiqueta inválido."}, status_code=400)
        campos["clase"] = datos["clase"]
    if "marca" in datos:
        marca, err = _validar_marca(datos.get("marca"))
        if err:
            return JSONResponse({"error": err}, status_code=400)
        campos["marca"] = marca
    if "color" in datos:
        campos["color"] = _validar_color(datos.get("color"))
    if "activo" in datos:
        campos["activo"] = bool(datos["activo"])

    if not campos:
        return JSONResponse({"error": "Indica algún campo a actualizar."}, status_code=400)

    # Revalida la unicidad si cambió algún campo del triplete (nombre, clase, marca).
    nombre_f = str(campos.get("nombre", actual["nombre"]))
    clase_f = str(campos.get("clase", actual["clase"]))
    marca_f = str(campos.get("marca", actual["marca"]))
    if repos.existe_etiqueta_nombre(nombre_f, clase_f, marca_f, excluir_id=etiqueta_id):
        return JSONResponse({"error": "Ya existe una etiqueta con ese nombre."}, status_code=409)

    etiqueta = repos.actualizar_etiqueta(etiqueta_id, campos)
    if etiqueta is None:
        return JSONResponse({"error": "Esa etiqueta ya no existe."}, status_code=404)
    return JSONResponse({"etiqueta": _etiqueta_a_dict(etiqueta)})


async def borrar(request: Request) -> Response:
    """DELETE /api/etiquetas/{id}: borra la etiqueta y sus asignaciones (cascada)."""
    etiqueta_id = request.path_params["etiqueta_id"]
    if not repos.borrar_etiqueta(etiqueta_id):
        return JSONResponse({"error": "Esa etiqueta ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Etiqueta borrada."})


RUTAS = [
    Route("/api/etiquetas", listar, methods=["GET"]),
    Route("/api/etiquetas", crear, methods=["POST"]),
    Route("/api/etiquetas/{etiqueta_id}", actualizar, methods=["PATCH"]),
    Route("/api/etiquetas/{etiqueta_id}", borrar, methods=["DELETE"]),
]
