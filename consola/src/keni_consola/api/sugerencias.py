"""API del kanban de sugerencias / auto-desarrollo (/api/sugerencias).

CRUD del kanban + disparadores del motor de desarrollo (discovery, construir, checkpoint,
promover). La persistencia es Postgres (`db_sugerencias`); la máquina de estados y el
lanzamiento de jobs viven en `keni_consola.sugerencias`. Errores en español, sin tracebacks.
"""

from __future__ import annotations

import logging

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import config, cuenta_claude, generaciones, permisos, sugerencias
from .._http_json import leer_json
from ..observabilidad import NOMBRE_LOGGER

_logger = logging.getLogger(NOMBRE_LOGGER)

# Timeout del proxy a worker-dev para la promoción (fetch+rebase+push puede tardar).
_TIMEOUT_PROMOVER = 120.0


def _llamar_dev(metodo: str, ruta: str, json: dict | None = None) -> tuple[int, dict]:
    """Llama al listener de promoción de worker-dev (httpx sincrono; se invoca en el threadpool).

    Devuelve (status, payload). Cualquier fallo de red/timeout se traduce a 502 con un payload
    de error legible (la promoción degrada con mensaje, nunca casca)."""
    import httpx

    base = config.dev_url().rstrip("/")
    bearer = cuenta_claude.bearer_efectivo()
    url = f"{base}{ruta}"
    cabeceras = {"Authorization": f"Bearer {bearer}"}
    try:
        with httpx.Client(timeout=_TIMEOUT_PROMOVER) as cliente:
            if metodo == "GET":
                r = cliente.get(url, headers=cabeceras)
            else:
                r = cliente.post(url, headers=cabeceras, json=json or {})
        try:
            payload = r.json()
        except ValueError:
            payload = {"ok": False, "detalle": "respuesta no JSON de worker-dev"}
        return r.status_code, (payload if isinstance(payload, dict) else {"ok": False, "detalle": "payload inesperado"})
    except httpx.HTTPError as e:
        _logger.warning("fallo al alcanzar worker-dev (%s %s): %s", metodo, ruta, e)
        return 502, {"ok": False, "detalle": "No se pudo contactar worker-dev para promover."}


def _catalogos() -> dict[str, list[str]]:
    """Catálogos para la UI (no duplicarlos en el front)."""
    return {
        "categorias": list(sugerencias.CATEGORIAS),
        "estados": list(sugerencias.ESTADOS),
    }


# --------------------------------------------------------------------------- #
# Identidad / propiedad. El TABLERO y su control (mover, discovery, construir,  #
# checkpoint, borrar, promover) son del SUPERADMIN; el resto del equipo solo    #
# crea ideas y ve LAS SUYAS y su spec. La propiedad se fija server-side por el   #
# id de la sesión (`autor_id`), nunca por lo que mande el cliente.              #
# --------------------------------------------------------------------------- #


def _uid(request: Request) -> str:
    """Id del usuario de la sesión (o "" si se entró por el token de mantenimiento)."""
    usuario = permisos.usuario_actual(request)
    return str(usuario["id"]) if usuario and usuario.get("id") else ""


def _nombre(request: Request) -> str:
    """Nombre de display del usuario de la sesión (nombre o usuario), o "" si no hay sesión."""
    usuario = permisos.usuario_actual(request) or {}
    return str(usuario.get("nombre") or usuario.get("usuario") or "")


def _puede_ver(request: Request, sug: dict) -> bool:
    """True si la sesión puede ver `sug`: superadmin (todo) o su autor (las suyas)."""
    if permisos.es_superadmin(request):
        return True
    return bool(sug.get("autor_id")) and sug["autor_id"] == _uid(request)


def _solo_superadmin(request: Request, mensaje: str) -> Response | None:
    """403 si la sesión NO es superadmin; None si puede continuar."""
    if not permisos.es_superadmin(request):
        return permisos.rechazo_solo_admin(mensaje)
    return None


async def listar(request: Request) -> Response:
    """GET /api/sugerencias: kanban + catálogos. Superadmin ve TODO; el resto solo SUS ideas."""
    es_super = permisos.es_superadmin(request)
    autor_id = None if es_super else _uid(request)
    return JSONResponse(
        {
            "sugerencias": sugerencias.listar(autor_id=autor_id),
            "superadmin": es_super,
            **_catalogos(),
        }
    )


async def obtener(request: Request) -> Response:
    """GET /api/sugerencias/{id} -> `{sugerencia}`. Dueño o superadmin; ajena -> 404 (no se filtra)."""
    sug = sugerencias.obtener(request.path_params["sugerencia_id"])
    if sug is None or not _puede_ver(request, sug):
        return JSONResponse({"error": "Esa sugerencia ya no existe."}, status_code=404)
    return JSONResponse({"sugerencia": sug})


async def crear(request: Request) -> Response:
    """POST /api/sugerencias `{titulo, detalle?, categoria?}` -> `{sugerencia}`.

    El autor (nombre + id de propiedad) sale de la SESIÓN, no del cuerpo: cada idea queda
    atada a quien la crea para que solo él (y el superadmin) la vea luego.
    """
    datos = await leer_json(request)
    titulo = datos.get("titulo")
    if not isinstance(titulo, str) or not titulo.strip():
        return JSONResponse({"error": "El título es obligatorio."}, status_code=400)

    detalle = datos.get("detalle") or ""
    if not isinstance(detalle, str):
        return JSONResponse({"error": "El detalle debe ser texto."}, status_code=400)

    categoria = datos.get("categoria") or sugerencias.CATEGORIA_DEFECTO
    if categoria not in sugerencias.CATEGORIAS:
        return JSONResponse({"error": "Categoría no permitida."}, status_code=400)

    sugerencia = sugerencias.crear(
        titulo, detalle=detalle, categoria=categoria,
        autor=_nombre(request), autor_id=_uid(request),
    )
    return JSONResponse({"sugerencia": sugerencia})


async def actualizar(request: Request) -> Response:
    """PATCH /api/sugerencias/{id} `{estado?|titulo?|detalle?|categoria?}` -> `{sugerencia}`.

    Mover de ESTADO (tablero/flujo) es solo del superadmin; editar el TEXTO lo puede hacer el
    superadmin o el AUTOR de la idea.
    """
    sugerencia_id = request.path_params["sugerencia_id"]
    datos = await leer_json(request)

    actual0 = sugerencias.obtener(sugerencia_id)
    # Una sugerencia que la sesión no puede ver es, para ella, inexistente (no se filtra que
    # exista una ajena). Quien la ve es superadmin o su autor.
    if actual0 is None or not _puede_ver(request, actual0):
        return JSONResponse({"error": "Esa sugerencia ya no existe."}, status_code=404)
    es_super = permisos.es_superadmin(request)
    es_dueno = bool(actual0.get("autor_id")) and actual0["autor_id"] == _uid(request)

    # Cambio de ESTADO (validado por la máquina de estados). Solo superadmin.
    if "estado" in datos:
        if not es_super:
            return permisos.rechazo_solo_admin("Solo un superadmin puede mover sugerencias.")
        estado = datos.get("estado")
        if estado not in sugerencias.ESTADOS:
            return JSONResponse({"error": "Estado no permitido."}, status_code=400)
        try:
            actualizada = sugerencias.cambiar_estado(sugerencia_id, estado)
        except sugerencias.TransicionInvalida:
            return JSONResponse(
                {"error": "Ese cambio de estado no está permitido."}, status_code=400
            )
        if actualizada is None:
            return JSONResponse({"error": "Esa sugerencia ya no existe."}, status_code=404)

    # Edición de TEXTO (titulo/detalle/categoria): superadmin o el autor de la idea.
    texto = {k: datos[k] for k in ("titulo", "detalle", "categoria") if k in datos}
    if texto:
        if not (es_super or es_dueno):
            return permisos.rechazo_solo_admin(
                "Solo el autor o un superadmin puede editar esta idea."
            )
        try:
            actualizada = sugerencias.editar(sugerencia_id, texto)
        except ValueError:
            return JSONResponse({"error": "El título es obligatorio."}, status_code=400)
        if actualizada is None:
            return JSONResponse({"error": "Esa sugerencia ya no existe."}, status_code=404)

    if "estado" not in datos and not texto:
        return JSONResponse({"error": "No hay nada que actualizar."}, status_code=400)

    actual = sugerencias.obtener(sugerencia_id)
    if actual is None:
        return JSONResponse({"error": "Esa sugerencia ya no existe."}, status_code=404)
    return JSONResponse({"sugerencia": actual})


async def borrar(request: Request) -> Response:
    """DELETE /api/sugerencias/{id} -> `{ok: true}`. Solo superadmin (limpia el tablero)."""
    rechazo = _solo_superadmin(request, "Solo un superadmin puede borrar sugerencias.")
    if rechazo is not None:
        return rechazo
    sugerencia_id = request.path_params["sugerencia_id"]
    if not sugerencias.borrar(sugerencia_id):
        return JSONResponse({"error": "Esa sugerencia ya no existe."}, status_code=404)
    return JSONResponse({"ok": True})


def _lanzar_o_error(funcion, *args, **kwargs) -> Response:
    """Ejecuta un lanzador del motor y mapea sus resultados/errores a una respuesta.

    None -> 404 (la sugerencia no existe); `ColaLlenaError` -> 429; éxito -> `{generacion}`.
    """
    try:
        gen = funcion(*args, **kwargs)
    except generaciones.ColaLlenaError as e:
        return JSONResponse(
            {"error": str(e) or "Hay demasiadas generaciones en curso; inténtalo en unos segundos."},
            status_code=429,
        )
    if gen is None:
        return JSONResponse({"error": "Esa sugerencia ya no existe."}, status_code=404)
    return JSONResponse({"generacion": gen})


def _nota(datos: dict) -> str:
    """Nota opcional del cuerpo (texto del usuario para los agentes); "" si no es texto."""
    nota = datos.get("nota") or ""
    return nota if isinstance(nota, str) else ""


async def discovery(request: Request) -> Response:
    """POST /api/sugerencias/{id}/discovery `{nota?}` -> `{generacion}` (encola dev-discovery)."""
    rechazo = _solo_superadmin(request, "Solo un superadmin puede lanzar discovery.")
    if rechazo is not None:
        return rechazo
    datos = await leer_json(request)
    return _lanzar_o_error(
        sugerencias.lanzar_discovery, request.path_params["sugerencia_id"], nota=_nota(datos)
    )


async def construir(request: Request) -> Response:
    """POST /api/sugerencias/{id}/construir `{complejidad?, nota?}` -> `{generacion}`."""
    rechazo = _solo_superadmin(request, "Solo un superadmin puede construir.")
    if rechazo is not None:
        return rechazo
    sugerencia_id = request.path_params["sugerencia_id"]
    datos = await leer_json(request)
    complejidad = datos.get("complejidad") or ""
    if not isinstance(complejidad, str):
        complejidad = ""
    return _lanzar_o_error(
        sugerencias.lanzar_construir, sugerencia_id, complejidad=complejidad, nota=_nota(datos)
    )


# Acciones válidas del checkpoint humano sobre una sugerencia en `revision`.
_ACCIONES_CHECKPOINT = ("continuar", "cambios", "cancelar")


async def checkpoint(request: Request) -> Response:
    """POST /api/sugerencias/{id}/checkpoint `{accion, comentario?}` -> `{sugerencia}`.

    - continuar: sigue el pipeline (lanza la siguiente fase si la hay; si no, queda lista para
      promover).
    - cambios: re-ejecuta la construcción con el comentario como feedback.
    - cancelar: descarta la sugerencia.
    """
    rechazo = _solo_superadmin(request, "Solo un superadmin puede resolver un checkpoint.")
    if rechazo is not None:
        return rechazo
    sugerencia_id = request.path_params["sugerencia_id"]
    datos = await leer_json(request)
    accion = datos.get("accion")
    if accion not in _ACCIONES_CHECKPOINT:
        return JSONResponse({"error": "Acción de checkpoint no permitida."}, status_code=400)
    comentario = datos.get("comentario") or ""
    if not isinstance(comentario, str):
        comentario = ""

    sug = sugerencias.obtener(sugerencia_id)
    if sug is None:
        return JSONResponse({"error": "Esa sugerencia ya no existe."}, status_code=404)

    try:
        actualizada = sugerencias.aplicar_checkpoint(sugerencia_id, accion, comentario=comentario)
    except sugerencias.TransicionInvalida:
        return JSONResponse(
            {"error": "El checkpoint no es aplicable en este estado."}, status_code=400
        )
    except generaciones.ColaLlenaError as e:
        return JSONResponse(
            {"error": str(e) or "Hay demasiadas generaciones en curso; inténtalo en unos segundos."},
            status_code=429,
        )
    if actualizada is None:
        return JSONResponse({"error": "Esa sugerencia ya no existe."}, status_code=404)
    return JSONResponse({"sugerencia": actualizada})


async def promover(request: Request) -> Response:
    """POST /api/sugerencias/{id}/promover -> `{ok, detalle, rama}` (checkpoint humano → main).

    SUPERADMIN-gated: promover ejecuta un `git push` REAL a `main` (es control del tablero, que
    es del superadmin). PROXEA (httpx+bearer) al listener de worker-dev (`KENI_DEV_URL`), que hace
    fetch+rebase+push de la rama de la sugerencia dentro de su worktree. Solo desde estado
    `revision`; si worker-dev no responde, degrada con error claro y NO mueve el kanban. Tras un
    push OK, marca la sugerencia `hecha`.
    """
    rechazo = _solo_superadmin(request, "Solo un superadmin puede promover a main.")
    if rechazo is not None:
        return rechazo
    sugerencia_id = request.path_params["sugerencia_id"]
    sug = sugerencias.obtener(sugerencia_id)
    if sug is None:
        return JSONResponse({"error": "Esa sugerencia ya no existe."}, status_code=404)
    if sug["estado"] != "revision":
        return JSONResponse(
            {"ok": False, "detalle": "La sugerencia no está lista para promover."},
            status_code=400,
        )

    status, payload = await run_in_threadpool(
        _llamar_dev, "POST", "/control/dev/promover", {"sugerencia_id": sugerencia_id}
    )
    if status != 200 or not payload.get("ok"):
        detalle = payload.get("detalle") or payload.get("error") or "No se pudo promover la rama a main."
        return JSONResponse({"ok": False, "detalle": detalle}, status_code=status if status >= 400 else 502)

    # Push real OK: registra la decisión humana y mueve el kanban a `hecha`.
    try:
        local = sugerencias.promover(sugerencia_id)
    except sugerencias.TransicionInvalida:
        local = None
    return JSONResponse({
        "ok": True,
        "detalle": payload.get("detalle") or "Rama promovida a main.",
        "rama": payload.get("rama", ""),
        "sugerencia": (local or {}).get("sugerencia"),
    })


RUTAS = [
    Route("/api/sugerencias", listar, methods=["GET"]),
    Route("/api/sugerencias", crear, methods=["POST"]),
    Route("/api/sugerencias/{sugerencia_id}", obtener, methods=["GET"]),
    Route("/api/sugerencias/{sugerencia_id}", actualizar, methods=["PATCH"]),
    Route("/api/sugerencias/{sugerencia_id}", borrar, methods=["DELETE"]),
    Route("/api/sugerencias/{sugerencia_id}/discovery", discovery, methods=["POST"]),
    Route("/api/sugerencias/{sugerencia_id}/construir", construir, methods=["POST"]),
    Route("/api/sugerencias/{sugerencia_id}/checkpoint", checkpoint, methods=["POST"]),
    Route("/api/sugerencias/{sugerencia_id}/promover", promover, methods=["POST"]),
]
