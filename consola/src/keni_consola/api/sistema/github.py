"""Cuenta de GitHub del servidor (panel ADMIN): proxy del `back` al control del `daemons`.

Gemelo de `cuenta.py`: el `back` NO ejecuta `gh` (solo encola); quien gestiona la cuenta de
GitHub es el proceso `daemons` por su listener de CONTROL (`control.py` + `proveedor_github.py`).
Estas rutas son la cara ADMIN de ese control: validan la sesion admin (conectar/desconectar la
cuenta de GitHub es sensible) y REENVIAN por la red interna a `KENI_CONTROL_URL` con el bearer
efectivo (auto-persistido en /data; sin configurar nada). ACTIVO por defecto: si el control no
responde (daemons caido), `disponible:false` con el error, en vez de 500.

Reusa el cliente de control (`_llamar_control`) y el patron admin-gated (`_proxy`) de `cuenta.py`:
un unico proxy para todo el listener de control.

Endpoints (bajo `/api/sistema/github`, CONTRATO con el frontend):
  - GET  /api/sistema/github                -> {disponible, auth:{logueado, usuario?, scopes?}}
  - POST /api/sistema/github/login/iniciar  -> {sesion, codigo, url, salida} | {error}
  - POST /api/sistema/github/login/confirmar-> {ok, mensaje}
  - POST /api/sistema/github/login/cancelar -> {ok}
  - POST /api/sistema/github/logout         -> {ok, mensaje}
"""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ._comun import _es_admin, _rechazo_no_admin
from .cuenta import _llamar_control, _proxy


async def github(request: Request) -> Response:
    """GET /api/sistema/github: estado de auth de GitHub (admin)."""
    if not _es_admin(request):
        return _rechazo_no_admin()
    status, payload = await run_in_threadpool(_llamar_control, "GET", "/control/github/estado")
    payload["disponible"] = status == 200
    return JSONResponse(payload, status_code=200 if status == 200 else status)


async def login_iniciar(request: Request) -> Response:
    """POST /api/sistema/github/login/iniciar: lanza el device flow, devuelve code+url (admin)."""
    return await _proxy(request, "POST", "/control/github/login/iniciar", leer_cuerpo=True)


async def login_confirmar(request: Request) -> Response:
    """POST /api/sistema/github/login/confirmar: espera a que gh complete el sondeo (admin)."""
    return await _proxy(request, "POST", "/control/github/login/confirmar", leer_cuerpo=True)


async def login_cancelar(request: Request) -> Response:
    """POST /api/sistema/github/login/cancelar: cancela un login en curso (admin)."""
    return await _proxy(request, "POST", "/control/github/login/cancelar", leer_cuerpo=True)


async def logout(request: Request) -> Response:
    """POST /api/sistema/github/logout: cierra la sesion de GitHub del servidor (admin)."""
    return await _proxy(request, "POST", "/control/github/logout", leer_cuerpo=False)
