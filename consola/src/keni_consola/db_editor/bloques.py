"""Persistencia — dominio editor: bloques (capas reutilizables). Ver barrel `db.py`."""
from __future__ import annotations

from ..tiempo import ahora_iso
from ._comun import Any, _conectar, uuid

# --------------------------------------------------------------------------- #
# Bloques (almacén de capas reutilizables)                                       #
# --------------------------------------------------------------------------- #

_COLS_BLOQUES = (
    "id",
    "marca",
    "nombre",
    "capas",
    "categorias",
    "miniatura",
    "autor_id",
    "autor_nombre",
    "creado",
    "actualizado",
)
_SELECT_BLOQUES = f"SELECT {', '.join(_COLS_BLOQUES)} FROM bloques"
_CAMPOS_EDITABLES_BLOQUES: tuple[str, ...] = ("nombre", "capas", "categorias", "miniatura")


def _fila_a_bloque(fila: Any) -> dict[str, Any]:
    item: dict[str, Any] = {col: fila[col] for col in _COLS_BLOQUES}
    item["capas"] = fila["capas"] or "[]"
    item["categorias"] = fila["categorias"] or "[]"
    return item


def crear_bloque(
    *,
    marca: str = "",
    nombre: str = "",
    capas: str = "[]",
    categorias: str = "[]",
    miniatura: str = "",
    autor: dict[str, str] | None = None,
    id: str = "",
    creado: str = "",
    actualizado: str = "",
) -> dict[str, Any]:
    """Crea un bloque (grupo de capas reutilizable) y lo devuelve."""
    autor = autor or {}
    ahora = ahora_iso()
    fila = {
        "id": id or uuid.uuid4().hex[:12],
        "marca": marca or "",
        "nombre": nombre or "",
        "capas": capas or "[]",
        "categorias": categorias or "[]",
        "miniatura": miniatura or "",
        "autor_id": autor.get("id", "") or "",
        "autor_nombre": autor.get("usuario", "") or "",
        "creado": creado or ahora,
        "actualizado": actualizado or ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_BLOQUES)
        con.execute(
            f"INSERT INTO bloques ({', '.join(_COLS_BLOQUES)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_BLOQUES),
        )
        con.commit()
    finally:
        con.close()
    return _fila_a_bloque(fila)


def listar_bloques(*, marca: str | None = None) -> list[dict[str, Any]]:
    """Bloques, filtro opcional por marca. Mas recientes primero."""
    sql = _SELECT_BLOQUES
    params: list[Any] = []
    if marca:
        sql += " WHERE marca = ?"
        params.append(marca)
    sql += " ORDER BY creado DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_bloque(f) for f in filas]


def obtener_bloque(bloque_id: str) -> dict[str, Any] | None:
    con = _conectar()
    try:
        fila = con.execute(f"{_SELECT_BLOQUES} WHERE id = ?", (bloque_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_bloque(fila) if fila is not None else None


def actualizar_bloque(bloque_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_BLOQUES}
    if not cambios:
        return obtener_bloque(bloque_id)
    ahora = ahora_iso()
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, bloque_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE bloques SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(f"{_SELECT_BLOQUES} WHERE id = ?", (bloque_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_bloque(fila) if fila is not None else None


def borrar_bloque(bloque_id: str) -> dict[str, Any] | None:
    item = obtener_bloque(bloque_id)
    if item is None:
        return None
    con = _conectar()
    try:
        con.execute("DELETE FROM bloques WHERE id = ?", (bloque_id,))
        con.commit()
    finally:
        con.close()
    return item
