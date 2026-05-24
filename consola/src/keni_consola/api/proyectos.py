"""API Proyectos: listar carpetas, editar su CLAUDE.md y abrir el asistente.

La LOGICA de carpetas (allowlist en consola.toml) vive en `consola.proyectos`; el
lanzamiento de Claude Code en `consola.lanzador`. Este modulo solo orquesta los
endpoints JSON.

SEGURIDAD: guardar CLAUDE.md y "abrir en Claude Code" SOLO operan sobre carpetas
de la allowlist (consola.toml), resueltas por id estable. Sin shell=True. Los
errores salen como mensajes en espanol, sin tracebacks crudos.

`abrir_en_claude_code` es modulo-nivel e inyectable: `crear_app(abrir=...)` lo
reasigna; los tests pasan un mock para NO lanzar nada real.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import lanzador, proyectos
from .._http_json import leer_json

# Inyectable (ver docstring). Por defecto, la funcion real.
abrir_en_claude_code = lanzador.abrir_en_claude_code


def _proyecto_a_dict(p: proyectos.Proyecto) -> dict:
    """Serializa un proyecto con el contenido de su CLAUDE.md (o None si no aplica)."""
    claude_md = proyectos.claude_md_de(p) if (p.existe and p.tiene_claude_md) else None
    return {
        "id": p.id,
        "nombre": p.nombre,
        "ruta": str(p.ruta),
        "existe": p.existe,
        "tiene_claude_md": p.tiene_claude_md,
        "claude_md": claude_md,
    }


def _resolver_o_400(proyecto_id: object) -> proyectos.Proyecto | JSONResponse:
    """Resuelve un proyecto por id contra la allowlist; 400 si falta o no esta."""
    if not isinstance(proyecto_id, str) or not proyecto_id:
        return JSONResponse({"error": "Falta el identificador del proyecto."}, status_code=400)
    p = proyectos.proyecto_por_id(proyecto_id)
    if p is None:
        return JSONResponse({"error": "Proyecto no permitido o inexistente."}, status_code=400)
    return p


async def listar(request: Request) -> Response:
    try:
        lista = proyectos.cargar_proyectos()
    except proyectos.ConsolaConfigInvalida:
        return JSONResponse(
            {"error": "No se pudo leer la lista de carpetas guardadas. Pídele ayuda a quien configuró la consola."},
            status_code=400,
        )
    return JSONResponse({"proyectos": [_proyecto_a_dict(p) for p in lista]})


async def crear(request: Request) -> Response:
    datos = await leer_json(request)
    nombre = datos.get("nombre")
    ruta = datos.get("ruta")
    if not isinstance(nombre, str) or not isinstance(ruta, str):
        return JSONResponse({"error": "Faltan el nombre o la ruta."}, status_code=400)
    try:
        p = proyectos.anadir_proyecto(nombre, ruta)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except OSError:
        return JSONResponse(
            {"error": "No se pudo guardar la carpeta. Inténtalo de nuevo."}, status_code=400
        )
    return JSONResponse({"mensaje": f"Añadida la carpeta {p.nombre}."})


async def guardar_claude_md(request: Request) -> Response:
    proyecto_id = request.path_params["proyecto_id"]
    p = _resolver_o_400(proyecto_id)
    if isinstance(p, JSONResponse):
        return p
    datos = await leer_json(request)
    contenido = datos.get("contenido")
    if not isinstance(contenido, str):
        return JSONResponse({"error": "Falta el contenido del CLAUDE.md."}, status_code=400)
    try:
        proyectos.guardar_claude_md(p, contenido)
    except (ValueError, OSError):
        return JSONResponse(
            {"error": "No se pudo guardar. Revisa que la carpeta siga disponible."},
            status_code=400,
        )
    return JSONResponse({"mensaje": "CLAUDE.md guardado."})


async def abrir(request: Request) -> Response:
    proyecto_id = request.path_params["proyecto_id"]
    p = _resolver_o_400(proyecto_id)
    if isinstance(p, JSONResponse):
        return p
    if not p.existe:
        return JSONResponse({"error": "La carpeta del proyecto ya no existe."}, status_code=400)
    try:
        mensaje = abrir_en_claude_code(p.ruta)
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    return JSONResponse({"mensaje": mensaje})


RUTAS = [
    Route("/api/proyectos", listar, methods=["GET"]),
    Route("/api/proyectos", crear, methods=["POST"]),
    Route("/api/proyectos/{proyecto_id}/claude-md", guardar_claude_md, methods=["PUT"]),
    Route("/api/proyectos/{proyecto_id}/abrir", abrir, methods=["POST"]),
]
