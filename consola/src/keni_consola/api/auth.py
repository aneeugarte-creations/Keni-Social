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
# MFA (segundo factor PASSKEYS / WebAuthn), GATEADO por `KENI_CONSOLA_MFA` (def OFF).
# --------------------------------------------------------------------------- #
#
# FLUJO LOGIN con MFA ON y usuario con >=1 passkey:
#   1) POST /api/auth/login  con user/pass OK -> NO crea sesion. Devuelve 200 {mfa_required:
#      true} y siembra una cookie PRE-AUTH de corta vida (5 min) que SOLO identifica al usuario
#      que ya supero el factor 1. No es una sesion: no abre nada de `/api`.
#   2) POST /api/auth/mfa/login/opciones (cookie pre-auth) -> devuelve las opciones WebAuthn de
#      autenticacion y siembra la cookie de CHALLENGE (Fernet, 5 min) atada al usuario.
#   3) El navegador corre `startAuthentication` (Face ID / huella / llave) y POSTea la assertion
#      a POST /api/auth/mfa/verify (cookie pre-auth + cookie challenge) -> verifica y SOLO
#      entonces crea la sesion real. `verify` tambien acepta un RECOVERY code (sin assertion).
# Con el flag OFF o sin passkeys, el login crea la sesion directamente (comportamiento de hoy).
#
# El CHALLENGE de cada ceremonia se recuerda SOLO en una cookie Fernet de vida corta (nunca se
# confia en un challenge que mande el cliente). Hay cookies de challenge SEPARADAS para la
# ceremonia de REGISTRO y la de LOGIN.

# Cookie PRE-AUTH (factor-1 superado, pendiente del segundo factor). Separada de la de sesion,
# HttpOnly + SameSite=Strict. Su valor es un token CIFRADO (Fernet, `KENI_CONSOLA_MFA_KEY`) con
# el id del usuario + un timestamp; Fernet aporta firma + caducidad (TTL). NUNCA abre `/api`.
COOKIE_MFA_PENDIENTE = "keni_consola_mfa_pendiente"
# Cookies de CHALLENGE WebAuthn (Fernet, atan `{challenge, usuario_id}`). Una por ceremonia.
COOKIE_MFA_CHALLENGE_LOGIN = "keni_consola_mfa_reto_login"
COOKIE_MFA_CHALLENGE_REGISTRO = "keni_consola_mfa_reto_registro"
# Vida del estado pre-auth/challenge: 5 minutos para completar la ceremonia. Corta a proposito.
_MFA_PENDIENTE_TTL_SEG = 300

_MSG_MFA_NO_DISPONIBLE = (
    "El segundo factor no está disponible: falta configurar la clave de firma "
    "(KENI_CONSOLA_MFA_KEY). Avisa a un administrador."
)
_MSG_MFA_CODIGO_KO = "Código incorrecto o caducado."
_MSG_MFA_PENDIENTE_KO = "Sesión de verificación caducada. Vuelve a iniciar sesión."
# Mensaje generico de fallo de la ceremonia WebAuthn (no damos pistas sobre el porque).
_MSG_MFA_CEREMONIA_KO = "No se pudo verificar la llave de acceso. Inténtalo de nuevo."


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


def _emitir_token_challenge(challenge_b64url: str, usuario_id: str) -> str | None:
    """Token CIFRADO (Fernet) que recuerda el challenge de una ceremonia atado al usuario.

    Reusa la clave de MFA: Fernet firma + fecha el token (caduca via `_MFA_PENDIENTE_TTL_SEG`).
    None si no hay clave valida (la API lo trata como MFA no disponible: fail-safe).
    """
    clave = _mfa_clave()
    try:
        fernet = auth.cifrador(clave)
    except auth.MfaNoDisponible:
        return None
    carga = json.dumps({"reto": challenge_b64url, "uid": usuario_id, "ts": int(time.time())})
    return fernet.encrypt(carga.encode("utf-8")).decode("utf-8")


def _leer_token_challenge(token: str | None, usuario_id: str) -> str | None:
    """Challenge (base64url) de una cookie valida, NO caducada y del MISMO usuario; None si no.

    Verifica firma + TTL via Fernet y que el `uid` del token coincida con el de la cookie
    pre-auth (la ceremonia es de ESE usuario). Cualquier fallo -> None (no se confia en un
    challenge corrupto, ajeno o vencido). El cliente NUNCA aporta el challenge esperado.
    """
    if not token:
        return None
    clave = _mfa_clave()
    try:
        fernet = auth.cifrador(clave)
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
    if not isinstance(datos, dict) or datos.get("uid") != usuario_id:
        return None
    reto = datos.get("reto")
    return reto if isinstance(reto, str) and reto else None


def _set_cookie_challenge(resp: Response, nombre: str, token: str) -> None:
    """Siembra una cookie de challenge WebAuthn: HttpOnly, SameSite=Strict, vida corta (5 min)."""
    resp.set_cookie(
        nombre,
        token,
        httponly=True,
        samesite="strict",
        secure=seguridad.cookie_secure(),
        path="/",
        max_age=_MFA_PENDIENTE_TTL_SEG,
    )


def _borrar_cookie_challenge(resp: Response, nombre: str) -> None:
    """Borra una cookie de challenge WebAuthn (tras verificar o al fallar)."""
    resp.delete_cookie(nombre, path="/")


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
    # Higiene: la ceremonia termino, cerramos la cookie de challenge de login.
    _borrar_cookie_challenge(resp, COOKIE_MFA_CHALLENGE_LOGIN)
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

    # ELEVACION MFA (gateada): si el flag esta ON y este usuario tiene >=1 passkey (`mfa_activo`),
    # NO abrimos la sesion todavia. Devolvemos {mfa_required: true} y sembramos la cookie
    # pre-auth (factor-1 superado, pendiente de la ceremonia WebAuthn). Con el flag OFF o
    # `mfa_activo=0`, este bloque se salta entero y el login crea la sesion EXACTAMENTE como hoy.
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
    # Higiene: si quedara una cookie pre-auth o de challenge a medias, las limpiamos tambien.
    _borrar_cookie_pendiente(resp)
    _borrar_cookie_challenge(resp, COOKIE_MFA_CHALLENGE_LOGIN)
    _borrar_cookie_challenge(resp, COOKIE_MFA_CHALLENGE_REGISTRO)
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
                # MFA (segundo factor, passkeys): `mfa_habilitado` refleja el flag del servidor
                # (la UI solo muestra la seccion de llaves en "Mi cuenta" si esta ON);
                # `mfa_activo` dice si ESTE usuario tiene >=1 passkey. Con el flag OFF, la UI no
                # pinta nada de MFA.
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
# MFA: configuracion de la Relying Party (RP) WebAuthn                          #
# --------------------------------------------------------------------------- #


def _rp_id() -> str:
    """RP ID efectivo (dominio sin esquema/puerto). Dev `localhost`, prod `social.kenitech.io`."""
    return config.rp_id()


def _rp_nombre() -> str:
    """Nombre legible de la RP que muestra el SO al crear/usar la passkey."""
    return config.rp_nombre()


def _rp_origenes() -> list[str]:
    """Origen(es) esperado(s) de la ceremonia (lista; el primero es el canonico para py_webauthn)."""
    return config.rp_origenes()


# --------------------------------------------------------------------------- #
# MFA: ceremonia de LOGIN (segundo paso, cookie pre-auth + challenge)           #
# --------------------------------------------------------------------------- #


async def mfa_login_opciones(request: Request) -> Response:
    """POST /api/auth/mfa/login/opciones: opciones WebAuthn de autenticacion + cookie de challenge.

    PUBLICO (solo exige la cookie pre-auth). Devuelve las opciones spec-JSON para
    `startAuthentication` y siembra la cookie de challenge (Fernet, 5 min, atada al usuario).
    Si el usuario ya no tiene passkeys (reset admin entre pasos), caduca la pre-auth.
    """
    if not seguridad.mfa_habilitado():
        return JSONResponse({"error": _MSG_MFA_PENDIENTE_KO}, status_code=401)
    usuario_id = _leer_token_pendiente(request.cookies.get(COOKIE_MFA_PENDIENTE))
    if usuario_id is None:
        resp = JSONResponse({"error": _MSG_MFA_PENDIENTE_KO}, status_code=401)
        _borrar_cookie_pendiente(resp)
        return resp

    credenciales = auth.listar_credenciales_mfa(usuario_id)
    if not credenciales:
        resp = JSONResponse({"error": _MSG_MFA_PENDIENTE_KO}, status_code=401)
        _borrar_cookie_pendiente(resp)
        return resp

    try:
        opciones_json, challenge = auth.opciones_login(_rp_id(), credenciales)
    except auth.MfaNoDisponible:  # pragma: no cover - opciones_login no firma; defensivo
        return JSONResponse({"error": _MSG_MFA_NO_DISPONIBLE}, status_code=503)

    # Recordamos el challenge SOLO en la cookie (firmada+fechada). Fail-safe si falta la clave.
    token_reto = _emitir_token_challenge(challenge, usuario_id)
    if token_reto is None:
        _logger.warning("MFA login/opciones: KENI_CONSOLA_MFA_KEY falta/es invalida (fail-safe).")
        return JSONResponse({"error": _MSG_MFA_NO_DISPONIBLE}, status_code=503)

    resp = Response(content=opciones_json, media_type="application/json")
    _set_cookie_challenge(resp, COOKIE_MFA_CHALLENGE_LOGIN, token_reto)
    return resp


async def mfa_verify(request: Request) -> Response:
    """POST /api/auth/mfa/verify: 2o paso del login. Valida una ASSERTION WebAuthn o un recovery.

    PUBLICO (cookie pre-auth + cookie challenge). Cuerpo: `{assertion: {...}}` (la credencial que
    devuelve `startAuthentication`) O `{codigo: "XXXX-XXXX"}` (un codigo de recuperacion). Si
    cuadra, crea la sesion real, siembra su cookie y borra las pre-auth/challenge. Con el flag OFF
    no deberia recibir trafico; aun asi rehusa limpiamente.
    """
    if not seguridad.mfa_habilitado():
        return JSONResponse({"error": _MSG_MFA_PENDIENTE_KO}, status_code=401)

    usuario_id = _leer_token_pendiente(request.cookies.get(COOKIE_MFA_PENDIENTE))
    if usuario_id is None:
        resp = JSONResponse({"error": _MSG_MFA_PENDIENTE_KO}, status_code=401)
        _borrar_cookie_pendiente(resp)
        return resp

    estado = auth.estado_mfa(usuario_id)
    if estado is None or not estado["activo"]:
        # El usuario perdio sus passkeys entre el login y este paso (reset admin). Caduca.
        resp = JSONResponse({"error": _MSG_MFA_PENDIENTE_KO}, status_code=401)
        _borrar_cookie_pendiente(resp)
        return resp

    datos = await leer_json(request)
    assertion = datos.get("assertion")
    codigo = datos.get("codigo")

    # VIA 1: codigo de RECUPERACION (un solo uso). No necesita challenge.
    if isinstance(codigo, str) and codigo.strip():
        ok, restantes = auth.verificar_codigo_recuperacion(codigo, estado["recovery_codes"])
        if ok:
            auth.actualizar_recovery_mfa(usuario_id, restantes)
            usuario = auth.obtener_usuario_por_id(usuario_id)
            if usuario is None:
                return JSONResponse({"error": _MSG_MFA_PENDIENTE_KO}, status_code=401)
            return _respuesta_sesion_creada(usuario_id, usuario)
        return JSONResponse({"error": _MSG_MFA_CODIGO_KO}, status_code=401)

    # VIA 2: assertion WebAuthn. Exige la cookie de challenge (NUNCA un challenge del cliente).
    if not isinstance(assertion, (dict, str)) or not assertion:
        return JSONResponse({"error": "Falta la llave de acceso o el código."}, status_code=400)

    challenge = _leer_token_challenge(
        request.cookies.get(COOKIE_MFA_CHALLENGE_LOGIN), usuario_id
    )
    if challenge is None:
        resp = JSONResponse({"error": _MSG_MFA_PENDIENTE_KO}, status_code=401)
        _borrar_cookie_challenge(resp, COOKIE_MFA_CHALLENGE_LOGIN)
        return resp

    credential_id = auth.credential_id_de_respuesta(assertion)
    credencial = (
        auth.credencial_mfa_por_credential_id(usuario_id, credential_id)
        if credential_id
        else None
    )
    if credencial is None:
        return JSONResponse({"error": _MSG_MFA_CEREMONIA_KO}, status_code=401)

    try:
        nuevo_sign_count = auth.verificar_login(
            assertion, challenge, credencial, _rp_id(), _rp_origenes()
        )
    except Exception as exc:  # noqa: BLE001 - py_webauthn lanza varias; tratamos todas como KO
        _logger.info("MFA verify: assertion WebAuthn rechazada: %s", exc)
        return JSONResponse({"error": _MSG_MFA_CEREMONIA_KO}, status_code=401)

    # Aviso (no bloqueante) si el contador RETROCEDE: posible clon, pero muchos autenticadores
    # reportan 0 y nunca incrementan, asi que no es veredicto. Igual actualizamos el contador.
    if nuevo_sign_count and nuevo_sign_count < int(credencial.get("sign_count", 0) or 0):
        _logger.warning(
            "MFA verify: sign_count retrocedio para la credencial %s (posible clon).",
            credencial["id"],
        )
    auth.actualizar_sign_count_mfa(credencial["id"], nuevo_sign_count)

    usuario = auth.obtener_usuario_por_id(usuario_id)
    if usuario is None:
        return JSONResponse({"error": _MSG_MFA_PENDIENTE_KO}, status_code=401)
    return _respuesta_sesion_creada(usuario_id, usuario)


# --------------------------------------------------------------------------- #
# MFA: enrolamiento de passkeys (requiere sesion COMPLETA)                      #
# --------------------------------------------------------------------------- #


def _exige_sesion(request: Request) -> dict | None:
    """Usuario de la sesion actual, o None (el llamante responde 401). Token de mant. -> None."""
    usuario = getattr(request.state, "usuario", None)
    return usuario if isinstance(usuario, dict) else None


async def mfa_registro_opciones(request: Request) -> Response:
    """POST /api/auth/mfa/registro/opciones: opciones WebAuthn de REGISTRO + cookie de challenge.

    Requiere flag ON + sesion completa. Devuelve las opciones spec-JSON para `startRegistration`
    (excluye las passkeys ya enroladas) y siembra la cookie de challenge de registro.
    """
    if not seguridad.mfa_habilitado():
        return JSONResponse({"error": "El segundo factor no está habilitado."}, status_code=404)
    usuario = _exige_sesion(request)
    if usuario is None:
        return JSONResponse({"error": "Necesitas una sesión iniciada."}, status_code=401)

    existentes = auth.listar_credenciales_mfa(usuario["id"])
    try:
        opciones_json, challenge = auth.opciones_registro(
            usuario["id"], usuario.get("usuario", "usuario"), _rp_id(), _rp_nombre(), existentes
        )
    except auth.MfaNoDisponible:  # pragma: no cover - opciones_registro no firma; defensivo
        return JSONResponse({"error": _MSG_MFA_NO_DISPONIBLE}, status_code=503)

    token_reto = _emitir_token_challenge(challenge, usuario["id"])
    if token_reto is None:
        _logger.warning("MFA registro/opciones: KENI_CONSOLA_MFA_KEY falta/es invalida (fail-safe).")
        return JSONResponse({"error": _MSG_MFA_NO_DISPONIBLE}, status_code=503)

    resp = Response(content=opciones_json, media_type="application/json")
    _set_cookie_challenge(resp, COOKIE_MFA_CHALLENGE_REGISTRO, token_reto)
    return resp


async def mfa_registro_verificar(request: Request) -> Response:
    """POST /api/auth/mfa/registro/verificar: guarda la passkey nueva; devuelve recovery la 1a vez.

    Cuerpo `{credential: {...}, nombre?}`. Verifica la respuesta de `startRegistration` contra la
    cookie de challenge, persiste la credencial (clave publica + sign_count + transports) y marca
    `mfa_activo=1`. Si era la PRIMERA passkey, genera y devuelve los codigos de recuperacion en
    CLARO UNA sola vez (`{recovery_codes}`). Requiere flag ON + sesion completa.
    """
    if not seguridad.mfa_habilitado():
        return JSONResponse({"error": "El segundo factor no está habilitado."}, status_code=404)
    usuario = _exige_sesion(request)
    if usuario is None:
        return JSONResponse({"error": "Necesitas una sesión iniciada."}, status_code=401)

    datos = await leer_json(request)
    credential = datos.get("credential")
    nombre = datos.get("nombre")
    nombre = nombre.strip()[:80] if isinstance(nombre, str) else ""
    if not isinstance(credential, (dict, str)) or not credential:
        return JSONResponse({"error": "Falta la credencial de la llave."}, status_code=400)

    challenge = _leer_token_challenge(
        request.cookies.get(COOKIE_MFA_CHALLENGE_REGISTRO), usuario["id"]
    )
    if challenge is None:
        resp = JSONResponse(
            {"error": "La ceremonia de registro caducó. Vuelve a intentarlo."}, status_code=400
        )
        _borrar_cookie_challenge(resp, COOKIE_MFA_CHALLENGE_REGISTRO)
        return resp

    try:
        nueva = auth.verificar_registro(credential, challenge, _rp_id(), _rp_origenes())
    except Exception as exc:  # noqa: BLE001 - py_webauthn lanza varias; tratamos todas como KO
        _logger.info("MFA registro/verificar: respuesta WebAuthn rechazada: %s", exc)
        resp = JSONResponse({"error": _MSG_MFA_CEREMONIA_KO}, status_code=400)
        _borrar_cookie_challenge(resp, COOKIE_MFA_CHALLENGE_REGISTRO)
        return resp

    # ¿Es la PRIMERA passkey? Lo es si el usuario aun no tenia ninguna antes de guardar esta.
    es_primera = not auth.listar_credenciales_mfa(usuario["id"])
    guardada = auth.guardar_credencial_mfa(
        usuario["id"],
        credential_id=nueva["credential_id"],
        public_key=nueva["public_key"],
        sign_count=nueva["sign_count"],
        transports=nueva["transports"],
        nombre=nombre,
    )
    if not guardada:
        # credential_id duplicado (mismo autenticador ya enrolado).
        resp = JSONResponse(
            {"error": "Esa llave de acceso ya está registrada."}, status_code=409
        )
        _borrar_cookie_challenge(resp, COOKIE_MFA_CHALLENGE_REGISTRO)
        return resp

    cuerpo: dict = {"ok": True}
    if es_primera:
        codigos = auth.generar_codigos_recuperacion()
        auth.fijar_recovery_mfa(usuario["id"], auth.hashear_codigos_recuperacion(codigos))
        cuerpo["recovery_codes"] = codigos
    resp = JSONResponse(cuerpo)
    _borrar_cookie_challenge(resp, COOKIE_MFA_CHALLENGE_REGISTRO)
    return resp


async def mfa_credenciales(request: Request) -> Response:
    """GET /api/auth/mfa/credenciales: lista las passkeys del usuario (SIN secretos).

    Devuelve `{credenciales: [{id, nombre, creada, ultimo_uso}]}`. Requiere flag ON + sesion.
    """
    if not seguridad.mfa_habilitado():
        return JSONResponse({"error": "El segundo factor no está habilitado."}, status_code=404)
    usuario = _exige_sesion(request)
    if usuario is None:
        return JSONResponse({"error": "Necesitas una sesión iniciada."}, status_code=401)
    credenciales = [
        {
            "id": c["id"],
            "nombre": c["nombre"],
            "creada": c["creada"],
            "ultimo_uso": c["ultimo_uso"],
        }
        for c in auth.listar_credenciales_mfa(usuario["id"])
    ]
    return JSONResponse({"credenciales": credenciales})


async def mfa_credencial_borrar(request: Request) -> Response:
    """DELETE /api/auth/mfa/credenciales/{id}: borra UNA passkey del propio usuario (204).

    Si era la ULTIMA, `borrar_credencial_mfa` apaga `mfa_activo` y limpia recovery. Requiere
    sesion completa (flag ON u OFF: un usuario debe poder quitar una llave aunque el operador
    apague el gate). 404 si esa credencial no es suya / no existe.
    """
    usuario = _exige_sesion(request)
    if usuario is None:
        return JSONResponse({"error": "Necesitas una sesión iniciada."}, status_code=401)
    cred_id = request.path_params.get("id", "")
    if not auth.borrar_credencial_mfa(usuario["id"], cred_id):
        return JSONResponse({"error": "Esa llave de acceso no existe."}, status_code=404)
    return Response(status_code=204)


async def mfa_disable(request: Request) -> Response:
    """POST /api/auth/mfa/disable: apaga el MFA del propio usuario (exige su contrasena actual).

    Cuerpo `{password_actual}`. Verifica la contrasena (misma guarda que el cambio de pass) y
    borra TODAS las passkeys + recovery + flag. Requiere sesion completa (el flag puede estar ON
    u OFF: un usuario debe poder desactivar su MFA aunque el operador haya apagado el gate luego).
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
    # MFA passkeys. `login/opciones` y `verify` son PUBLICOS (cookie pre-auth); el resto exige
    # sesion completa.
    Route("/api/auth/mfa/login/opciones", mfa_login_opciones, methods=["POST"]),
    Route("/api/auth/mfa/verify", mfa_verify, methods=["POST"]),
    Route("/api/auth/mfa/registro/opciones", mfa_registro_opciones, methods=["POST"]),
    Route("/api/auth/mfa/registro/verificar", mfa_registro_verificar, methods=["POST"]),
    Route("/api/auth/mfa/credenciales", mfa_credenciales, methods=["GET"]),
    Route("/api/auth/mfa/credenciales/{id}", mfa_credencial_borrar, methods=["DELETE"]),
    Route("/api/auth/mfa/disable", mfa_disable, methods=["POST"]),
]
