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

# Fuerza minima de contrasena. Politica alineada con NIST 800-63B: manda la LONGITUD
# (12+), sin reglas de composicion (mayus/digito/simbolo) que solo empujan a patrones
# predecibles ("Password1!"). El filtro de calidad real es el BLOQUEO de contrasenas
# comunes/obvias y de la que coincide con el usuario (ver `motivo_rechazo_password`).
LONGITUD_MIN_PASSWORD = 12
# Tope de longitud (anti-DoS): hashear con scrypt una contrasena enorme es un consumo
# de CPU/memoria barato de provocar; la capamos ANTES de hashear. Idem el nombre.
LONGITUD_MAX_PASSWORD = 1024
LONGITUD_MAX_USUARIO = 64

# Contrasenas prohibidas (minusculas): las mas comunes/filtradas y las "obvias" del
# contexto (la vieja password del seed, marcas, la propia palabra "contrasena"). No es
# una lista exhaustiva tipo HIBP, pero corta lo que un humano elige por pereza. Se
# compara en minusculas y sin espacios para que "Cambiar " o "ADMIN" tambien caigan.
PASSWORDS_PROHIBIDAS: frozenset[str] = frozenset({
    "cambiar", "password", "passw0rd", "contrasena", "contraseña", "12345678",
    "123456789", "1234567890", "123456789012", "qwertyuiop", "qwerty123",
    "1q2w3e4r5t", "111111111111", "000000000000", "abcdefghijkl", "aaaaaaaaaaaa",
    "letmein", "welcome", "iloveyou", "admin1234", "administrador", "usuario1234",
    "keni", "kenitech", "kenisocial", "unotv", "clarosports", "claro-sports",
    "naciongamer", "fundacion", "piso15", "redessociales", "socialmedia",
})


def motivo_rechazo_password(password: object, usuario: str = "") -> str | None:
    """Devuelve el MOTIVO (texto) por el que `password` no es aceptable, o None si lo es.

    Politica NIST: longitud minima `LONGITUD_MIN_PASSWORD`, tope anti-DoS
    `LONGITUD_MAX_PASSWORD`, y rechazo de contrasenas comunes/obvias o que coincidan con
    el nombre de usuario. Sin reglas de composicion. El mensaje es apto para mostrar al
    usuario tal cual (la API lo reenvia).
    """
    if not isinstance(password, str):
        return "La contraseña debe ser texto."
    if len(password) < LONGITUD_MIN_PASSWORD:
        return f"La contraseña debe tener al menos {LONGITUD_MIN_PASSWORD} caracteres."
    if len(password) > LONGITUD_MAX_PASSWORD:
        return f"La contraseña no puede superar {LONGITUD_MAX_PASSWORD} caracteres."
    normal = password.strip().lower()
    if normal in PASSWORDS_PROHIBIDAS:
        return "Esa contraseña es demasiado común. Elige una menos predecible."
    if usuario and normal == usuario.strip().lower():
        return "La contraseña no puede ser igual a tu usuario."
    if len(set(password)) < 5:
        return "La contraseña es demasiado repetitiva. Usa más variedad de caracteres."
    return None


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
