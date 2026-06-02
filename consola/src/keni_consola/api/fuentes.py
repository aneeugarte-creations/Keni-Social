"""API del HUB de fuentes (item G): TODAS las fuentes de insumo, no solo RSS.

Convierte "Fuentes" en el lugar donde se dan de alta fuentes de cualquier `tipo`
(rss/api/galeria/idea/interna), cada una con su `config` (JSON especifico del tipo),
`prioridad` y `etiquetas`. Es ADITIVO: `fuentes_rss` sigue siendo la fuente de verdad del
Radar v1; este hub se siembra de ella (migracion idempotente en `db._sembrar_fuentes_hub_
desde_rss`) y NO la sustituye.

  - GET  /api/fuentes?tipo=         -> {fuentes:[...], agencias:[...], pendientes:[...]}
  - POST /api/fuentes               -> crea una fuente {tipo, nombre, config?, marca?,
                                       prioridad?, etiquetas?}
  - PUT  /api/fuentes/{id}          -> edita parcialmente
  - DELETE /api/fuentes/{id}        -> borra

Las AGENCIAS (Reuters/AFP, item F) se exponen como su estado HONESTO (`agencias`): cada una
disponible o "pendiente/no configurada" segun haya credencial, sin inventar nada. Validacion:
`tipo` de una allowlist, `marca` del catalogo unico, `config` un objeto JSON. Errores en
espanol; SQL parametrizado en `db`.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import agencias, marcas, repos
from .._http_json import leer_json
from ..db import _TIPOS_FUENTE

_MARCAS_IDS = {m[0] for m in marcas.opciones()}


def _validar_tipo(tipo: Any) -> tuple[str | None, str | None]:
    """Valida `tipo` contra la allowlist. `(tipo, None)` o `(None, mensaje)`."""
    if not isinstance(tipo, str) or not tipo.strip():
        return None, "El tipo de fuente es obligatorio."
    if tipo not in _TIPOS_FUENTE:
        return None, "Tipo de fuente no permitido."
    return tipo, None


def _validar_marca(marca: Any) -> tuple[str | None, str | None]:
    if marca is None:
        marca = ""
    if not isinstance(marca, str):
        return None, "La marca debe ser texto."
    if marca and marca not in _MARCAS_IDS:
        return None, "Marca no permitida."
    return marca, None


def _validar_config(valor: Any) -> tuple[dict[str, Any] | None, str | None]:
    if valor is None:
        return {}, None
    if isinstance(valor, dict):
        return valor, None
    return None, "La configuración de la fuente debe ser un objeto."


def _validar_etiquetas(valor: Any) -> tuple[list[str] | None, str | None]:
    if valor is None:
        return [], None
    if isinstance(valor, list) and all(isinstance(v, str) for v in valor):
        return [v.strip() for v in valor if v.strip()], None
    return None, "Las etiquetas deben ser una lista de texto."


def _fuente_a_dict(fuente: dict[str, Any]) -> dict[str, Any]:
    """Serializa una fuente del hub resolviendo el nombre de la marca."""
    return {
        **fuente,
        "marca_nombre": marcas.etiqueta_de(fuente["marca"]) if fuente["marca"] else "",
    }


async def listar(request: Request) -> Response:
    """`GET /api/fuentes?tipo=` -> fuentes del hub + estado de agencias + pendientes."""
    tipo = request.query_params.get("tipo") or None
    if tipo is not None and tipo not in _TIPOS_FUENTE:
        return JSONResponse({"error": "Tipo de fuente no permitido."}, status_code=400)
    fuentes = repos.listar_fuentes(tipo=tipo)
    return JSONResponse(
        {
            "fuentes": [_fuente_a_dict(f) for f in fuentes],
            "tipos": list(_TIPOS_FUENTE),
            "agencias": [agencias.estado_fuente(a) for a in ("reuters", "afp")],
            "pendientes": agencias.fuentes_pendientes(),
        }
    )


async def crear(request: Request) -> Response:
    """`POST /api/fuentes` -> crea una fuente {tipo, nombre, config?, marca?, prioridad?, etiquetas?}."""
    datos = await leer_json(request)
    tipo, error = _validar_tipo(datos.get("tipo"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    nombre = datos.get("nombre")
    if not isinstance(nombre, str) or not nombre.strip():
        return JSONResponse({"error": "El nombre de la fuente es obligatorio."}, status_code=400)
    config_obj, error = _validar_config(datos.get("config"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    marca, error = _validar_marca(datos.get("marca"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    etiquetas, error = _validar_etiquetas(datos.get("etiquetas"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    try:
        prioridad = int(datos.get("prioridad", 0) or 0)
    except (TypeError, ValueError):
        return JSONResponse({"error": "La prioridad debe ser un número."}, status_code=400)

    fuente = repos.crear_fuente(
        tipo=tipo,
        nombre=nombre.strip(),
        config=config_obj,
        marca=marca,
        prioridad=prioridad,
        etiquetas=etiquetas,
    )
    return JSONResponse({"fuente": _fuente_a_dict(fuente)})


async def actualizar(request: Request) -> Response:
    """`PUT /api/fuentes/{id}` -> edita parcialmente (tipo/nombre/config/marca/prioridad/etiquetas/activo)."""
    fuente_id = request.path_params["fuente_id"]
    if repos.obtener_fuente(fuente_id) is None:
        return JSONResponse({"error": "Esa fuente ya no existe."}, status_code=404)
    datos = await leer_json(request)
    campos: dict[str, Any] = {}
    if "tipo" in datos:
        tipo, error = _validar_tipo(datos.get("tipo"))
        if error is not None:
            return JSONResponse({"error": error}, status_code=400)
        campos["tipo"] = tipo
    if "nombre" in datos:
        nombre = datos.get("nombre")
        if not isinstance(nombre, str) or not nombre.strip():
            return JSONResponse({"error": "El nombre de la fuente es obligatorio."}, status_code=400)
        campos["nombre"] = nombre.strip()
    if "config" in datos:
        config_obj, error = _validar_config(datos.get("config"))
        if error is not None:
            return JSONResponse({"error": error}, status_code=400)
        campos["config"] = config_obj
    if "marca" in datos:
        marca, error = _validar_marca(datos.get("marca"))
        if error is not None:
            return JSONResponse({"error": error}, status_code=400)
        campos["marca"] = marca
    if "etiquetas" in datos:
        etiquetas, error = _validar_etiquetas(datos.get("etiquetas"))
        if error is not None:
            return JSONResponse({"error": error}, status_code=400)
        campos["etiquetas"] = etiquetas
    if "prioridad" in datos:
        try:
            campos["prioridad"] = int(datos.get("prioridad") or 0)
        except (TypeError, ValueError):
            return JSONResponse({"error": "La prioridad debe ser un número."}, status_code=400)
    if "activo" in datos:
        campos["activo"] = bool(datos.get("activo"))

    fuente = repos.actualizar_fuente(fuente_id, campos)
    if fuente is None:
        return JSONResponse({"error": "Esa fuente ya no existe."}, status_code=404)
    return JSONResponse({"fuente": _fuente_a_dict(fuente)})


async def borrar(request: Request) -> Response:
    fuente_id = request.path_params["fuente_id"]
    if not repos.borrar_fuente(fuente_id):
        return JSONResponse({"error": "Esa fuente ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Fuente borrada."})


RUTAS = [
    Route("/api/fuentes", listar, methods=["GET"]),
    Route("/api/fuentes", crear, methods=["POST"]),
    Route("/api/fuentes/{fuente_id}", actualizar, methods=["PUT"]),
    Route("/api/fuentes/{fuente_id}", borrar, methods=["DELETE"]),
]
