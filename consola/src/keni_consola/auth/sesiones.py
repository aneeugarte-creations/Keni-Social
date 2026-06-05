"""Sesiones server-side: crear, validar (ventana deslizante) y borrar.

Una sesion es un token aleatorio url-safe (~256 bits) guardado en la tabla
`sesiones` junto al `usuario_id` y su expiracion. El token viaja en la cookie
`keni_consola_sesion` (HttpOnly + SameSite=Strict, la pone la capa API). La
expiracion es configurable (`horas_sesion`) y se RENUEVA con cada uso.
"""

from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Any

from .. import db
from . import _comun

# Nombre de la cookie de sesion (CONTRATO con el frontend y el middleware de seguridad).
COOKIE_SESION = "keni_consola_sesion"


def crear_sesion(usuario_id: str) -> str:
    """Crea una sesion para `usuario_id` y devuelve su token (url-safe, ~256 bits)."""
    token = secrets.token_urlsafe(32)
    ahora = _comun.ahora()
    expira = ahora + timedelta(hours=_comun.horas_sesion())
    con = db.conectar()
    try:
        con.execute(
            "INSERT INTO sesiones (token, usuario_id, creada, ultimo_uso, expira) "
            "VALUES (?, ?, ?, ?, ?)",
            (token, usuario_id, _comun.iso(ahora), _comun.iso(ahora), _comun.iso(expira)),
        )
        con.commit()
    finally:
        con.close()
    return token


def sesion_valida(token: str) -> dict[str, Any] | None:
    """Devuelve el usuario (forma publica) de una sesion VIGENTE, o None.

    Si la sesion expiro, la borra y devuelve None. Si es valida, RENUEVA `ultimo_uso`
    y `expira` (ventana deslizante) y actualiza el `ultimo_acceso` del usuario.

    TOPE ABSOLUTO: ademas de la expiracion DESLIZANTE (`expira`, que se renueva en cada uso),
    se impone un tope DURO contra `creada`: si la sesion lleva mas de `max_horas_sesion()`
    desde que se creo, se rechaza y borra AUNQUE se haya usado hace un instante. Asi un token
    renovado indefinidamente (sesion viva o robada-y-usada) no vive para siempre; la ventana
    deslizante (idle) sigue intacta. Default GENEROSO (30 d): no afecta el uso normal del piloto.
    """
    if not token:
        return None
    con = db.conectar()
    try:
        fila = con.execute(
            "SELECT s.token AS s_token, s.expira AS s_expira, s.creada AS s_creada, "
            "u.id AS id, u.usuario AS usuario, "
            "u.rol AS rol, u.debe_cambiar_password AS debe_cambiar_password, "
            "u.cargo AS cargo, u.creado AS creado, u.ultimo_acceso AS ultimo_acceso "
            "FROM sesiones s JOIN usuarios u ON u.id = s.usuario_id WHERE s.token = ?",
            (token,),
        ).fetchone()
        if fila is None:
            return None
        expira = _comun.parsear_iso(fila["s_expira"])
        ahora = _comun.ahora()
        if expira is None or ahora >= expira:
            con.execute("DELETE FROM sesiones WHERE token = ?", (token,))
            con.commit()
            return None
        # Tope ABSOLUTO contra `creada`: caduca la sesion pasada `max_horas_sesion()` desde su
        # creacion, AUNQUE la ventana deslizante siga vigente (token renovado/robado-y-usado).
        # Una `creada` ilegible/vacia (registros muy viejos) NO se castiga: si no podemos juzgar
        # su edad, dejamos que mande la expiracion deslizante (degradacion conservadora).
        creada = _comun.parsear_iso(fila["s_creada"])
        if creada is not None:
            tope = creada + timedelta(hours=_comun.max_horas_sesion())
            if ahora >= tope:
                con.execute("DELETE FROM sesiones WHERE token = ?", (token,))
                con.commit()
                return None
        # Vigente: ventana deslizante + ultimo_acceso del usuario.
        nueva_expira = ahora + timedelta(hours=_comun.horas_sesion())
        con.execute(
            "UPDATE sesiones SET ultimo_uso = ?, expira = ? WHERE token = ?",
            (_comun.iso(ahora), _comun.iso(nueva_expira), token),
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
            # `cargo` (organigrama) lo usa la cadena de aprobacion para validar el cargo
            # requerido por nivel (item C). "" si el usuario no tiene cargo asignado.
            "cargo": fila["cargo"] or "",
            "debe_cambiar_password": bool(fila["debe_cambiar_password"]),
            "creado": fila["creado"],
            "ultimo_acceso": _comun.iso(ahora),
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
