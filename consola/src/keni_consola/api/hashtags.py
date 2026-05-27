"""API Hashtags: grupos de hashtags (CRUD) + sugerencia por IA.

El SPA gestiona grupos reutilizables de hashtags por marca y, opcionalmente, pide
sugerencias de hashtags a partir de un texto. Persistencia en SQLite (`consola.db`).

SEGURIDAD / VALIDACION (reusa las fuentes de verdad):
  - `marca` (si viene) SOLO del catalogo unico (`consola.marcas`, por su id canonico).
  - `red` (en sugerir, si viene) SOLO una red canonica (`consola.redes`).
  - Cada hashtag se normaliza con `#` inicial; SQL parametrizado en `consola.db`.
  - La sugerencia corre como TRABAJO de IA en background (`consola.generaciones`): el
    endpoint responde `{generacion}` y el frontend sondea hasta `resultado={hashtags}`.
    En tests NUNCA se llama a `claude` real (se inyecta `lanzar_generacion`).
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import generaciones, marcas, redes, repos
from .._http_json import leer_json
from ..dominio import hashtags as dom_hashtags
from ..dominio import jobspec
from ..seguridad import autor_de_peticion
from . import skills

# Marcas validas: TODAS las del catalogo unico (por su id canonico). Mismo criterio
# que publicaciones.
_MARCAS: tuple[tuple[str, str], ...] = tuple(marcas.opciones())
_MARCAS_IDS = {m[0] for m in _MARCAS}

# Prompt + parseo de la sugerencia viven AHORA en el dominio (`dominio.hashtags`), para
# que el WORKER de generacion los reconstruya sin importar de `api/` (#130 Fase 2). Aqui
# se reexportan por compat de referencias (el dominio del job apunta al mismo parseo).
_normalizar_tag = dom_hashtags.normalizar_tag


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


# Sugerencia por IA: el prompt + el parseo viven en `dominio.hashtags` (para el worker).
# Se reexportan aqui para no romper los call sites (tests/otros modulos los referencian).
construir_prompt_sugerencia = dom_hashtags.construir_prompt_sugerencia
parsear_hashtags = dom_hashtags.parsear_hashtags


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
    """Sugiere hashtags por IA, EN SEGUNDO PLANO `{texto, marca, red?}` -> `{generacion}`.

    Lanza un trabajo de claude (tipo "hashtags") que no bloquea; el frontend sondea
    `GET /api/generaciones/{id}` y, al completarse, recoge `resultado = {hashtags:[..]}`.
    """
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

    def procesar(salida: str, _metricas: object) -> dict[str, object]:
        return {"hashtags": parsear_hashtags(salida)}

    # Atribucion por usuario (#130 Fase 1): la generacion la dispara el usuario actual.
    autor = autor_de_peticion(request) or {}
    gen = generaciones.crear(
        {
            "tipo": "hashtags",
            "marca": marca,
            "etiqueta": f"Hashtags · {marcas.etiqueta_de(marca)}",
            "autor_id": autor.get("id", ""),
            "autor_nombre": autor.get("usuario", ""),
        }
    )
    # ENCOLA y devuelve de inmediato (#130 Fase 2): el worker reconstruye el parseo de
    # hashtags desde el `spec` y corre `claude -p` (con #137). `procesar` solo lo usa un
    # lanzador inyectado (tests). El cwd lo resuelve el worker (jobspec.cwd, via env vars).
    spec = jobspec.construir(prompt=prompt, procesar=jobspec.construir_hashtags())
    try:
        generaciones.encolar_job_claude(
            gen["id"], prompt=prompt, cwd=skills._cwd_skills(), procesar=procesar, spec=spec
        )
    except generaciones.ColaLlenaError:
        # Cola al tope (#137): marcamos el registro y RE-LANZAMOS para que el manejador
        # central responda 429 (backpressure) en vez de un error generico.
        generaciones.actualizar(
            gen["id"],
            {"estado": generaciones.ESTADO_ERROR, "motivo": generaciones.MOTIVO_COLA_LLENA,
             "error": "Hay demasiadas generaciones en curso; inténtalo en unos segundos.",
             "fecha_fin": generaciones.ahora_iso()},
        )
        raise
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo; reflejamos error en el registro
        generaciones.actualizar(
            gen["id"],
            {"estado": generaciones.ESTADO_ERROR, "error": "No se pudieron sugerir hashtags.",
             "fecha_fin": generaciones.ahora_iso()},
        )
    return JSONResponse({"generacion": generaciones.obtener(gen["id"]) or gen})


RUTAS = [
    Route("/api/hashtags", listar, methods=["GET"]),
    Route("/api/hashtags", crear, methods=["POST"]),
    Route("/api/hashtags/sugerir", sugerir, methods=["POST"]),
    Route("/api/hashtags/{grupo_id}", actualizar, methods=["PUT"]),
    Route("/api/hashtags/{grupo_id}", borrar, methods=["DELETE"]),
]
