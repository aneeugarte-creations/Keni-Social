"""API Tareas: gestion de tareas por proyecto (listar, crear, cambiar estado,
borrar, abrir el asistente). Persistencia en SQLite (`consola.db`, via `consola.db`).

Cada tarea referencia un PROYECTO de la allowlist compartida (`consola.proyectos`).

SEGURIDAD:
  - Una tarea SOLO puede apuntar a un proyecto presente en la allowlist (consola.toml):
    al crear se valida el id contra `consola.proyectos.proyecto_por_id`.
  - "Abrir en Claude Code" resuelve la carpeta SOLO desde la allowlist y delega en
    el lanzador compartido. Sin shell=True; sin rutas crudas del cliente.
  - SQL parametrizado en `consola.db` (nunca f-strings con datos).

El wrapper `abrir_tarea_en_claude_code` es modulo-nivel para que los tests lo
parcheen (mockeen) y NO se lance nada real. Por defecto reusa
`consola.lanzador.abrir_en_claude_code` SIN editarlo.
"""

from __future__ import annotations

from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import db, lanzador, proyectos
from .._http_json import leer_json


def abrir_tarea_en_claude_code(ruta: Path, detalle: str = "") -> str:
    """Abre el asistente (Claude Code) en la carpeta de la tarea.

    `detalle` viaja como prompt inicial; sin detalle, abre el asistente sin prompt.
    """
    return lanzador.abrir_en_claude_code(ruta, prompt=detalle or None)


def _nombres_proyecto() -> dict[str, proyectos.Proyecto]:
    """Mapa id->Proyecto de la allowlist (vacio si el consola.toml esta roto)."""
    try:
        return {p.id: p for p in proyectos.cargar_proyectos()}
    except proyectos.ConsolaConfigInvalida:
        return {}


def _tarea_a_dict(tarea: dict, por_id: dict[str, proyectos.Proyecto]) -> dict:
    """Serializa una tarea, resolviendo el nombre legible de su proyecto."""
    proyecto = por_id.get(tarea["proyecto"])
    nombre = proyecto.nombre if proyecto is not None else ""
    return {
        "id": tarea["id"],
        "proyecto": tarea["proyecto"],
        "proyecto_nombre": nombre,
        "titulo": tarea["titulo"],
        "detalle": tarea["detalle"],
        "estado": tarea["estado"],
        "fecha": tarea["fecha"],
    }


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


async def listar(request: Request) -> Response:
    por_id = _nombres_proyecto()
    tareas = db.listar_tareas()
    return JSONResponse(
        {
            "tareas": [_tarea_a_dict(t, por_id) for t in tareas],
            "proyectos": [
                {"id": p.id, "nombre": p.nombre, "existe": p.existe} for p in por_id.values()
            ],
        }
    )


async def crear(request: Request) -> Response:
    datos = await leer_json(request)
    proyecto_id = datos.get("proyecto")
    titulo = datos.get("titulo")
    detalle = datos.get("detalle", "")
    if not isinstance(titulo, str) or not titulo.strip():
        return JSONResponse({"error": "La tarea necesita un titulo."}, status_code=400)
    if not isinstance(proyecto_id, str) or not proyecto_id.strip():
        return JSONResponse({"error": "La tarea necesita un proyecto."}, status_code=400)
    if not isinstance(detalle, str):
        detalle = ""
    # Allowlist: solo proyectos configurados.
    if proyectos.proyecto_por_id(proyecto_id) is None:
        return JSONResponse({"error": "Proyecto no permitido o inexistente."}, status_code=400)

    tarea = db.crear_tarea(proyecto_id, titulo.strip(), detalle.strip())
    return JSONResponse({"tarea": _tarea_a_dict(tarea, _nombres_proyecto())})


async def actualizar(request: Request) -> Response:
    tarea_id = request.path_params["tarea_id"]
    datos = await leer_json(request)
    estado = datos.get("estado")
    if estado not in db.ESTADOS_TAREA:
        validos = " o ".join(f'"{e}"' for e in db.ESTADOS_TAREA)
        return JSONResponse({"error": f"Estado inválido. Usa {validos}."}, status_code=400)
    tarea = db.actualizar_estado_tarea(tarea_id, estado)
    if tarea is None:
        return JSONResponse({"error": "La tarea ya no existe."}, status_code=404)
    return JSONResponse({"tarea": _tarea_a_dict(tarea, _nombres_proyecto())})


async def borrar(request: Request) -> Response:
    tarea_id = request.path_params["tarea_id"]
    if not db.borrar_tarea(tarea_id):
        return JSONResponse({"error": "La tarea ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Tarea borrada."})


async def abrir(request: Request) -> Response:
    tarea_id = request.path_params["tarea_id"]
    tarea = db.obtener_tarea(tarea_id)
    if tarea is None:
        return JSONResponse({"error": "La tarea ya no existe."}, status_code=400)
    # Allowlist: la carpeta solo se resuelve desde consola.proyectos por id estable.
    p = proyectos.proyecto_por_id(tarea["proyecto"])
    if p is None:
        return JSONResponse(
            {"error": "El proyecto de esta tarea ya no está configurado."}, status_code=400
        )
    if not p.existe:
        return JSONResponse({"error": "La carpeta del proyecto ya no existe."}, status_code=400)
    try:
        mensaje = abrir_tarea_en_claude_code(p.ruta, tarea["detalle"])
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    return JSONResponse({"mensaje": mensaje})


RUTAS = [
    Route("/api/tareas", listar, methods=["GET"]),
    Route("/api/tareas", crear, methods=["POST"]),
    Route("/api/tareas/{tarea_id}", actualizar, methods=["PATCH"]),
    Route("/api/tareas/{tarea_id}", borrar, methods=["DELETE"]),
    Route("/api/tareas/{tarea_id}/abrir", abrir, methods=["POST"]),
]
