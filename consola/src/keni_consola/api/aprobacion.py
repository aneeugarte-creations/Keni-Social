"""API Aprobacion de PUBLICACIONES (#9): cola de revision, decision y programacion.

CONSOLIDACION (aprobacion unica): este modulo YA NO tiene un flujo de aprobacion propio.
La aprobacion de una publicacion es ahora la MISMA cadena multinivel del tablero de
contenido (`api/colaboracion.py` + `dominio/colaboracion.py`), porque una publicacion ES
una fila `contenido_plataforma` (`es_publicacion=1`): su id es el `plataforma_id`. Estos
endpoints se conservan por RETROCOMPAT (quien los llame sigue funcionando), pero por dentro
FORWARDEAN a la cadena:

  - GET  /api/aprobacion/cola                  -> piezas en revision (sin cambios; lectura).
  - POST /api/aprobacion/{id}/enviar-a-revision -> crea una cadena SIMPLE (1 nivel) y deja
        la pieza `en_revision` (equivale a la vieja transicion borrador->en_revision).
  - POST /api/aprobacion/{id}/aprobar           -> DECIDE el nivel actual de la cadena como
        aprobado; si la cadena queda completa, la pieza pasa a `aprobado`.
  - POST /api/aprobacion/{id}/rechazar          -> DECIDE el nivel actual como rechazado;
        la pieza vuelve a `borrador`.
  - POST /api/aprobacion/{id}/programar {fecha} -> aprobado -> programado (NO es aprobacion;
        es programacion: se conserva intacta porque el programador lee `programado`).

La logica PURA (orden, "otro par de ojos", estado global) vive en `dominio.colaboracion`;
la traduccion estado-cadena -> estado-publicacion en `colaboracion.estado_publicacion_para`.

GATING (frontera del producto): programar NO publica en ninguna plataforma. Deja la pieza
en `programado` con su `fecha_programada`; el programador del servidor (`programador.py`) la
PREPARA (dry-run) al vencer. "El humano aprueba; el sistema no publica solo."
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import repos
from .._http_json import leer_json
from ..dominio import colaboracion
from ..dominio.publicaciones import publicacion_a_dict
from ..estados import (
    DECISION_APROBADO,
    DECISION_RECHAZADO,
    ESTADO_APROBADO,
    ESTADO_EN_REVISION,
    ESTADO_PROGRAMADO,
)
from ..seguridad import autor_de_peticion


def _rol_de_peticion(request: Request) -> str | None:
    """Rol del usuario de la sesion (None si entro por token de bootstrap / sin sesion)."""
    usuario = getattr(request.state, "usuario", None)
    if isinstance(usuario, dict):
        return usuario.get("rol")
    return None


def _reflejar_estado_pieza(
    publicacion_id: str, nivel_decidido: dict[str, Any]
) -> dict[str, Any] | None:
    """Aplica el estado GLOBAL de la cadena al `estado` editorial de la publicacion.

    Lee la cadena de la pieza, la resume con `dominio.colaboracion` y traduce ese estado
    global al estado editorial que el resto del flujo (y el programador) entiende. Ademas,
    propaga al registro publico de la publicacion los campos de revision legados
    (`revisor_*`/`revisado_en`) tomados de la ULTIMA decision, para que la cola/UI sigan
    mostrando quien revisó y cuándo. Devuelve la publicacion actualizada.
    """
    cadena = repos.listar_aprobaciones(publicacion_id)
    estado_global = colaboracion.estado_cadena(cadena)
    estado_pieza = colaboracion.estado_publicacion_para(estado_global)
    campos: dict[str, Any] = {
        "revisor_id": nivel_decidido.get("decisor_id", "") or "",
        "revisor_nombre": nivel_decidido.get("decisor_nombre", "") or "",
        "revisado_en": nivel_decidido.get("decidido_en", "") or "",
    }
    if estado_pieza is not None:  # None == "sin_cadena": no se toca el estado editorial.
        campos["estado"] = estado_pieza
    return repos.actualizar_publicacion(publicacion_id, campos)


async def _decidir(request: Request, decision: str) -> Response:
    """Forwardea aprobar/rechazar al nivel ACTUAL de la cadena de la publicacion.

    Centraliza el patron: 404 si la pieza no existe; 409 si no hay nivel pendiente que
    decidir (no se mando a revision o la cadena esta parada); delega la regla de "otro par
    de ojos" y de orden en `dominio.colaboracion.decidir`; refleja el estado resultante en
    la pieza.
    """
    publicacion_id = request.path_params["publicacion_id"]
    pub = repos.obtener_publicacion(publicacion_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)

    cadena = repos.listar_aprobaciones(publicacion_id)
    nivel = colaboracion.nivel_actual(cadena)
    if nivel is None:
        return JSONResponse(
            {"error": "Esta publicación no está en revisión."}, status_code=409
        )

    # El autor de la pieza es quien la mando a revision (autor_id de la publicacion).
    autor_pieza_id = pub.get("autor_id", "") or ""
    campos, error = colaboracion.decidir(
        nivel,
        cadena,
        decision,
        autor_de_peticion(request),
        rol=_rol_de_peticion(request),
        autor_pieza_id=autor_pieza_id,
    )
    if error is not None:
        return JSONResponse({"error": error}, status_code=409)

    nivel_decidido = repos.actualizar_aprobacion(nivel["id"], campos)
    if nivel_decidido is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)

    actualizada = _reflejar_estado_pieza(publicacion_id, nivel_decidido)
    if actualizada is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    return JSONResponse({"publicacion": publicacion_a_dict(actualizada)})


async def cola(request: Request) -> Response:
    """Cola de aprobacion: piezas EN REVISION, mas antiguas primero (FIFO de revision).

    Devuelve `{cola: [...], total: N}`. Cada item incluye `autor_nombre`/`autor_id`
    (quien envio) y `enviado_a_revision_en` (cuando), para que el equipo vea que espera
    revision y desde cuando. Lectura: sin cambios respecto al flujo legado.
    """
    pendientes = repos.listar_publicaciones(estado=ESTADO_EN_REVISION)
    # Mas antiguas primero por `enviado_a_revision_en` (lo que lleva mas esperando, arriba).
    pendientes.sort(key=lambda p: p.get("enviado_a_revision_en") or "")
    items = [publicacion_a_dict(p) for p in pendientes]
    return JSONResponse({"cola": items, "total": len(items)})


async def enviar_a_revision(request: Request) -> Response:
    """POST /api/aprobacion/{id}/enviar-a-revision: crea la cadena SIMPLE y deja en revision.

    Equivale a la vieja transicion borrador->en_revision, pero montando una cadena de un
    solo nivel ("otro par de ojos") sobre la pieza. Solo desde `borrador`. 409 si no lo esta.
    """
    publicacion_id = request.path_params["publicacion_id"]
    pub = repos.obtener_publicacion(publicacion_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    if pub.get("estado") != "borrador":
        return JSONResponse(
            {"error": "Solo se puede enviar a revisión una pieza en borrador."},
            status_code=409,
        )

    autor = autor_de_peticion(request) or {}
    # `contenido_id` no viaja en el dict publico de la publicacion; se lee de la fila
    # plataforma (la publicacion ES esa fila: su id es el `plataforma_id`).
    plat = repos.obtener_contenido_plataforma(publicacion_id)
    # Crea la cadena SIMPLE (1 nivel pendiente) y marca la pieza en revision, fijando autoria
    # y el sello de envio (lo que la cola muestra). El autor original no se pisa si ya existe.
    repos.crear_cadena_aprobacion(
        plataforma_id=publicacion_id,
        contenido_id=(plat or {}).get("contenido_id", "") or "",
        etiquetas=colaboracion.cadena_simple(),
    )
    actualizada = repos.actualizar_publicacion(
        publicacion_id,
        {
            "estado": ESTADO_EN_REVISION,
            "enviado_a_revision_en": datetime.now().isoformat(timespec="seconds"),
            "revisor_id": "",
            "revisor_nombre": "",
            "revisado_en": "",
            "autor_id": pub.get("autor_id") or autor.get("id", ""),
            "autor_nombre": pub.get("autor_nombre") or autor.get("usuario", ""),
        },
    )
    if actualizada is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    return JSONResponse({"publicacion": publicacion_a_dict(actualizada)})


async def aprobar(request: Request) -> Response:
    """POST /api/aprobacion/{id}/aprobar: decide el nivel actual como aprobado (revisor != autor)."""
    return await _decidir(request, DECISION_APROBADO)


async def rechazar(request: Request) -> Response:
    """POST /api/aprobacion/{id}/rechazar: decide el nivel actual como rechazado (vuelve a borrador)."""
    return await _decidir(request, DECISION_RECHAZADO)


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

    NO es aprobacion: es programacion, y se conserva intacta. Solo se puede programar una
    pieza APROBADA (el humano ya la aprobó vía la cadena). NO publica: deja la pieza en
    `programado` con su `fecha_programada`; el programador del servidor la PREPARA (dry-run)
    al vencer. Posteo real (vía Metricool) GATED por `KENI_PUBLICAR_REAL`. 404 si no existe;
    409 si no está aprobada; 400 si la fecha no es válida/futura.
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
