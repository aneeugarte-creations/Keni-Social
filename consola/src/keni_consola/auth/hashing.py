"""Hash de contrasena (scrypt + salt, VERSIONADO) y politica de fuerza/longitud.

SEGURIDAD: la contrasena NUNCA se guarda ni se loguea en claro. Se deriva con
`hashlib.scrypt` (coste de CPU/memoria) sobre un salt aleatorio por usuario, y la
verificacion es en tiempo constante (`hmac.compare_digest`) para no filtrar por timing.

FORMATO VERSIONADO (para poder SUBIR el coste sin romper logins existentes): el campo
`hash` que se guarda es AUTO-DESCRIPTIVO, `scrypt$<n>$<r>$<p>$<hex>`, de modo que la
verificacion usa los parametros con que se DERIVO ese hash, no los actuales. Un hash LEGADO
(128 hex sin `$`, de antes de versionar) se interpreta con los parametros antiguos
(`_SCRYPT_N_LEGADO`). Al hacer login con un hash legado o por debajo del coste objetivo, el
llamante lo RE-DERIVA al coste actual (`necesita_rehash` + re-hash on login en
`auth.usuarios.autenticar`), de forma transparente para el usuario.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from ..estados import ROLES_USUARIO

# Parametros OBJETIVO de scrypt (coste de CPU/memoria). Subidos por encima del suelo de OWASP
# (`2**14`) a `2**16` (hardening enterprise 2026-06). `dklen=64` => 128 hex en el digest.
# `maxmem`: scrypt necesita ~128*N*r bytes; con maxmem=0 OpenSSL lo capa a 32 MB y `2**16`
# (~64 MB) fallaria, asi que lo fijamos generoso (acomoda N hasta `2**17`).
_SCRYPT_N = 2 ** 16
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 64
_SALT_BYTES = 16
_SCRYPT_MAXMEM = 256 * 1024 * 1024
# Parametros de un hash LEGADO (campo `hash` sin prefijo de version): scrypt N=2**14, r=8, p=1.
_SCRYPT_N_LEGADO = 2 ** 14

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
# compara en minusculas y sin espacios para que "Cambiar " o "ADMIN" tambien caigan, y
# ademas se chequea SIN digitos finales (ver `_raiz_sin_digitos`) para tumbar la treta de
# "password2026"/"clarosports1". Lista ampliada (hardening enterprise 2026-06).
PASSWORDS_PROHIBIDAS: frozenset[str] = frozenset({
    # Secuencias / repeticiones / teclado.
    "cambiar", "password", "passw0rd", "contrasena", "contraseña", "12345678",
    "123456789", "1234567890", "123456789012", "qwertyuiop", "qwerty123",
    "1q2w3e4r5t", "111111111111", "000000000000", "abcdefghijkl", "aaaaaaaaaaaa",
    "qwertyuiopasdfghjkl", "asdfghjklzxcvbnm", "1234qwerasdf", "zxcvbnmasdf",
    "123123123123", "121212121212", "abcd1234abcd", "passwordpassword",
    # Comunes (top listas filtradas) y sus variantes en español.
    "letmein", "welcome", "iloveyou", "admin1234", "administrador", "usuario1234",
    "qwerty", "monkey", "dragon", "football", "baseball", "superman", "batman",
    "trustno1", "sunshine", "princess", "whatever", "starwars", "michael",
    "contrasenasegura", "contraseñasegura", "miclavesegura", "claveseguraaa",
    "bienvenido", "holahola", "teamo", "futbol", "mexicomexico", "mexico1234",
    # Contexto Keni / piloto AMX (marca, equipo, lugar): nunca como contrasena.
    "keni", "kenitech", "kenisocial", "kenisocialai", "kenitechio", "kenienterprise",
    "unotv", "unotvnoticias", "clarosports", "claro-sports", "claromexico", "claro",
    "naciongamer", "fundacion", "fundaciontelevisa", "televisa", "piso15",
    "redessociales", "socialmedia", "communitymanager", "marketingdigital",
})


def _raiz_sin_digitos(normal: str) -> str:
    """Quita digitos finales (y separadores sueltos) para cazar 'password2026'/'clarosports1'.

    Una contrasena debil no deja de serlo por pegarle un anio o un '1' al final: comparamos
    tambien la RAIZ sin ese sufijo numerico contra la blocklist. Solo recorta el final para no
    convertir algo legitimo en una palabra prohibida por accidente.
    """
    return normal.rstrip("0123456789").rstrip("-_. ")


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
    if normal in PASSWORDS_PROHIBIDAS or _raiz_sin_digitos(normal) in PASSWORDS_PROHIBIDAS:
        return "Esa contraseña es demasiado común. Elige una menos predecible."
    if usuario and normal == usuario.strip().lower():
        return "La contraseña no puede ser igual a tu usuario."
    if len(set(password)) < 5:
        return "La contraseña es demasiado repetitiva. Usa más variedad de caracteres."
    return None


def _hash_password(password: str, salt: bytes, n: int = _SCRYPT_N) -> str:
    """Deriva el digest scrypt (hex) de `password` con `salt` y coste `n` (sin la contrasena).

    `r`/`p`/`dklen` son fijos; `n` es parametrizable para poder VERIFICAR hashes derivados con
    un coste distinto (legado) sin re-derivar a ciegas. La salida es solo el digest hex; el
    formato versionado (`scrypt$n$r$p$hex`) lo compone `_componer`/`hashear_password`.
    """
    bruto = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
        maxmem=_SCRYPT_MAXMEM,
    )
    return bruto.hex()


def _componer(n: int, digest_hex: str) -> str:
    """Campo `hash` versionado y auto-descriptivo: `scrypt$<n>$<r>$<p>$<digest_hex>`."""
    return f"scrypt${n}${_SCRYPT_R}${_SCRYPT_P}${digest_hex}"


def _parsear(hash_field: str) -> tuple[int, str]:
    """Devuelve `(n, digest_hex)` de un campo `hash`: versionado (`scrypt$...`) o LEGADO (128 hex).

    Un campo sin prefijo `scrypt$` es un hash legado (de antes de versionar): se interpreta con
    `_SCRYPT_N_LEGADO`. Solo se respetan `r`/`p` actuales (nunca variaron); si algun dia
    cambian, este parser hay que ampliarlo. Un formato corrupto cae a `(_SCRYPT_N, "")` -> la
    verificacion fallara (no casca).
    """
    if not hash_field.startswith("scrypt$"):
        return _SCRYPT_N_LEGADO, hash_field
    partes = hash_field.split("$")
    # ["scrypt", n, r, p, digest]
    if len(partes) != 5:
        return _SCRYPT_N, ""
    try:
        return int(partes[1]), partes[4]
    except ValueError:
        return _SCRYPT_N, ""


def hashear_password(password: str) -> tuple[str, str]:
    """Genera `(salt_hex, hash_field)` para una contrasena nueva (salt aleatorio, coste OBJETIVO).

    `hash_field` viene en el formato versionado `scrypt$<n>$<r>$<p>$<hex>`.
    """
    salt = secrets.token_bytes(_SALT_BYTES)
    return salt.hex(), _componer(_SCRYPT_N, _hash_password(password, salt, _SCRYPT_N))


def verificar_password(password: str, salt_hex: str, hash_field: str) -> bool:
    """True si `password` coincide con el `hash` guardado (en tiempo constante).

    Acepta tanto el formato VERSIONADO (`scrypt$...`) como un hash LEGADO (128 hex): los
    parametros con que verificar se leen del propio `hash_field` (ver `_parsear`).
    """
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    n, digest_esperado = _parsear(hash_field)
    if not digest_esperado:
        return False
    calculado = _hash_password(password, salt, n)
    return hmac.compare_digest(calculado, digest_esperado)


def necesita_rehash(hash_field: str) -> bool:
    """True si el `hash` guardado se derivo por DEBAJO del coste objetivo (legado o `n` menor).

    Lo consulta el login (`auth.usuarios.autenticar`) tras una verificacion correcta para
    RE-DERIVAR la contrasena al coste actual de forma transparente. Un formato corrupto no se
    re-hashea (la verificacion ya habria fallado).
    """
    n, digest = _parsear(hash_field)
    return bool(digest) and n < _SCRYPT_N


def hash_en_falso(password: str) -> None:
    """Hashea contra un salt fijo y descarta el resultado (igualar coste de timing).

    Se usa en el login cuando el usuario no existe: gastamos el mismo tiempo de scrypt
    (al coste OBJETIVO) que si existiera, para no filtrar por timing si una cuenta esta dada
    de alta.
    """
    _hash_password(password, b"\x00" * _SALT_BYTES, _SCRYPT_N)


def password_aceptable(password: object) -> bool:
    """Valida la longitud de una contrasena: minimo de fuerza y MAXIMO anti-DoS (scrypt)."""
    return (
        isinstance(password, str)
        and LONGITUD_MIN_PASSWORD <= len(password) <= LONGITUD_MAX_PASSWORD
    )


def rol_valido(rol: object) -> bool:
    """True si `rol` es uno de los roles permitidos."""
    return isinstance(rol, str) and rol in ROLES_USUARIO
