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

from .. import auth, seguridad
from .._http_json import leer_json

# Mensaje GENERICO de login fallido: NO revela si el usuario existe (anti enumeracion).
_MSG_LOGIN_KO = "Usuario o contraseña incorrectos."


def _set_cookie_sesion(resp: Response, token: str) -> None:
    """Siembra la cookie de sesion: HttpOnly, SameSite=Strict, path=/ (CONTRATO).

    `max_age` acompana a la expiracion server-side para que el navegador la descarte
    cuando caduca. HttpOnly: el JS no la lee (defensa anti-XSS de robo de sesion).
    `Secure` (cuando va detras de un proxy TLS, #130): la cookie no viaja por HTTP plano.
    """
    resp.set_cookie(
        auth.COOKIE_SESION,
        token,
        httponly=True,
        samesite="strict",
        secure=seguridad.cookie_secure(),
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
    if len(password) > auth.LONGITUD_MAX_PASSWORD or len(usuario) > auth.LONGITUD_MAX_USUARIO:
        # Tope anti-DoS: no hasheamos (scrypt) entradas absurdamente largas. Generico.
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
    """GET /api/auth/me: el usuario de la sesion actual (401 si se entro por token).

    Devuelve, ademas del nucleo de sesion, `creado` y `ultimo_acceso` para que la
    pagina "Mi cuenta" muestre los datos de la cuenta sin un endpoint aparte. (El
    login mantiene su forma minima de 4 campos; estos extras solo llegan por `me`.)
    """
    usuario = getattr(request.state, "usuario", None)
    if usuario is None:
        return JSONResponse({"error": "No hay sesión iniciada."}, status_code=401)
    # `marcas` (organigrama AMX): se consultan SIEMPRE porque la sesion del middleware
    # no las arrastra (la cookie no carga la tabla N:M). La pagina de Mi cuenta y el filtro
    # de la rota las usan para saber a que verticales pertenece la persona.
    refrescado = auth.obtener_usuario_por_id(usuario["id"]) or {}
    return JSONResponse(
        {
            "usuario": {
                "id": usuario["id"],
                "usuario": usuario["usuario"],
                "rol": usuario["rol"],
                "debe_cambiar_password": usuario["debe_cambiar_password"],
                "creado": usuario.get("creado", ""),
                "ultimo_acceso": usuario.get("ultimo_acceso", ""),
                "cargo": refrescado.get("cargo", "") or usuario.get("cargo", "") or "",
                "cobertura": bool(refrescado.get("cobertura") or usuario.get("cobertura")),
                "marcas": list(refrescado.get("marcas") or []),
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
            {
                "error": (
                    f"La contraseña nueva debe tener entre {auth.LONGITUD_MIN_PASSWORD} "
                    f"y {auth.LONGITUD_MAX_PASSWORD} caracteres."
                )
            },
            status_code=400,
        )
    # Tope anti-DoS en la actual (no hasheamos una entrada enorme); cuenta como incorrecta.
    if len(actual) > auth.LONGITUD_MAX_PASSWORD or not auth.verificar_password_actual(usuario["id"], actual):
        return JSONResponse({"error": "La contraseña actual no es correcta."}, status_code=400)

    auth.establecer_password(usuario["id"], nueva, debe_cambiar_password=False)
    # `establecer_password` invalida TODAS las sesiones del usuario (seguridad). Para no
    # forzar un re-login en el cambio voluntario, reabrimos UNA sesion nueva (rotacion)
    # y la sembramos en la cookie del dispositivo actual.
    token = auth.crear_sesion(usuario["id"])
    resp = Response(status_code=204)
    _set_cookie_sesion(resp, token)
    return resp


RUTAS = [
    Route("/api/auth/login", login, methods=["POST"]),
    Route("/api/auth/logout", logout, methods=["POST"]),
    Route("/api/auth/me", me, methods=["GET"]),
    Route("/api/auth/cambiar-password", cambiar_password, methods=["POST"]),
]
