"""Auth multiusuario de la Consola Keni: usuarios, roles, sesiones, bootstrap (#130).

Evoluciona la barrera de TOKEN unico de #134 a un modelo MULTIUSUARIO con login
user/pass y roles (`admin`/`editor`). Convive con el token: el middleware
`SeguridadConsola` (ver `seguridad.py`) acepta UNA sesion valida (cookie) O el
token de bootstrap (cabecera/cookie), de modo que los clientes y tests que ya usan
el token siguen funcionando.

QUE VIVE AQUI
=============
  - Hash de contrasena con `hashlib.scrypt` (n=2**14, r=8, p=1) + salt aleatorio por
    usuario. Se guarda `salt` y `hash` (hex); la verificacion es en tiempo constante
    (`hmac.compare_digest`). NUNCA se guarda ni se loguea la contrasena en claro.
  - CRUD de usuarios (crear/listar/editar/borrar) con las GUARDAS de negocio
    (no quedarse sin admins) en la capa API; aqui se exponen los conteos necesarios.
  - Sesiones server-side: tabla `sesiones` (token aleatorio url-safe, usuario_id,
    creada, ultimo_uso, expira). El token viaja en la cookie `keni_consola_sesion`.
    La expiracion es configurable y se RENUEVA con cada uso (sliding window).
  - Bootstrap idempotente: si no hay usuarios, crea un `admin` desde las env
    `KENI_CONSOLA_ADMIN_USER` / `KENI_CONSOLA_ADMIN_PASS` (o una pass aleatoria que
    se muestra UNA vez en el log, como el token de #134), con `debe_cambiar_password`.
  - Limite basico de intentos fallidos por usuario (anti fuerza bruta barato).

El esquema de `usuarios`/`sesiones` lo crea `db.py` (on-demand, idempotente); aqui
solo se opera sobre el reusando `db.conectar()`. Cada funcion abre/cierra su propia
conexion (la app es local y de poca concurrencia).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from . import db
from .estados import ROL_ADMIN, ROL_EDITOR, ROLES_USUARIO
from .observabilidad import NOMBRE_LOGGER

_logger = logging.getLogger(NOMBRE_LOGGER)

# Env vars del bootstrap del primer admin.
ENV_ADMIN_USER = "KENI_CONSOLA_ADMIN_USER"
ENV_ADMIN_PASS = "KENI_CONSOLA_ADMIN_PASS"
# Env var (opcional) para la duracion de la sesion en horas (def 12h).
ENV_SESION_HORAS = "KENI_CONSOLA_SESION_HORAS"

ADMIN_POR_DEFECTO = "admin"
SESION_HORAS_DEF = 12

# Nombre de la cookie de sesion (CONTRATO con el frontend). HttpOnly + SameSite=Strict.
COOKIE_SESION = "keni_consola_sesion"

# Parametros de scrypt (coste de CPU/memoria). `dklen=64` => hash de 128 hex chars.
_SCRYPT_N = 2 ** 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 64
_SALT_BYTES = 16

# Fuerza minima de contrasena (razonable, sin exagerar para una app local).
LONGITUD_MIN_PASSWORD = 8

# Anti fuerza bruta: tras N fallos seguidos, el usuario queda bloqueado un rato.
MAX_INTENTOS_FALLIDOS = 5
BLOQUEO_MINUTOS = 5


# --------------------------------------------------------------------------- #
# Utilidades de tiempo                                                         #
# --------------------------------------------------------------------------- #


def _ahora() -> datetime:
    """Instante actual en UTC (con tzinfo), para comparar fechas de sesion sin ambiguedad."""
    return datetime.now(UTC)


def _iso(momento: datetime) -> str:
    """Serializa un datetime a ISO-8601 (segundos), para guardar en SQLite."""
    return momento.astimezone(UTC).isoformat(timespec="seconds")


def _parsear_iso(texto: str) -> datetime | None:
    """Parsea un ISO-8601 guardado; None si esta vacio o es ilegible."""
    if not texto:
        return None
    try:
        momento = datetime.fromisoformat(texto)
    except ValueError:
        return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=UTC)
    return momento


def horas_sesion() -> int:
    """Duracion de la sesion en horas (env `KENI_CONSOLA_SESION_HORAS`, def 12)."""
    crudo = os.environ.get(ENV_SESION_HORAS, "").strip()
    if not crudo:
        return SESION_HORAS_DEF
    try:
        horas = int(crudo)
    except ValueError:
        return SESION_HORAS_DEF
    return horas if horas > 0 else SESION_HORAS_DEF


# --------------------------------------------------------------------------- #
# Hash de contrasena (scrypt + salt; comparacion en tiempo constante)          #
# --------------------------------------------------------------------------- #


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


def password_aceptable(password: object) -> bool:
    """Valida la fuerza minima de una contrasena (longitud razonable, sin espacios solo)."""
    return isinstance(password, str) and len(password) >= LONGITUD_MIN_PASSWORD


def rol_valido(rol: object) -> bool:
    """True si `rol` es uno de los roles permitidos."""
    return isinstance(rol, str) and rol in ROLES_USUARIO


# --------------------------------------------------------------------------- #
# Serializacion de filas                                                       #
# --------------------------------------------------------------------------- #


def _fila_a_usuario_publico(fila: sqlite3.Row) -> dict[str, Any]:
    """Forma PUBLICA de un usuario para la API (NUNCA salt/hash)."""
    return {
        "id": fila["id"],
        "usuario": fila["usuario"],
        "rol": fila["rol"],
        "debe_cambiar_password": bool(fila["debe_cambiar_password"]),
        "creado": fila["creado"],
        "ultimo_acceso": fila["ultimo_acceso"],
    }


# --------------------------------------------------------------------------- #
# CRUD de usuarios                                                             #
# --------------------------------------------------------------------------- #


def crear_usuario(
    usuario: str, password: str, rol: str = ROL_EDITOR, *, debe_cambiar_password: bool = False
) -> dict[str, Any] | None:
    """Inserta un usuario nuevo y lo devuelve (forma publica). None si el nombre ya existe.

    NO valida fuerza/rol (lo hace la API contra sus mensajes); aqui solo persiste.
    """
    salt_hex, hash_hex = hashear_password(password)
    nuevo = {
        "id": uuid.uuid4().hex[:12],
        "usuario": usuario,
        "rol": rol,
        "salt": salt_hex,
        "hash": hash_hex,
        "debe_cambiar_password": 1 if debe_cambiar_password else 0,
        "intentos_fallidos": 0,
        "bloqueo_hasta": "",
        "creado": _iso(_ahora()),
        "ultimo_acceso": "",
    }
    con = db.conectar()
    try:
        con.execute(
            "INSERT INTO usuarios (id, usuario, rol, salt, hash, debe_cambiar_password, "
            "intentos_fallidos, bloqueo_hasta, creado, ultimo_acceso) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                nuevo["id"], nuevo["usuario"], nuevo["rol"], nuevo["salt"], nuevo["hash"],
                nuevo["debe_cambiar_password"], nuevo["intentos_fallidos"],
                nuevo["bloqueo_hasta"], nuevo["creado"], nuevo["ultimo_acceso"],
            ),
        )
        con.commit()
    except sqlite3.IntegrityError:
        return None  # usuario UNIQUE: ya existe
    finally:
        con.close()
    return {
        "id": nuevo["id"],
        "usuario": nuevo["usuario"],
        "rol": nuevo["rol"],
        "debe_cambiar_password": bool(nuevo["debe_cambiar_password"]),
        "creado": nuevo["creado"],
        "ultimo_acceso": nuevo["ultimo_acceso"],
    }


def listar_usuarios() -> list[dict[str, Any]]:
    """Todos los usuarios (forma publica), por nombre ascendente."""
    con = db.conectar()
    try:
        filas = con.execute(
            "SELECT id, usuario, rol, debe_cambiar_password, creado, ultimo_acceso "
            "FROM usuarios ORDER BY usuario ASC"
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_usuario_publico(f) for f in filas]


def obtener_usuario_por_id(usuario_id: str) -> dict[str, Any] | None:
    """Un usuario por id (forma publica); None si no existe."""
    con = db.conectar()
    try:
        fila = con.execute(
            "SELECT id, usuario, rol, debe_cambiar_password, creado, ultimo_acceso "
            "FROM usuarios WHERE id = ?",
            (usuario_id,),
        ).fetchone()
    finally:
        con.close()
    return _fila_a_usuario_publico(fila) if fila is not None else None


def _fila_credenciales(con: sqlite3.Connection, usuario: str) -> sqlite3.Row | None:
    """Fila COMPLETA (incluye salt/hash) por nombre de usuario; None si no existe.

    De uso interno (login/cambio de pass): nunca sale de este modulo.
    """
    return con.execute(
        "SELECT id, usuario, rol, salt, hash, debe_cambiar_password, "
        "intentos_fallidos, bloqueo_hasta, creado, ultimo_acceso "
        "FROM usuarios WHERE usuario = ?",
        (usuario,),
    ).fetchone()


def contar_admins() -> int:
    """Numero de usuarios con rol admin (para las guardas de 'ultimo admin')."""
    con = db.conectar()
    try:
        fila = con.execute(
            "SELECT COUNT(*) AS n FROM usuarios WHERE rol = ?", (ROL_ADMIN,)
        ).fetchone()
    finally:
        con.close()
    return int(fila["n"]) if fila is not None else 0


def cambiar_rol(usuario_id: str, rol: str) -> bool:
    """Cambia el rol de un usuario; True si existia. NO aplica guardas (lo hace la API)."""
    con = db.conectar()
    try:
        cur = con.execute("UPDATE usuarios SET rol = ? WHERE id = ?", (rol, usuario_id))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def establecer_password(
    usuario_id: str, password: str, *, debe_cambiar_password: bool = False
) -> bool:
    """Fija una contrasena nueva (re-salt) y resetea intentos/bloqueo; True si existia.

    Usado tanto por el reset del admin (PATCH) como por el cambio del propio usuario.
    """
    salt_hex, hash_hex = hashear_password(password)
    con = db.conectar()
    try:
        cur = con.execute(
            "UPDATE usuarios SET salt = ?, hash = ?, debe_cambiar_password = ?, "
            "intentos_fallidos = 0, bloqueo_hasta = '' WHERE id = ?",
            (salt_hex, hash_hex, 1 if debe_cambiar_password else 0, usuario_id),
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def borrar_usuario(usuario_id: str) -> bool:
    """Borra un usuario y sus sesiones; True si existia. NO aplica guardas (lo hace la API)."""
    con = db.conectar()
    try:
        con.execute("DELETE FROM sesiones WHERE usuario_id = ?", (usuario_id,))
        cur = con.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Login (con anti fuerza bruta) y cambio de contrasena                          #
# --------------------------------------------------------------------------- #


def autenticar(usuario: str, password: str) -> dict[str, Any] | None:
    """Verifica credenciales y devuelve el usuario (forma publica) o None.

    Devuelve None SIN distinguir entre usuario inexistente, contrasena incorrecta o
    cuenta bloqueada: la API responde un mensaje GENERICO (no enumeracion). Cuenta los
    fallos por usuario y bloquea temporalmente tras `MAX_INTENTOS_FALLIDOS`.
    """
    con = db.conectar()
    try:
        fila = _fila_credenciales(con, usuario)
        if fila is None:
            # Usuario inexistente: igualamos el coste haciendo un hash "en falso" para
            # no filtrar por tiempo si el usuario existe o no (best-effort).
            _hash_password(password, b"\x00" * _SALT_BYTES)
            return None

        bloqueo = _parsear_iso(fila["bloqueo_hasta"])
        if bloqueo is not None and _ahora() < bloqueo:
            return None  # bloqueado: no revelamos el motivo

        if not verificar_password(password, fila["salt"], fila["hash"]):
            fallidos = int(fila["intentos_fallidos"]) + 1
            nuevo_bloqueo = ""
            if fallidos >= MAX_INTENTOS_FALLIDOS:
                nuevo_bloqueo = _iso(_ahora() + timedelta(minutes=BLOQUEO_MINUTOS))
                fallidos = 0  # reiniciamos el contador tras aplicar el bloqueo
            con.execute(
                "UPDATE usuarios SET intentos_fallidos = ?, bloqueo_hasta = ? WHERE id = ?",
                (fallidos, nuevo_bloqueo, fila["id"]),
            )
            con.commit()
            return None

        # Exito: reseteamos contador/bloqueo y marcamos ultimo acceso.
        ahora_iso = _iso(_ahora())
        con.execute(
            "UPDATE usuarios SET intentos_fallidos = 0, bloqueo_hasta = '', ultimo_acceso = ? "
            "WHERE id = ?",
            (ahora_iso, fila["id"]),
        )
        con.commit()
        return {
            "id": fila["id"],
            "usuario": fila["usuario"],
            "rol": fila["rol"],
            "debe_cambiar_password": bool(fila["debe_cambiar_password"]),
            "creado": fila["creado"],
            "ultimo_acceso": ahora_iso,
        }
    finally:
        con.close()


def verificar_password_actual(usuario_id: str, password: str) -> bool:
    """True si `password` es la contrasena ACTUAL del usuario (para el cambio de pass)."""
    con = db.conectar()
    try:
        fila = con.execute(
            "SELECT salt, hash FROM usuarios WHERE id = ?", (usuario_id,)
        ).fetchone()
    finally:
        con.close()
    if fila is None:
        return False
    return verificar_password(password, fila["salt"], fila["hash"])


# --------------------------------------------------------------------------- #
# Sesiones server-side                                                         #
# --------------------------------------------------------------------------- #


def crear_sesion(usuario_id: str) -> str:
    """Crea una sesion para `usuario_id` y devuelve su token (url-safe, ~256 bits)."""
    token = secrets.token_urlsafe(32)
    ahora = _ahora()
    expira = ahora + timedelta(hours=horas_sesion())
    con = db.conectar()
    try:
        con.execute(
            "INSERT INTO sesiones (token, usuario_id, creada, ultimo_uso, expira) "
            "VALUES (?, ?, ?, ?, ?)",
            (token, usuario_id, _iso(ahora), _iso(ahora), _iso(expira)),
        )
        con.commit()
    finally:
        con.close()
    return token


def sesion_valida(token: str) -> dict[str, Any] | None:
    """Devuelve el usuario (forma publica) de una sesion VIGENTE, o None.

    Si la sesion expiro, la borra y devuelve None. Si es valida, RENUEVA `ultimo_uso`
    y `expira` (ventana deslizante) y actualiza el `ultimo_acceso` del usuario.
    """
    if not token:
        return None
    con = db.conectar()
    try:
        fila = con.execute(
            "SELECT s.token AS s_token, s.expira AS s_expira, u.id AS id, u.usuario AS usuario, "
            "u.rol AS rol, u.debe_cambiar_password AS debe_cambiar_password, "
            "u.creado AS creado, u.ultimo_acceso AS ultimo_acceso "
            "FROM sesiones s JOIN usuarios u ON u.id = s.usuario_id WHERE s.token = ?",
            (token,),
        ).fetchone()
        if fila is None:
            return None
        expira = _parsear_iso(fila["s_expira"])
        ahora = _ahora()
        if expira is None or ahora >= expira:
            con.execute("DELETE FROM sesiones WHERE token = ?", (token,))
            con.commit()
            return None
        # Vigente: ventana deslizante + ultimo_acceso del usuario.
        nueva_expira = ahora + timedelta(hours=horas_sesion())
        con.execute(
            "UPDATE sesiones SET ultimo_uso = ?, expira = ? WHERE token = ?",
            (_iso(ahora), _iso(nueva_expira), token),
        )
        con.execute(
            "UPDATE usuarios SET ultimo_acceso = ? WHERE id = ?",
            (_iso(ahora), fila["id"]),
        )
        con.commit()
        return {
            "id": fila["id"],
            "usuario": fila["usuario"],
            "rol": fila["rol"],
            "debe_cambiar_password": bool(fila["debe_cambiar_password"]),
            "creado": fila["creado"],
            "ultimo_acceso": _iso(ahora),
        }
    finally:
        con.close()


def borrar_sesion(token: str) -> None:
    """Invalida una sesion por su token (logout). Idempotente."""
    if not token:
        return
    con = db.conectar()
    try:
        con.execute("DELETE FROM sesiones WHERE token = ?", (token,))
        con.commit()
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Bootstrap del primer admin                                                   #
# --------------------------------------------------------------------------- #


def hay_usuarios() -> bool:
    """True si ya existe al menos un usuario (el bootstrap es no-op entonces)."""
    con = db.conectar()
    try:
        fila = con.execute("SELECT 1 FROM usuarios LIMIT 1").fetchone()
    finally:
        con.close()
    return fila is not None


def bootstrap_admin() -> None:
    """Crea el primer admin si la BD no tiene usuarios (idempotente y seguro en tests).

    Usuario desde `KENI_CONSOLA_ADMIN_USER` (def "admin"). Contrasena desde
    `KENI_CONSOLA_ADMIN_PASS`; si no esta, se genera una aleatoria y se MUESTRA UNA
    vez en el log (como el token de #134), para que el operador local pueda entrar.
    El admin nace con `debe_cambiar_password=True` (debe cambiarla al primer login).
    """
    if hay_usuarios():
        return

    usuario = os.environ.get(ENV_ADMIN_USER, "").strip() or ADMIN_POR_DEFECTO
    pass_env = os.environ.get(ENV_ADMIN_PASS, "")
    generada = not pass_env
    password = pass_env or secrets.token_urlsafe(12)

    creado = crear_usuario(usuario, password, ROL_ADMIN, debe_cambiar_password=True)
    if creado is None:
        # Carrera improbable (otro proceso lo creo entre el check y el insert): no-op.
        return

    if generada:
        _logger.warning(
            "No hay usuarios: admin de bootstrap creado. usuario=%s contrasena=%s "
            "(temporal, debe cambiarse al primer acceso; fija KENI_CONSOLA_ADMIN_PASS "
            "para una estable).",
            usuario,
            password,
        )
    else:
        _logger.info(
            "Admin de bootstrap creado con KENI_CONSOLA_ADMIN_PASS. usuario=%s "
            "(debe cambiar la contrasena al primer acceso).",
            usuario,
        )
