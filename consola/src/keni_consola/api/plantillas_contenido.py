"""API Plantillas de CONTENIDO: plantillas reutilizables por TIPO de nota recurrente.

A diferencia de `api/plantillas.py` (un texto de copy PLANO por marca/red), aqui una
plantilla modela un TIPO de nota recurrente (p.ej. "gol", "alineacion", "efeméride"):
una ESTRUCTURA de cuerpo con marcadores `{{variable}}` mas la lista DECLARADA de esas
variables. Al armar una pieza, el equipo elige la plantilla, rellena las variables y el
endpoint `aplicar` devuelve el copy base ya compuesto. Nada se publica aqui (eso es
Metricool): es un ACTIVO reutilizable que acelera crear piezas.

Persistencia en Postgres (`repos` -> `db.py`). Las `variables` se guardan como JSON
(lista de `{clave, etiqueta, ejemplo}`); la API serializa/valida, la BD solo almacena.

SEGURIDAD / VALIDACION (reusa las fuentes de verdad):
  - `nombre` y `estructura` obligatorios (no vacios).
  - `marca` (si viene) SOLO del catalogo unico (`consola.marcas`).
  - `red` (si viene) SOLO una red canonica (`consola.redes`).
  - `clave` de cada variable: identificador simple `[a-zA-Z0-9_]` (lo que se sustituye).
  - SQL parametrizado en `db.py`; errores en espanol, sin tracebacks crudos.
"""

from __future__ import annotations

import json
import re
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import marcas, redes, repos
from .._http_json import leer_json
from ..seguridad import autor_de_peticion

# Marcas validas: TODAS las del catalogo unico (por su id canonico). Mismo criterio que
# `api/plantillas.py` y `api/publicaciones.py`.
_MARCAS_IDS = {m[0] for m in marcas.opciones()}

# Clave de variable: identificador simple (lo que se sustituye en `{{clave}}`).
_RE_CLAVE = re.compile(r"^[a-zA-Z0-9_]{1,40}$")

# Marcador en la estructura: `{{ clave }}` con espacios opcionales.
_RE_MARCADOR = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

# Limites defensivos (mismo espiritu que el resto de la consola: textos acotados).
_MAX_ESTRUCTURA = 8000
_MAX_VARIABLES = 50


def _normalizar_variables(crudo: Any) -> tuple[list[dict[str, str]] | None, str | None]:
    """Valida/normaliza la lista de variables declaradas. `(lista, None)` o `(None, msg)`.

    Cada variable es `{clave, etiqueta?, ejemplo?}`. `clave` es obligatoria y unica.
    """
    if crudo is None:
        return [], None
    if not isinstance(crudo, list):
        return None, "Las variables deben ser una lista."
    if len(crudo) > _MAX_VARIABLES:
        return None, f"Demasiadas variables (máximo {_MAX_VARIABLES})."
    salida: list[dict[str, str]] = []
    vistas: set[str] = set()
    for v in crudo:
        if not isinstance(v, dict):
            return None, "Cada variable debe ser un objeto {clave, etiqueta, ejemplo}."
        clave = v.get("clave")
        if not isinstance(clave, str) or not _RE_CLAVE.match(clave):
            return None, "La clave de una variable debe ser letras, números o guion bajo."
        if clave in vistas:
            return None, f"La variable «{clave}» está repetida."
        vistas.add(clave)
        etiqueta = v.get("etiqueta", "")
        ejemplo = v.get("ejemplo", "")
        if not isinstance(etiqueta, str) or not isinstance(ejemplo, str):
            return None, "La etiqueta y el ejemplo de una variable deben ser texto."
        salida.append({"clave": clave, "etiqueta": etiqueta, "ejemplo": ejemplo})
    return salida, None


def _cargar_variables(crudo: str) -> list[dict[str, str]]:
    """Deserializa el JSON de variables guardado; lista vacia si esta corrupto."""
    try:
        datos = json.loads(crudo or "[]")
    except (ValueError, TypeError):
        return []
    return datos if isinstance(datos, list) else []


def _plantilla_a_dict(p: dict[str, Any]) -> dict[str, Any]:
    """Serializa una plantilla resolviendo nombres legibles y deserializando variables."""
    return {
        "id": p["id"],
        "nombre": p["nombre"],
        "tipo_nota": p["tipo_nota"],
        "descripcion": p["descripcion"],
        "marca": p["marca"],
        "marca_nombre": marcas.etiqueta_de(p["marca"]) if p["marca"] else "",
        "red": p["red"],
        "red_nombre": redes.nombre_por_id(p["red"]) if p["red"] else "",
        "estructura": p["estructura"],
        "variables": _cargar_variables(p["variables"]),
        "activo": bool(p["activo"]),
        "autor_nombre": p.get("autor_nombre", ""),
        "creado": p.get("creado", ""),
        "actualizado": p.get("actualizado", ""),
    }


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


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


async def listar(request: Request) -> Response:
    """Listado de plantillas de contenido. `?marca=&tipo=&solo_activas=1` filtran."""
    qp = request.query_params
    marca = qp.get("marca") or None
    tipo = qp.get("tipo") or None
    solo_activas = qp.get("solo_activas") in ("1", "true", "si")
    plantillas = repos.listar_plantillas_contenido(
        marca=marca, tipo_nota=tipo, solo_activas=solo_activas
    )
    return JSONResponse({"plantillas": [_plantilla_a_dict(p) for p in plantillas]})


async def crear(request: Request) -> Response:
    """Crea una plantilla `{nombre, estructura, tipo_nota?, descripcion?, marca?, red?, variables?}`."""
    datos = await leer_json(request)
    nombre = datos.get("nombre")
    if not isinstance(nombre, str) or not nombre.strip():
        return JSONResponse({"error": "El nombre de la plantilla es obligatorio."}, status_code=400)
    estructura = datos.get("estructura")
    if not isinstance(estructura, str) or not estructura.strip():
        return JSONResponse({"error": "La estructura de la plantilla es obligatoria."}, status_code=400)
    if len(estructura) > _MAX_ESTRUCTURA:
        return JSONResponse({"error": "La estructura es demasiado larga."}, status_code=400)
    marca, error = _validar_marca(datos.get("marca", ""))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    red, error = _validar_red(datos.get("red", ""))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    variables, error = _normalizar_variables(datos.get("variables"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    tipo_nota = datos.get("tipo_nota", "")
    descripcion = datos.get("descripcion", "")
    if not isinstance(tipo_nota, str) or not isinstance(descripcion, str):
        return JSONResponse({"error": "El tipo de nota y la descripción deben ser texto."}, status_code=400)

    autor = autor_de_peticion(request) or {}
    plantilla = repos.crear_plantilla_contenido(
        nombre=nombre.strip(),
        tipo_nota=tipo_nota.strip(),
        descripcion=descripcion,
        marca=marca,
        red=red,
        estructura=estructura,
        variables=json.dumps(variables, ensure_ascii=False),
        autor=autor,
    )
    return JSONResponse({"plantilla": _plantilla_a_dict(plantilla)})


async def actualizar(request: Request) -> Response:
    """Edicion PARCIAL `{nombre?, tipo_nota?, descripcion?, marca?, red?, estructura?, variables?, activo?}`."""
    plantilla_id = request.path_params["plantilla_id"]
    datos = await leer_json(request)
    campos: dict[str, Any] = {}
    if "nombre" in datos:
        nombre = datos.get("nombre")
        if not isinstance(nombre, str) or not nombre.strip():
            return JSONResponse({"error": "El nombre de la plantilla es obligatorio."}, status_code=400)
        campos["nombre"] = nombre.strip()
    if "estructura" in datos:
        estructura = datos.get("estructura")
        if not isinstance(estructura, str) or not estructura.strip():
            return JSONResponse({"error": "La estructura de la plantilla es obligatoria."}, status_code=400)
        if len(estructura) > _MAX_ESTRUCTURA:
            return JSONResponse({"error": "La estructura es demasiado larga."}, status_code=400)
        campos["estructura"] = estructura
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
    if "variables" in datos:
        variables, error = _normalizar_variables(datos.get("variables"))
        if error is not None:
            return JSONResponse({"error": error}, status_code=400)
        campos["variables"] = json.dumps(variables, ensure_ascii=False)
    for clave in ("tipo_nota", "descripcion"):
        if clave in datos:
            valor = datos.get(clave)
            if not isinstance(valor, str):
                return JSONResponse({"error": f"El campo «{clave}» debe ser texto."}, status_code=400)
            campos[clave] = valor.strip() if clave == "tipo_nota" else valor
    if "activo" in datos:
        campos["activo"] = bool(datos.get("activo"))
    if not campos:
        return JSONResponse({"error": "No hay nada que actualizar."}, status_code=400)

    plantilla = repos.actualizar_plantilla_contenido(plantilla_id, campos)
    if plantilla is None:
        return JSONResponse({"error": "Esa plantilla ya no existe."}, status_code=404)
    return JSONResponse({"plantilla": _plantilla_a_dict(plantilla)})


async def borrar(request: Request) -> Response:
    plantilla_id = request.path_params["plantilla_id"]
    if not repos.borrar_plantilla_contenido(plantilla_id):
        return JSONResponse({"error": "Esa plantilla ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Plantilla borrada."})


async def aplicar(request: Request) -> Response:
    """Rellena la estructura de una plantilla con los `valores` dados -> `{copy, faltan}`.

    Body: `{"valores": {"clave": "texto", ...}}`. Sustituye cada `{{clave}}` por su valor;
    las claves sin valor se listan en `faltan` y se dejan tal cual (la UI las resalta). El
    render se hace EN SERVIDOR para que la sustitucion sea la fuente de verdad.
    """
    plantilla_id = request.path_params["plantilla_id"]
    plantilla = repos.obtener_plantilla_contenido(plantilla_id)
    if plantilla is None:
        return JSONResponse({"error": "Esa plantilla ya no existe."}, status_code=404)
    datos = await leer_json(request)
    valores = datos.get("valores", {})
    if not isinstance(valores, dict):
        return JSONResponse({"error": "Los valores deben ser un objeto {clave: texto}."}, status_code=400)

    faltan: list[str] = []

    def _sustituir(match: re.Match[str]) -> str:
        clave = match.group(1)
        valor = valores.get(clave)
        if isinstance(valor, str) and valor != "":
            return valor
        if clave not in faltan:
            faltan.append(clave)
        return match.group(0)  # deja el marcador visible

    copy = _RE_MARCADOR.sub(_sustituir, plantilla["estructura"])
    return JSONResponse({"copy": copy, "faltan": faltan})


RUTAS = [
    Route("/api/plantillas-contenido", listar, methods=["GET"]),
    Route("/api/plantillas-contenido", crear, methods=["POST"]),
    Route("/api/plantillas-contenido/{plantilla_id}", actualizar, methods=["PUT"]),
    Route("/api/plantillas-contenido/{plantilla_id}", borrar, methods=["DELETE"]),
    Route("/api/plantillas-contenido/{plantilla_id}/aplicar", aplicar, methods=["POST"]),
]
