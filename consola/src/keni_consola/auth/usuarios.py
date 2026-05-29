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

import uuid
from datetime import timedelta
from typing import Any

from .. import db, motor_db
from ..estados import ROL_ADMIN, ROL_EDITOR
from . import _comun
from .hashing import hash_en_falso, hashear_password, verificar_password

# Anti fuerza bruta: tras N fallos seguidos, el usuario queda bloqueado un rato.
MAX_INTENTOS_FALLIDOS = 5
BLOQUEO_MINUTOS = 5


# --------------------------------------------------------------------------- #
# Serializacion de filas                                                       #
# --------------------------------------------------------------------------- #


# Columnas PUBLICAS del usuario, en orden estable. `cargo` y `cobertura` se anadieron a
# `usuarios` con `_migrar_columnas_usuarios`; todo SELECT pasa por aqui para que tipos y
# columnas no se desincronicen.
_COLUMNAS_USUARIO_PUBLICAS = (
    "id", "usuario", "rol", "debe_cambiar_password", "creado", "ultimo_acceso",
    "cargo", "cobertura",
)
_SELECT_USUARIO_PUBLICO = ", ".join(_COLUMNAS_USUARIO_PUBLICAS)


def _fila_a_usuario_publico(fila: Any, marcas: list[str] | None = None) -> dict[str, Any]:
    """Forma PUBLICA de un usuario para la API (NUNCA salt/hash).

    `cargo` es la FUNCION del equipo ("director", "community_manager"...). `cobertura` es
    el flag que dice si esa persona entra en la rota de turnos. Ambos vacios/`False` por
    defecto para usuarios legados.

    `marcas` (organigrama AMX): lista de ids canonicos de las verticales a las que
    pertenece la persona (`["claro-sports", "unotv"]`). Llega de la tabla N:M
    `usuarios_marcas`. Si el caller ya las consulto pasa la lista; en caso contrario se
    consulta aqui (una query por usuario) para mantener la forma publica completa.
    """
    if marcas is None:
        marcas = _marcas_de_usuario(fila["id"])
    return {
        "id": fila["id"],
        "usuario": fila["usuario"],
        "rol": fila["rol"],
        "debe_cambiar_password": bool(fila["debe_cambiar_password"]),
        "creado": fila["creado"],
        "ultimo_acceso": fila["ultimo_acceso"],
        "cargo": fila["cargo"],
        "cobertura": bool(fila["cobertura"]),
        "marcas": marcas,
    }


def _marcas_de_usuario(usuario_id: str, con: Any | None = None) -> list[str]:
    """Lista de marcas (ids canonicos) de un usuario, ordenadas alfabeticamente.

    Si se pasa `con`, REUSA esa conexion (para batches o transacciones); si no, abre la
    suya. Vacio si el usuario no tiene marcas asignadas (caso normal en usuarios legados
    antes del organigrama AMX).
    """
    cerrar = False
    if con is None:
        con = db.conectar()
        cerrar = True
    try:
        filas = con.execute(
            "SELECT marca_id FROM usuarios_marcas WHERE usuario_id = ? ORDER BY marca_id ASC",
            (usuario_id,),
        ).fetchall()
    finally:
        if cerrar:
            con.close()
    return [f["marca_id"] for f in filas]


def _marcas_de_usuarios(usuario_ids: list[str], con: Any | None = None) -> dict[str, list[str]]:
    """Mapa `id -> [marcas]` para un lote de usuarios (evita N+1 en `listar_usuarios`)."""
    if not usuario_ids:
        return {}
    cerrar = False
    if con is None:
        con = db.conectar()
        cerrar = True
    try:
        # Construimos placeholders parametrizados (los ids vienen de la BD, no del usuario,
        # pero igualmente nunca f-string con datos).
        marcadores = ", ".join(["?"] * len(usuario_ids))
        filas = con.execute(
            "SELECT usuario_id, marca_id FROM usuarios_marcas "
            f"WHERE usuario_id IN ({marcadores}) ORDER BY usuario_id ASC, marca_id ASC",
            tuple(usuario_ids),
        ).fetchall()
    finally:
        if cerrar:
            con.close()
    indice: dict[str, list[str]] = {uid: [] for uid in usuario_ids}
    for fila in filas:
        indice.setdefault(fila["usuario_id"], []).append(fila["marca_id"])
    return indice


def reemplazar_marcas_de_usuario(usuario_id: str, marcas: list[str]) -> bool:
    """Reemplaza el conjunto de marcas de un usuario (DELETE + INSERT en una transaccion).

    Devuelve True si el usuario existia, False si no (no se hace nada). La capa API valida
    cada `marca_id` contra el catalogo canonico ANTES de llegar aqui; este modulo solo
    persiste. Idempotente: si la lista nueva coincide con la actual, el resultado neto es
    el mismo (las filas se reescriben pero el contenido no cambia).

    Acepta strings duplicados (los deduplica) y los ordena para que el orden de insercion
    sea estable (no relevante para correccion, pero ayuda al log/diff).
    """
    con = db.conectar()
    try:
        existe = con.execute(
            "SELECT 1 FROM usuarios WHERE id = ?", (usuario_id,)
        ).fetchone()
        if existe is None:
            return False
        con.execute("DELETE FROM usuarios_marcas WHERE usuario_id = ?", (usuario_id,))
        for marca in sorted(set(marcas)):
            con.execute(
                "INSERT INTO usuarios_marcas (usuario_id, marca_id) VALUES (?, ?)",
                (usuario_id, marca),
            )
        con.commit()
        return True
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# CRUD de usuarios                                                             #
# --------------------------------------------------------------------------- #


def crear_usuario(
    usuario: str,
    password: str,
    rol: str = ROL_EDITOR,
    *,
    debe_cambiar_password: bool = False,
    cargo: str = "",
    cobertura: bool = False,
    marcas: list[str] | None = None,
) -> dict[str, Any] | None:
    """Inserta un usuario nuevo y lo devuelve (forma publica). None si el nombre ya existe.

    NO valida fuerza/rol/cargo/marcas (lo hace la API contra sus mensajes); aqui solo
    persiste. `cargo` es texto libre validado en la API (allowlist en
    `estados.CARGOS_USUARIO`); `cobertura` indica si la persona entra en la rota de
    turnos (`False` por defecto). `marcas` (organigrama AMX): lista de ids canonicos de
    verticales (`["claro-sports", "unotv"]`); vacio/`None` deja al usuario sin marcas.
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
        "cargo": cargo,
        "cobertura": 1 if cobertura else 0,
    }
    con = db.conectar()
    try:
        con.execute(
            "INSERT INTO usuarios (id, usuario, rol, salt, hash, debe_cambiar_password, "
            "intentos_fallidos, bloqueo_hasta, creado, ultimo_acceso, cargo, cobertura) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                nuevo["id"], nuevo["usuario"], nuevo["rol"], nuevo["salt"], nuevo["hash"],
                nuevo["debe_cambiar_password"], nuevo["intentos_fallidos"],
                nuevo["bloqueo_hasta"], nuevo["creado"], nuevo["ultimo_acceso"],
                nuevo["cargo"], nuevo["cobertura"],
            ),
        )
        # Marcas del organigrama (N:M): sembrarlas en la misma conexion para que el
        # alta del usuario quede COMPLETA si la transaccion confirma.
        marcas_norm = sorted(set(marcas or []))
        for marca in marcas_norm:
            con.execute(
                "INSERT INTO usuarios_marcas (usuario_id, marca_id) VALUES (?, ?)",
                (nuevo["id"], marca),
            )
        con.commit()
    except motor_db.IntegrityError:
        return None  # usuario UNIQUE: ya existe (neutro: SQLite o Postgres)
    finally:
        con.close()
    return {
        "id": nuevo["id"],
        "usuario": nuevo["usuario"],
        "rol": nuevo["rol"],
        "debe_cambiar_password": bool(nuevo["debe_cambiar_password"]),
        "creado": nuevo["creado"],
        "ultimo_acceso": nuevo["ultimo_acceso"],
        "cargo": nuevo["cargo"],
        "cobertura": bool(nuevo["cobertura"]),
        "marcas": marcas_norm,
    }


def listar_usuarios() -> list[dict[str, Any]]:
    """Todos los usuarios (forma publica), por nombre ascendente.

    Cada usuario incluye su lista de `marcas` (organigrama AMX). Para evitar N+1, se hace
    una sola consulta a `usuarios_marcas` y se indexa por `usuario_id`.
    """
    con = db.conectar()
    try:
        filas = con.execute(
            f"SELECT {_SELECT_USUARIO_PUBLICO} FROM usuarios ORDER BY usuario ASC"
        ).fetchall()
        marcas_por_uid = _marcas_de_usuarios([f["id"] for f in filas], con=con)
    finally:
        con.close()
    return [_fila_a_usuario_publico(f, marcas_por_uid.get(f["id"], [])) for f in filas]


def obtener_usuario_por_id(usuario_id: str) -> dict[str, Any] | None:
    """Un usuario por id (forma publica); None si no existe."""
    con = db.conectar()
    try:
        fila = con.execute(
            f"SELECT {_SELECT_USUARIO_PUBLICO} FROM usuarios WHERE id = ?",
            (usuario_id,),
        ).fetchone()
        if fila is None:
            return None
        marcas = _marcas_de_usuario(usuario_id, con=con)
    finally:
        con.close()
    return _fila_a_usuario_publico(fila, marcas)


def actualizar_perfil(
    usuario_id: str,
    *,
    cargo: str | None = None,
    cobertura: bool | None = None,
    marcas: list[str] | None = None,
) -> bool:
    """Actualiza `cargo`, `cobertura` y/o `marcas` de un usuario; True si existia.

    NO aplica guardas (lo hace la API contra `CARGOS_USUARIO` y el catalogo de marcas).
    Pasar `None` deja el campo intacto; `cargo=""` lo limpia; `marcas=[]` borra todas las
    asignaciones N:M de ese usuario; `marcas=[...]` las REEMPLAZA al conjunto dado.
    """
    campos: list[str] = []
    valores: list[Any] = []
    if cargo is not None:
        campos.append("cargo = ?")
        valores.append(cargo)
    if cobertura is not None:
        campos.append("cobertura = ?")
        valores.append(1 if cobertura else 0)
    # Sin campos directos ni marcas -> simple existencia.
    if not campos and marcas is None:
        return obtener_usuario_por_id(usuario_id) is not None
    if campos:
        valores.append(usuario_id)
        con = db.conectar()
        try:
            cur = con.execute(
                f"UPDATE usuarios SET {', '.join(campos)} WHERE id = ?", tuple(valores)
            )
            con.commit()
            existia = cur.rowcount > 0
        finally:
            con.close()
        if not existia:
            return False
    if marcas is not None:
        if not reemplazar_marcas_de_usuario(usuario_id, marcas):
            # El usuario no existe (caso ya cubierto si no habia campos directos arriba).
            return False
    return True


def _fila_credenciales(con: Any, usuario: str) -> Any:
    """Fila COMPLETA (incluye salt/hash) por nombre de usuario; None si no existe.

    De uso interno (login): nunca sale de este modulo.
    """
    return con.execute(
        "SELECT id, usuario, rol, salt, hash, debe_cambiar_password, "
        "intentos_fallidos, bloqueo_hasta, creado, ultimo_acceso, cargo, cobertura "
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
        marcas = _marcas_de_usuario(fila["id"], con=con)
        return {
            "id": fila["id"],
            "usuario": fila["usuario"],
            "rol": fila["rol"],
            "debe_cambiar_password": bool(fila["debe_cambiar_password"]),
            "creado": fila["creado"],
            "ultimo_acceso": ahora_iso,
            "cargo": fila["cargo"],
            "cobertura": bool(fila["cobertura"]),
            "marcas": marcas,
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
