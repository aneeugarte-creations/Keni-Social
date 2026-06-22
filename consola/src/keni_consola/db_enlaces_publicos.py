"""Persistencia — enlaces PÚBLICOS de campaña (capability-URL de solo lectura).

Un enlace mapea un `token` indescifrable a UNA campaña y un periodo+modo CONGELADOS. La
validez (no caducado, no revocado) la decide la capa de negocio (`campanias.py`); aquí solo
el CRUD. Mismo patrón que `db_campanias.py` (implementación de `db.py`).
"""
from __future__ import annotations

from ._db_comun import (
    Any,
    _conectar,
    ahora_iso,
    uuid,
)

_COLS_ENLACE = (
    "id",
    "campania_id",
    "token",
    "rango",
    "ocultar_ads",
    "creado",
    "expira",
    "desactivado",
)
_SELECT_ENLACE = f"SELECT {', '.join(_COLS_ENLACE)} FROM enlaces_publicos_campania"


def _fila_a_enlace(fila: Any) -> dict[str, Any]:
    e = {col: fila[col] for col in _COLS_ENLACE}
    e["ocultar_ads"] = bool(fila["ocultar_ads"])
    e["desactivado"] = bool(fila["desactivado"])
    return e


def crear_enlace_publico(
    *, campania_id: str, token: str, rango: str, ocultar_ads: bool, expira: str
) -> dict[str, Any]:
    """Inserta un enlace público y lo devuelve. NO valida (lo hace `campanias.py`)."""
    fila = {
        "id": uuid.uuid4().hex[:12],
        "campania_id": campania_id,
        "token": token,
        "rango": rango,
        "ocultar_ads": 1 if ocultar_ads else 0,
        "creado": ahora_iso(),
        "expira": expira,
        "desactivado": 0,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_ENLACE)
        con.execute(
            f"INSERT INTO enlaces_publicos_campania ({', '.join(_COLS_ENLACE)}) "
            f"VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_ENLACE),
        )
        con.commit()
    finally:
        con.close()
    return _fila_a_enlace(fila)


def obtener_enlace_por_token(token: str) -> dict[str, Any] | None:
    """Enlace por token (None si no existe). NO filtra por caducidad/revocación."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_ENLACE} WHERE token = ?", (token,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_enlace(fila) if fila is not None else None


def listar_enlaces_de_campania(campania_id: str) -> list[dict[str, Any]]:
    """Enlaces de una campaña, más recientes primero (incluye revocados, para la gestión)."""
    con = _conectar()
    try:
        filas = con.execute(
            f"{_SELECT_ENLACE} WHERE campania_id = ? ORDER BY creado DESC, id DESC",
            (campania_id,),
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_enlace(f) for f in filas]


def desactivar_enlace_publico(enlace_id: str, campania_id: str) -> bool:
    """Marca un enlace como revocado (no borra). True si existía y pertenecía a la campaña."""
    con = _conectar()
    try:
        cur = con.execute(
            "UPDATE enlaces_publicos_campania SET desactivado = 1 "
            "WHERE id = ? AND campania_id = ?",
            (enlace_id, campania_id),
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()
