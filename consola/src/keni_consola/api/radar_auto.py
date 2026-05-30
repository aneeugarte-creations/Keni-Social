"""API de la AUTO-PROMOCION del Radar (fase3): bandeja revisable + ejecucion a demanda.

La logica vive en `radar_auto.py`. Aqui solo dos endpoints, para que "lo importante del dia"
no dependa de un clic manual pero siga siendo SEGURO y REVISABLE:

  GET  /api/radar/auto/bandeja   -> temas que se promoverian AHORA (sin escribir nada) +
                                    la config viva (activo, umbral, geo, max). Lectura.
  POST /api/radar/auto/ejecutar  -> ejecuta el batch (promueve a `flujo='importante'`).
                                    SOLO ADMIN: es una accion que escribe en el tablero.

El daemon (`radar_auto.iniciar_radar_auto`, gateado por `KENI_RADAR_AUTO`) hace lo mismo en
bucle; estos endpoints permiten al equipo VER y disparar el batch sin esperar al daemon.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import config, permisos, radar_auto


def _config_viva() -> dict[str, object]:
    """Config actual de la auto-promocion (para que la UI muestre el modo y los umbrales)."""
    return {
        "activo": config.radar_auto_activo(),
        "umbral": config.radar_auto_umbral(),
        "geo": config.radar_auto_geo(),
        "max_por_barrido": config.radar_auto_max(),
        "intervalo_horas": config.radar_auto_intervalo_horas(),
        "marca": config.radar_auto_marca(),
    }


async def bandeja(request: Request) -> Response:
    """GET /api/radar/auto/bandeja: temas que se auto-promoverian ahora (sin escribir).

    Respuesta `{config, temas:[{titulo, senal, por_que, ...}], total}`. Si el daemon esta
    apagado, la bandeja igual se calcula (es informativa): asi el equipo ve que ENTRARIA si
    lo activara o si pulsa "ejecutar".
    """
    temas = radar_auto.previsualizar_bandeja()
    return JSONResponse({"config": _config_viva(), "temas": temas, "total": len(temas)})


async def ejecutar(request: Request) -> Response:
    """POST /api/radar/auto/ejecutar: promueve el batch a `flujo='importante'` (SOLO ADMIN).

    Respuesta `{promovidos:[{contenido}], total}`. Es la MISMA promocion que hace el daemon,
    a demanda. Restringido a admin porque escribe en el tablero compartido.
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(
            "Solo un administrador puede ejecutar la auto-promoción del Radar."
        )
    creados = radar_auto.ejecutar_barrido()
    return JSONResponse({"promovidos": creados, "total": len(creados)})


RUTAS = [
    Route("/api/radar/auto/bandeja", bandeja, methods=["GET"]),
    Route("/api/radar/auto/ejecutar", ejecutar, methods=["POST"]),
]
