"""Persistencia — dominio hashtags_franjas. Implementación de db.py (ver barrel `db.py`)."""
from __future__ import annotations

from ._db_comun import (
    Any,
    _conectar,
    uuid,
)

# --- Franjas editoriales --------------------------------------------------- #
# Dict publico (paridad con `ficheros._leer_franjas_marca`): `id, marca, red, dia_semana, hora`.
_COLS_FRANJA_EDIT = ("id", "marca", "red", "dia_semana", "hora", "categoria")
_SELECT_FRANJA_EDIT = f"SELECT {', '.join(_COLS_FRANJA_EDIT)} FROM franjas_editoriales"


def _fila_a_franja(fila: Any) -> dict[str, Any]:
    """Fila de `franjas_editoriales` -> dict publico."""
    return {
        "id": fila["id"],
        "marca": fila["marca"] or "",
        "red": fila["red"] or "",
        "dia_semana": int(fila["dia_semana"] or 0),
        "hora": fila["hora"] or "",
        "categoria": fila["categoria"] or "",
    }


def listar_franjas() -> list[dict[str, Any]]:
    """Todas las franjas editoriales, ordenadas por dia/hora/id (determinista)."""
    con = _conectar()
    try:
        filas = con.execute(
            f"{_SELECT_FRANJA_EDIT} ORDER BY dia_semana ASC, hora ASC, id ASC"
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_franja(f) for f in filas]


def crear_franja(
    dia_semana: int, hora: str, marca: str = "", red: str = "", categoria: str = ""
) -> dict[str, Any]:
    """Crea una franja editorial y la devuelve. `categoria` '' = genérica (vale para todo)."""
    franja = {
        "id": uuid.uuid4().hex[:12],
        "marca": marca or "",
        "red": red or "",
        "dia_semana": int(dia_semana),
        "hora": hora or "",
        "categoria": (categoria or "").strip().lower(),
    }
    con = _conectar()
    try:
        # ON CONFLICT (...) DO NOTHING: idempotente frente a un alta repetida de la misma
        # franja (mismo patron que `rota_franjas`). Requiere el indice unico
        # `idx_franjas_editoriales_uniq2` (lo crea `_crear_indices_unicos_idempotencia`);
        # PRECONDICION: una BD con duplicados previos impide crearlo -> limpiar antes.
        con.execute(
            "INSERT INTO franjas_editoriales (id, marca, red, dia_semana, hora, categoria) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (marca, red, dia_semana, hora, categoria) DO NOTHING",
            (franja["id"], franja["marca"], franja["red"], franja["dia_semana"],
             franja["hora"], franja["categoria"]),
        )
        con.commit()
    finally:
        con.close()
    return franja


def borrar_franja(franja_id: str) -> bool:
    """Borra una franja editorial; True si existia, False si no."""
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM franjas_editoriales WHERE id = ?", (franja_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()
