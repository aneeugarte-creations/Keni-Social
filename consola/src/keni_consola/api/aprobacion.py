"""API Aprobacion de equipo (#9, Fase 3): cola de revision + programacion en dry-run.

Monta el flujo de aprobacion de equipo SOBRE las publicaciones ya existentes (reusa
`repos`/`dominio.publicaciones`, no reinventa el almacen). Endpoints (todos POST salvo
la cola), con la identidad del usuario que ya deja el middleware en `request.state`:

  - GET  /api/aprobacion/cola                  -> piezas en revision (quien envio + cuando).
  - POST /api/aprobacion/{id}/enviar-a-revision -> borrador -> en_revision (autor).
  - POST /api/aprobacion/{id}/aprobar           -> en_revision -> aprobado (revisor != autor).
  - POST /api/aprobacion/{id}/rechazar          -> en_revision -> borrador (revisor != autor).
  - POST /api/aprobacion/{id}/programar {fecha} -> aprobado  -> programado (fecha futura).

GATING (frontera del producto): programar NO publica en ninguna plataforma. Deja la
pieza en `programado` con su `fecha_programada`; el programador del servidor
(`programador.py`) la PREPARA (dry-run) al vencer. El posteo real esta GATED por #5
(Meta App Review) y #8. "El humano aprueba; el sistema no publica solo."

SEPARACION DE FUNCIONES: quien aprueba/rechaza no puede ser el autor que la envio
(salvo admin) — la regla vive en `dominio.aprobacion`. Aqui solo se resuelve la
identidad/rol y se delega.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import repos
from .._http_json import leer_json
from ..dominio import aprobacion
from ..dominio.publicaciones import publicacion_a_dict
from ..estados import ESTADO_APROBADO, ESTADO_EN_REVISION, ESTADO_PROGRAMADO
from ..seguridad import autor_de_peticion


def _rol_de_peticion(request: Request) -> str | None:
    """Rol del usuario de la sesion (None si entro por token de bootstrap / sin sesion)."""
    usuario = getattr(request.state, "usuario", None)
    if isinstance(usuario, dict):
        return usuario.get("rol")
    return None


async def _aplicar_transicion(request: Request, transicion: str) -> Response:
    """Resuelve la pieza + identidad, ejecuta la transicion de `dominio.aprobacion` y guarda.

    `transicion` es "enviar"|"aprobar"|"rechazar". Centraliza el patron comun (404 si no
    existe, 409 si la transicion no es valida, 200 con la pieza actualizada).
    """
    publicacion_id = request.path_params["publicacion_id"]
    pub = repos.obtener_publicacion(publicacion_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)

    autor = autor_de_peticion(request)
    rol = _rol_de_peticion(request)
    if transicion == "enviar":
        campos, error = aprobacion.enviar_a_revision(pub, autor)
    elif transicion == "aprobar":
        campos, error = aprobacion.aprobar(pub, autor, rol=rol)
    else:  # rechazar
        campos, error = aprobacion.rechazar(pub, autor, rol=rol)

    if error is not None:
        return JSONResponse({"error": error}, status_code=409)

    actualizada = repos.actualizar_publicacion(publicacion_id, campos)
    if actualizada is None:  # carrera: borrada entre el obtener y el actualizar
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    return JSONResponse({"publicacion": publicacion_a_dict(actualizada)})


async def cola(request: Request) -> Response:
    """Cola de aprobacion: piezas EN REVISION, mas antiguas primero (FIFO de revision).

    Devuelve `{cola: [...], total: N}`. Cada item incluye `autor_nombre`/`autor_id`
    (quien envio) y `enviado_a_revision_en` (cuando), para que el equipo vea que espera
    revision y desde cuando.
    """
    pendientes = repos.listar_publicaciones(estado=ESTADO_EN_REVISION)
    # Mas antiguas primero por `enviado_a_revision_en` (lo que lleva mas esperando, arriba).
    pendientes.sort(key=lambda p: p.get("enviado_a_revision_en") or "")
    items = [publicacion_a_dict(p) for p in pendientes]
    return JSONResponse({"cola": items, "total": len(items)})


async def enviar_a_revision(request: Request) -> Response:
    """POST /api/aprobacion/{id}/enviar-a-revision: borrador -> en_revision."""
    return await _aplicar_transicion(request, "enviar")


async def aprobar(request: Request) -> Response:
    """POST /api/aprobacion/{id}/aprobar: en_revision -> aprobado (revisor != autor)."""
    return await _aplicar_transicion(request, "aprobar")


async def rechazar(request: Request) -> Response:
    """POST /api/aprobacion/{id}/rechazar: en_revision -> borrador (revisor != autor)."""
    return await _aplicar_transicion(request, "rechazar")


def _validar_fecha_programada(valor: Any) -> tuple[str | None, str | None]:
    """Valida `fecha` como datetime ISO FUTURO; devuelve `(iso_normalizada, None)` o `(None, error)`.

    Acepta 'YYYY-MM-DDTHH:MM' (o con segundos). Debe ser estrictamente futura: no tiene
    sentido programar para un instante ya pasado (el programador la prepararia de inmediato,
    sorprendiendo al usuario). Se normaliza a minutos ('YYYY-MM-DDTHH:MM').
    """
    if not isinstance(valor, str) or not valor.strip():
        return None, "Indica la fecha y hora de publicación (formato YYYY-MM-DDTHH:MM)."
    try:
        fecha = datetime.fromisoformat(valor.strip())
    except ValueError:
        return None, "La fecha no es válida (usa el formato YYYY-MM-DDTHH:MM)."
    if fecha <= datetime.now():
        return None, "La fecha debe ser futura."
    return fecha.strftime("%Y-%m-%dT%H:%M"), None


async def programar(request: Request) -> Response:
    """POST /api/aprobacion/{id}/programar {fecha}: aprobado -> programado en esa fecha.

    Solo se puede programar una pieza APROBADA (el humano ya la aprobó). NO publica: deja
    la pieza en `programado` con su `fecha_programada`; el programador del servidor la
    PREPARA (dry-run) al vencer. Posteo real GATED por #5/#8. 404 si no existe; 409 si no
    está aprobada; 400 si la fecha no es válida/futura.
    """
    publicacion_id = request.path_params["publicacion_id"]
    pub = repos.obtener_publicacion(publicacion_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    if pub.get("estado") != ESTADO_APROBADO:
        return JSONResponse(
            {"error": "Solo se puede programar una pieza aprobada."}, status_code=409
        )

    datos = await leer_json(request)
    fecha, error = _validar_fecha_programada(datos.get("fecha"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)

    actualizada = repos.actualizar_publicacion(
        publicacion_id,
        {"estado": ESTADO_PROGRAMADO, "fecha_programada": fecha, "preparado_en": ""},
    )
    if actualizada is None:  # carrera: borrada entre el obtener y el actualizar
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    return JSONResponse({"publicacion": publicacion_a_dict(actualizada)})


RUTAS = [
    Route("/api/aprobacion/cola", cola, methods=["GET"]),
    Route("/api/aprobacion/{publicacion_id}/enviar-a-revision", enviar_a_revision, methods=["POST"]),
    Route("/api/aprobacion/{publicacion_id}/aprobar", aprobar, methods=["POST"]),
    Route("/api/aprobacion/{publicacion_id}/rechazar", rechazar, methods=["POST"]),
    Route("/api/aprobacion/{publicacion_id}/programar", programar, methods=["POST"]),
]
