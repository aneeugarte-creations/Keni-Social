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

import json
import logging
import time

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import auth, config, seguridad
from .._http_json import leer_json
from ..observabilidad import NOMBRE_LOGGER

_logger = logging.getLogger(NOMBRE_LOGGER)

# Mensaje GENERICO de login fallido: NO revela si el usuario existe (anti enumeracion).
_MSG_LOGIN_KO = "Usuario o contraseña incorrectos."

# --------------------------------------------------------------------------- #
# MFA (segundo factor TOTP), GATEADO por `KENI_CONSOLA_MFA` (def OFF).          #
# --------------------------------------------------------------------------- #
#
# FLUJO con MFA ON y usuario `mfa_activo`:
#   1) POST /api/auth/login  con user/pass OK -> NO crea sesion. Devuelve 200 {mfa_required:
#      true} y siembra una cookie PRE-AUTH de corta vida (5 min) que SOLO identifica al usuario
#      que ya supero el factor 1. No es una sesion: no abre nada de `/api`.
#   2) POST /api/auth/mfa/verify  con el codigo TOTP (o un recovery code) + esa cookie pre-auth
#      -> valida y SOLO entonces crea la sesion real + la cookie de sesion.
# Con el flag OFF o `mfa_activo=0`, el login crea la sesion directamente (comportamiento de hoy).

# Cookie PRE-AUTH (factor-1 superado, pendiente de TOTP). Separada de la de sesion, HttpOnly +
# SameSite=Strict. Su valor es un token CIFRADO (Fernet, clave `KENI_CONSOLA_MFA_KEY`) con el id
# del usuario + un timestamp; Fernet aporta firma + caducidad (TTL). NUNCA da acceso a `/api`.
COOKIE_MFA_PENDIENTE = "keni_consola_mfa_pendiente"
# Vida del estado pre-auth: 5 minutos para teclear el codigo. Corta a proposito.
_MFA_PENDIENTE_TTL_SEG = 300

_MSG_MFA_NO_DISPONIBLE = (
    "El segundo factor no está disponible: falta configurar la clave de cifrado "
    "(KENI_CONSOLA_MFA_KEY). Avisa a un administrador."
)
_MSG_MFA_CODIGO_KO = "Código incorrecto o caducado."
_MSG_MFA_PENDIENTE_KO = "Sesión de verificación caducada. Vuelve a iniciar sesión."


def _mfa_clave() -> str | None:
    """Clave Fernet para cifrar el secreto/estado MFA (`KENI_CONSOLA_MFA_KEY`); None si no esta."""
    return config.mfa_key()


def _emitir_token_pendiente(usuario_id: str) -> str | None:
    """Token PRE-AUTH cifrado (Fernet) con el id del usuario; None si no hay clave valida.

    Reusa la clave de MFA: Fernet firma y fecha el token, y `decrypt(ttl=...)` lo caduca. Si la
    clave falta/es invalida devolvemos None: la API trata eso como MFA no disponible (fail-safe).
    """
    clave = _mfa_clave()
    try:
        fernet = auth.mfa.cifrador(clave)
    except auth.MfaNoDisponible:
        return None
    carga = json.dumps({"uid": usuario_id, "ts": int(time.time())})
    return fernet.encrypt(carga.encode("utf-8")).decode("utf-8")


def _leer_token_pendiente(token: str | None) -> str | None:
    """Id de usuario de un token PRE-AUTH valido y NO caducado; None si invalido/caducado.

    Verifica firma + TTL (`_MFA_PENDIENTE_TTL_SEG`) via Fernet. Cualquier fallo -> None (no se
    confia en un token corrupto, ajeno o vencido).
    """
    if not token:
        return None
    clave = _mfa_clave()
    try:
        fernet = auth.mfa.cifrador(clave)
        from cryptography.fernet import InvalidToken
    except auth.MfaNoDisponible:
        return None
    except ImportError:  # pragma: no cover - cryptography presente en el back hosted
        return None
    try:
        crudo = fernet.decrypt(token.encode("utf-8"), ttl=_MFA_PENDIENTE_TTL_SEG)
    except (InvalidToken, ValueError, TypeError):
        return None
    try:
        datos = json.loads(crudo.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    uid = datos.get("uid") if isinstance(datos, dict) else None
    return uid if isinstance(uid, str) and uid else None


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


def _set_cookie_pendiente(resp: Response, token: str) -> None:
    """Siembra la cookie PRE-AUTH (factor-1 superado): HttpOnly, SameSite=Strict, vida corta.

    Misma postura de seguridad que la cookie de sesion (HttpOnly + Strict + Secure tras TLS),
    pero con un `max_age` de 5 min. Esta cookie NO da acceso a `/api`: solo sirve para el paso
    `/api/auth/mfa/verify`.
    """
    resp.set_cookie(
        COOKIE_MFA_PENDIENTE,
        token,
        httponly=True,
        samesite="strict",
        secure=seguridad.cookie_secure(),
        path="/",
        max_age=_MFA_PENDIENTE_TTL_SEG,
    )


def _borrar_cookie_pendiente(resp: Response) -> None:
    """Borra la cookie PRE-AUTH (tras verificar el segundo factor o al fallar)."""
    resp.delete_cookie(COOKIE_MFA_PENDIENTE, path="/")


def _respuesta_sesion_creada(usuario_id: str, usuario: dict) -> Response:
    """Crea la sesion real, siembra su cookie y borra la pre-auth; devuelve la respuesta 200."""
    token = auth.crear_sesion(usuario_id)
    resp = JSONResponse(
        {
            "usuario": {
                "id": usuario["id"],
                "usuario": usuario["usuario"],
                "rol": usuario["rol"],
                "debe_cambiar_password": usuario["debe_cambiar_password"],
            }
        }
    )
    _set_cookie_sesion(resp, token)
    _borrar_cookie_pendiente(resp)
    return resp


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

    # ELEVACION MFA (gateada): si el flag esta ON y este usuario tiene el segundo factor activo,
    # NO abrimos la sesion todavia. Devolvemos {mfa_required: true} y sembramos la cookie
    # pre-auth (factor-1 superado, pendiente de TOTP). Con el flag OFF o `mfa_activo=0`, este
    # bloque se salta entero y el login crea la sesion EXACTAMENTE como hoy.
    if seguridad.mfa_habilitado() and autenticado.get("mfa_activo"):
        token_pendiente = _emitir_token_pendiente(autenticado["id"])
        if token_pendiente is None:
            # FAIL-SAFE: el usuario tiene MFA activo pero no hay clave de cifrado valida. NO
            # podemos verificar el segundo factor; tampoco abrimos sesion saltandonoslo. Rehusa.
            _logger.warning(
                "MFA activo para un usuario pero KENI_CONSOLA_MFA_KEY falta/es invalida: "
                "login rechazado (fail-safe). usuario=%s",
                autenticado["usuario"],
            )
            return JSONResponse({"error": _MSG_MFA_NO_DISPONIBLE}, status_code=503)
        resp = JSONResponse({"mfa_required": True})
        _set_cookie_pendiente(resp, token_pendiente)
        return resp

    return _respuesta_sesion_creada(autenticado["id"], autenticado)


async def logout(request: Request) -> Response:
    """POST /api/auth/logout: invalida la sesion (si la hay) y borra la cookie (204)."""
    token = request.cookies.get(auth.COOKIE_SESION)
    if token:
        auth.borrar_sesion(token)
    resp = Response(status_code=204)
    _borrar_cookie_sesion(resp)
    # Higiene: si quedara una cookie pre-auth a medias, la limpiamos tambien.
    _borrar_cookie_pendiente(resp)
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
                "puede_coordinar": bool(
                    refrescado.get("puede_coordinar") or usuario.get("puede_coordinar")
                ),
                "marcas": list(refrescado.get("marcas") or []),
                # MFA (segundo factor): `mfa_habilitado` refleja el flag del servidor (la UI
                # solo muestra la seccion de MFA en "Mi cuenta" si esta ON); `mfa_activo` dice
                # si ESTE usuario ya lo enrolo. Con el flag OFF, la UI no pinta nada de MFA.
                "mfa_habilitado": seguridad.mfa_habilitado(),
                "mfa_activo": bool(refrescado.get("mfa_activo")),
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


# --------------------------------------------------------------------------- #
# MFA: verificacion del segundo factor en el login (cookie pre-auth)            #
# --------------------------------------------------------------------------- #


async def mfa_verify(request: Request) -> Response:
    """POST /api/auth/mfa/verify: 2o paso del login. Valida TOTP o recovery + cookie pre-auth.

    Es PUBLICO (solo exige la cookie pre-auth, no una sesion). Cuerpo: `{codigo}` (un TOTP de 6
    digitos o un codigo de recuperacion). Si el codigo es valido, crea la sesion real, siembra
    su cookie y borra la pre-auth. Si el flag esta OFF, esta ruta no deberia recibir trafico
    (el login nunca emite la cookie pre-auth); aun asi rehusa limpiamente.
    """
    if not seguridad.mfa_habilitado():
        # Con el flag OFF nunca se emite la cookie pre-auth; cerramos la via por si acaso.
        return JSONResponse({"error": _MSG_MFA_PENDIENTE_KO}, status_code=401)

    usuario_id = _leer_token_pendiente(request.cookies.get(COOKIE_MFA_PENDIENTE))
    if usuario_id is None:
        resp = JSONResponse({"error": _MSG_MFA_PENDIENTE_KO}, status_code=401)
        _borrar_cookie_pendiente(resp)
        return resp

    datos = await leer_json(request)
    codigo = datos.get("codigo")
    if not isinstance(codigo, str) or not codigo.strip():
        return JSONResponse({"error": "Falta el código."}, status_code=400)

    estado = auth.estado_mfa(usuario_id)
    if estado is None or not estado["activo"] or not estado["secret_cifrado"]:
        # El usuario perdio el MFA entre el login y este paso (reset admin, p.ej.). Caduca.
        resp = JSONResponse({"error": _MSG_MFA_PENDIENTE_KO}, status_code=401)
        _borrar_cookie_pendiente(resp)
        return resp

    # 1) Codigo TOTP. Descifrar el secreto puede rehusar (fail-safe) si la clave desaparecio.
    try:
        secreto = auth.descifrar_secreto(estado["secret_cifrado"], _mfa_clave())
    except auth.MfaNoDisponible:
        _logger.warning("MFA verify: no se pudo descifrar el secreto (clave ausente/invalida).")
        return JSONResponse({"error": _MSG_MFA_NO_DISPONIBLE}, status_code=503)

    if auth.verificar_totp(secreto, codigo):
        usuario = auth.obtener_usuario_por_id(usuario_id)
        if usuario is None:
            return JSONResponse({"error": _MSG_MFA_PENDIENTE_KO}, status_code=401)
        return _respuesta_sesion_creada(usuario_id, usuario)

    # 2) Codigo de RECUPERACION (un solo uso). Si acierta, se consume y se re-persiste la lista.
    ok, restantes = auth.verificar_codigo_recuperacion(codigo, estado["recovery_codes"])
    if ok:
        auth.actualizar_recovery_mfa(usuario_id, restantes)
        usuario = auth.obtener_usuario_por_id(usuario_id)
        if usuario is None:
            return JSONResponse({"error": _MSG_MFA_PENDIENTE_KO}, status_code=401)
        return _respuesta_sesion_creada(usuario_id, usuario)

    return JSONResponse({"error": _MSG_MFA_CODIGO_KO}, status_code=401)


# --------------------------------------------------------------------------- #
# MFA: enrolamiento (requiere sesion COMPLETA: el middleware ya la exige)        #
# --------------------------------------------------------------------------- #


def _exige_sesion(request: Request) -> dict | None:
    """Usuario de la sesion actual, o None (el llamante responde 401). Token de mant. -> None."""
    usuario = getattr(request.state, "usuario", None)
    return usuario if isinstance(usuario, dict) else None


async def mfa_setup(request: Request) -> Response:
    """POST /api/auth/mfa/setup: genera un secreto TOTP nuevo, lo cifra y lo guarda (sin activar).

    Devuelve `{secret, uri}` para pintar el QR. El MFA NO queda activo hasta confirmar el primer
    codigo (`/api/auth/mfa/activate`). Requiere el flag MFA ON y sesion completa.
    """
    if not seguridad.mfa_habilitado():
        return JSONResponse({"error": "El segundo factor no está habilitado."}, status_code=404)
    usuario = _exige_sesion(request)
    if usuario is None:
        return JSONResponse({"error": "Necesitas una sesión iniciada."}, status_code=401)

    secreto = auth.generar_secreto()
    try:
        cifrado = auth.cifrar_secreto(secreto, _mfa_clave())
    except auth.MfaNoDisponible:
        _logger.warning("MFA setup rechazado: KENI_CONSOLA_MFA_KEY falta/es invalida (fail-safe).")
        return JSONResponse({"error": _MSG_MFA_NO_DISPONIBLE}, status_code=503)

    auth.guardar_secreto_mfa(usuario["id"], cifrado)
    uri = auth.uri_aprovisionamiento(secreto, usuario.get("usuario", "usuario"))
    # `secret` se devuelve para que la UI lo muestre como texto alternativo al QR. El secreto
    # cifrado ya quedo en BD; este claro solo viaja al cliente que acaba de autenticarse.
    return JSONResponse({"secret": secreto, "uri": uri})


async def mfa_activate(request: Request) -> Response:
    """POST /api/auth/mfa/activate: confirma el primer TOTP, activa el MFA y devuelve recovery.

    Cuerpo `{codigo}`. Verifica el codigo contra el secreto enrolado por `setup`; si cuadra,
    marca `mfa_activo=1`, genera los codigos de recuperacion, guarda sus HASHES y devuelve los
    codigos en CLARO UNA sola vez (`{recovery_codes}`). Requiere flag ON + sesion completa.
    """
    if not seguridad.mfa_habilitado():
        return JSONResponse({"error": "El segundo factor no está habilitado."}, status_code=404)
    usuario = _exige_sesion(request)
    if usuario is None:
        return JSONResponse({"error": "Necesitas una sesión iniciada."}, status_code=401)

    datos = await leer_json(request)
    codigo = datos.get("codigo")
    if not isinstance(codigo, str) or not codigo.strip():
        return JSONResponse({"error": "Falta el código."}, status_code=400)

    estado = auth.estado_mfa(usuario["id"])
    if estado is None or not estado["secret_cifrado"]:
        return JSONResponse(
            {"error": "Primero genera un código de configuración (setup)."}, status_code=400
        )
    try:
        secreto = auth.descifrar_secreto(estado["secret_cifrado"], _mfa_clave())
    except auth.MfaNoDisponible:
        return JSONResponse({"error": _MSG_MFA_NO_DISPONIBLE}, status_code=503)

    if not auth.verificar_totp(secreto, codigo):
        return JSONResponse({"error": _MSG_MFA_CODIGO_KO}, status_code=400)

    codigos = auth.generar_codigos_recuperacion()
    auth.activar_mfa(usuario["id"], auth.hashear_codigos_recuperacion(codigos))
    return JSONResponse({"recovery_codes": codigos})


async def mfa_disable(request: Request) -> Response:
    """POST /api/auth/mfa/disable: apaga el MFA del propio usuario (exige su contrasena actual).

    Cuerpo `{password_actual}`. Verifica la contrasena (misma guarda que el cambio de pass) y
    limpia secreto + flag + recovery. Requiere sesion completa (el flag puede estar ON u OFF: un
    usuario debe poder desactivar su MFA aunque el operador haya apagado el gate luego).
    """
    usuario = _exige_sesion(request)
    if usuario is None:
        return JSONResponse({"error": "Necesitas una sesión iniciada."}, status_code=401)

    datos = await leer_json(request)
    actual = datos.get("password_actual")
    if not isinstance(actual, str) or not actual:
        return JSONResponse({"error": "Falta la contraseña actual."}, status_code=400)
    if len(actual) > auth.LONGITUD_MAX_PASSWORD or not auth.verificar_password_actual(
        usuario["id"], actual
    ):
        return JSONResponse({"error": "La contraseña actual no es correcta."}, status_code=400)

    auth.desactivar_mfa(usuario["id"])
    return Response(status_code=204)


RUTAS = [
    Route("/api/auth/login", login, methods=["POST"]),
    Route("/api/auth/logout", logout, methods=["POST"]),
    Route("/api/auth/me", me, methods=["GET"]),
    Route("/api/auth/cambiar-password", cambiar_password, methods=["POST"]),
    # MFA (segundo factor). `verify` es publico (cookie pre-auth); el resto exige sesion.
    Route("/api/auth/mfa/verify", mfa_verify, methods=["POST"]),
    Route("/api/auth/mfa/setup", mfa_setup, methods=["POST"]),
    Route("/api/auth/mfa/activate", mfa_activate, methods=["POST"]),
    Route("/api/auth/mfa/disable", mfa_disable, methods=["POST"]),
]
