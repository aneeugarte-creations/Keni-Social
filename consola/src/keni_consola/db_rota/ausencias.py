"""Persistencia — rota: ausencias / vacaciones (tabla `rota_ausencias`)."""
from __future__ import annotations

from ._comun import (
    TIPOS_AUSENCIA,
    Any,
    _conectar,
    ahora_iso,
    uuid,
)

# --------------------------------------------------------------------------- #
# Ausencias / vacaciones                                                       #
# --------------------------------------------------------------------------- #

_COLS_AUSENCIA_ROTA = (
    "id",
    "miembro_id",
    "miembro_nombre",
    "tipo",
    "desde",
    "hasta",
    "motivo",
    "creado",
)
_SELECT_AUSENCIA_ROTA = f"SELECT {', '.join(_COLS_AUSENCIA_ROTA)} FROM rota_ausencias"


def _fila_a_ausencia_rota(fila: Any) -> dict[str, Any]:
    return {col: fila[col] for col in _COLS_AUSENCIA_ROTA}


# --- Ausencias / vacaciones ---------------------------------------------------


def crear_ausencia_rota(
    miembro_id: str,
    desde: str,
    hasta: str,
    *,
    miembro_nombre: str = "",
    tipo: str = "otro",
    motivo: str = "",
) -> dict[str, Any]:
    """Inserta una ausencia (rango inclusivo) y la devuelve. NO valida (lo hace la API)."""
    ahora = ahora_iso()
    fila = {
        "id": uuid.uuid4().hex[:12],
        "miembro_id": miembro_id or "",
        "miembro_nombre": miembro_nombre or "",
        "tipo": tipo if tipo in TIPOS_AUSENCIA else "otro",
        "desde": desde or "",
        "hasta": hasta or "",
        "motivo": motivo or "",
        "creado": ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_AUSENCIA_ROTA)
        con.execute(
            f"INSERT INTO rota_ausencias ({', '.join(_COLS_AUSENCIA_ROTA)}) "
            f"VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_AUSENCIA_ROTA),
        )
        con.commit()
    finally:
        con.close()
    return fila


def listar_ausencias_rota(
    miembro_id: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
) -> list[dict[str, Any]]:
    """Ausencias de la rota, mas recientes primero. Filtros opcionales por miembro y solape de rango.

    `desde`/`hasta` filtran las ausencias que SOLAPAN con ese rango (ausencia.hasta >= desde
    AND ausencia.desde <= hasta): util para resolver las ausencias relevantes a una semana.
    """
    clausulas: list[str] = []
    params: list[Any] = []
    if miembro_id:
        clausulas.append("miembro_id = ?")
        params.append(miembro_id)
    if desde:
        clausulas.append("hasta >= ?")
        params.append(desde)
    if hasta:
        clausulas.append("desde <= ?")
        params.append(hasta)
    sql = _SELECT_AUSENCIA_ROTA
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY desde DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_ausencia_rota(f) for f in filas]


def obtener_ausencia_rota(ausencia_id: str) -> dict[str, Any] | None:
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_AUSENCIA_ROTA} WHERE id = ?", (ausencia_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_ausencia_rota(fila) if fila is not None else None


def actualizar_ausencia_rota(
    ausencia_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente una ausencia (tipo/desde/hasta/motivo); None si el id no existe."""
    editables = ("tipo", "desde", "hasta", "motivo")
    cambios = {k: v for k, v in campos.items() if k in editables}
    if not cambios:
        return obtener_ausencia_rota(ausencia_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    params: list[Any] = list(cambios.values())
    params.append(ausencia_id)
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE rota_ausencias SET {', '.join(asignaciones)} WHERE id = ?",
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_AUSENCIA_ROTA} WHERE id = ?", (ausencia_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_ausencia_rota(fila) if fila is not None else None


def borrar_ausencia_rota(ausencia_id: str) -> bool:
    """Borra una ausencia; True si existia, False si no."""
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM rota_ausencias WHERE id = ?", (ausencia_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()
