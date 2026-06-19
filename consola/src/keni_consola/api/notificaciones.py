"""API de NOTIFICACIONES in-app (el "cajon" de la campana, junto al selector de marca).

El reparto (a quien se notifica cuando pasa algo) vive en `dominio/notificaciones.py` y lo
disparan otros api/* (colaboracion, contenido). Aqui solo se LEE el buzon del usuario de la
sesion y se marcan leidas. Todo esta acotado a la MARCA activa (`?marca_id=`): el cajon solo
muestra la marca seleccionada en el switch.

ENDPOINTS
  GET  /api/notificaciones[?marca_id=]            buzon (mas recientes primero) + no_leidas
  GET  /api/notificaciones/contador[?marca_id=]   solo el contador no_leidas (sondeo ligero)
  POST /api/notificaciones/{id}/leer              marca UNA como leida (solo del usuario)
  POST /api/notificaciones/leer-todas[?marca_id=] marca TODAS como leidas
  GET  /api/notificaciones/menciones-candidatos?marca_id=
                                                  usuarios de la marca para el autocompletado @
"""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import auth, repos
from ..seguridad import autor_de_peticion


def _usuario_id(request: Request) -> str | None:
    autor = autor_de_peticion(request)
    return autor.get("id") if autor else None


def _marca(request: Request) -> str | None:
    """Marca activa del cajon (`?marca_id=`). Vacio/ausente = todas las marcas del usuario."""
    marca = request.query_params.get("marca_id")
    marca = (marca or "").strip()
    return marca or None


def _listar(usuario_id: str, marca_id: str | None) -> dict:
    notificaciones = repos.listar_notificaciones(usuario_id, marca_id)
    no_leidas = repos.contar_notificaciones_no_leidas(usuario_id, marca_id)
    return {
        "notificaciones": notificaciones,
        "no_leidas": no_leidas,
        "total": len(notificaciones),
    }


async def listar(request: Request) -> Response:
    """GET /api/notificaciones: buzon del usuario (acotado a la marca activa) + no_leidas."""
    usuario_id = _usuario_id(request)
    if not usuario_id:
        return JSONResponse({"notificaciones": [], "no_leidas": 0, "total": 0})
    marca_id = _marca(request)
    cuerpo = await run_in_threadpool(_listar, usuario_id, marca_id)
    return JSONResponse(cuerpo)


async def contador(request: Request) -> Response:
    """GET /api/notificaciones/contador: solo el numero de no leidas (para el sondeo del badge)."""
    usuario_id = _usuario_id(request)
    if not usuario_id:
        return JSONResponse({"no_leidas": 0})
    no_leidas = await run_in_threadpool(
        repos.contar_notificaciones_no_leidas, usuario_id, _marca(request)
    )
    return JSONResponse({"no_leidas": no_leidas})


async def marcar_leida(request: Request) -> Response:
    """POST /api/notificaciones/{id}/leer: marca UNA como leida (solo si es del usuario)."""
    usuario_id = _usuario_id(request)
    if not usuario_id:
        return JSONResponse({"error": "Sin sesión."}, status_code=401)
    notificacion_id = request.path_params["notificacion_id"]
    await run_in_threadpool(repos.marcar_notificacion_leida, notificacion_id, usuario_id)
    return JSONResponse({"ok": True})


async def marcar_todas_leidas(request: Request) -> Response:
    """POST /api/notificaciones/leer-todas: marca todas (de la marca activa) como leidas."""
    usuario_id = _usuario_id(request)
    if not usuario_id:
        return JSONResponse({"error": "Sin sesión."}, status_code=401)
    marcadas = await run_in_threadpool(
        repos.marcar_notificaciones_leidas, usuario_id, _marca(request)
    )
    return JSONResponse({"marcadas": marcadas})


def _menciones_candidatos(usuario_id: str, marca_id: str | None) -> dict:
    candidatos = [
        {
            "id": u["id"],
            "nombre": (u.get("nombre") or "").strip() or u.get("usuario", ""),
            "usuario": u.get("usuario", ""),
        }
        for u in auth.listar_usuarios()
        if u["id"] != usuario_id and (not marca_id or marca_id in (u.get("marcas") or []))
    ]
    return {"usuarios": candidatos}


async def menciones_candidatos(request: Request) -> Response:
    """GET /api/notificaciones/menciones-candidatos?marca_id=: usuarios de la marca para el @.

    Devuelve la gente de la marca activa (id + nombre visible + usuario) para alimentar el
    autocompletado de menciones en los comentarios. Excluye a quien pregunta (no te @ a ti).
    Disponible para cualquier sesion (no admin-only): es solo el directorio del workspace.
    """
    usuario_id = _usuario_id(request)
    if not usuario_id:
        return JSONResponse({"usuarios": []})
    marca_id = _marca(request)
    cuerpo = await run_in_threadpool(_menciones_candidatos, usuario_id, marca_id)
    return JSONResponse(cuerpo)


RUTAS = [
    Route("/api/notificaciones", listar, methods=["GET"]),
    Route("/api/notificaciones/contador", contador, methods=["GET"]),
    Route("/api/notificaciones/menciones-candidatos", menciones_candidatos, methods=["GET"]),
    Route("/api/notificaciones/leer-todas", marcar_todas_leidas, methods=["POST"]),
    Route("/api/notificaciones/{notificacion_id}/leer", marcar_leida, methods=["POST"]),
]
