"""Persistencia — dominio editor: plantillas de diseño. Implementación de db.py (ver barrel `db.py`)."""
from __future__ import annotations

from ._comun import Any, _conectar, datetime, uuid

# --------------------------------------------------------------------------- #
# Plantillas de diseño (editor profesional: N plantillas reutilizables por marca) #
# --------------------------------------------------------------------------- #

_COLS_PLANTILLAS_DISENO = (
    "id",
    "marca",
    "nombre",
    "categoria",
    "tipo",
    "documento",
    "miniatura",
    "lineas",
    "activo",
    "autor_id",
    "autor_nombre",
    "creado",
    "actualizado",
)
_SELECT_PLANTILLAS_DISENO = f"SELECT {', '.join(_COLS_PLANTILLAS_DISENO)} FROM plantillas_diseno"

_CAMPOS_EDITABLES_PLANTILLAS_DISENO: tuple[str, ...] = (
    "nombre",
    "categoria",
    "tipo",
    "documento",
    "miniatura",
    "lineas",
    "activo",
)


def _fila_a_plantilla_diseno(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `plantillas_diseno` en dict (con defaults defensivos)."""
    item: dict[str, Any] = {col: fila[col] for col in _COLS_PLANTILLAS_DISENO}
    item["activo"] = bool(fila["activo"])
    item["documento"] = fila["documento"] or "{}"
    item["lineas"] = fila["lineas"] or "[]"
    item["categoria"] = fila["categoria"] or "post"
    item["tipo"] = fila["tipo"] if fila["tipo"] in ("foto", "miniatura") else "foto"
    return item


def crear_plantilla_diseno(
    *,
    marca: str,
    nombre: str = "",
    categoria: str = "post",
    tipo: str = "foto",
    documento: str = "{}",
    miniatura: str = "",
    lineas: str = "[]",
    activo: bool = True,
    autor: dict[str, str] | None = None,
    id: str = "",
    creado: str = "",
    actualizado: str = "",
) -> dict[str, Any]:
    """Crea una plantilla de diseño y la devuelve. NO valida el documento (lo hace la API)."""
    autor = autor or {}
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": id or uuid.uuid4().hex[:12],
        "marca": marca or "",
        "nombre": nombre or "",
        "categoria": categoria or "post",
        "tipo": tipo if tipo in ("foto", "miniatura") else "foto",
        "documento": documento or "{}",
        "miniatura": miniatura or "",
        "lineas": lineas or "[]",
        "activo": 1 if activo else 0,
        "autor_id": autor.get("id", "") or "",
        "autor_nombre": autor.get("usuario", "") or "",
        "creado": creado or ahora,
        "actualizado": actualizado or ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_PLANTILLAS_DISENO)
        con.execute(
            f"INSERT INTO plantillas_diseno ({', '.join(_COLS_PLANTILLAS_DISENO)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_PLANTILLAS_DISENO),
        )
        con.commit()
    finally:
        con.close()
    return _fila_a_plantilla_diseno(fila)


def listar_plantillas_diseno(
    *,
    marca: str | None = None,
    categoria: str | None = None,
    tipo: str | None = None,
    solo_activas: bool = False,
) -> list[dict[str, Any]]:
    """Plantillas de diseño, filtros combinables (AND). Mas recientes primero."""
    clausulas: list[str] = []
    params: list[Any] = []
    if marca:
        clausulas.append("marca = ?")
        params.append(marca)
    if categoria:
        clausulas.append("categoria = ?")
        params.append(categoria)
    if tipo:
        clausulas.append("tipo = ?")
        params.append(tipo)
    if solo_activas:
        clausulas.append("activo = 1")
    sql = _SELECT_PLANTILLAS_DISENO
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY creado DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_plantilla_diseno(f) for f in filas]


def obtener_plantilla_diseno(plantilla_id: str) -> dict[str, Any] | None:
    """Una plantilla de diseño por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(f"{_SELECT_PLANTILLAS_DISENO} WHERE id = ?", (plantilla_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_plantilla_diseno(fila) if fila is not None else None


def actualizar_plantilla_diseno(plantilla_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Edita parcialmente; None si el id no existe. Filtra a la lista blanca."""
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_PLANTILLAS_DISENO}
    if "activo" in cambios:
        cambios["activo"] = 1 if cambios["activo"] else 0
    if not cambios:
        return obtener_plantilla_diseno(plantilla_id)
    ahora = datetime.now().isoformat(timespec="seconds")
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, plantilla_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE plantillas_diseno SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(f"{_SELECT_PLANTILLAS_DISENO} WHERE id = ?", (plantilla_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_plantilla_diseno(fila) if fila is not None else None


def borrar_plantilla_diseno(plantilla_id: str) -> dict[str, Any] | None:
    """Borra una plantilla de diseño; devuelve la borrada o None."""
    item = obtener_plantilla_diseno(plantilla_id)
    if item is None:
        return None
    con = _conectar()
    try:
        con.execute("DELETE FROM plantillas_diseno WHERE id = ?", (plantilla_id,))
        con.commit()
    finally:
        con.close()
    return item
