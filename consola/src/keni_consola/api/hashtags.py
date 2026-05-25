"""API Hashtags: grupos de hashtags (CRUD) + sugerencia por IA.

El SPA gestiona grupos reutilizables de hashtags por marca y, opcionalmente, pide
sugerencias de hashtags a partir de un texto. Persistencia en SQLite (`consola.db`).

SEGURIDAD / VALIDACION (reusa las fuentes de verdad):
  - `marca` (si viene) SOLO del catalogo unico (`consola.marcas`, por su id canonico).
  - `red` (en sugerir, si viene) SOLO una red canonica (`consola.redes`).
  - Cada hashtag se normaliza con `#` inicial; SQL parametrizado en `consola.db`.
  - La sugerencia corre el MISMO runner mockeable que Skills: en tests NUNCA se llama
    a `claude` real (se parchea `skills._runner` o se inyecta un runner).
"""

from __future__ import annotations

import re
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import marcas, redes, repos
from .._http_json import leer_json
from . import skills

# Marcas validas: TODAS las del catalogo unico (por su id canonico). Mismo criterio
# que publicaciones.
_MARCAS: tuple[tuple[str, str], ...] = tuple(marcas.opciones())
_MARCAS_IDS = {m[0] for m in _MARCAS}

# Caracteres validos dentro de un hashtag (letras Unicode, digitos y _). Sin espacios.
_RE_TAG = re.compile(r"#?([\wÀ-ɏ]+)", re.UNICODE)


def _normalizar_tag(crudo: str) -> str | None:
    """Normaliza un hashtag a `#xxx` (un solo token). None si queda vacio."""
    if not isinstance(crudo, str):
        return None
    crudo = crudo.strip()
    if not crudo:
        return None
    m = _RE_TAG.search(crudo)
    if m is None:
        return None
    return f"#{m.group(1)}"


def _normalizar_lista_tags(crudas: Any) -> list[str] | None:
    """Normaliza una lista de hashtags; None si `crudas` no es una lista de strings.

    Quita vacios y duplicados (preservando el orden de aparicion).
    """
    if not isinstance(crudas, list):
        return None
    salida: list[str] = []
    vistos: set[str] = set()
    for cruda in crudas:
        if not isinstance(cruda, str):
            return None
        tag = _normalizar_tag(cruda)
        if tag is None or tag in vistos:
            continue
        vistos.add(tag)
        salida.append(tag)
    return salida


def _grupo_a_dict(grupo: dict[str, Any]) -> dict[str, Any]:
    """Serializa un grupo resolviendo el nombre legible de la marca."""
    return {
        "id": grupo["id"],
        "nombre": grupo["nombre"],
        "marca": grupo["marca"],
        "marca_nombre": marcas.etiqueta_de(grupo["marca"]) if grupo["marca"] else "",
        "hashtags": grupo["hashtags"],
    }


# --------------------------------------------------------------------------- #
# Sugerencia por IA: prompt + parseo tolerante                                 #
# --------------------------------------------------------------------------- #


def construir_prompt_sugerencia(texto: str, marca: str, red: str | None = None) -> str:
    """Prompt para pedir hashtags. El texto viaja como argumento (sin shell)."""
    destino = f" para {redes.nombre_por_id(red)}" if red else ""
    return (
        f"Sugiere entre 8 y 15 hashtags relevantes en español{destino} para la marca "
        f"{marca}, a partir del siguiente texto. Responde SOLO con los hashtags, uno por "
        f"línea, cada uno empezando por #, sin numeración ni explicaciones:\n\n{texto}"
    )


def parsear_hashtags(salida: str) -> list[str]:
    """Extrae hashtags de la salida cruda del asistente (tolerante).

    Estrategia: primero busca tokens `#xxx`; si no hay ninguno, cae a tratar cada
    LINEA no vacia como un hashtag (normalizandola). Quita duplicados preservando el
    orden. Devuelve `[]` si no hay nada utilizable.
    """
    salida = salida or ""
    encontrados = re.findall(r"#([\wÀ-ɏ]+)", salida, re.UNICODE)
    if encontrados:
        crudos = [f"#{t}" for t in encontrados]
    else:
        crudos = [linea for linea in salida.splitlines() if linea.strip()]
    salida_norm: list[str] = []
    vistos: set[str] = set()
    for crudo in crudos:
        tag = _normalizar_tag(crudo)
        if tag is None or tag in vistos:
            continue
        vistos.add(tag)
        salida_norm.append(tag)
    return salida_norm


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


async def listar(request: Request) -> Response:
    """Listado de grupos de hashtags."""
    grupos = repos.listar_grupos_hashtags()
    return JSONResponse({"grupos": [_grupo_a_dict(g) for g in grupos]})


async def crear(request: Request) -> Response:
    """Crea un grupo. `{nombre, marca?, hashtags:[..]}` -> `{grupo}`."""
    datos = await leer_json(request)
    nombre = datos.get("nombre")
    if not isinstance(nombre, str) or not nombre.strip():
        return JSONResponse({"error": "El nombre del grupo es obligatorio."}, status_code=400)
    marca = datos.get("marca", "")
    if marca is None:
        marca = ""
    if not isinstance(marca, str):
        return JSONResponse({"error": "La marca debe ser texto."}, status_code=400)
    if marca and marca not in _MARCAS_IDS:
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    crudas = datos.get("hashtags", [])
    tags = _normalizar_lista_tags(crudas)
    if tags is None:
        return JSONResponse({"error": "Los hashtags deben ser una lista de texto."}, status_code=400)
    grupo = repos.crear_grupo_hashtags(nombre.strip(), marca=marca, hashtags=tags)
    return JSONResponse({"grupo": _grupo_a_dict(grupo)})


async def actualizar(request: Request) -> Response:
    """Edicion PARCIAL `{nombre?, marca?, hashtags?}` -> `{grupo}` | 404."""
    grupo_id = request.path_params["grupo_id"]
    datos = await leer_json(request)
    campos: dict[str, Any] = {}
    if "nombre" in datos:
        nombre = datos.get("nombre")
        if not isinstance(nombre, str) or not nombre.strip():
            return JSONResponse({"error": "El nombre del grupo es obligatorio."}, status_code=400)
        campos["nombre"] = nombre.strip()
    if "marca" in datos:
        marca = datos.get("marca")
        if marca is None:
            marca = ""
        if not isinstance(marca, str):
            return JSONResponse({"error": "La marca debe ser texto."}, status_code=400)
        if marca and marca not in _MARCAS_IDS:
            return JSONResponse({"error": "Marca no permitida."}, status_code=400)
        campos["marca"] = marca
    if "hashtags" in datos:
        tags = _normalizar_lista_tags(datos.get("hashtags"))
        if tags is None:
            return JSONResponse(
                {"error": "Los hashtags deben ser una lista de texto."}, status_code=400
            )
        campos["hashtags"] = tags
    if not campos:
        return JSONResponse(
            {"error": "No hay nada que actualizar (nombre, marca o hashtags)."}, status_code=400
        )
    grupo = repos.actualizar_grupo_hashtags(grupo_id, campos)
    if grupo is None:
        return JSONResponse({"error": "Ese grupo de hashtags ya no existe."}, status_code=404)
    return JSONResponse({"grupo": _grupo_a_dict(grupo)})


async def borrar(request: Request) -> Response:
    grupo_id = request.path_params["grupo_id"]
    if not repos.borrar_grupo_hashtags(grupo_id):
        return JSONResponse({"error": "Ese grupo de hashtags ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Grupo de hashtags borrado."})


async def sugerir(request: Request) -> Response:
    """Sugiere hashtags por IA `{texto, marca, red?}` -> `{hashtags:[..]}`."""
    datos = await leer_json(request)
    texto = datos.get("texto")
    marca = datos.get("marca")
    if not isinstance(texto, str) or not texto.strip():
        return JSONResponse({"error": "Falta el texto para sugerir hashtags."}, status_code=400)
    if not isinstance(marca, str) or marca not in _MARCAS_IDS:
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    red = datos.get("red")
    if red is not None:
        if not isinstance(red, str) or not redes.es_red(red):
            return JSONResponse({"error": "Red no permitida."}, status_code=400)
    else:
        red = None

    prompt = construir_prompt_sugerencia(texto.strip(), marca, red)
    try:
        salida, _metricas = skills._runner(
            prompt, cwd=skills._cwd_skills(), timeout=skills._TIMEOUT_DEF
        )
    except skills.SkillError as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        return JSONResponse({"error": "No se pudieron sugerir hashtags."}, status_code=500)

    hashtags = parsear_hashtags(salida)
    if not hashtags:
        return JSONResponse(
            {"hashtags": [], "mensaje": "El asistente no devolvió hashtags utilizables."}
        )
    return JSONResponse({"hashtags": hashtags})


RUTAS = [
    Route("/api/hashtags", listar, methods=["GET"]),
    Route("/api/hashtags", crear, methods=["POST"]),
    Route("/api/hashtags/sugerir", sugerir, methods=["POST"]),
    Route("/api/hashtags/{grupo_id}", actualizar, methods=["PUT"]),
    Route("/api/hashtags/{grupo_id}", borrar, methods=["DELETE"]),
]
