"""API Tareas: TABLERO de pendientes COMPARTIDO del equipo (#145, F5).

Listar, crear, asignar responsable, cambiar estado, poner enlace de accion, borrar y abrir
el asistente. Persistencia en SQLite (`consola.db`). El tablero es UNICO y compartido: todo
el equipo autenticado lo ve y lo edita; cada tarea lleva su propia identidad (autor = quien
la creo, responsable = a quien se le asigna).

Cada tarea referencia un PROYECTO de la allowlist compartida (`consola.proyectos`); ese
proyecto ES el acotado por marca/proyecto (se puede filtrar por `?proyecto=<id>`).

SEGURIDAD:
  - Multiusuario: el middleware ya autentica (sesion o token de mantenimiento) y deja el
    usuario en `request.state.usuario`. Esta API no relaja ese control; cualquier usuario
    autenticado ve y edita el tablero compartido (el equipo gestiona sus pendientes).
  - Una tarea SOLO puede apuntar a un proyecto presente en la allowlist (consola.toml):
    al crear se valida el id contra `consola.proyectos.proyecto_por_id`.
  - El RESPONSABLE solo puede ser un usuario REAL de la consola (`auth.obtener_usuario_por_id`);
    nunca se confia en el nombre que mande el cliente.
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

from .. import auth, lanzador, proyectos, repos
from .._http_json import leer_json
from ..seguridad import autor_de_peticion

# Longitud maxima del enlace de accion (defensa: evita strings absurdos en la BD).
_MAX_ENLACE = 2000


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
        # Atribucion por usuario (#130 Fase 1): quien creo la tarea. "" en tareas
        # legadas/anonimas (la UI lo muestra como "desconocido").
        "autor_id": tarea.get("autor_id", "") or "",
        "autor_nombre": tarea.get("autor_nombre", "") or "",
        # Tablero compartido (#145 F5): a quien se le asigno y enlace de accion.
        # "" = sin asignar / sin enlace (la UI lo muestra como "sin asignar").
        "responsable_id": tarea.get("responsable_id", "") or "",
        "responsable_nombre": tarea.get("responsable_nombre", "") or "",
        "enlace": tarea.get("enlace", "") or "",
    }


def _usuarios_asignables() -> list[dict[str, str]]:
    """Lista de usuarios reales (id + nombre) para el selector de responsable.

    Reusa la lista de usuarios de la consola (`auth.listar_usuarios`, misma fuente que
    /api/usuarios). Solo expone id y nombre: el selector no necesita rol ni mas estado.
    """
    return [{"id": u["id"], "usuario": u["usuario"]} for u in auth.listar_usuarios()]


def _resolver_responsable(responsable_id: object) -> tuple[dict[str, str] | None, bool]:
    """Resuelve un `responsable_id` del cliente a `{"id", "usuario"}`.

    Devuelve `(responsable, valido)`:
      - `("" / None)` -> `(None, True)`: sin asignar (se permite explicitamente).
      - id de un usuario REAL -> `({"id", "usuario"}, True)`.
      - cualquier otra cosa (id inexistente / tipo raro) -> `(None, False)`: invalido.
    """
    if responsable_id in (None, ""):
        return None, True
    if not isinstance(responsable_id, str):
        return None, False
    usuario = auth.obtener_usuario_por_id(responsable_id)
    if usuario is None:
        return None, False
    return {"id": usuario["id"], "usuario": usuario["usuario"]}, True


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


async def listar(request: Request) -> Response:
    """GET /api/tareas[?proyecto=<id>]: tablero compartido del equipo.

    Devuelve, ademas de las tareas y los proyectos de la allowlist, la lista de usuarios
    asignables (para el selector de responsable). Con `?proyecto=<id>` acota a un proyecto
    (acotado por marca/proyecto, #145 F5).
    """
    por_id = _nombres_proyecto()
    proyecto_filtro = request.query_params.get("proyecto") or None
    # Solo se filtra por un proyecto de la allowlist; un id ajeno devuelve vacio sin error.
    if proyecto_filtro is not None and proyecto_filtro not in por_id:
        tareas: list[dict] = []
    else:
        tareas = repos.listar_tareas(proyecto_filtro)
    return JSONResponse(
        {
            "tareas": [_tarea_a_dict(t, por_id) for t in tareas],
            "proyectos": [
                {"id": p.id, "nombre": p.nombre, "existe": p.existe} for p in por_id.values()
            ],
            "usuarios": _usuarios_asignables(),
        }
    )


async def crear(request: Request) -> Response:
    datos = await leer_json(request)
    proyecto_id = datos.get("proyecto")
    titulo = datos.get("titulo")
    detalle = datos.get("detalle", "")
    enlace = datos.get("enlace", "")
    if not isinstance(titulo, str) or not titulo.strip():
        return JSONResponse({"error": "La tarea necesita un titulo."}, status_code=400)
    if not isinstance(proyecto_id, str) or not proyecto_id.strip():
        return JSONResponse({"error": "La tarea necesita un proyecto."}, status_code=400)
    if not isinstance(detalle, str):
        detalle = ""
    if not isinstance(enlace, str):
        enlace = ""
    enlace = enlace.strip()
    if len(enlace) > _MAX_ENLACE:
        return JSONResponse({"error": "El enlace es demasiado largo."}, status_code=400)
    # Allowlist: solo proyectos configurados.
    if proyectos.proyecto_por_id(proyecto_id) is None:
        return JSONResponse({"error": "Proyecto no permitido o inexistente."}, status_code=400)
    # El responsable, si se manda, debe ser un usuario REAL (no se confia en el cliente).
    responsable, valido = _resolver_responsable(datos.get("responsable_id"))
    if not valido:
        return JSONResponse({"error": "El responsable no es un usuario válido."}, status_code=400)

    tarea = repos.crear_tarea(
        proyecto_id,
        titulo.strip(),
        detalle.strip(),
        autor=autor_de_peticion(request),
        responsable=responsable,
        enlace=enlace,
    )
    return JSONResponse({"tarea": _tarea_a_dict(tarea, _nombres_proyecto())})


async def actualizar(request: Request) -> Response:
    """PATCH /api/tareas/{id}: cambia estado, responsable y/o enlace de accion.

    Cada campo es opcional; se aplican solo los presentes. Retrocompatible con el cliente
    que solo manda `{"estado": ...}`.
    """
    tarea_id = request.path_params["tarea_id"]
    datos = await leer_json(request)
    campos: dict[str, object] = {}

    if "estado" in datos:
        estado = datos.get("estado")
        if estado not in repos.ESTADOS_TAREA:
            validos = " o ".join(f'"{e}"' for e in repos.ESTADOS_TAREA)
            return JSONResponse({"error": f"Estado inválido. Usa {validos}."}, status_code=400)
        campos["estado"] = estado

    if "responsable_id" in datos:
        responsable, valido = _resolver_responsable(datos.get("responsable_id"))
        if not valido:
            return JSONResponse(
                {"error": "El responsable no es un usuario válido."}, status_code=400
            )
        # Sin asignar limpia ambas columnas; asignado las fija a la par.
        campos["responsable_id"] = responsable["id"] if responsable else ""
        campos["responsable_nombre"] = responsable["usuario"] if responsable else ""

    if "enlace" in datos:
        enlace = datos.get("enlace")
        if not isinstance(enlace, str):
            enlace = ""
        enlace = enlace.strip()
        if len(enlace) > _MAX_ENLACE:
            return JSONResponse({"error": "El enlace es demasiado largo."}, status_code=400)
        campos["enlace"] = enlace

    if not campos:
        return JSONResponse(
            {"error": "Indica un estado, un responsable o un enlace."}, status_code=400
        )

    tarea = repos.actualizar_tarea(tarea_id, campos)
    if tarea is None:
        return JSONResponse({"error": "La tarea ya no existe."}, status_code=404)
    return JSONResponse({"tarea": _tarea_a_dict(tarea, _nombres_proyecto())})


async def borrar(request: Request) -> Response:
    tarea_id = request.path_params["tarea_id"]
    if not repos.borrar_tarea(tarea_id):
        return JSONResponse({"error": "La tarea ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Tarea borrada."})


async def abrir(request: Request) -> Response:
    tarea_id = request.path_params["tarea_id"]
    tarea = repos.obtener_tarea(tarea_id)
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
