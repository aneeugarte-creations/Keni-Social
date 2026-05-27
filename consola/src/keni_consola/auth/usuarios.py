"""Cuentas de usuario: CRUD, login con anti fuerza bruta y cambio de contrasena.

El esquema de `usuarios`/`sesiones` lo crea `db.py` (on-demand, idempotente); aqui
solo se opera reusando `db.conectar()`. Cada funcion abre/cierra su propia conexion
(la app es local y de poca concurrencia).

FORMA PUBLICA de un usuario (lo que sale a la API): `id, usuario, rol,
debe_cambiar_password, creado, ultimo_acceso`. NUNCA `salt`/`hash`. Las GUARDAS de
negocio (no quedarse sin admins, no auto-borrado) viven en la capa API; aqui solo se
persiste y se exponen los conteos necesarios.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import timedelta
from typing import Any

from .. import db
from ..estados import ROL_ADMIN, ROL_EDITOR
from . import _comun
from .hashing import hash_en_falso, hashear_password, verificar_password

# Anti fuerza bruta: tras N fallos seguidos, el usuario queda bloqueado un rato.
MAX_INTENTOS_FALLIDOS = 5
BLOQUEO_MINUTOS = 5


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
        "creado": _comun.iso(_comun.ahora()),
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

    De uso interno (login): nunca sale de este modulo.
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
    SEGURIDAD: invalida TODAS las sesiones del usuario (revision de seguridad de auth):
    cambiar/resetear la contrasena debe expulsar cualquier sesion activa (token robado,
    equipo prestado, cuenta sospechosa). El cambio voluntario re-emite una sesion nueva
    para el dispositivo actual desde la capa API.
    """
    salt_hex, hash_hex = hashear_password(password)
    con = db.conectar()
    try:
        cur = con.execute(
            "UPDATE usuarios SET salt = ?, hash = ?, debe_cambiar_password = ?, "
            "intentos_fallidos = 0, bloqueo_hasta = '' WHERE id = ?",
            (salt_hex, hash_hex, 1 if debe_cambiar_password else 0, usuario_id),
        )
        con.execute("DELETE FROM sesiones WHERE usuario_id = ?", (usuario_id,))
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
# Login (con anti fuerza bruta) y verificacion de la contrasena actual          #
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
            # Usuario inexistente: igualamos el coste con un hash "en falso" para no
            # filtrar por tiempo si el usuario existe o no (best-effort).
            hash_en_falso(password)
            return None

        bloqueo = _comun.parsear_iso(fila["bloqueo_hasta"])
        if bloqueo is not None and _comun.ahora() < bloqueo:
            return None  # bloqueado: no revelamos el motivo

        if not verificar_password(password, fila["salt"], fila["hash"]):
            fallidos = int(fila["intentos_fallidos"]) + 1
            nuevo_bloqueo = ""
            if fallidos >= MAX_INTENTOS_FALLIDOS:
                nuevo_bloqueo = _comun.iso(_comun.ahora() + timedelta(minutes=BLOQUEO_MINUTOS))
                fallidos = 0  # reiniciamos el contador tras aplicar el bloqueo
            con.execute(
                "UPDATE usuarios SET intentos_fallidos = ?, bloqueo_hasta = ? WHERE id = ?",
                (fallidos, nuevo_bloqueo, fila["id"]),
            )
            con.commit()
            return None

        # Exito: reseteamos contador/bloqueo y marcamos ultimo acceso.
        ahora_iso = _comun.iso(_comun.ahora())
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
