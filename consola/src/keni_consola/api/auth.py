"""API Auth: login user/pass, logout, sesion actual y cambio de contrasena (#130).

Endpoints (todos bajo `/api/auth`, CONTRATO con el frontend):

  - POST /api/auth/login    {usuario, password} -> 200 {usuario:{...}} + cookie de sesion.
    401 GENERICO ("Usuario o contrasena incorrectos") sin revelar si el usuario existe.
  - POST /api/auth/logout   -> 204; invalida la sesion server-side y borra la cookie.
  - GET  /api/auth/me       -> 200 {usuario:{...}} si hay sesion; 401 si no.
  - POST /api/auth/cambiar-password {password_actual, password_nueva} -> 204
    (sirve para el cambio FORZADO al primer acceso y el voluntario; valida la actual).

La barrera de credencial la aplica el middleware `SeguridadConsola`: `/api/auth/login`
es PUBLICO (crea la sesion), el resto exige sesion o token de bootstrap. La cookie de
sesion es HttpOnly + SameSite=Strict (no la lee JS; el navegador no la manda cross-site).

`auth.py` (modulo de dominio) hace el trabajo real (hash, sesiones, anti fuerza bruta);
aqui solo va el contrato HTTP y la gestion de la cookie.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import auth
from .._http_json import leer_json

# Mensaje GENERICO de login fallido: NO revela si el usuario existe (anti enumeracion).
_MSG_LOGIN_KO = "Usuario o contraseña incorrectos."


def _set_cookie_sesion(resp: Response, token: str) -> None:
    """Siembra la cookie de sesion: HttpOnly, SameSite=Strict, path=/ (CONTRATO).

    `max_age` acompana a la expiracion server-side para que el navegador la descarte
    cuando caduca. HttpOnly: el JS no la lee (defensa anti-XSS de robo de sesion).
    """
    resp.set_cookie(
        auth.COOKIE_SESION,
        token,
        httponly=True,
        samesite="strict",
        path="/",
        max_age=auth.horas_sesion() * 3600,
    )


def _borrar_cookie_sesion(resp: Response) -> None:
    """Borra la cookie de sesion (logout)."""
    resp.delete_cookie(auth.COOKIE_SESION, path="/")


async def login(request: Request) -> Response:
    """POST /api/auth/login: valida credenciales, abre sesion y siembra la cookie."""
    datos = await leer_json(request)
    usuario = datos.get("usuario")
    password = datos.get("password")
    if not isinstance(usuario, str) or not isinstance(password, str) or not usuario or not password:
        # Mismo mensaje generico que un fallo de credenciales (no damos pistas).
        return JSONResponse({"error": _MSG_LOGIN_KO}, status_code=401)

    autenticado = auth.autenticar(usuario, password)
    if autenticado is None:
        return JSONResponse({"error": _MSG_LOGIN_KO}, status_code=401)

    token = auth.crear_sesion(autenticado["id"])
    resp = JSONResponse(
        {
            "usuario": {
                "id": autenticado["id"],
                "usuario": autenticado["usuario"],
                "rol": autenticado["rol"],
                "debe_cambiar_password": autenticado["debe_cambiar_password"],
            }
        }
    )
    _set_cookie_sesion(resp, token)
    return resp


async def logout(request: Request) -> Response:
    """POST /api/auth/logout: invalida la sesion (si la hay) y borra la cookie (204)."""
    token = request.cookies.get(auth.COOKIE_SESION)
    if token:
        auth.borrar_sesion(token)
    resp = Response(status_code=204)
    _borrar_cookie_sesion(resp)
    return resp


async def me(request: Request) -> Response:
    """GET /api/auth/me: el usuario de la sesion actual (401 si se entro por token)."""
    usuario = getattr(request.state, "usuario", None)
    if usuario is None:
        return JSONResponse({"error": "No hay sesión iniciada."}, status_code=401)
    return JSONResponse(
        {
            "usuario": {
                "id": usuario["id"],
                "usuario": usuario["usuario"],
                "rol": usuario["rol"],
                "debe_cambiar_password": usuario["debe_cambiar_password"],
            }
        }
    )


async def cambiar_password(request: Request) -> Response:
    """POST /api/auth/cambiar-password: cambia la contrasena del usuario de la sesion (204).

    Sirve para el cambio FORZADO (primer acceso con `debe_cambiar_password`) y el
    voluntario. Valida la contrasena actual y la fuerza minima de la nueva. Solo opera
    sobre la PROPIA cuenta (la de la sesion): por token de bootstrap no hay usuario, 401.
    """
    usuario = getattr(request.state, "usuario", None)
    if usuario is None:
        return JSONResponse(
            {"error": "Necesitas una sesión iniciada para cambiar la contraseña."},
            status_code=401,
        )

    datos = await leer_json(request)
    actual = datos.get("password_actual")
    nueva = datos.get("password_nueva")
    if not isinstance(actual, str) or not actual:
        return JSONResponse({"error": "Falta la contraseña actual."}, status_code=400)
    if not auth.password_aceptable(nueva):
        return JSONResponse(
            {"error": f"La contraseña nueva debe tener al menos {auth.LONGITUD_MIN_PASSWORD} caracteres."},
            status_code=400,
        )
    if not auth.verificar_password_actual(usuario["id"], actual):
        return JSONResponse({"error": "La contraseña actual no es correcta."}, status_code=400)

    auth.establecer_password(usuario["id"], nueva, debe_cambiar_password=False)
    return Response(status_code=204)


RUTAS = [
    Route("/api/auth/login", login, methods=["POST"]),
    Route("/api/auth/logout", logout, methods=["POST"]),
    Route("/api/auth/me", me, methods=["GET"]),
    Route("/api/auth/cambiar-password", cambiar_password, methods=["POST"]),
]
