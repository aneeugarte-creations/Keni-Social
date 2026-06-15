"""Cuenta de Claude del servidor (panel ADMIN): proxy del `back` al control del `daemons`.

El `back` NO ejecuta `claude` (solo encola); quien gestiona la cuenta es el proceso
`daemons` por su listener de CONTROL (`control.py` + `cuenta_claude.py`). Estas rutas son la
cara ADMIN de ese control: validan la sesion admin (la info y, sobre todo, el CAMBIO de
cuenta son sensibles) y REENVIAN por la red interna a `KENI_CONTROL_URL` con el bearer
`KENI_CONTROL_BEARER`. Sin control configurado (sin bearer), degradan con un payload claro
(`disponible:false`) en vez de 500: la seccion avisa "no configurado".

Endpoints (bajo `/api/sistema/cuenta`, CONTRATO con el frontend):
  - GET  /api/sistema/cuenta              -> {disponible, auth:{...}, uso:{...}}
  - POST /api/sistema/cuenta/login/iniciar-> {sesion, url, salida} | {error}
  - POST /api/sistema/cuenta/login/codigo -> {ok, mensaje, salida}
  - POST /api/sistema/cuenta/login/cancelar-> {ok}
  - POST /api/sistema/cuenta/logout       -> {ok, mensaje}
"""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ... import config
from ._comun import _es_admin, _logger, _rechazo_no_admin

# Timeout del proxy al control. Generoso: `login/iniciar` espera a que `claude` emita la URL
# (roundtrip OAuth) y `login/codigo` a que cierre el login.
_TIMEOUT_PROXY = 90.0


def _control_configurado() -> bool:
    return bool(config.control_bearer())


def _llamar_control(metodo: str, ruta: str, json: dict | None = None) -> tuple[int, dict]:
    """Llama al control del `daemons` (httpx sincrono; se invoca en el threadpool).

    Devuelve (status, payload). Cualquier fallo de red/timeout se traduce a un payload de
    error legible con status 502 (la seccion degrada, nunca casca)."""
    import httpx

    base = config.control_url().rstrip("/")
    bearer = config.control_bearer() or ""
    url = f"{base}{ruta}"
    cabeceras = {"Authorization": f"Bearer {bearer}"}
    try:
        with httpx.Client(timeout=_TIMEOUT_PROXY) as cliente:
            if metodo == "GET":
                r = cliente.get(url, headers=cabeceras)
            else:
                r = cliente.post(url, headers=cabeceras, json=json or {})
        try:
            payload = r.json()
        except ValueError:
            payload = {"error": "respuesta no JSON del control"}
        return r.status_code, (payload if isinstance(payload, dict) else {"error": "payload inesperado"})
    except httpx.HTTPError as e:
        _logger.warning("fallo al alcanzar el control del daemons (%s %s): %s", metodo, ruta, e)
        return 502, {"error": "no se pudo contactar el control del servidor"}


async def _proxy(request: Request, metodo: str, ruta: str, *, leer_cuerpo: bool) -> Response:
    """Patron comun: admin-gated + control configurado + reenvio al control."""
    if not _es_admin(request):
        return _rechazo_no_admin()
    if not _control_configurado():
        return JSONResponse(
            {"disponible": False, "error": "gestion de cuenta no configurada en este servidor"},
            status_code=200,
        )
    cuerpo: dict | None = None
    if leer_cuerpo:
        try:
            datos = await request.json()
            cuerpo = datos if isinstance(datos, dict) else {}
        except Exception:  # noqa: BLE001 -- cuerpo ausente/no-JSON: lo tratamos como vacio
            cuerpo = {}
    status, payload = await run_in_threadpool(_llamar_control, metodo, ruta, cuerpo)
    return JSONResponse(payload, status_code=status)


async def cuenta(request: Request) -> Response:
    """GET /api/sistema/cuenta: estado de auth + medidor de uso (admin)."""
    if not _es_admin(request):
        return _rechazo_no_admin()
    if not _control_configurado():
        return JSONResponse({"disponible": False})
    status, payload = await run_in_threadpool(_llamar_control, "GET", "/control/cuenta/estado")
    payload["disponible"] = status == 200
    return JSONResponse(payload, status_code=200 if status == 200 else status)


async def login_iniciar(request: Request) -> Response:
    """POST /api/sistema/cuenta/login/iniciar: lanza el login, devuelve la URL (admin)."""
    return await _proxy(request, "POST", "/control/cuenta/login/iniciar", leer_cuerpo=True)


async def login_codigo(request: Request) -> Response:
    """POST /api/sistema/cuenta/login/codigo: pega el codigo de autorizacion (admin)."""
    return await _proxy(request, "POST", "/control/cuenta/login/codigo", leer_cuerpo=True)


async def login_cancelar(request: Request) -> Response:
    """POST /api/sistema/cuenta/login/cancelar: cancela un login en curso (admin)."""
    return await _proxy(request, "POST", "/control/cuenta/login/cancelar", leer_cuerpo=True)


async def logout(request: Request) -> Response:
    """POST /api/sistema/cuenta/logout: cierra la sesion de Claude del servidor (admin)."""
    return await _proxy(request, "POST", "/control/cuenta/logout", leer_cuerpo=False)
