"""Hash de contrasena (scrypt + salt) y politica de fuerza/longitud.

SEGURIDAD: la contrasena NUNCA se guarda ni se loguea en claro. Se deriva con
`hashlib.scrypt` (coste de CPU/memoria) sobre un salt aleatorio por usuario, y la
verificacion es en tiempo constante (`hmac.compare_digest`) para no filtrar por
timing. El hash resultante son 64 bytes => 128 caracteres hex (contrato que tambien
verifican los tests).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from ..estados import ROLES_USUARIO

# Parametros de scrypt (coste de CPU/memoria). `dklen=64` => hash de 128 hex chars.
_SCRYPT_N = 2 ** 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 64
_SALT_BYTES = 16

# Fuerza minima de contrasena (razonable, sin exagerar para una app local).
LONGITUD_MIN_PASSWORD = 8
# Tope de longitud (anti-DoS): hashear con scrypt una contrasena enorme es un consumo
# de CPU/memoria barato de provocar; la capamos ANTES de hashear. Idem el nombre.
LONGITUD_MAX_PASSWORD = 1024
LONGITUD_MAX_USUARIO = 64


def _hash_password(password: str, salt: bytes) -> str:
    """Deriva el hash scrypt de `password` con `salt`; devuelve hex (sin la contrasena)."""
    bruto = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
        maxmem=0,
    )
    return bruto.hex()


def hashear_password(password: str) -> tuple[str, str]:
    """Genera `(salt_hex, hash_hex)` para una contrasena nueva (salt aleatorio)."""
    salt = secrets.token_bytes(_SALT_BYTES)
    return salt.hex(), _hash_password(password, salt)


def verificar_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    """True si `password` coincide con el `hash` guardado (comparacion en tiempo constante)."""
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    calculado = _hash_password(password, salt)
    return hmac.compare_digest(calculado, hash_hex)


def hash_en_falso(password: str) -> None:
    """Hashea contra un salt fijo y descarta el resultado (igualar coste de timing).

    Se usa en el login cuando el usuario no existe: gastamos el mismo tiempo de scrypt
    que si existiera, para no filtrar por timing si una cuenta esta dada de alta.
    """
    _hash_password(password, b"\x00" * _SALT_BYTES)


def password_aceptable(password: object) -> bool:
    """Valida la longitud de una contrasena: minimo de fuerza y MAXIMO anti-DoS (scrypt)."""
    return (
        isinstance(password, str)
        and LONGITUD_MIN_PASSWORD <= len(password) <= LONGITUD_MAX_PASSWORD
    )


def rol_valido(rol: object) -> bool:
    """True si `rol` es uno de los roles permitidos."""
    return isinstance(rol, str) and rol in ROLES_USUARIO
