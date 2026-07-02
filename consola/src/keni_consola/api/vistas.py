"""API Vistas guardadas: presets nombrados del dashboard de Analíticas.

Una vista guardada congela la configuración de vista (`config`, el `VistaConfig` de la capa
de presentación: red en foco, secciones, columnas) MÁS la marca (id canónico; '' = todas) y
el periodo (token de `?periodo=`), para recuperar de un clic un corte completo (p. ej.
"Claro Sports IG dirección").

Son COMPARTIDAS por el equipo (piloto AMX): cualquiera con sesión las ve, aplica y borra;
`autor_*` queda como atribución (quién la creó), no controla el acceso. Este módulo solo es
la frontera HTTP; la persistencia vive en `repos`/`db_vistas`.
"""

from __future__ import annotations

from typing import Any

from keni_shared import marcas
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import repos
from .._http_json import leer_json
from ..seguridad import autor_de_peticion

_MARCAS_IDS = {mid for mid, _ in marcas.opciones()}


def _con_nombre(vista: dict[str, Any]) -> dict[str, Any]:
    """Añade `marca_nombre` (etiqueta legible; '' si la vista es de "todas")."""
    mid = vista.get("marca") or ""
    nombre = next((et for cid, et in marcas.opciones() if cid == mid), "") if mid else ""
    return {**vista, "marca_nombre": nombre}


def _leer_marca(valor: Any) -> tuple[str | None, str | None]:
    """Marca de la vista: '' (todas) o un id canónico permitido. Devuelve (marca, error)."""
    if valor is None:
        return "", None
    if not isinstance(valor, str):
        return None, "La marca debe ser un id de texto."
    if valor and valor not in _MARCAS_IDS:
        return None, "Marca no permitida."
    return valor, None


async def listar_vistas(request: Request) -> Response:
    """Vistas guardadas (compartidas), opcionalmente filtradas por `?marca=`."""
    marca = request.query_params.get("marca")
    if marca is not None:
        marca, error = _leer_marca(marca)
        if error is not None:
            return JSONResponse({"error": error}, status_code=400)
    return JSONResponse(
        {"vistas": [_con_nombre(v) for v in repos.listar_vistas(marca=marca)]}
    )


async def crear_vista(request: Request) -> Response:
    """Crea una vista: `{nombre, marca?, periodo, config}`. La atribución sale de la sesión."""
    datos = await leer_json(request)
    nombre = datos.get("nombre")
    if not isinstance(nombre, str) or not nombre.strip():
        return JSONResponse({"error": "Ponle un nombre a la vista."}, status_code=400)
    marca, error = _leer_marca(datos.get("marca"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    periodo = datos.get("periodo")
    if not isinstance(periodo, str) or not periodo:
        return JSONResponse({"error": "Falta el periodo de la vista."}, status_code=400)
    config = datos.get("config")
    if not isinstance(config, dict):
        return JSONResponse(
            {"error": "La configuración de la vista debe ser un objeto."}, status_code=400
        )
    autor = autor_de_peticion(request) or {}
    vista = repos.crear_vista(
        nombre=nombre.strip(),
        marca=marca,
        periodo=periodo,
        config=config,
        autor_id=autor.get("id", ""),
        autor_nombre=autor.get("usuario", ""),
    )
    return JSONResponse({"vista": _con_nombre(vista)}, status_code=201)


async def actualizar_vista(request: Request) -> Response:
    """Edición parcial: `{nombre?, marca?, periodo?, config?}`; 404 si no existe."""
    vista_id = request.path_params["vista_id"]
    datos = await leer_json(request)
    campos: dict[str, Any] = {}
    if "nombre" in datos:
        if not isinstance(datos["nombre"], str) or not datos["nombre"].strip():
            return JSONResponse({"error": "Ponle un nombre a la vista."}, status_code=400)
        campos["nombre"] = datos["nombre"].strip()
    if "marca" in datos:
        marca, error = _leer_marca(datos.get("marca"))
        if error is not None:
            return JSONResponse({"error": error}, status_code=400)
        campos["marca"] = marca
    if "periodo" in datos:
        if not isinstance(datos["periodo"], str) or not datos["periodo"]:
            return JSONResponse({"error": "Falta el periodo de la vista."}, status_code=400)
        campos["periodo"] = datos["periodo"]
    if "config" in datos:
        if not isinstance(datos["config"], dict):
            return JSONResponse(
                {"error": "La configuración de la vista debe ser un objeto."},
                status_code=400,
            )
        campos["config"] = datos["config"]
    vista = repos.actualizar_vista(vista_id, campos)
    if vista is None:
        return JSONResponse({"error": "Esa vista ya no existe."}, status_code=404)
    return JSONResponse({"vista": _con_nombre(vista)})


async def eliminar_vista(request: Request) -> Response:
    """Borra una vista; 404 si no existe."""
    if not repos.borrar_vista(request.path_params["vista_id"]):
        return JSONResponse({"error": "Esa vista ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Vista borrada."})


RUTAS = [
    Route("/api/metricas/vistas", listar_vistas, methods=["GET"]),
    Route("/api/metricas/vistas", crear_vista, methods=["POST"]),
    Route("/api/metricas/vistas/{vista_id}", actualizar_vista, methods=["PUT"]),
    Route("/api/metricas/vistas/{vista_id}", eliminar_vista, methods=["DELETE"]),
]
