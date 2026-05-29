"""API Tareas: TABLERO de pendientes COMPARTIDO del equipo (#145, F5 + unificacion).

Listar, crear, asignar responsable, cambiar estado, poner enlace de accion, borrar y abrir
el asistente. Persistencia en SQLite (`consola.db`). El tablero es UNICO y compartido: todo
el equipo autenticado lo ve y lo edita; cada tarea lleva su propia identidad (autor = quien
la creo, responsable = a quien se le asigna).

Unificacion de pendientes: un pendiente puede ser (a) cobertura de un evento de la rota
(`evento_id` referencia un `rota_eventos`) o (b) tarea libre con responsable. El PROYECTO
de la allowlist es OPCIONAL: una tarea libre puede no estar atada a ningun proyecto (en
ese caso "abrir en Claude Code" responde 400). Ademas, GET devuelve `eventos_sin_cubrir`:
eventos de la rota de esta semana y la siguiente cuyo turno no tiene miembro asignado
(pendientes IMPLICITOS) para que la UI los muestre arriba.

SEGURIDAD:
  - Multiusuario: el middleware ya autentica (sesion o token de mantenimiento) y deja el
    usuario en `request.state.usuario`. Esta API no relaja ese control; cualquier usuario
    autenticado ve y edita el tablero compartido (el equipo gestiona sus pendientes).
  - Si la tarea LLEVA proyecto, debe estar en la allowlist (consola.toml): al crear se
    valida el id contra `consola.proyectos.proyecto_por_id`. Vacio se permite (tarea libre).
  - Si la tarea LLEVA `evento_id`, el evento debe existir en `rota_eventos` (no se confia
    en ids inventados desde el cliente).
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

from datetime import date, timedelta
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
    """Serializa una tarea, resolviendo el nombre legible de su proyecto y su evento.

    `proyecto_existe` (bool): si el id del proyecto sigue en la allowlist Y la carpeta
    existe en disco. La UI lo usa para decidir si "abrir en Claude Code" es viable.

    Si la tarea lleva `evento_id`, hidrata `evento_titulo`, `evento_fecha`, `evento_hora`
    y `evento_tipo_cobertura` (consulta `rota_eventos`). Si el evento se borro despues,
    los campos hidratados quedan "" (pero `evento_id` se conserva en la tarea).
    """
    proyecto = por_id.get(tarea["proyecto"])
    nombre = proyecto.nombre if proyecto is not None else ""
    proyecto_existe = proyecto is not None and proyecto.existe

    evento_id = tarea.get("evento_id", "") or ""
    evento_titulo = ""
    evento_fecha = ""
    evento_hora = ""
    evento_tipo_cobertura = ""
    if evento_id:
        evento = repos.obtener_evento_rota(evento_id)
        if evento is not None:
            evento_titulo = evento.get("titulo", "") or ""
            evento_fecha = evento.get("fecha", "") or ""
            evento_hora = evento.get("hora", "") or ""
            evento_tipo_cobertura = evento.get("tipo_cobertura", "") or ""

    return {
        "id": tarea["id"],
        "proyecto": tarea["proyecto"],
        "proyecto_nombre": nombre,
        "proyecto_existe": proyecto_existe,
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
        # Pendientes unificados: referencia opcional a un evento de la rota + hidratacion.
        "evento_id": evento_id,
        "evento_titulo": evento_titulo,
        "evento_fecha": evento_fecha,
        "evento_hora": evento_hora,
        "evento_tipo_cobertura": evento_tipo_cobertura,
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
# Pendientes implicitos: eventos de la rota sin cobertura asignada              #
# --------------------------------------------------------------------------- #
#
# La UI muestra arriba los eventos "sin cubrir": eventos de la rota cuya cobertura aun
# no tiene a nadie asignado (turno con `miembro_id == ""`) Y los eventos de semanas que
# aun no se han propuesto (sin ningun turno). Acotamos a la semana ACTUAL y la SIGUIENTE
# (lunes de la semana actual -> domingo de la siguiente) para no inundar con un calendario
# completo. Los eventos `no_cubrir` (decision editorial: no se cubre) NO cuentan.


def _rango_dos_semanas(hoy: date) -> tuple[str, str]:
    """`(lunes, domingo)` ISO del rango "semana actual + semana siguiente" desde `hoy`."""
    lunes = hoy - timedelta(days=hoy.weekday())
    domingo_siguiente = lunes + timedelta(days=13)  # 14 dias inclusivos
    return lunes.isoformat(), domingo_siguiente.isoformat()


def _eventos_sin_cubrir(hoy: date | None = None) -> list[dict]:
    """Eventos de la rota de esta semana y la siguiente que NADIE cubre via su turno.

    Cobertura DERIVADA: un evento esta cubierto si EXISTE algun turno en `rota_turnos`
    cuya `franja_id` corresponde a una de las franjas vivas activas a la hora del evento
    (modelo "franjas por semana"). Filtra `tipo_cobertura=no_cubrir` (decision editorial).

    Devuelve dicts ligeros (id, titulo, fecha, hora, contenido, tipo_cobertura, prioridad)
    ordenados por fecha y hora ascendentes (mismo orden que `listar_eventos_rota`).
    """
    from .. import rota as dominio

    hoy = hoy or date.today()
    desde, hasta = _rango_dos_semanas(hoy)
    eventos = repos.listar_eventos_rota(desde=desde, hasta=hasta)
    # Filtra los `no_cubrir` (decision editorial: ese evento no se cubre, no es pendiente).
    eventos = [e for e in eventos if e.get("tipo_cobertura", "") != "no_cubrir"]

    # Trae los turnos y las franjas vivas de las DOS semanas que cubren el rango.
    semanas = sorted({
        (date.fromisoformat(desde) + timedelta(days=7 * i)).isoformat() for i in range(2)
    })
    turnos_por_semana: dict[str, list[dict]] = {}
    franjas_por_semana: dict[str, list[dict]] = {}
    for semana in semanas:
        turnos_por_semana[semana] = repos.listar_turnos_rota(semana=semana)
        # Siembra defaults si la semana esta vacia.
        franjas_lista = repos.listar_franjas_semana(semana)
        if not franjas_lista:
            franjas_lista = repos.sembrar_franjas_por_defecto(semana)
        franjas_por_semana[semana] = franjas_lista

    sin_cubrir: list[dict] = []
    for e in eventos:
        fecha = e.get("fecha", "") or ""
        semana_evento = dominio.lunes_de_semana_iso(fecha)
        turnos = turnos_por_semana.get(semana_evento, [])
        franjas = franjas_por_semana.get(semana_evento, [])
        cubridores = dominio.cobertura_de_evento(e, turnos, franjas)
        if cubridores:
            continue
        sin_cubrir.append(
            {
                "id": e["id"],
                "titulo": e["titulo"],
                "fecha": fecha,
                "hora": e.get("hora", "") or "",
                "contenido": e.get("contenido", "") or "",
                "tipo_cobertura": e.get("tipo_cobertura", "") or "",
                "prioridad": e.get("prioridad", "") or "",
            }
        )
    return sin_cubrir


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


async def listar(request: Request) -> Response:
    """GET /api/tareas[?proyecto=<id>][&evento_id=<id>]: tablero compartido del equipo.

    Devuelve, ademas de las tareas y los proyectos de la allowlist, la lista de usuarios
    asignables (para el selector de responsable) y los EVENTOS SIN CUBRIR de la rota de
    esta semana y la siguiente (pendientes IMPLICITOS, para que la UI los muestre arriba).
    Filtros opcionales: `?proyecto=<id>` (acotado por marca/proyecto, #145 F5) y
    `?evento_id=<id>` (tareas atadas a un evento concreto).
    """
    por_id = _nombres_proyecto()
    proyecto_filtro = request.query_params.get("proyecto") or None
    evento_filtro = request.query_params.get("evento_id") or None
    # Solo se filtra por un proyecto de la allowlist; un id ajeno devuelve vacio sin error.
    if proyecto_filtro is not None and proyecto_filtro not in por_id:
        tareas: list[dict] = []
    else:
        tareas = repos.listar_tareas(proyecto_filtro, evento_filtro)
    return JSONResponse(
        {
            "tareas": [_tarea_a_dict(t, por_id) for t in tareas],
            "proyectos": [
                {"id": p.id, "nombre": p.nombre, "existe": p.existe} for p in por_id.values()
            ],
            "usuarios": _usuarios_asignables(),
            "eventos_sin_cubrir": _eventos_sin_cubrir(),
        }
    )


async def crear(request: Request) -> Response:
    """POST /api/tareas: crea un pendiente (libre o atado a evento/proyecto).

    El TITULO sigue siendo obligatorio. El PROYECTO es OPCIONAL (pendientes unificados):
    si llega vacio o falta, la tarea queda sin proyecto (tarea libre). Si llega un id, se
    valida contra la allowlist. `evento_id` es opcional; si llega, el evento debe existir
    en la rota.
    """
    datos = await leer_json(request)
    proyecto_id = datos.get("proyecto")
    titulo = datos.get("titulo")
    detalle = datos.get("detalle", "")
    enlace = datos.get("enlace", "")
    evento_id = datos.get("evento_id", "")
    if not isinstance(titulo, str) or not titulo.strip():
        return JSONResponse({"error": "La tarea necesita un titulo."}, status_code=400)
    # Proyecto: opcional (pendientes unificados). Vacio / faltante -> tarea libre.
    if proyecto_id is None:
        proyecto_id = ""
    if not isinstance(proyecto_id, str):
        return JSONResponse({"error": "El proyecto debe ser un id de la allowlist."}, status_code=400)
    proyecto_id = proyecto_id.strip()
    if not isinstance(detalle, str):
        detalle = ""
    if not isinstance(enlace, str):
        enlace = ""
    enlace = enlace.strip()
    if len(enlace) > _MAX_ENLACE:
        return JSONResponse({"error": "El enlace es demasiado largo."}, status_code=400)
    # Allowlist: si la tarea LLEVA proyecto, solo se aceptan ids configurados. Vacio se permite.
    if proyecto_id and proyectos.proyecto_por_id(proyecto_id) is None:
        return JSONResponse({"error": "Proyecto no permitido o inexistente."}, status_code=400)
    # Evento de la rota: opcional. Si llega, debe existir (defensa: no se confia en ids del cliente).
    if not isinstance(evento_id, str):
        evento_id = ""
    evento_id = evento_id.strip()
    if evento_id and repos.obtener_evento_rota(evento_id) is None:
        return JSONResponse(
            {"error": "Ese evento ya no está en la rota"}, status_code=400
        )
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
        evento_id=evento_id,
    )
    return JSONResponse({"tarea": _tarea_a_dict(tarea, _nombres_proyecto())})


async def actualizar(request: Request) -> Response:
    """PATCH /api/tareas/{id}: cambia estado, responsable, enlace y/o evento_id.

    Cada campo es opcional; se aplican solo los presentes. Retrocompatible con el cliente
    que solo manda `{"estado": ...}`. `evento_id=""` desata la tarea de cualquier evento.
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

    if "evento_id" in datos:
        evento_id = datos.get("evento_id")
        if not isinstance(evento_id, str):
            evento_id = ""
        evento_id = evento_id.strip()
        # Vacio = desatar; con valor, el evento debe existir (defensa contra ids inventados).
        if evento_id and repos.obtener_evento_rota(evento_id) is None:
            return JSONResponse(
                {"error": "Ese evento ya no está en la rota"}, status_code=400
            )
        campos["evento_id"] = evento_id

    if not campos:
        return JSONResponse(
            {"error": "Indica un estado, un responsable, un enlace o un evento."},
            status_code=400,
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
    """POST /api/tareas/{id}/abrir: abre Claude Code en la carpeta del proyecto.

    Si la tarea NO esta atada a un proyecto (tarea libre): 400 explicito pidiendo al
    usuario que le ponga un proyecto desde el detalle (no se puede abrir un asistente
    en una carpeta inexistente).
    """
    tarea_id = request.path_params["tarea_id"]
    tarea = repos.obtener_tarea(tarea_id)
    if tarea is None:
        return JSONResponse({"error": "La tarea ya no existe."}, status_code=400)
    # Pendientes unificados: una tarea libre (sin proyecto) NO se puede abrir en Claude Code.
    proyecto_id = (tarea.get("proyecto") or "").strip()
    if not proyecto_id:
        return JSONResponse(
            {
                "error": "Esta tarea no está atada a un proyecto: añade uno desde el detalle "
                "para abrirla en Claude Code."
            },
            status_code=400,
        )
    # Allowlist: la carpeta solo se resuelve desde consola.proyectos por id estable.
    p = proyectos.proyecto_por_id(proyecto_id)
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
