"""Segundo factor TOTP (MFA): generacion/verificacion del secreto, cifrado en reposo y
codigos de recuperacion. GATEADO por `KENI_CONSOLA_MFA` (def OFF) desde la capa API.

SEGURIDAD (no negociable):
  - El secreto TOTP se guarda SIEMPRE cifrado con Fernet (`cifrar_secreto`/`descifrar_secreto`)
    bajo la clave `KENI_CONSOLA_MFA_KEY`. NUNCA en claro.
  - FAIL-SAFE: si el flag MFA esta ON pero `KENI_CONSOLA_MFA_KEY` falta o es invalida,
    `cifrador()` lanza `MfaNoDisponible` y la API REHUSA el enrolamiento/verificacion (con un
    aviso logueado), en vez de tocar el secreto en claro. Sin clave, no hay MFA.
  - Los codigos de RECUPERACION se guardan HASHEADOS (scrypt, el mismo hasher que la
    contrasena) y se comparan en tiempo constante; el codigo gastado se consume (un solo uso).
  - La verificacion TOTP usa `pyotp` con `valid_window=1` (tolera un paso de 30s de desfase de
    reloj) y comparacion en tiempo constante.

Este modulo NO toca la BD ni lee `config`/env directamente para los SECRETOS de negocio: la
clave Fernet se le pasa como argumento desde la API (que la resuelve via `config.mfa_key()`),
para que sea facil de testear y para que la decision fail-safe sea explicita en un solo sitio.
"""

from __future__ import annotations

import base64
import json
import secrets
from typing import Any

from .hashing import hashear_password, verificar_password

# Emisor por defecto que se muestra en la app de autenticacion (Google Authenticator, etc.).
EMISOR_DEFECTO = "Keni Consola"

# Cuantos codigos de recuperacion se generan al activar el MFA. 10 es el estandar de facto.
NUM_CODIGOS_RECUPERACION = 10
# Bytes de entropia por codigo de recuperacion (5 bytes -> 8 chars base32, ~40 bits).
_BYTES_CODIGO_RECUPERACION = 5


class MfaNoDisponible(RuntimeError):
    """El MFA no puede operar: falta `KENI_CONSOLA_MFA_KEY` o es invalida (fail-safe).

    La API la captura para responder un error claro (y loguear un aviso) SIN tocar nunca el
    secreto en claro: enrolar/verificar rehusan limpiamente cuando no hay clave de cifrado.
    """


# --------------------------------------------------------------------------- #
# Cifrado del secreto en reposo (Fernet)                                       #
# --------------------------------------------------------------------------- #


def cifrador(clave: str | None) -> Any:
    """Construye un `Fernet` a partir de la clave (base64 url-safe de 32 bytes); o rehusa.

    `clave` es el valor de `KENI_CONSOLA_MFA_KEY` (lo resuelve la API). Si es None/vacia o no
    es una clave Fernet bien formada, lanza `MfaNoDisponible` (fail-safe): nunca se cae a un
    modo "sin cifrar". `cryptography` es una dependencia del back hosted; si faltara, tambien
    se trata como no disponible (no se intenta un fallback inseguro).
    """
    if not clave:
        raise MfaNoDisponible(
            "Falta KENI_CONSOLA_MFA_KEY: el segundo factor no puede operar sin clave de cifrado."
        )
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:  # pragma: no cover - dependencia presente en el back hosted
        raise MfaNoDisponible(
            "Falta la dependencia 'cryptography' para cifrar el secreto MFA."
        ) from exc
    try:
        return Fernet(clave.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise MfaNoDisponible(
            "KENI_CONSOLA_MFA_KEY no es una clave Fernet valida (base64 url-safe de 32 bytes)."
        ) from exc


def cifrar_secreto(secret: str, clave: str | None) -> str:
    """Cifra el secreto TOTP (base32) con Fernet; devuelve el token (str). Rehusa sin clave."""
    fernet = cifrador(clave)
    return fernet.encrypt(secret.encode("utf-8")).decode("utf-8")


def descifrar_secreto(token_cifrado: str, clave: str | None) -> str:
    """Descifra el secreto TOTP; lanza `MfaNoDisponible` si la clave falta o no descifra.

    Tratamos un fallo de descifrado (token corrupto o clave equivocada) como MFA no disponible:
    la verificacion rehusa en vez de continuar con un secreto basura.
    """
    fernet = cifrador(clave)
    try:
        from cryptography.fernet import InvalidToken
    except ImportError as exc:  # pragma: no cover
        raise MfaNoDisponible("Falta 'cryptography' para descifrar el secreto MFA.") from exc
    try:
        return fernet.decrypt(token_cifrado.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise MfaNoDisponible(
            "No se pudo descifrar el secreto MFA (clave incorrecta o dato corrupto)."
        ) from exc


# --------------------------------------------------------------------------- #
# Secreto TOTP y URI de aprovisionamiento                                       #
# --------------------------------------------------------------------------- #


def generar_secreto() -> str:
    """Genera un secreto TOTP nuevo en base32 (lo que comparte el QR con la app autenticadora)."""
    import pyotp

    return pyotp.random_base32()


def uri_aprovisionamiento(secret: str, email: str, emisor: str = EMISOR_DEFECTO) -> str:
    """URI `otpauth://` para el QR (la app autenticadora la lee y registra la cuenta).

    `email`/nombre identifica la cuenta dentro de la app; `emisor` es la etiqueta de la app.
    """
    import pyotp

    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=emisor)


def verificar_totp(secret: str, code: str) -> bool:
    """True si `code` es un TOTP valido para `secret` (tolerancia de +-1 paso de 30s).

    `valid_window=1` cubre un desfase razonable de reloj. `pyotp.verify` compara en tiempo
    constante. Entradas no numericas/vacias devuelven False sin lanzar.
    """
    if not isinstance(code, str):
        return False
    code = code.strip().replace(" ", "")
    if not code or not code.isdigit():
        return False
    import pyotp

    try:
        return bool(pyotp.TOTP(secret).verify(code, valid_window=1))
    except Exception:  # noqa: BLE001 - un secreto corrupto no debe tumbar el login
        return False


# --------------------------------------------------------------------------- #
# Codigos de recuperacion (un solo uso, guardados HASHEADOS)                     #
# --------------------------------------------------------------------------- #


def _formatear_codigo(crudo: str) -> str:
    """Formatea un codigo base32 como `XXXX-XXXX` (mas legible para teclear)."""
    crudo = crudo.upper()
    if len(crudo) >= 8:
        return f"{crudo[:4]}-{crudo[4:8]}"
    return crudo


def _normalizar_codigo(codigo: str) -> str:
    """Normaliza un codigo de recuperacion tecleado: mayusculas, sin guiones ni espacios."""
    return codigo.strip().upper().replace("-", "").replace(" ", "")


def generar_codigos_recuperacion(n: int = NUM_CODIGOS_RECUPERACION) -> list[str]:
    """Genera `n` codigos de recuperacion en CLARO (se muestran UNA vez al usuario).

    Cada codigo es base32 (~40 bits) formateado `XXXX-XXXX`. El CLARO se ensena al activar; lo
    que se PERSISTE es el hash (`hashear_codigos_recuperacion`). El usuario los guarda; el
    sistema solo conserva los hashes.
    """
    codigos: list[str] = []
    for _ in range(max(1, n)):
        bruto = base64.b32encode(secrets.token_bytes(_BYTES_CODIGO_RECUPERACION)).decode("ascii")
        bruto = bruto.rstrip("=")[:8]
        codigos.append(_formatear_codigo(bruto))
    return codigos


def hashear_codigos_recuperacion(codigos: list[str]) -> str:
    """Serializa a JSON la lista de codigos de recuperacion HASHEADOS (scrypt + salt).

    Cada entrada es `{"salt": ..., "hash": ...}` del codigo NORMALIZADO. Es lo que se guarda en
    `usuarios.mfa_recovery_codes`. No guarda el codigo en claro en ningun punto.
    """
    entradas: list[dict[str, str]] = []
    for codigo in codigos:
        salt_hex, hash_hex = hashear_password(_normalizar_codigo(codigo))
        entradas.append({"salt": salt_hex, "hash": hash_hex})
    return json.dumps(entradas)


def verificar_codigo_recuperacion(codigo: str, recovery_json: str) -> tuple[bool, str]:
    """Verifica un codigo de recuperacion contra la lista de hashes; lo CONSUME si acierta.

    Devuelve `(ok, recovery_json_actualizado)`:
      - `ok=True`  -> el codigo coincidia con un hash; ese hash se ELIMINA de la lista (un solo
        uso) y `recovery_json_actualizado` es la lista restante (a re-persistir por el llamante).
      - `ok=False` -> ningun hash coincide; la lista se devuelve INTACTA.
    Comparacion en tiempo constante (via `verificar_password`/`hmac.compare_digest`). Entradas
    vacias o JSON ilegible -> `(False, recovery_json)`.
    """
    if not isinstance(codigo, str) or not codigo.strip():
        return False, recovery_json
    try:
        entradas = json.loads(recovery_json or "[]")
    except (json.JSONDecodeError, TypeError):
        return False, recovery_json or "[]"
    if not isinstance(entradas, list):
        return False, "[]"
    normalizado = _normalizar_codigo(codigo)
    restantes: list[dict[str, str]] = []
    acertado = False
    for entrada in entradas:
        if (
            not acertado
            and isinstance(entrada, dict)
            and verificar_password(normalizado, entrada.get("salt", ""), entrada.get("hash", ""))
        ):
            acertado = True  # consumido: NO lo re-anadimos a `restantes`
            continue
        restantes.append(entrada)
    return acertado, json.dumps(restantes)
