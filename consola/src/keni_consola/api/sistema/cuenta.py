"""Cuenta de Claude del servidor (panel ADMIN): proxy del `back` al control del `daemons`.

El `back` NO ejecuta `claude` (solo encola); quien gestiona la cuenta es el proceso
`daemons` por su listener de CONTROL (`control.py` + `cuenta_claude.py`). Estas rutas son la
cara ADMIN de ese control: validan la sesion admin (la info y, sobre todo, el CAMBIO de
cuenta son sensibles) y REENVIAN por la red interna a `KENI_CONTROL_URL` con el bearer
efectivo (auto-persistido en /data; sin configurar nada). ACTIVO por defecto: si el control no
responde (daemons caido), `disponible:false` con el error, en vez de 500.

Soporta DOS cuentas (`?cuenta=a|b`, def 'a'): A es la cuenta historica (config-dir heredado);
B vive en `/data/claude-cfg-b` (split por marcas). El selector se reenvia al control tal cual;
la cuenta A queda IDENTICA (no se anade query). `login/codigo` y `login/cancelar` van por id de
sesion (no llevan selector).

Endpoints (bajo `/api/sistema/cuenta`, CONTRATO con el frontend):
  - GET  /api/sistema/cuenta              -> {disponible, auth:{...}, uso:{...}}  (?cuenta=a|b)
  - POST /api/sistema/cuenta/login/iniciar-> {sesion, url, salida} | {error}  (?cuenta=a|b)
  - POST /api/sistema/cuenta/login/codigo -> {ok, mensaje, salida}
  - POST /api/sistema/cuenta/login/cancelar-> {ok}
  - POST /api/sistema/cuenta/logout       -> {ok, mensaje}  (?cuenta=a|b)
"""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ... import config, cuenta_claude
from ._comun import _es_admin, _logger, _rechazo_no_admin

# Timeout del proxy al control. Generoso: `login/iniciar` espera a que `claude` emita la URL
# (roundtrip OAuth) y `login/codigo` a que cierre el login.
_TIMEOUT_PROXY = 90.0


def _llamar_control(metodo: str, ruta: str, json: dict | None = None) -> tuple[int, dict]:
    """Llama al control del `daemons` (httpx sincrono; se invoca en el threadpool).

    Devuelve (status, payload). Cualquier fallo de red/timeout se traduce a un payload de
    error legible con status 502 (la seccion degrada, nunca casca)."""
    import httpx

    base = config.control_url().rstrip("/")
    bearer = cuenta_claude.bearer_efectivo()
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


def _con_cuenta(request: Request, ruta: str) -> str:
    """Anade `?cuenta=b` a la ruta del control si la peticion selecciona la cuenta B.

    La cuenta A (def) deja la ruta INTACTA: su contrato con el control no cambia. Solo se
    aceptan 'a'|'b'; cualquier otro valor cae a 'a' (la ruta queda intacta)."""
    cuenta = (request.query_params.get("cuenta") or "a").strip().lower()
    return f"{ruta}?cuenta=b" if cuenta == "b" else ruta


async def _proxy(request: Request, metodo: str, ruta: str, *, leer_cuerpo: bool) -> Response:
    """Patron comun: admin-gated + reenvio al control del daemons (con selector de cuenta)."""
    if not _es_admin(request):
        return _rechazo_no_admin()
    ruta = _con_cuenta(request, ruta)
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
    ruta = _con_cuenta(request, "/control/cuenta/estado")
    status, payload = await run_in_threadpool(_llamar_control, "GET", ruta)
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
