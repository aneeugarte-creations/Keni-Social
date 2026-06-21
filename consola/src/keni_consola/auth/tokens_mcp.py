"""Tokens del MCP operativo por IDENTIDAD: emitir, validar, revocar y listar.

Un token MCP es un secreto aleatorio url-safe (~256 bits) en la tabla `tokens_mcp`, atado
a UN `usuario_id`. A diferencia de `KENI_MCP_BEARER` (un secreto COMPARTIDO que no identifica
a nadie y obliga al guard a confiar en una cabecera `X-Keni-Usuario-Id`), cada token MCP
identifica a su dueno: el guard de `/mcp` resuelve la identidad de la peticion del token
presentado, sin cabeceras. Caducidad opcional (`expira`, None = sin caducidad) y revocacion
(`revocado`).

A diferencia de las SESIONES (`sesiones.py`), la caducidad NO es deslizante: `expira` es un
tope FIJO desde la emision. Validar refresca `ultimo_uso` (para auditoria), no la caducidad.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import timedelta
from typing import Any

from .. import db
from . import _comun


def crear_token_mcp(usuario_id: str, etiqueta: str, expira: float | None = None) -> str:
    """Crea un token MCP para `usuario_id` y devuelve su valor (url-safe, ~256 bits).

    `etiqueta` es la nota humana del emisor ("ralph:<id>", "Claude Code de Ana"). `expira` son
    las HORAS hasta caducar (None = sin caducidad). El valor se devuelve UNA vez: luego solo se
    valida por igualdad de la fila, nunca se vuelve a leer en claro. Cada fila lleva un `id`
    opaco y NO secreto (lo expone el listado y lo usa la consola para revocar).
    """
    token = secrets.token_urlsafe(32)
    ahora = _comun.ahora()
    vence = None if expira is None else _comun.iso(ahora + timedelta(hours=expira))
    con = db.conectar()
    try:
        con.execute(
            "INSERT INTO tokens_mcp (token, id, usuario_id, etiqueta, creado, ultimo_uso, expira, "
            "revocado) VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
            (token, str(uuid.uuid4()), usuario_id, etiqueta, _comun.iso(ahora), None, vence),
        )
        con.commit()
    finally:
        con.close()
    return token


def token_mcp_valido(token: str) -> dict[str, Any] | None:
    """Devuelve el usuario (forma publica) dueno de un token MCP VIGENTE, o None.

    None si el token no existe, esta revocado o caduco. Si es valido, refresca `ultimo_uso` del
    token y el `ultimo_acceso` del usuario (auditoria), igual que una sesion. La caducidad
    (`expira`) es un tope FIJO desde la emision: NO se desliza con el uso.
    """
    if not token:
        return None
    con = db.conectar()
    try:
        fila = con.execute(
            "SELECT t.expira AS t_expira, t.revocado AS t_revocado, "
            "u.id AS id, u.usuario AS usuario, u.rol AS rol, "
            "u.debe_cambiar_password AS debe_cambiar_password, u.superadmin AS superadmin, "
            "u.cargo AS cargo, u.creado AS creado, u.ultimo_acceso AS ultimo_acceso "
            "FROM tokens_mcp t JOIN usuarios u ON u.id = t.usuario_id WHERE t.token = ?",
            (token,),
        ).fetchone()
        if fila is None or fila["t_revocado"]:
            return None
        ahora = _comun.ahora()
        expira = _comun.parsear_iso(fila["t_expira"])
        if expira is not None and ahora >= expira:
            return None
        con.execute(
            "UPDATE tokens_mcp SET ultimo_uso = ? WHERE token = ?",
            (_comun.iso(ahora), token),
        )
        con.execute(
            "UPDATE usuarios SET ultimo_acceso = ? WHERE id = ?",
            (_comun.iso(ahora), fila["id"]),
        )
        con.commit()
        return {
            "id": fila["id"],
            "usuario": fila["usuario"],
            "rol": fila["rol"],
            "superadmin": bool(fila["superadmin"]),
            "cargo": fila["cargo"] or "",
            "debe_cambiar_password": bool(fila["debe_cambiar_password"]),
            "creado": fila["creado"],
            "ultimo_acceso": _comun.iso(ahora),
        }
    finally:
        con.close()


def revocar_token_mcp(token: str) -> bool:
    """Revoca un token MCP por su valor (no lo borra: marca `revocado=1`). Idempotente.

    Devuelve True si existia un token con ese valor (revocado o no), False si no existia.
    """
    if not token:
        return False
    con = db.conectar()
    try:
        cur = con.execute("UPDATE tokens_mcp SET revocado = 1 WHERE token = ?", (token,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def revocar_token_mcp_de_usuario(usuario_id: str, token_id: str) -> bool:
    """Revoca el token `token_id` de `usuario_id` (marca `revocado=1`). Idempotente.

    Revoca por el `id` opaco que expone el listado (no por el secreto), y exige que el token
    sea de `usuario_id`: nadie puede revocar tokens de otra persona. Devuelve True si existia un
    token con ese `id` para ese usuario (revocado o no), False si no.
    """
    if not token_id:
        return False
    con = db.conectar()
    try:
        cur = con.execute(
            "UPDATE tokens_mcp SET revocado = 1 WHERE id = ? AND usuario_id = ?",
            (token_id, usuario_id),
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def listar_tokens_mcp(usuario_id: str) -> list[dict[str, Any]]:
    """Lista los tokens MCP de `usuario_id`, SIN el valor del token (mas nuevos primero).

    Cada item trae `id` (opaco, para revocar), `etiqueta`, `creado`, `ultimo_uso`, `expira` y
    `revocado` para que la cuenta vea y gestione sus tokens. El secreto NUNCA sale aqui (solo se
    entrega una vez, al crear).
    """
    con = db.conectar()
    try:
        filas = con.execute(
            "SELECT id, etiqueta, creado, ultimo_uso, expira, revocado FROM tokens_mcp "
            "WHERE usuario_id = ? ORDER BY creado DESC",
            (usuario_id,),
        ).fetchall()
        return [
            {
                "id": f["id"],
                "etiqueta": f["etiqueta"],
                "creado": f["creado"],
                "ultimo_uso": f["ultimo_uso"],
                "expira": f["expira"],
                "revocado": bool(f["revocado"]),
            }
            for f in filas
        ]
    finally:
        con.close()
