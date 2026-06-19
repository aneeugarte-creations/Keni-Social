"""API Auth: login user/pass, logout, sesion actual y cambio de contrasena (#130).

Endpoints (todos bajo `/api/auth`, CONTRATO con el frontend):

  - POST /api/auth/login    {usuario, password} -> 200 {usuario:{...}} + cookie de sesion.
    401 GENERICO ("Usuario o contrasena incorrectos") sin revelar si el usuario existe.
  - POST /api/auth/logout   -> 204; invalida la sesion server-side y borra la cookie.
  - GET  /api/auth/me       -> 200 {usuario:{...}} si hay sesion; 401 si no.
  - PATCH /api/auth/me      {nombre} -> 200 {nombre}; la persona edita SU nombre humano.
  - POST /api/auth/cambiar-password {password_actual, password_nueva} -> 204
    (sirve para el cambio FORZADO al primer acceso y el voluntario; valida la actual).
  - POST /api/auth/passkey/opciones -> opciones WebAuthn de login DESCUBRIBLE (passwordless).
  - POST /api/auth/passkey/verify {assertion} -> 200 {usuario}; login solo con la passkey.

La barrera de credencial la aplica el middleware `SeguridadConsola`: `/api/auth/login`
es PUBLICO (crea la sesion), el resto exige sesion o token de bootstrap. La cookie de
sesion es HttpOnly + SameSite=Strict (no la lee JS; el navegador no la manda cross-site).

`auth.py` (modulo de dominio) hace el trabajo real (hash, sesiones, anti fuerza bruta);
aqui solo va el contrato HTTP y la gestion de la cookie.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import deque

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import auth, config, permisos, seguridad
from .._http_json import leer_json
from ..observabilidad import NOMBRE_LOGGER

_logger = logging.getLogger(NOMBRE_LOGGER)

# Mensaje GENERICO de login fallido: NO revela si el usuario existe (anti enumeracion).
_MSG_LOGIN_KO = "Usuario o contraseña incorrectos."

# --------------------------------------------------------------------------- #
# Limite de intentos de login POR IP (ventana deslizante, hardening 2026-06)   #
# --------------------------------------------------------------------------- #
#
# COMPLEMENTA el lockout POR CUENTA de `auth.usuarios` (que, solo, es un vector de DoS:
# cualquiera puede bloquear la cuenta de otro a base de fallos). Solo cuentan los intentos
# FALLIDOS: los logins correctos no consumen cupo (el polling/uso normal no se ve afectado).
# Al frente hay ademas un rate limit por IP en Traefik (deploy/docker-compose.yml).
#
# EN MEMORIA y POR PROCESO a proposito: el back corre 1 solo worker uvicorn (ver
# deploy/back/Dockerfile), asi que el estado es efectivamente global; si algun dia se
# escala a N procesos/replicas, el limite pasa a ser por-proceso (N veces mas laxo), lo
# cual sigue siendo una barrera util — documentado, no un bug. La IP viene de
# `request.client` (uvicorn --proxy-headers ya resuelve X-Forwarded-For desde Traefik).
# Ajustables por env (enteros): KENI_LOGIN_IP_MAX (def 20 fallos) y
# KENI_LOGIN_IP_VENTANA_SEG (def 300 s). OJO: una oficina entera puede salir por UNA IP
# (NAT); 20 fallos/5 min es generoso para humanos y ridiculo para fuerza bruta.
_LOGIN_IP_MAX_DEF = 20
_LOGIN_IP_VENTANA_SEG_DEF = 300
_intentos_login_por_ip: dict[str, deque[float]] = {}
_candado_login_ips = threading.Lock()

_MSG_LOGIN_IP_LIMITE = "Demasiados intentos desde esta dirección. Inténtalo de nuevo en unos minutos."


def _entero_env(nombre: str, defecto: int) -> int:
    """Entero de una env var (defecto si falta o no parsea). Lectura en caliente: barata."""
    try:
        return int(os.environ.get(nombre, "") or defecto)
    except ValueError:
        return defecto


def _ip_cliente(request: Request) -> str:
    """IP de origen de la peticion ("" si el transporte no la expone, p.ej. ciertos tests)."""
    cliente = request.client
    return cliente.host if cliente is not None else ""


def _login_ip_bloqueada(ip: str) -> bool:
    """True si esta IP agoto su cupo de intentos FALLIDOS dentro de la ventana."""
    maximo = _entero_env("KENI_LOGIN_IP_MAX", _LOGIN_IP_MAX_DEF)
    ventana = _entero_env("KENI_LOGIN_IP_VENTANA_SEG", _LOGIN_IP_VENTANA_SEG_DEF)
    corte = time.monotonic() - ventana
    with _candado_login_ips:
        cola = _intentos_login_por_ip.get(ip)
        if cola is None:
            return False
        while cola and cola[0] < corte:
            cola.popleft()
        if not cola:
            # Higiene: no acumular claves de IPs ya "limpias" (memoria acotada).
            _intentos_login_por_ip.pop(ip, None)
            return False
        return len(cola) >= maximo


def _login_ip_registrar_fallo(ip: str) -> None:
    """Anota un intento FALLIDO de esta IP (los exitosos no cuentan)."""
    with _candado_login_ips:
        _intentos_login_por_ip.setdefault(ip, deque()).append(time.monotonic())


def reiniciar_limite_login_por_ip() -> None:
    """Vacia el estado del limite por IP (lo usa la suite de tests entre casos)."""
    with _candado_login_ips:
        _intentos_login_por_ip.clear()

# --------------------------------------------------------------------------- #
# MFA (segundo factor PASSKEYS / WebAuthn), GATEADO por `KENI_CONSOLA_MFA` (def OFF).
# --------------------------------------------------------------------------- #
#
# FLUJO LOGIN con MFA ON y usuario con >=1 passkey:
#   1) POST /api/auth/login  con user/pass OK -> NO crea sesion. Devuelve 200 {mfa_required:
#      true} y establece una cookie PRE-AUTH de corta vida (5 min) que SOLO identifica al usuario
#      que ya supero el factor 1. No es una sesion: no abre nada de `/api`.
#   2) POST /api/auth/mfa/login/opciones (cookie pre-auth) -> devuelve las opciones WebAuthn de
#      autenticacion y establece la cookie de CHALLENGE (Fernet, 5 min) atada al usuario.
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
# Challenge del login PASSWORDLESS (credencial descubrible): aun NO sabemos quien es, asi que el
# token NO ata usuario (uid=""); la assertion se verifica criptograficamente contra la clave
# publica de la credencial que el navegador devuelva.
COOKIE_MFA_CHALLENGE_PASSKEY = "keni_consola_mfa_reto_passkey"
# Challenge del ALTA ASISTIDA por superadmin (registro de una passkey EN NOMBRE de otra cuenta):
# atada al usuario DESTINO. Cookie propia para no pisar el enrolamiento que el superadmin pudiera
# tener a la vez sobre SU cuenta (`..._REGISTRO`).
COOKIE_MFA_CHALLENGE_ASISTIDO = "keni_consola_mfa_reto_asistido"
# Vida del estado pre-auth/challenge: 5 minutos para completar la ceremonia. Corta a proposito.
_MFA_PENDIENTE_TTL_SEG = 300

_MSG_MFA_NO_DISPONIBLE = (
    "El segundo factor no está disponible: falta configurar la clave de firma "
    "(KENI_CONSOLA_MFA_KEY). Avisa a un administrador."
)
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
    """Establece una cookie de challenge WebAuthn: HttpOnly, SameSite=Strict, vida corta (5 min)."""
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
    """Establece la cookie de sesion: HttpOnly, SameSite=Strict, path=/ (CONTRATO).

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
    """Establece la cookie PRE-AUTH (factor-1 superado): HttpOnly, SameSite=Strict, vida corta.

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


def _respuesta_sesion_creada(
    usuario_id: str, usuario: dict, *, debe_inscribir_mfa: bool = False
) -> Response:
    """Crea la sesion real, establece su cookie y borra la pre-auth; devuelve la respuesta 200.

    `debe_inscribir_mfa` (flujo de GRACIA): True cuando a esta persona el admin le EXIGE
    segundo factor (`mfa_requerido`) y aun NO tiene passkey. NO bloqueamos el login (no hay
    lockout): abrimos la sesion pero marcamos al cliente para que la UI FUERCE la inscripcion.
    """
    token = auth.crear_sesion(usuario_id)
    cuerpo = {
        "id": usuario["id"],
        "usuario": usuario["usuario"],
        "rol": usuario["rol"],
        "debe_cambiar_password": usuario["debe_cambiar_password"],
    }
    if debe_inscribir_mfa:
        cuerpo["debe_inscribir_mfa"] = True
    resp = JSONResponse({"usuario": cuerpo})
    _set_cookie_sesion(resp, token)
    _borrar_cookie_pendiente(resp)
    # Higiene: la ceremonia termino, cerramos la cookie de challenge de login.
    _borrar_cookie_challenge(resp, COOKIE_MFA_CHALLENGE_LOGIN)
    return resp


def _elevar_a_segundo_factor(autenticado: dict) -> Response:
    """Responde {mfa_required:true} + cookie pre-auth, o 503 (fail-safe) si no hay clave.

    El usuario YA superó la contraseña y DEBE pasar el segundo factor (tiene >=1 passkey). NO se
    abre sesion todavia. Si no hay clave de firma valida (`KENI_CONSOLA_MFA_KEY`), NO podemos
    emitir la pre-auth NI verificar la ceremonia: rehusamos (503) en vez de media-autenticar.
    """
    token_pendiente = _emitir_token_pendiente(autenticado["id"])
    if token_pendiente is None:
        _logger.warning(
            "MFA exigido para un usuario pero KENI_CONSOLA_MFA_KEY falta/es invalida: "
            "login rechazado (fail-safe). usuario=%s",
            autenticado["usuario"],
        )
        return JSONResponse({"error": _MSG_MFA_NO_DISPONIBLE}, status_code=503)
    resp = JSONResponse({"mfa_required": True})
    _set_cookie_pendiente(resp, token_pendiente)
    return resp


def _mfa_requerido_a(autenticado: dict) -> bool:
    """True si a ESTE usuario se le EXIGE segundo factor Y la maquinaria puede operar.

    Delega en `seguridad.mfa_requerido_para` (fuente única), que combina las tres políticas de
    obligación (global `KENI_CONSOLA_MFA`, admins `KENI_CONSOLA_MFA_ADMIN`, y la columna
    per-usuario `mfa_requerido`), todas gateadas por que haya clave de firma (anti-lockout).
    """
    return seguridad.mfa_requerido_para(autenticado)


def _mfa_enrolamiento_disponible(usuario: dict | None) -> bool:
    """¿Puede ESTE usuario (de sesion) usar los endpoints de enrolamiento de passkeys?

    MFA es OPT-IN POR USUARIO: con la maquinaria activa (hay clave de firma) CUALQUIER
    usuario con sesion puede inscribir una passkey para SU cuenta. Sin maquinaria (sin
    clave) no se puede correr la ceremonia -> 404. La obligacion (admin / flag global) solo
    decide a QUIEN se le FUERZA, no quien PUEDE activarlo.
    """
    return usuario is not None and seguridad.mfa_maquinaria_activa()


async def login(request: Request) -> Response:
    """POST /api/auth/login: valida credenciales, abre sesion y establece la cookie.

    Antes de NADA (ni siquiera leer el body) se aplica el limite de intentos FALLIDOS por
    IP (429): es la barrera barata contra fuerza bruta distribuida sobre muchas cuentas y
    contra el DoS de lockout (bloquear cuentas ajenas a base de fallos).
    """
    ip = _ip_cliente(request)
    if _login_ip_bloqueada(ip):
        return JSONResponse({"error": _MSG_LOGIN_IP_LIMITE}, status_code=429)

    datos = await leer_json(request)
    usuario = datos.get("usuario")
    password = datos.get("password")
    if not isinstance(usuario, str) or not isinstance(password, str) or not usuario or not password:
        # Mismo mensaje generico que un fallo de credenciales (no damos pistas).
        _login_ip_registrar_fallo(ip)
        return JSONResponse({"error": _MSG_LOGIN_KO}, status_code=401)
    if len(password) > auth.LONGITUD_MAX_PASSWORD or len(usuario) > auth.LONGITUD_MAX_USUARIO:
        # Tope anti-DoS: no hasheamos (scrypt) entradas absurdamente largas. Generico.
        _login_ip_registrar_fallo(ip)
        return JSONResponse({"error": _MSG_LOGIN_KO}, status_code=401)

    autenticado = auth.autenticar(usuario, password)
    if autenticado is None:
        _login_ip_registrar_fallo(ip)
        return JSONResponse({"error": _MSG_LOGIN_KO}, status_code=401)

    # ¿Hay que EXIGIR el segundo factor a este usuario?
    #   - Si la maquinaria esta activa (hay clave) y el usuario YA tiene passkey -> ceremonia.
    #   - EXIGIDO POR EL ADMIN (`mfa_requerido`) + hay clave: si aun NO tiene passkey, entra en
    #     GRACIA (sesion marcada `debe_inscribir_mfa`); el frontend lo fuerza a inscribir una
    #     llave antes de usar la consola. La clave es la red anti-lockout: sin clave no se eleva
    #     ni se fuerza nada. Sin maquinaria (sin clave): sesion directa, INTACTO.
    mfa_activo = bool(autenticado.get("mfa_activo"))
    requiere_mfa = _mfa_requerido_a(autenticado)

    if mfa_activo and seguridad.mfa_maquinaria_activa():
        return _elevar_a_segundo_factor(autenticado)

    if requiere_mfa and not mfa_activo:
        # GRACIA: se le exige MFA pero aun SIN passkey. No bloqueamos el login: abrimos sesion
        # y marcamos `debe_inscribir_mfa` para que la UI lo fuerce a inscribir una llave ya.
        _logger.info(
            "Usuario con MFA exigido y sin passkey entra en gracia (debe inscribir). usuario=%s",
            autenticado["usuario"],
        )
        return _respuesta_sesion_creada(
            autenticado["id"], autenticado, debe_inscribir_mfa=True
        )

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
    # `marcas` (organigrama del cliente): se consultan SIEMPRE porque la sesion del middleware
    # no las arrastra (la cookie no carga la tabla N:M). La pagina de Mi cuenta y el filtro
    # de la rota las usan para saber a que verticales pertenece la persona.
    refrescado = auth.obtener_usuario_por_id(usuario["id"]) or {}
    mfa_activo = bool(refrescado.get("mfa_activo"))
    # `debe_inscribir_mfa`: a esta persona se le EXIGE segundo factor (por política global, de
    # admin o per-usuario; ver `seguridad.mfa_requerido_para`), la maquinaria opera (hay clave) y
    # aun no tiene passkey. El frontend lo usa para FORZAR el enrolamiento (pantalla obligatoria)
    # antes de dejar usar la consola.
    debe_inscribir_mfa = seguridad.mfa_requerido_para(refrescado) and not mfa_activo
    return JSONResponse(
        {
            "usuario": {
                "id": usuario["id"],
                "usuario": usuario["usuario"],
                "rol": usuario["rol"],
                # `es_admin` (rediseño de la Prompts): bool plano para que el frontend
                # gatee acciones de admin (publicar a producción, aprobar solicitudes) sin
                # re-derivar el rol. Fuente única: `permisos.es_admin`.
                "es_admin": permisos.es_admin(request),
                # `es_superadmin`: UNICO con acceso a Usuarios (gestion de cuentas). Un admin
                # normal NO. El frontend gatea el panel y el enlace del menu con esto.
                "es_superadmin": permisos.es_superadmin(request),
                "debe_cambiar_password": usuario["debe_cambiar_password"],
                "creado": usuario.get("creado", ""),
                "ultimo_acceso": usuario.get("ultimo_acceso", ""),
                # `nombre` (humano, organigrama): lo edita la propia persona en "Mi cuenta"
                # (PATCH /api/auth/me). Si esta vacio la UI cae al `usuario` (login).
                "nombre": refrescado.get("nombre", "") or usuario.get("nombre", "") or "",
                "cargo": refrescado.get("cargo", "") or usuario.get("cargo", "") or "",
                "cobertura": bool(refrescado.get("cobertura") or usuario.get("cobertura")),
                "puede_coordinar": bool(
                    refrescado.get("puede_coordinar") or usuario.get("puede_coordinar")
                ),
                "marcas": list(refrescado.get("marcas") or []),
                # MFA (segundo factor, passkeys): `mfa_habilitado` refleja la disponibilidad
                # EFECTIVA de la maquinaria (flag global ON, o MFA de admin obligatorio + hay
                # clave): la UI muestra la seccion de "Llaves de acceso" cuando esta activa, para
                # que un admin obligado pueda inscribirse aunque el flag global este OFF.
                # `mfa_activo` dice si ESTE usuario tiene >=1 passkey. `debe_inscribir_mfa` empuja
                # al admin sin passkey a registrar una (forzado de experiencia, sin lockout).
                "mfa_habilitado": seguridad.mfa_maquinaria_activa(),
                "mfa_activo": mfa_activo,
                "debe_inscribir_mfa": debe_inscribir_mfa,
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
    motivo = auth.motivo_rechazo_password(nueva, usuario.get("usuario", ""), config.password_min())
    if motivo is not None:
        return JSONResponse({"error": motivo}, status_code=400)
    # Tope anti-DoS en la actual (no hasheamos una entrada enorme); cuenta como incorrecta.
    if len(actual) > auth.LONGITUD_MAX_PASSWORD or not auth.verificar_password_actual(usuario["id"], actual):
        return JSONResponse({"error": "La contraseña actual no es correcta."}, status_code=400)

    auth.establecer_password(usuario["id"], nueva, debe_cambiar_password=False)
    # `establecer_password` invalida TODAS las sesiones del usuario (seguridad). Para no
    # forzar un re-login en el cambio voluntario, reabrimos UNA sesion nueva (rotacion)
    # y la inicializamos en la cookie del dispositivo actual.
    token = auth.crear_sesion(usuario["id"])
    resp = Response(status_code=204)
    _set_cookie_sesion(resp, token)
    return resp


# Limite del nombre HUMANO (organigrama). Igual que en `api/usuarios` (el admin lo edita
# alli); aqui la persona edita el SUYO desde "Mi cuenta".
_LONGITUD_MAX_NOMBRE = 120


async def actualizar_mi_perfil(request: Request) -> Response:
    """PATCH /api/auth/me: la persona edita SU PROPIO nombre humano (organigrama).

    Solo el `nombre` (lo que se pinta en las tarjetas): NUNCA el rol, el login ni las
    marcas (eso es competencia del admin en `/api/usuarios`). Por token de bootstrap no hay
    usuario -> 401. `nombre=""` deja la tarjeta cayendo al login.
    """
    usuario = getattr(request.state, "usuario", None)
    if usuario is None:
        return JSONResponse(
            {"error": "Necesitas una sesión iniciada para editar tu perfil."},
            status_code=401,
        )
    datos = await leer_json(request)
    nombre = datos.get("nombre")
    if not isinstance(nombre, str):
        return JSONResponse({"error": "El nombre debe ser texto."}, status_code=400)
    nombre = nombre.strip()
    if len(nombre) > _LONGITUD_MAX_NOMBRE:
        return JSONResponse(
            {"error": f"El nombre no puede superar {_LONGITUD_MAX_NOMBRE} caracteres."},
            status_code=400,
        )
    auth.actualizar_perfil(usuario["id"], nombre=nombre)
    return JSONResponse({"nombre": nombre})


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
    `startAuthentication` y establece la cookie de challenge (Fernet, 5 min, atada al usuario).
    Si el usuario ya no tiene passkeys (reset admin entre pasos), caduca la pre-auth.
    """
    # Maquinaria EFECTIVA (flag global, o MFA de admin obligatorio + clave): si el login elevó,
    # aquí debe estar activa. (Solo se llega con cookie pre-auth, que solo existe si se elevó.)
    if not seguridad.mfa_maquinaria_activa():
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
    """POST /api/auth/mfa/verify: 2o paso del login. Valida una ASSERTION WebAuthn (passkey).

    PUBLICO (cookie pre-auth + cookie challenge). Cuerpo: `{assertion: {...}}` (la credencial que
    devuelve `startAuthentication`). Si cuadra, crea la sesion real, establece su cookie y borra
    las pre-auth/challenge. Con el flag OFF no deberia recibir trafico; aun asi rehusa limpiamente.
    NO hay via de codigo de recuperacion (se retiro): la recuperacion es por reset de un superadmin.
    """
    if not seguridad.mfa_maquinaria_activa():
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

    # Assertion WebAuthn. Exige la cookie de challenge (NUNCA un challenge del cliente).
    if not isinstance(assertion, (dict, str)) or not assertion:
        return JSONResponse({"error": "Falta la llave de acceso."}, status_code=400)

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
    # reportan 0 y nunca incrementan, asi que no es dictamen. Igual actualizamos el contador.
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
# Login PASSWORDLESS por passkey (credencial descubrible, sin usuario/contrasena) #
# --------------------------------------------------------------------------- #


async def passkey_opciones(request: Request) -> Response:
    """POST /api/auth/passkey/opciones: opciones WebAuthn de login SIN usuario previo (descubrible).

    PUBLICO. La maquinaria MFA debe estar activa (hay clave). `allow_credentials` vacio: el
    navegador ofrece las passkeys descubribles que el usuario tenga para este sitio. El challenge
    se guarda en una cookie Fernet (5 min) NO atada a usuario; la identidad la prueba luego la
    assertion. Fail-safe (503) si falta la clave de firma.
    """
    if not seguridad.mfa_maquinaria_activa():
        return JSONResponse({"error": _MSG_MFA_NO_DISPONIBLE}, status_code=503)
    try:
        # Sin credenciales -> allow_credentials vacio -> login por credencial DESCUBRIBLE.
        opciones_json, challenge = auth.opciones_login(_rp_id(), [])
    except auth.MfaNoDisponible:  # pragma: no cover - opciones_login no firma; defensivo
        return JSONResponse({"error": _MSG_MFA_NO_DISPONIBLE}, status_code=503)
    token_reto = _emitir_token_challenge(challenge, "")
    if token_reto is None:
        _logger.warning("passkey/opciones: KENI_CONSOLA_MFA_KEY falta/es invalida (fail-safe).")
        return JSONResponse({"error": _MSG_MFA_NO_DISPONIBLE}, status_code=503)
    resp = Response(content=opciones_json, media_type="application/json")
    _set_cookie_challenge(resp, COOKIE_MFA_CHALLENGE_PASSKEY, token_reto)
    return resp


async def passkey_verify(request: Request) -> Response:
    """POST /api/auth/passkey/verify: login passwordless. Verifica una assertion y ABRE la sesion.

    PUBLICO. Cuerpo `{assertion: {...}}` (lo que devuelve `startAuthentication`). La credencial
    se localiza GLOBALMENTE por su id; se verifica la firma contra su clave publica EXIGIENDO
    user-verification (la passkey vale por dos factores: posesion + biometria/PIN). Si cuadra,
    crea la sesion real. Aplica el limite por IP (igual que el login) contra abuso.
    """
    ip = _ip_cliente(request)
    if _login_ip_bloqueada(ip):
        return JSONResponse({"error": _MSG_LOGIN_IP_LIMITE}, status_code=429)
    if not seguridad.mfa_maquinaria_activa():
        return JSONResponse({"error": _MSG_MFA_NO_DISPONIBLE}, status_code=503)

    challenge = _leer_token_challenge(request.cookies.get(COOKIE_MFA_CHALLENGE_PASSKEY), "")
    if challenge is None:
        resp = JSONResponse({"error": _MSG_MFA_CEREMONIA_KO}, status_code=401)
        _borrar_cookie_challenge(resp, COOKIE_MFA_CHALLENGE_PASSKEY)
        return resp

    datos = await leer_json(request)
    assertion = datos.get("assertion")
    if not isinstance(assertion, (dict, str)) or not assertion:
        return JSONResponse({"error": "Falta la llave de acceso."}, status_code=400)

    credential_id = auth.credential_id_de_respuesta(assertion)
    credencial = auth.credencial_mfa_global(credential_id) if credential_id else None
    if credencial is None:
        _login_ip_registrar_fallo(ip)
        return JSONResponse({"error": _MSG_MFA_CEREMONIA_KO}, status_code=401)

    try:
        nuevo_sign_count = auth.verificar_login(
            assertion, challenge, credencial, _rp_id(), _rp_origenes(),
            require_user_verification=True,
        )
    except Exception as exc:  # noqa: BLE001 - py_webauthn lanza varias; todas son KO
        _login_ip_registrar_fallo(ip)
        _logger.info("passkey/verify: assertion WebAuthn rechazada: %s", exc)
        return JSONResponse({"error": _MSG_MFA_CEREMONIA_KO}, status_code=401)

    if nuevo_sign_count and nuevo_sign_count < int(credencial.get("sign_count", 0) or 0):
        _logger.warning(
            "passkey/verify: sign_count retrocedio para la credencial %s (posible clon).",
            credencial["id"],
        )
    auth.actualizar_sign_count_mfa(credencial["id"], nuevo_sign_count)

    usuario = auth.obtener_usuario_por_id(credencial["usuario_id"])
    if usuario is None:  # credencial huerfana (usuario borrado): trata como ceremonia KO
        return JSONResponse({"error": _MSG_MFA_CEREMONIA_KO}, status_code=401)
    resp = _respuesta_sesion_creada(usuario["id"], usuario)
    _borrar_cookie_challenge(resp, COOKIE_MFA_CHALLENGE_PASSKEY)
    return resp


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
    (excluye las passkeys ya enroladas) y establece la cookie de challenge de registro.
    """
    usuario = _exige_sesion(request)
    if usuario is None:
        return JSONResponse({"error": "Necesitas una sesión iniciada."}, status_code=401)
    if not _mfa_enrolamiento_disponible(usuario):
        return JSONResponse({"error": "El segundo factor no está habilitado."}, status_code=404)

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
    """POST /api/auth/mfa/registro/verificar: guarda la passkey nueva (responde `{ok: true}`).

    Cuerpo `{credential: {...}, nombre?}`. Verifica la respuesta de `startRegistration` contra la
    cookie de challenge, persiste la credencial (clave publica + sign_count + transports) y marca
    `mfa_activo=1`. NO hay codigos de recuperacion (se retiraron): la recuperacion de cuenta es por
    reset de MFA de un superadmin. Requiere enrolamiento disponible + sesion completa.
    """
    usuario = _exige_sesion(request)
    if usuario is None:
        return JSONResponse({"error": "Necesitas una sesión iniciada."}, status_code=401)
    if not _mfa_enrolamiento_disponible(usuario):
        return JSONResponse({"error": "El segundo factor no está habilitado."}, status_code=404)

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

    resp = JSONResponse({"ok": True})
    _borrar_cookie_challenge(resp, COOKIE_MFA_CHALLENGE_REGISTRO)
    return resp


async def mfa_credenciales(request: Request) -> Response:
    """GET /api/auth/mfa/credenciales: lista las passkeys del usuario (SIN secretos).

    Devuelve `{credenciales: [{id, nombre, creada, ultimo_uso}]}`. Requiere enrolamiento
    disponible + sesion.
    """
    usuario = _exige_sesion(request)
    if usuario is None:
        return JSONResponse({"error": "Necesitas una sesión iniciada."}, status_code=401)
    if not _mfa_enrolamiento_disponible(usuario):
        return JSONResponse({"error": "El segundo factor no está habilitado."}, status_code=404)
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


async def mfa_credencial_renombrar(request: Request) -> Response:
    """PATCH /api/auth/mfa/credenciales/{id}: renombra UNA passkey del propio usuario (204).

    Cuerpo `{nombre}` (etiqueta legible; "" la vacía). Solo toca la etiqueta. Requiere sesión
    completa; 404 si esa credencial no es suya / no existe.
    """
    usuario = _exige_sesion(request)
    if usuario is None:
        return JSONResponse({"error": "Necesitas una sesión iniciada."}, status_code=401)
    datos = await leer_json(request)
    nombre = datos.get("nombre")
    if not isinstance(nombre, str):
        return JSONResponse({"error": "El nombre debe ser texto."}, status_code=400)
    nombre = nombre.strip()[:80]
    cred_id = request.path_params.get("id", "")
    if not auth.renombrar_credencial_mfa(usuario["id"], cred_id, nombre):
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


# --------------------------------------------------------------------------- #
# Alta ASISTIDA de passkey: un SUPERADMIN lanza la ceremonia (QR) para OTRA cuenta #
# --------------------------------------------------------------------------- #
#
# La passkey se crea en el TELÉFONO de la persona (Face ID/huella) por el QR híbrido: el superadmin
# arma la ceremonia desde la ficha del usuario, pero `authenticatorAttachment=cross-platform`
# fuerza el flujo «otro dispositivo» (QR), de modo que la clave privada NACE y se queda en el móvil
# de la persona, NO en el equipo del superadmin. El user handle es el de la cuenta DESTINO, así que
# la credencial queda guardada CONTRA esa cuenta. Requiere SESIÓN superadmin. (Proximidad: el móvil
# que escanea debe tener Bluetooth y estar cerca del equipo que muestra el QR.)

_MSG_SOLO_SUPERADMIN_PASSKEY = (
    "Solo un superadministrador puede registrar llaves de acceso de otra cuenta."
)


async def passkey_asistida_opciones(request: Request) -> Response:
    """POST /api/auth/passkey-asistida/{usuario_id}/opciones: opciones de REGISTRO para OTRA cuenta.

    Solo superadmin. Arma las opciones WebAuthn con el user handle de la cuenta DESTINO y forzando
    `cross-platform` (sale el QR / «otro dispositivo»: la passkey se crea en el teléfono de la
    persona). Siembra la cookie de challenge atada al usuario destino. 404 si la cuenta no existe;
    503 si la maquinaria MFA no opera (falta clave de firma).
    """
    if not permisos.es_superadmin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_SUPERADMIN_PASSKEY)
    if not seguridad.mfa_maquinaria_activa():
        return JSONResponse({"error": _MSG_MFA_NO_DISPONIBLE}, status_code=503)
    usuario_id = request.path_params["usuario_id"]
    destino = auth.obtener_usuario_por_id(usuario_id)
    if destino is None:
        return JSONResponse({"error": "El usuario no existe."}, status_code=404)

    existentes = auth.listar_credenciales_mfa(usuario_id)
    try:
        opciones_json, challenge = auth.opciones_registro(
            usuario_id,
            destino.get("usuario", "usuario"),
            _rp_id(),
            _rp_nombre(),
            existentes,
            solo_cross_device=True,
        )
    except auth.MfaNoDisponible:  # pragma: no cover - opciones_registro no firma; defensivo
        return JSONResponse({"error": _MSG_MFA_NO_DISPONIBLE}, status_code=503)

    token_reto = _emitir_token_challenge(challenge, usuario_id)
    if token_reto is None:
        _logger.warning(
            "passkey-asistida/opciones: KENI_CONSOLA_MFA_KEY falta/es invalida (fail-safe)."
        )
        return JSONResponse({"error": _MSG_MFA_NO_DISPONIBLE}, status_code=503)

    resp = Response(content=opciones_json, media_type="application/json")
    _set_cookie_challenge(resp, COOKIE_MFA_CHALLENGE_ASISTIDO, token_reto)
    return resp


async def passkey_asistida_verificar(request: Request) -> Response:
    """POST /api/auth/passkey-asistida/{usuario_id}/verificar: guarda la passkey en la cuenta DESTINO.

    Solo superadmin. Cuerpo `{credential, nombre?}` (lo que devuelve `startRegistration` en el
    navegador del superadmin cuando la persona escanea el QR). Verifica contra la cookie de
    challenge atada al destino y persiste la credencial CONTRA esa cuenta (enciende su `mfa_activo`).
    Se registra en el log para auditoría. 404 si la cuenta no existe; 409 si la llave ya estaba.
    """
    if not permisos.es_superadmin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_SUPERADMIN_PASSKEY)
    if not seguridad.mfa_maquinaria_activa():
        return JSONResponse({"error": _MSG_MFA_NO_DISPONIBLE}, status_code=503)
    usuario_id = request.path_params["usuario_id"]
    destino = auth.obtener_usuario_por_id(usuario_id)
    if destino is None:
        return JSONResponse({"error": "El usuario no existe."}, status_code=404)

    datos = await leer_json(request)
    credential = datos.get("credential")
    nombre = datos.get("nombre")
    nombre = nombre.strip()[:80] if isinstance(nombre, str) else ""
    if not isinstance(credential, (dict, str)) or not credential:
        return JSONResponse({"error": "Falta la credencial de la llave."}, status_code=400)

    challenge = _leer_token_challenge(
        request.cookies.get(COOKIE_MFA_CHALLENGE_ASISTIDO), usuario_id
    )
    if challenge is None:
        resp = JSONResponse(
            {"error": "La ceremonia de registro caducó. Vuelve a intentarlo."}, status_code=400
        )
        _borrar_cookie_challenge(resp, COOKIE_MFA_CHALLENGE_ASISTIDO)
        return resp

    try:
        nueva = auth.verificar_registro(credential, challenge, _rp_id(), _rp_origenes())
    except Exception as exc:  # noqa: BLE001 - py_webauthn lanza varias; tratamos todas como KO
        _logger.info("passkey-asistida/verificar: respuesta WebAuthn rechazada: %s", exc)
        resp = JSONResponse({"error": _MSG_MFA_CEREMONIA_KO}, status_code=400)
        _borrar_cookie_challenge(resp, COOKIE_MFA_CHALLENGE_ASISTIDO)
        return resp

    guardada = auth.guardar_credencial_mfa(
        usuario_id,
        credential_id=nueva["credential_id"],
        public_key=nueva["public_key"],
        sign_count=nueva["sign_count"],
        transports=nueva["transports"],
        nombre=nombre,
    )
    if not guardada:
        resp = JSONResponse(
            {"error": "Esa llave de acceso ya está registrada."}, status_code=409
        )
        _borrar_cookie_challenge(resp, COOKIE_MFA_CHALLENGE_ASISTIDO)
        return resp

    autor = seguridad.autor_de_peticion(request)
    _logger.warning(
        "Alta ASISTIDA de passkey: superadmin %s registró una llave para la cuenta %s.",
        (autor or {}).get("usuario", "?"),
        destino["usuario"],
    )
    resp = JSONResponse({"ok": True})
    _borrar_cookie_challenge(resp, COOKIE_MFA_CHALLENGE_ASISTIDO)
    return resp


RUTAS = [
    Route("/api/auth/login", login, methods=["POST"]),
    Route("/api/auth/logout", logout, methods=["POST"]),
    Route("/api/auth/me", me, methods=["GET"]),
    Route("/api/auth/me", actualizar_mi_perfil, methods=["PATCH"]),
    Route("/api/auth/cambiar-password", cambiar_password, methods=["POST"]),
    # MFA passkeys. `login/opciones` y `verify` son PUBLICOS (cookie pre-auth); el resto exige
    # sesion completa.
    Route("/api/auth/mfa/login/opciones", mfa_login_opciones, methods=["POST"]),
    Route("/api/auth/mfa/verify", mfa_verify, methods=["POST"]),
    # Login PASSWORDLESS por passkey (PUBLICOS, sin usuario/contrasena previos).
    Route("/api/auth/passkey/opciones", passkey_opciones, methods=["POST"]),
    Route("/api/auth/passkey/verify", passkey_verify, methods=["POST"]),
    Route("/api/auth/mfa/registro/opciones", mfa_registro_opciones, methods=["POST"]),
    Route("/api/auth/mfa/registro/verificar", mfa_registro_verificar, methods=["POST"]),
    Route("/api/auth/mfa/credenciales", mfa_credenciales, methods=["GET"]),
    Route("/api/auth/mfa/credenciales/{id}", mfa_credencial_renombrar, methods=["PATCH"]),
    Route("/api/auth/mfa/credenciales/{id}", mfa_credencial_borrar, methods=["DELETE"]),
    Route("/api/auth/mfa/disable", mfa_disable, methods=["POST"]),
    # Alta ASISTIDA por superadmin: lanzar la ceremonia (QR) para registrar una passkey en el
    # teléfono de OTRA cuenta. Exige sesión superadmin (no es pública).
    Route(
        "/api/auth/passkey-asistida/{usuario_id}/opciones",
        passkey_asistida_opciones,
        methods=["POST"],
    ),
    Route(
        "/api/auth/passkey-asistida/{usuario_id}/verificar",
        passkey_asistida_verificar,
        methods=["POST"],
    ),
]
