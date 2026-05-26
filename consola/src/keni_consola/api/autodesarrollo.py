"""API Auto-desarrollo del buzón (/api/autodesarrollo): flag, disparo y auditoría.

Capa HTTP del lazo de auto-desarrollo (#109). La LÓGICA y los 6 gates de seguridad
viven en el dominio `consola.autodesarrollo`; aquí solo se serializa a JSON y se valida
la entrada. El lazo está DESACTIVADO por defecto (gate 1); activarlo exige confirmar el
riesgo de forma explícita.

  - `GET  /api/autodesarrollo`            -> estado: flag, cap de líneas, si hay flag por
                                             entorno (kill switch), y la auditoría reciente.
  - `POST /api/autodesarrollo/flag`       -> activa/desactiva el lazo. Activar requiere
                                             `{activo:true, confirmo_riesgo:true}`.
  - `POST /api/autodesarrollo/implementar`-> dispara la implementación de UNA sugerencia
                                             EN BACKGROUND (no bloquea). 409 si flag OFF.

SEGURIDAD: el disparo NUNCA corre el lazo de forma síncrona en la petición; lo lanza en
background (`disparar_implementacion`, INYECTABLE para tests). Con el flag OFF, el
endpoint de disparo responde 409 sin tocar nada.
"""

from __future__ import annotations

import threading

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import autodesarrollo, sugerencias
from .._http_json import leer_json


def disparar_implementacion(sugerencia: dict) -> None:
    """Lanza el lazo de implementación EN BACKGROUND (hilo daemon). INYECTABLE en tests.

    Los tests reemplazan esta función por una fake síncrona/no-op para que NUNCA se cree
    un worktree, ni se llame a `claude`, ni se haga push real. La implementación real solo
    arranca un hilo que ejecuta `autodesarrollo.implementar` (que ya respeta los 6 gates).
    """
    hilo = threading.Thread(
        target=autodesarrollo.implementar, args=(sugerencia,), daemon=True,
        name=f"autodes-{sugerencia.get('id', '')}",
    )
    hilo.start()


def _estado_dict() -> dict:
    """Instantánea del estado del lazo para la UI (flag, cap, kill switch, auditoría)."""
    import os

    return {
        "activo": autodesarrollo.flag_activo(),
        # True si el flag viene del ENTORNO (kill switch en caliente): la UI no puede
        # apagarlo por config en ese caso y lo advierte.
        "fijado_por_entorno": os.environ.get("KENI_AUTODESARROLLO") is not None,
        "cap_lineas": autodesarrollo.cap_lineas(),
        "auditoria": autodesarrollo.leer_auditoria(),
        "estados": list(autodesarrollo.ESTADOS),
    }


async def estado(request: Request) -> Response:
    """Estado del lazo + auditoría reciente."""
    return JSONResponse(_estado_dict())


async def cambiar_flag(request: Request) -> Response:
    """Activa/desactiva el lazo. Activar exige `{activo:true, confirmo_riesgo:true}`."""
    datos = await leer_json(request)
    activo = datos.get("activo")
    if not isinstance(activo, bool):
        return JSONResponse({"error": "Indica 'activo' como verdadero o falso."}, status_code=400)

    import os

    if os.environ.get("KENI_AUTODESARROLLO") is not None:
        return JSONResponse(
            {"error": "El lazo está fijado por la variable de entorno KENI_AUTODESARROLLO; "
                      "cámbiala ahí (kill switch en caliente)."},
            status_code=409,
        )

    if activo and datos.get("confirmo_riesgo") is not True:
        return JSONResponse(
            {"error": "Activar el auto-desarrollo es peligroso (la app implementa y mergea "
                      "sola). Debes confirmar el riesgo explícitamente."},
            status_code=400,
        )

    autodesarrollo.guardar_flag(activo)
    mensaje = (
        "Auto-desarrollo ACTIVADO. La app podrá implementar y mergear sugerencias sola "
        "(con sandbox y gates). Desactívalo cuando termines."
        if activo
        else "Auto-desarrollo desactivado. El buzón vuelve a solo recoger sugerencias."
    )
    return JSONResponse({**_estado_dict(), "mensaje": mensaje})


async def implementar(request: Request) -> Response:
    """Dispara la implementación de una sugerencia `{sugerencia_id}` EN BACKGROUND.

    409 si el flag está OFF (gate 1). 404 si la sugerencia no existe. 200 con un aviso si
    se lanzó (el resultado se consulta luego en la auditoría: mergeado/parked/rechazado).
    """
    if not autodesarrollo.flag_activo():
        return JSONResponse(
            {"error": "El auto-desarrollo está desactivado. Actívalo primero (es peligroso)."},
            status_code=409,
        )
    datos = await leer_json(request)
    sid = datos.get("sugerencia_id")
    if not isinstance(sid, str) or not sid:
        return JSONResponse({"error": "Falta la sugerencia."}, status_code=400)
    sugerencia = next((s for s in sugerencias.listar() if s["id"] == sid), None)
    if sugerencia is None:
        return JSONResponse({"error": "Esa sugerencia ya no existe."}, status_code=404)

    disparar_implementacion(sugerencia)
    return JSONResponse(
        {"mensaje": "Implementación lanzada en segundo plano. Revisa la auditoría para ver "
                    "si se mergeó, quedó para revisión (parked) o se rechazó."}
    )


RUTAS = [
    Route("/api/autodesarrollo", estado, methods=["GET"]),
    Route("/api/autodesarrollo/flag", cambiar_flag, methods=["POST"]),
    Route("/api/autodesarrollo/implementar", implementar, methods=["POST"]),
]
