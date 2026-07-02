"""Persistencia — dominio notificaciones. Implementación de db.py (ver barrel `db.py`)."""
from __future__ import annotations

from ._comun import (
    Any,
    _conectar,
    uuid,
)
from ..tiempo import ahora_iso

# --------------------------------------------------------------------------- #
# Notificaciones IN-APP (el "cajon" de la campana)                             #
# --------------------------------------------------------------------------- #
# Una fila = una noticia para UN destinatario. Append + update de `leida`. El reparto
# (a quien notificar) vive en `dominio/notificaciones.py`; aqui solo se persiste/lee.

_COLS_NOTIFICACION = (
    "id",
    "usuario_id",
    "marca_id",
    "tipo",
    "publicacion_id",
    "pieza_id",
    "actor_id",
    "actor_nombre",
    "resumen",
    "enlace",
    "leida",
    "creada",
)
_SELECT_NOTIFICACION = f"SELECT {', '.join(_COLS_NOTIFICACION)} FROM notificaciones"


def _fila_a_notificacion(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `notificaciones` en dict (`leida` como bool)."""
    item: dict[str, Any] = {col: fila[col] for col in _COLS_NOTIFICACION}
    item["leida"] = bool(fila["leida"])
    return item


def crear_notificacion(
    *,
    usuario_id: str,
    marca_id: str,
    tipo: str,
    publicacion_id: str = "",
    pieza_id: str = "",
    actor: dict[str, str] | None = None,
    resumen: str = "",
    enlace: str = "",
) -> dict[str, Any]:
    """Inserta UNA notificacion para un destinatario y la devuelve. NO valida ni filtra."""
    actor = actor or {}
    fila = {
        "id": uuid.uuid4().hex[:12],
        "usuario_id": usuario_id or "",
        "marca_id": marca_id or "",
        "tipo": tipo or "",
        "publicacion_id": publicacion_id or "",
        "pieza_id": pieza_id or "",
        "actor_id": actor.get("id", "") or "",
        "actor_nombre": actor.get("usuario", "") or actor.get("nombre", "") or "",
        "resumen": resumen or "",
        "enlace": enlace or "",
        "leida": 0,
        "creada": ahora_iso(),
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_NOTIFICACION)
        con.execute(
            f"INSERT INTO notificaciones ({', '.join(_COLS_NOTIFICACION)}) "
            f"VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_NOTIFICACION),
        )
        con.commit()
    finally:
        con.close()
    return _fila_a_notificacion(fila)


def listar_notificaciones(
    usuario_id: str, marca_id: str | None = None, limite: int = 50
) -> list[dict[str, Any]]:
    """Notificaciones de un usuario (mas recientes primero). `marca_id` filtra el workspace."""
    sql = f"{_SELECT_NOTIFICACION} WHERE usuario_id = ?"
    params: list[Any] = [usuario_id]
    if marca_id:
        sql += " AND marca_id = ?"
        params.append(marca_id)
    sql += " ORDER BY creada DESC, id DESC LIMIT ?"
    params.append(max(1, min(limite, 200)))
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_notificacion(f) for f in filas]


def contar_notificaciones_no_leidas(usuario_id: str, marca_id: str | None = None) -> int:
    """Cuenta las notificaciones SIN leer de un usuario (filtro opcional por marca)."""
    sql = "SELECT COUNT(*) AS n FROM notificaciones WHERE usuario_id = ? AND leida = 0"
    params: list[Any] = [usuario_id]
    if marca_id:
        sql += " AND marca_id = ?"
        params.append(marca_id)
    con = _conectar()
    try:
        fila = con.execute(sql, tuple(params)).fetchone()
    finally:
        con.close()
    return int(fila["n"]) if fila is not None else 0


def marcar_notificacion_leida(notificacion_id: str, usuario_id: str) -> bool:
    """Marca UNA notificacion como leida (solo si es del usuario). True si existia."""
    con = _conectar()
    try:
        cur = con.execute(
            "UPDATE notificaciones SET leida = 1 WHERE id = ? AND usuario_id = ?",
            (notificacion_id, usuario_id),
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def marcar_notificaciones_leidas(usuario_id: str, marca_id: str | None = None) -> int:
    """Marca como leidas TODAS las del usuario (opcionalmente solo las de una marca)."""
    sql = "UPDATE notificaciones SET leida = 1 WHERE usuario_id = ? AND leida = 0"
    params: list[Any] = [usuario_id]
    if marca_id:
        sql += " AND marca_id = ?"
        params.append(marca_id)
    con = _conectar()
    try:
        cur = con.execute(sql, tuple(params))
        con.commit()
        return cur.rowcount
    finally:
        con.close()
