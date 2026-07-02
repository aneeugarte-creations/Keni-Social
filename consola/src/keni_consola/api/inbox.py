"""API Inbox: LECTURA del buzón de redes (mensajes directos + comentarios) por marca.

SOLO lectura: expone lo que la audiencia escribe (DMs y comentarios de publicaciones de
Facebook e Instagram) para que una persona lo lea y actúe con criterio. NADA de responder
ni escribir (eso es otra capa). Consume `keni_metricas.servicio`, que lee de Metricool y
degrada por red (una red sin buzón habilitado se omite, no rompe el resto).

`?marca=` es OBLIGATORIO: se acepta tanto el `id_metricas` (forma guion_bajo, como lo pasa
el dashboard) como el id canónico; una marca desconocida responde 400. La respuesta agrupa
por red y sella `generado_en` (ISO) para "Actualizado hace X".
"""

from __future__ import annotations

import logging

from keni_metricas import servicio
from keni_shared import marcas
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from ..tiempo import ahora_iso

_log = logging.getLogger("keni_consola.api.inbox")

# Ventana por defecto y tope (días) de los comentarios. El endpoint de Metricool es de alto
# volumen; se acota a una ventana corta. El tope evita barridos accidentales muy largos.
_DIAS_COMENTARIOS_DEFECTO = 7
_DIAS_COMENTARIOS_MAX = 30


def _resolver_marca(raw: str | None) -> str | None:
    """Resuelve `?marca=` a su `id_metricas` (frontera de métricas), o None si no existe.

    Acepta el `id_metricas` (guion_bajo, como lo pasa el dashboard) y el id canónico
    (guion-medio). None = marca ausente o desconocida (el endpoint responde 400).
    """
    marca = (raw or "").strip()
    if not marca:
        return None
    if marcas.marca_por_id_metricas(marca) is not None:
        return marca
    if marcas.es_marca(marca):
        return marcas.id_metricas_de(marca)
    return None


def _validar_dias(raw: str | None) -> int:
    """Ventana de comentarios: entero acotado a [1, _DIAS_COMENTARIOS_MAX]; def 7 si falta/inválido."""
    try:
        dias = int(raw) if raw not in (None, "") else _DIAS_COMENTARIOS_DEFECTO
    except (TypeError, ValueError):
        return _DIAS_COMENTARIOS_DEFECTO
    return max(1, min(dias, _DIAS_COMENTARIOS_MAX))


async def conversaciones(request: Request) -> Response:
    """GET /api/inbox/conversaciones: mensajes directos (DMs) de una marca, agrupados por red.

    `?marca=` obligatorio (desconocida → 400). Responde `{"por_red": [{red, conversaciones:[...]}],
    "generado_en"}`. Degrada por red: una red sin buzón habilitado se omite. Computado al vuelo.
    """
    marca = _resolver_marca(request.query_params.get("marca"))
    if marca is None:
        return JSONResponse({"error": "Falta una marca válida (?marca=)."}, status_code=400)
    try:
        payload = await run_in_threadpool(servicio.construir_inbox_conversaciones, marca)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        _log.exception("Fallo al leer las conversaciones (marca=%s).", marca)
        return JSONResponse({"error": "No se pudo leer las conversaciones."}, status_code=500)
    return JSONResponse({**payload, "generado_en": ahora_iso()})


async def comentarios(request: Request) -> Response:
    """GET /api/inbox/comentarios: comentarios de publicaciones de una marca, agrupados por red.

    `?marca=` obligatorio (desconocida → 400); `?dias=` acota la ventana (def 7, máx 30).
    Responde `{"por_red": [{red, comentarios:[...]}], "dias", "generado_en"}`. Degrada por red.
    Computado al vuelo (endpoint de alto volumen: ventana corta + troceo por día en la fuente).
    """
    marca = _resolver_marca(request.query_params.get("marca"))
    if marca is None:
        return JSONResponse({"error": "Falta una marca válida (?marca=)."}, status_code=400)
    dias = _validar_dias(request.query_params.get("dias"))
    try:
        payload = await run_in_threadpool(servicio.construir_inbox_comentarios, marca, dias)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        _log.exception("Fallo al leer los comentarios (marca=%s, dias=%s).", marca, dias)
        return JSONResponse({"error": "No se pudo leer los comentarios."}, status_code=500)
    return JSONResponse({**payload, "dias": dias, "generado_en": ahora_iso()})


RUTAS = [
    Route("/api/inbox/conversaciones", conversaciones, methods=["GET"]),
    Route("/api/inbox/comentarios", comentarios, methods=["GET"]),
]
