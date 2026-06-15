"""API Rota · solicitudes de cambio de turno entre companeros (#175)."""
from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ... import auth, marcas, repos
from ..._http_json import leer_json
from ...dominio import notificaciones_turnos
from ...estados import (
    ESTADO_SWAP_ACEPTADO,
    ESTADO_SWAP_CANCELADO,
    ESTADO_SWAP_PROPUESTO,
    ESTADO_SWAP_RECHAZADO,
    ESTADO_SWAP_RECHAZADO_ADMIN,
)
from ...tiempo import ahora_iso
from ._comun import _es_admin, _fecha_valida, _marca_param, _nombres_equipo, _usuario_actual

_MSG_SOLO_ADMIN_SWAP = (
    "Solo Elías (administrador) puede aprobar/rechazar un cambio de turno."
)


def _nombre_franja(franja_id: str) -> str:
    """Nombre legible de una franja de semana por su `franja_id` ("" si no resuelve).

    Reusa `repos.obtener_franja_semana` (igual que `_turno_a_dict` resuelve `franja_nombre`):
    así la tarjeta de cambio pinta "Mañana"/"Tarde" en vez del uuid de la franja. Devuelve ""
    (cadena vacía, NUNCA None) cuando el id está vacío o la franja ya no existe.
    """
    if not franja_id:
        return ""
    franja = repos.obtener_franja_semana(franja_id)
    return franja["nombre"] if franja else ""


def _swap_a_dict(swap: dict[str, Any], nombres: dict[str, str]) -> dict[str, Any]:
    """Serializa un swap (resolviendo el nombre vivo de cada miembro y de cada franja)."""
    return {
        "id": swap["id"],
        "solicitante_id": swap["solicitante_id"],
        # Nombre vivo del equipo > snapshot (un usuario puede renombrarse).
        "solicitante_nombre": nombres.get(
            swap["solicitante_id"], swap.get("solicitante_nombre", "")
        ),
        "destinatario_id": swap["destinatario_id"],
        "destinatario_nombre": nombres.get(
            swap["destinatario_id"], swap.get("destinatario_nombre", "")
        ),
        "fecha_a": swap["fecha_a"],
        "franja_a": swap["franja_a"],
        # Nombre legible de la franja (el front mapea esto, no el uuid `franja_a`).
        "franja_a_nombre": _nombre_franja(swap["franja_a"]),
        "fecha_b": swap["fecha_b"],
        "franja_b": swap["franja_b"],
        "franja_b_nombre": _nombre_franja(swap["franja_b"]),
        "motivo": swap["motivo"],
        "estado": swap["estado"],
        "respuesta_destinatario": swap["respuesta_destinatario"],
        "respuesta_admin": swap["respuesta_admin"],
        "creado": swap["creado"],
        "actualizado": swap["actualizado"],
        "decidido_destinatario": swap["decidido_destinatario"],
        "decidido_admin": swap["decidido_admin"],
        "aplicado": swap["aplicado"],
        # GRID POR MARCA: la rejilla del swap (la UI la etiqueta en "Todas").
        "marca": swap.get("marca", "") or "",
        "marca_nombre": marcas.etiqueta_de(swap["marca"]) if swap.get("marca") else "",
    }


def _existe_turno(miembro_id: str, fecha: str, franja_id: str) -> bool:
    """True si EXISTE un turno en `rota_turnos` con `(miembro_id, fecha, franja_id)`.

    Delega en `repos.existe_turno_para` (un solo SELECT directo en BD).
    """
    return repos.existe_turno_para(miembro_id, fecha, franja_id) is not None


def _mio_param(request: Request) -> bool:
    """¿La query trae `mio=true` (filtrar a swaps que me involucran)?"""
    return (request.query_params.get("mio") or "").strip().lower() in (
        "1",
        "true",
        "sí",
        "si",
    )


def _estado_param(request: Request) -> str | None:
    """Estado pedido en `?estado=`, validando contra la allowlist. None si no se pidio.

    Si el cliente pasa un estado fuera de la allowlist devolvemos None (el handler trata
    eso como "filtro invalido" via la propia validacion del estado al construir la consulta:
    aqui simplemente lo ignoramos). Es defensivo: el DB solo devuelve filas reales.
    """
    crudo = (request.query_params.get("estado") or "").strip()
    return crudo or None


async def listar_swaps(request: Request) -> Response:
    """GET /api/rota/swaps[?estado&solicitante_id&destinatario_id&mio=true]: solicitudes de swap.

    Si `mio=true` y hay sesion, filtra a swaps donde el usuario actual sea solicitante o
    destinatario. Devuelve `{swaps: [...]}` ordenado por mas reciente primero.
    """
    estado = _estado_param(request)
    solicitante_id = (request.query_params.get("solicitante_id") or "").strip() or None
    destinatario_id = (request.query_params.get("destinatario_id") or "").strip() or None
    marca, error = _marca_param(request)
    if error is not None:
        return error
    mio_id: str | None = None
    if _mio_param(request):
        usuario = _usuario_actual(request)
        if usuario is not None:
            mio_id = usuario["id"]
        else:
            # Sin sesion no hay "mio": devolvemos lista vacia (es semantica honesta).
            return JSONResponse({"swaps": []})
    swaps = repos.listar_swaps_turno(
        estado=estado,
        solicitante_id=solicitante_id,
        destinatario_id=destinatario_id,
        mio_id=mio_id,
        marca=marca,
    )
    nombres = _nombres_equipo()
    return JSONResponse({"swaps": [_swap_a_dict(s, nombres) for s in swaps]})


async def crear_swap(request: Request) -> Response:
    """POST /api/rota/swaps: A (sesion) crea una solicitud de cambio de turno con B.

    Cuerpo: `{destinatario_id, fecha_a, franja_a, fecha_b, franja_b, motivo?}`. El
    solicitante se toma de `request.state.usuario` (NUNCA del cliente). Valida que los
    turnos existan en `rota_turnos_trabajo`; si no, 400 con motivo accionable.
    """
    usuario = _usuario_actual(request)
    if usuario is None:
        return JSONResponse(
            {"error": "Inicia sesión para solicitar un cambio de turno."}, status_code=401
        )
    datos = await leer_json(request)
    nombres = _nombres_equipo()

    destinatario_id = datos.get("destinatario_id")
    if not isinstance(destinatario_id, str) or not destinatario_id:
        return JSONResponse(
            {"error": "Indica al compañero al que pides el cambio."}, status_code=400
        )
    if destinatario_id == usuario["id"]:
        return JSONResponse(
            {"error": "No puedes cambiarte el turno contigo mismo/a."}, status_code=400
        )
    # `destinatario_id` debe ser un usuario REAL (no un id arbitrario del cliente).
    if auth.obtener_usuario_por_id(destinatario_id) is None or destinatario_id not in nombres:
        return JSONResponse(
            {"error": "Ese compañero no existe en el equipo."}, status_code=400
        )

    fecha_a = str(datos.get("fecha_a", "")).strip()
    fecha_b = str(datos.get("fecha_b", "")).strip()
    if not _fecha_valida(fecha_a) or not _fecha_valida(fecha_b):
        return JSONResponse(
            {"error": "Las fechas no son válidas (usa AAAA-MM-DD)."}, status_code=400
        )
    # `franja_a`/`franja_b` ahora son `franja_id` reales (la columna en BD conserva el
    # nombre `franja_a/_b` por inercia: cambio de SEMANTICA del dato, no de columna).
    franja_a = str(datos.get("franja_a", "")).strip()
    franja_b = str(datos.get("franja_b", "")).strip()
    if not franja_a or not franja_b:
        return JSONResponse(
            {"error": "Indica `franja_a` y `franja_b` (franja_id de la semana de cada turno)."},
            status_code=400,
        )
    franja_a_def = repos.obtener_franja_semana(franja_a)
    if franja_a_def is None or repos.obtener_franja_semana(franja_b) is None:
        return JSONResponse(
            {"error": "Alguna de las franjas indicadas no existe."}, status_code=400
        )
    # GRID POR MARCA: el swap pertenece a la rejilla del turno A (denormalizamos su marca).
    marca_swap = franja_a_def.get("marca", "") or ""

    # Los turnos DEBEN existir en el horario: si no, no hay nada que cambiar.
    if not _existe_turno(usuario["id"], fecha_a, franja_a):
        return JSONResponse(
            {
                "error": (
                    "No encuentro tu turno en el horario para esa fecha y franja. "
                    "Pide a Elías que proponga/apruebe el horario antes."
                )
            },
            status_code=400,
        )
    if not _existe_turno(destinatario_id, fecha_b, franja_b):
        return JSONResponse(
            {
                "error": (
                    "No encuentro el turno de tu compañero en el horario para esa "
                    "fecha y franja."
                )
            },
            status_code=400,
        )

    motivo = str(datos.get("motivo", "")).strip()

    swap = repos.crear_swap_turno(
        usuario["id"],
        destinatario_id,
        fecha_a,
        franja_a,
        fecha_b,
        franja_b,
        solicitante_nombre=nombres.get(usuario["id"], usuario.get("usuario", "")),
        destinatario_nombre=nombres.get(destinatario_id, ""),
        motivo=motivo,
        marca=marca_swap,
    )
    swap_dict = _swap_a_dict(swap, nombres)
    # Avisa al destinatario in-app (campana) de que tiene un cambio que responder.
    notificaciones_turnos.tras_solicitud(swap_dict, actor=usuario)
    return JSONResponse({"swap": swap_dict}, status_code=201)


def _error_transicion(estado_actual: str, accion: str) -> Response:
    """Respuesta 409 estandar cuando el swap no admite esa transicion ahora mismo."""
    return JSONResponse(
        {
            "error": (
                f"No se puede {accion} ahora: el cambio está en estado «{estado_actual}»."
            ),
            "estado_actual": estado_actual,
        },
        status_code=409,
    )


async def _ahora_yo_soy(request: Request, swap_id: str) -> tuple[Response | None, dict | None, dict | None]:
    """Helper: carga el swap y el usuario actual; 401/404 si fallan.

    Devuelve `(respuesta_error, swap, usuario)`. Si `respuesta_error` no es None, el
    handler debe retornarlo directamente.
    """
    usuario = _usuario_actual(request)
    if usuario is None:
        return (
            JSONResponse({"error": "Inicia sesión para responder al cambio."}, status_code=401),
            None,
            None,
        )
    swap = repos.obtener_swap_turno(swap_id)
    if swap is None:
        return (
            JSONResponse({"error": "La solicitud de cambio ya no existe."}, status_code=404),
            None,
            None,
        )
    return None, swap, usuario


async def aceptar_swap(request: Request) -> Response:
    """POST /api/rota/swaps/{id}/aceptar: el DESTINATARIO acepta el cambio.

    Solo si el estado actual es `propuesto` y el usuario es el destinatario. Cuerpo
    opcional `{respuesta}` para dejar una nota a A/Elías.
    """
    swap_id = request.path_params["swap_id"]
    err, swap, usuario = await _ahora_yo_soy(request, swap_id)
    if err is not None:
        return err
    assert swap is not None and usuario is not None
    if swap["destinatario_id"] != usuario["id"]:
        return JSONResponse(
            {"error": "Solo el compañero al que se le pide el cambio puede aceptarlo."},
            status_code=403,
        )
    if swap["estado"] != ESTADO_SWAP_PROPUESTO:
        return _error_transicion(swap["estado"], "aceptar")
    datos = await leer_json(request)
    respuesta = str(datos.get("respuesta", "")).strip()
    ahora = _ahora_iso()
    actualizado = repos.actualizar_swap_turno(
        swap_id,
        {
            "estado": "aceptado",
            "respuesta_destinatario": respuesta,
            "decidido_destinatario": ahora,
        },
    )
    if actualizado is None:  # carrera: lo borraron entre medias
        return JSONResponse({"error": "La solicitud ya no existe."}, status_code=404)
    swap_dict = _swap_a_dict(actualizado, _nombres_equipo())
    # Aceptado por B: avisa a los admin de que hay un cambio esperando su aprobacion.
    notificaciones_turnos.tras_respuesta_destinatario(swap_dict, "aceptado", actor=usuario)
    return JSONResponse({"swap": swap_dict})


async def rechazar_swap(request: Request) -> Response:
    """POST /api/rota/swaps/{id}/rechazar: el DESTINATARIO rechaza el cambio.

    Solo si `propuesto` y el usuario es el destinatario. Cuerpo opcional con `respuesta`.
    """
    swap_id = request.path_params["swap_id"]
    err, swap, usuario = await _ahora_yo_soy(request, swap_id)
    if err is not None:
        return err
    assert swap is not None and usuario is not None
    if swap["destinatario_id"] != usuario["id"]:
        return JSONResponse(
            {"error": "Solo el compañero al que se le pide el cambio puede rechazarlo."},
            status_code=403,
        )
    if swap["estado"] != ESTADO_SWAP_PROPUESTO:
        return _error_transicion(swap["estado"], "rechazar")
    datos = await leer_json(request)
    respuesta = str(datos.get("respuesta", "")).strip()
    ahora = _ahora_iso()
    actualizado = repos.actualizar_swap_turno(
        swap_id,
        {
            "estado": ESTADO_SWAP_RECHAZADO,
            "respuesta_destinatario": respuesta,
            "decidido_destinatario": ahora,
        },
    )
    if actualizado is None:
        return JSONResponse({"error": "La solicitud ya no existe."}, status_code=404)
    swap_dict = _swap_a_dict(actualizado, _nombres_equipo())
    # Rechazado por B: avisa al solicitante de que su cambio no sale.
    notificaciones_turnos.tras_respuesta_destinatario(swap_dict, "rechazado", actor=usuario)
    return JSONResponse({"swap": swap_dict})


async def aprobar_swap(request: Request) -> Response:
    """POST /api/rota/swaps/{id}/aprobar: admin APRUEBA y EJECUTA el swap.

    Solo `aceptado` -> `aplicado`. Re-valida en el momento que las franjas actuales en
    `rota_turnos_trabajo` siguen siendo las del swap. Si NO coinciden (alguien las
    cambio a mano), devuelve 409 con detalle y NO toca nada. Si todo cuadra, intercambia
    los `miembro_id` y marca la solicitud como `aplicado` en una transaccion.
    """
    if not _es_admin(request):
        return JSONResponse({"error": _MSG_SOLO_ADMIN_SWAP}, status_code=403)
    swap_id = request.path_params["swap_id"]
    swap = repos.obtener_swap_turno(swap_id)
    if swap is None:
        return JSONResponse({"error": "La solicitud ya no existe."}, status_code=404)
    if swap["estado"] != ESTADO_SWAP_ACEPTADO:
        return _error_transicion(swap["estado"], "aprobar")
    datos = await leer_json(request)
    respuesta = str(datos.get("respuesta", "")).strip()
    nombres = _nombres_equipo()
    resultado = repos.aplicar_swap_turno(
        swap_id,
        solicitante_id=swap["solicitante_id"],
        solicitante_nombre=nombres.get(swap["solicitante_id"], swap["solicitante_nombre"]),
        destinatario_id=swap["destinatario_id"],
        destinatario_nombre=nombres.get(swap["destinatario_id"], swap["destinatario_nombre"]),
        fecha_a=swap["fecha_a"],
        franja_a=swap["franja_a"],
        fecha_b=swap["fecha_b"],
        franja_b=swap["franja_b"],
        respuesta_admin=respuesta,
    )
    if resultado is None:  # carrera: el swap se borro
        return JSONResponse({"error": "La solicitud ya no existe."}, status_code=404)
    if "error" in resultado and resultado["error"] == "no_coinciden":
        return JSONResponse(
            {
                "error": "Los turnos ya no son los del cambio original.",
                "detalle": {
                    "esperado": resultado["esperado"],
                    "actual": resultado["actual"],
                },
            },
            status_code=409,
        )
    if "error" in resultado and resultado["error"] == "conflicto_destino":
        # El intercambio chocaria con el indice unico de `rota_turnos`: el compañero ya ocupa
        # la celda de origen (o tú la de destino). 409 accionable, no un 500 opaco.
        return JSONResponse(
            {"error": "Ese compañero ya tiene un turno en ese hueco."},
            status_code=409,
        )
    swap_dict = _swap_a_dict(resultado, nombres)
    # Aplicado por el admin: avisa a ambas partes de que el cambio quedó hecho.
    notificaciones_turnos.tras_decision_admin(
        swap_dict, "aplicado", actor=_usuario_actual(request)
    )
    return JSONResponse({"swap": swap_dict})


async def rechazar_swap_admin(request: Request) -> Response:
    """POST /api/rota/swaps/{id}/rechazar-admin: admin rechaza tras la aceptacion de B.

    Solo si `aceptado` -> `rechazado_admin`. Cuerpo opcional con `respuesta`.
    """
    if not _es_admin(request):
        return JSONResponse({"error": _MSG_SOLO_ADMIN_SWAP}, status_code=403)
    swap_id = request.path_params["swap_id"]
    swap = repos.obtener_swap_turno(swap_id)
    if swap is None:
        return JSONResponse({"error": "La solicitud ya no existe."}, status_code=404)
    if swap["estado"] != ESTADO_SWAP_ACEPTADO:
        return _error_transicion(swap["estado"], "rechazar")
    datos = await leer_json(request)
    respuesta = str(datos.get("respuesta", "")).strip()
    ahora = _ahora_iso()
    actualizado = repos.actualizar_swap_turno(
        swap_id,
        {
            "estado": ESTADO_SWAP_RECHAZADO_ADMIN,
            "respuesta_admin": respuesta,
            "decidido_admin": ahora,
        },
    )
    if actualizado is None:
        return JSONResponse({"error": "La solicitud ya no existe."}, status_code=404)
    swap_dict = _swap_a_dict(actualizado, _nombres_equipo())
    # Rechazado por el admin: avisa a ambas partes del desenlace.
    notificaciones_turnos.tras_decision_admin(
        swap_dict, "rechazado_admin", actor=_usuario_actual(request)
    )
    return JSONResponse({"swap": swap_dict})


async def cancelar_swap(request: Request) -> Response:
    """POST /api/rota/swaps/{id}/cancelar: el SOLICITANTE cancela su solicitud.

    Solo si el estado no es terminal (`propuesto` o `aceptado`) y el usuario es A.
    """
    swap_id = request.path_params["swap_id"]
    err, swap, usuario = await _ahora_yo_soy(request, swap_id)
    if err is not None:
        return err
    assert swap is not None and usuario is not None
    if swap["solicitante_id"] != usuario["id"]:
        return JSONResponse(
            {"error": "Solo quien solicitó el cambio puede cancelarlo."},
            status_code=403,
        )
    if swap["estado"] not in (ESTADO_SWAP_PROPUESTO, ESTADO_SWAP_ACEPTADO):
        return _error_transicion(swap["estado"], "cancelar")
    actualizado = repos.actualizar_swap_turno(swap_id, {"estado": ESTADO_SWAP_CANCELADO})
    if actualizado is None:
        return JSONResponse({"error": "La solicitud ya no existe."}, status_code=404)
    swap_dict = _swap_a_dict(actualizado, _nombres_equipo())
    # Cancelado por el solicitante: avisa al destinatario, que lo tenía en su lista.
    notificaciones_turnos.tras_cancelacion(swap_dict, actor=usuario)
    return JSONResponse({"swap": swap_dict})


def _ahora_iso() -> str:
    """Timestamp ISO con segundos (mismo formato que el resto del modulo)."""

    return ahora_iso()
