"""Segundo factor WEBAUTHN/FIDO2 (passkeys): construccion de opciones de registro/login,
verificacion de las respuestas del autenticador y persistencia del CHALLENGE en una cookie
Fernet de vida corta. GATEADO por `KENI_CONSOLA_MFA` (def OFF) desde la capa API.

POR QUE PASSKEYS (y no TOTP): el equipo no usa apps autenticadoras. Las passkeys
(Face ID / Touch ID / Windows Hello / llave del telefono) son el segundo factor real:
el "secreto" (la clave privada) NUNCA sale del dispositivo del usuario; el servidor solo
guarda la CLAVE PUBLICA y un contador. No hay secreto cifrable en reposo del lado servidor,
asi que la antigua clave Fernet ya NO cifra un secreto TOTP: ahora FIRMA (y fecha) el
challenge/pre-auth en una cookie de vida corta, que es lo unico que el servidor debe
recordar entre el paso "opciones" y el paso "verificar".

SEGURIDAD (no negociable):
  - El CHALLENGE de cada ceremonia (registro o login) lo genera py_webauthn y se DEVUELVE
    al cliente dentro de las opciones; para verificar la respuesta hay que recordar ESE MISMO
    challenge. Lo guardamos en una cookie Fernet (clave `KENI_CONSOLA_MFA_KEY`) con TTL <= 5
    min, NUNCA confiando en un challenge que mande el cliente. La cookie ata `{challenge,
    usuario_id}`: la verificacion exige que el usuario de la cookie sea el de la ceremonia.
  - FAIL-SAFE: si el flag MFA esta ON pero `KENI_CONSOLA_MFA_KEY` falta o es invalida,
    `cifrador()` lanza `MfaNoDisponible` y la API REHUSA la ceremonia (con un aviso logueado)
    con 503, en vez de seguir media-autenticando. Sin clave, no hay segundo factor.
  - El sign_count se actualiza tras cada login; un contador que RETROCEDE se LOGUEA como aviso
    (posible clon) pero no tumba el login por si solo (muchos autenticadores reportan 0 y
    nunca incrementan): solo es senal, no dictamen.

RECUPERACION DE CUENTA: NO hay codigos de recuperacion (se retiraron por seguridad: eran un
camino contrasena+codigo que evitaba la passkey). Si alguien pierde todos sus dispositivos, un
SUPERADMIN resetea su MFA desde Usuarios (`PATCH /api/usuarios/{id}` con `mfa_reset`).

Este modulo NO toca la BD: la persistencia de credenciales (`webauthn_credenciales`) vive en
`auth.usuarios`. La clave Fernet se le pasa como argumento desde la API (que la resuelve via
`config.mfa_key()`), para que la decision fail-safe sea explicita en un solo sitio y facil de testear.
"""

from __future__ import annotations

import json
from typing import Any

# Nombre que se muestra al usuario al crear/usar una passkey (Relying Party display name).
# Lo sobrescribe la API con `config.rp_nombre()`; este es el defecto del dominio.
NOMBRE_RP_DEFECTO = "Keni Social"


class MfaNoDisponible(RuntimeError):
    """El segundo factor no puede operar: falta `KENI_CONSOLA_MFA_KEY` o es invalida (fail-safe).

    La API la captura para responder un error claro (503) y loguear un aviso SIN seguir una
    ceremonia a medias: las opciones/verificacion rehusan limpiamente cuando no hay clave para
    firmar/leer la cookie del challenge.
    """


# --------------------------------------------------------------------------- #
# Cifrado/firma de la cookie de challenge + pre-auth (Fernet)                  #
# --------------------------------------------------------------------------- #


def cifrador(clave: str | None) -> Any:
    """Construye un `Fernet` a partir de la clave (base64 url-safe de 32 bytes); o rehusa.

    `clave` es el valor de `KENI_CONSOLA_MFA_KEY` (lo resuelve la API). Si es None/vacia o no
    es una clave Fernet bien formada, lanza `MfaNoDisponible` (fail-safe): nunca se cae a un
    modo "sin firmar". `cryptography` es una dependencia del back hosted; si faltara, tambien
    se trata como no disponible (no se intenta un fallback inseguro).
    """
    if not clave:
        raise MfaNoDisponible(
            "Falta KENI_CONSOLA_MFA_KEY: el segundo factor no puede operar sin clave de firma."
        )
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:  # pragma: no cover - dependencia presente en el back hosted
        raise MfaNoDisponible(
            "Falta la dependencia 'cryptography' para firmar la cookie del segundo factor."
        ) from exc
    try:
        return Fernet(clave.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise MfaNoDisponible(
            "KENI_CONSOLA_MFA_KEY no es una clave Fernet valida (base64 url-safe de 32 bytes)."
        ) from exc


# --------------------------------------------------------------------------- #
# Helpers de codificacion base64url (interop con @simplewebauthn/browser)       #
# --------------------------------------------------------------------------- #
#
# py_webauthn trabaja con `bytes` y expone `bytes_to_base64url`/`base64url_to_bytes`. Guardamos
# `credential_id`/`public_key` como base64url (TEXT) en la BD para no depender del round-trip de
# BYTEA; estos wrappers concentran la conversion para que el resto del codigo hable en str.


def bytes_a_b64url(crudo: bytes) -> str:
    """Codifica bytes como base64url SIN padding (lo que usa la spec WebAuthn / @simplewebauthn)."""
    from webauthn.helpers import bytes_to_base64url

    return bytes_to_base64url(crudo)


def b64url_a_bytes(texto: str) -> bytes:
    """Decodifica base64url (con o sin padding) a bytes."""
    from webauthn.helpers import base64url_to_bytes

    return base64url_to_bytes(texto)


# --------------------------------------------------------------------------- #
# Registro de una passkey (enrolamiento)                                        #
# --------------------------------------------------------------------------- #


def opciones_registro(
    usuario_id: str,
    usuario_nombre: str,
    rp_id: str,
    rp_nombre: str,
    credenciales_existentes: list[dict[str, Any]],
    *,
    solo_cross_device: bool = False,
) -> tuple[str, str]:
    """Genera las opciones de REGISTRO (creacion de credencial) y devuelve `(opciones_json, challenge_b64url)`.

    `opciones_json` es JSON spec-compliant (de `options_to_json`) que el frontend pasa TAL CUAL
    a `startRegistration({optionsJSON})`. `challenge_b64url` es el challenge que hay que RECORDAR
    (en la cookie Fernet) para `verificar_registro`.

    `credenciales_existentes` son las passkeys que el usuario YA tiene (cada una con su
    `credential_id` en base64url): se pasan como `exclude_credentials` para que el navegador no
    deje registrar dos veces el MISMO autenticador.

    `solo_cross_device` (alta ASISTIDA por un superadmin): cuando True, fija
    `authenticatorAttachment=cross-platform`. Así el navegador NO ofrece el autenticador de
    plataforma de ESTA máquina (el Touch ID del superadmin) sino el flujo «otro dispositivo» —el
    código QR híbrido—, para que la passkey se cree en el TELÉFONO de la persona (Face ID/huella),
    no en el equipo del superadmin. En el enrolamiento normal (el usuario sobre su propia cuenta)
    se deja en False: cada quien elige su autenticador.
    """
    from webauthn import generate_registration_options, options_to_json
    from webauthn.helpers.structs import (
        AuthenticatorAttachment,
        AuthenticatorSelectionCriteria,
        PublicKeyCredentialDescriptor,
        ResidentKeyRequirement,
    )

    excluir = [
        PublicKeyCredentialDescriptor(id=b64url_a_bytes(c["credential_id"]))
        for c in credenciales_existentes
        if c.get("credential_id")
    ]
    seleccion = AuthenticatorSelectionCriteria(
        # Passkeys: pedimos resident key/discoverable cuando se pueda (mejor UX), pero sin
        # EXIGIRla (preferred) para no romper autenticadores de plataforma mas viejos.
        resident_key=ResidentKeyRequirement.PREFERRED,
        authenticator_attachment=(
            AuthenticatorAttachment.CROSS_PLATFORM if solo_cross_device else None
        ),
    )
    opciones = generate_registration_options(
        rp_id=rp_id,
        rp_name=rp_nombre,
        # El user handle DEBE ser bytes opacos y estables por usuario (no PII): usamos el id
        # interno (hex de 12 chars) codificado a bytes. `user_name`/`user_display_name` son la
        # etiqueta legible que el autenticador muestra.
        user_id=usuario_id.encode("utf-8"),
        user_name=usuario_nombre,
        user_display_name=usuario_nombre,
        exclude_credentials=excluir,
        authenticator_selection=seleccion,
    )
    challenge_b64url = bytes_a_b64url(opciones.challenge)
    return options_to_json(opciones), challenge_b64url


def verificar_registro(
    respuesta_json: str | dict[str, Any],
    challenge_esperado_b64url: str,
    rp_id: str,
    origenes_esperados: list[str],
) -> dict[str, Any]:
    """Verifica la respuesta de registro del navegador; devuelve la credencial a persistir.

    `respuesta_json` es el JSON que devuelve `startRegistration` (string u objeto). El challenge
    esperado viene de la cookie (NUNCA del cliente). Devuelve un dict listo para guardar:
    `{credential_id, public_key, sign_count, transports}` (los dos primeros en base64url).

    Lanza `Exception` (de py_webauthn) si la verificacion falla; la API la traduce a 400.
    """
    from webauthn import verify_registration_response

    cuerpo = respuesta_json if isinstance(respuesta_json, str) else json.dumps(respuesta_json)
    verificacion = verify_registration_response(
        credential=cuerpo,
        expected_challenge=b64url_a_bytes(challenge_esperado_b64url),
        expected_rp_id=rp_id,
        # py_webauthn acepta `str` o `list[str]` como origen(es) esperado(s): pasamos la lista
        # completa para soportar varios origenes permitidos (p.ej. dominio + alias).
        expected_origin=origenes_esperados or "",
    )
    transports = _transports_de_respuesta(respuesta_json)
    return {
        "credential_id": bytes_a_b64url(verificacion.credential_id),
        "public_key": bytes_a_b64url(verificacion.credential_public_key),
        "sign_count": int(verificacion.sign_count),
        "transports": json.dumps(transports),
    }


def _transports_de_respuesta(respuesta_json: str | dict[str, Any]) -> list[str]:
    """Extrae `response.transports` (p.ej. ["internal","hybrid"]) de la respuesta de registro.

    Es informativo (mejora la UX del proximo login al sugerir el transporte); si falta o el
    JSON es ilegible, devolvemos [] (no es critico para la seguridad).
    """
    try:
        datos = respuesta_json if isinstance(respuesta_json, dict) else json.loads(respuesta_json)
    except (json.JSONDecodeError, TypeError):
        return []
    resp = datos.get("response") if isinstance(datos, dict) else None
    transports = resp.get("transports") if isinstance(resp, dict) else None
    if isinstance(transports, list) and all(isinstance(t, str) for t in transports):
        return transports
    return []


# --------------------------------------------------------------------------- #
# Autenticacion con una passkey (segundo paso del login)                        #
# --------------------------------------------------------------------------- #


def opciones_login(
    rp_id: str,
    credenciales_usuario: list[dict[str, Any]],
) -> tuple[str, str]:
    """Genera las opciones de AUTENTICACION y devuelve `(opciones_json, challenge_b64url)`.

    `credenciales_usuario` son las passkeys del usuario que ya supero la contrasena: se pasan
    como `allow_credentials` para que el navegador ofrezca SOLO esas (y, con sus transports,
    sugiera donde estan). `opciones_json` va tal cual a `startAuthentication({optionsJSON})`.
    """
    from webauthn import generate_authentication_options, options_to_json
    from webauthn.helpers.structs import PublicKeyCredentialDescriptor

    permitir = []
    for c in credenciales_usuario:
        if not c.get("credential_id"):
            continue
        transports = _transports_guardados(c.get("transports"))
        permitir.append(
            PublicKeyCredentialDescriptor(
                id=b64url_a_bytes(c["credential_id"]),
                transports=transports or None,
            )
        )
    # Lista vacia -> `None` (OMITIR `allowCredentials`): login por credencial DESCUBRIBLE
    # (passwordless). Un `allowCredentials: []` explicito lo interpretan algunos navegadores como
    # "ninguna credencial permitida"; omitirlo es lo correcto para el flujo sin usuario.
    opciones = generate_authentication_options(rp_id=rp_id, allow_credentials=permitir or None)
    return options_to_json(opciones), bytes_a_b64url(opciones.challenge)


def _transports_guardados(crudo: Any) -> list[Any]:
    """Convierte el JSON `transports` guardado en una lista de `AuthenticatorTransport`.

    Los transports son una pista (no critica): si el valor es ilegible o trae un transporte
    desconocido para esta version de py_webauthn, lo ignoramos sin fallar.
    """
    if not crudo:
        return []
    try:
        from webauthn.helpers.structs import AuthenticatorTransport
    except ImportError:  # pragma: no cover
        return []
    try:
        valores = json.loads(crudo) if isinstance(crudo, str) else crudo
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(valores, list):
        return []
    salida: list[Any] = []
    for v in valores:
        try:
            salida.append(AuthenticatorTransport(v))
        except ValueError:
            continue
    return salida


def verificar_login(
    respuesta_json: str | dict[str, Any],
    challenge_esperado_b64url: str,
    credencial: dict[str, Any],
    rp_id: str,
    origenes_esperados: list[str],
    *,
    require_user_verification: bool = False,
) -> int:
    """Verifica la assertion del navegador contra la credencial guardada; devuelve el nuevo sign_count.

    `credencial` es la fila de `webauthn_credenciales` (con `public_key` y `sign_count` en
    base64url/int). El challenge esperado viene de la cookie. Lanza la `Exception` de
    py_webauthn si la firma/origen/challenge no cuadran (la API -> 401).

    `require_user_verification`: en el 2o factor (tras la contrasena) NO se exige UV (`False`):
    la contrasena ya fue el factor 1. En el login PASSWORDLESS (la passkey es la unica prueba)
    se exige `True`: el autenticador DEBE haber verificado al usuario (biometria/PIN), de modo
    que la passkey valga por dos factores (algo que tienes + algo que eres/sabes).

    Sobre sign_count: py_webauthn detecta un contador clonado. Aqui pasamos `expected_sign_count`
    para que no rechace autenticadores que reportan 0 y nunca incrementan; la deteccion de
    regresion (posible clon) la hace el llamante comparando el valor devuelto con el guardado.
    """
    from webauthn import verify_authentication_response

    cuerpo = respuesta_json if isinstance(respuesta_json, str) else json.dumps(respuesta_json)
    verificacion = verify_authentication_response(
        credential=cuerpo,
        expected_challenge=b64url_a_bytes(challenge_esperado_b64url),
        expected_rp_id=rp_id,
        expected_origin=origenes_esperados or "",
        credential_public_key=b64url_a_bytes(credencial["public_key"]),
        credential_current_sign_count=int(credencial.get("sign_count", 0) or 0),
        require_user_verification=require_user_verification,
    )
    return int(verificacion.new_sign_count)


def credential_id_de_respuesta(respuesta_json: str | dict[str, Any]) -> str | None:
    """`id` (base64url) de la credencial usada en una assertion de login; None si ilegible.

    La API lo usa para localizar en BD la fila `webauthn_credenciales` con la que verificar.
    `id` ya viene en base64url desde @simplewebauthn (es el `rawId` codificado).
    """
    try:
        datos = respuesta_json if isinstance(respuesta_json, dict) else json.loads(respuesta_json)
    except (json.JSONDecodeError, TypeError):
        return None
    cid = datos.get("id") if isinstance(datos, dict) else None
    return cid if isinstance(cid, str) and cid else None
