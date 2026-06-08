"""Persistencia — dominio editor: activos de marca. Implementación de db.py (ver barrel `db.py`)."""
from __future__ import annotations

from ._comun import Any, _conectar, datetime, uuid

# --------------------------------------------------------------------------- #
# Activos de marca (editor profesional: kit visual reutilizable por marca)       #
# --------------------------------------------------------------------------- #

_COLS_MARCA_ACTIVOS = (
    "id",
    "marca",
    "tipo",
    "nombre",
    "objeto",
    "metadatos",
    "lineas",
    "aprobado",
    "autor_id",
    "autor_nombre",
    "creado",
    "actualizado",
)
_SELECT_MARCA_ACTIVOS = f"SELECT {', '.join(_COLS_MARCA_ACTIVOS)} FROM marca_activos"

# Campos editables via `actualizar_marca_activo` (lista blanca). `id`, `marca`, `objeto`,
# `autor_*` y `creado` no son editables (un activo nuevo se cataloga aparte).
_CAMPOS_EDITABLES_MARCA_ACTIVOS: tuple[str, ...] = (
    "tipo",
    "nombre",
    "metadatos",
    "lineas",
    "aprobado",
)


def _fila_a_marca_activo(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `marca_activos` en dict (con defaults defensivos)."""
    item: dict[str, Any] = {col: fila[col] for col in _COLS_MARCA_ACTIVOS}
    item["aprobado"] = bool(fila["aprobado"])
    item["metadatos"] = fila["metadatos"] or "{}"
    item["lineas"] = fila["lineas"] or "[]"
    item["tipo"] = fila["tipo"] or "arte"
    return item


def crear_marca_activo(
    *,
    marca: str,
    tipo: str = "arte",
    nombre: str = "",
    objeto: str = "",
    metadatos: str = "{}",
    lineas: str = "[]",
    aprobado: bool = True,
    autor: dict[str, str] | None = None,
    id: str = "",
    creado: str = "",
    actualizado: str = "",
) -> dict[str, Any]:
    """Cataloga un activo de marca y lo devuelve. NO valida (lo hace la API)."""
    autor = autor or {}
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": id or uuid.uuid4().hex[:12],
        "marca": marca or "",
        "tipo": tipo or "arte",
        "nombre": nombre or "",
        "objeto": objeto or "",
        "metadatos": metadatos or "{}",
        "lineas": lineas or "[]",
        "aprobado": 1 if aprobado else 0,
        "autor_id": autor.get("id", "") or "",
        "autor_nombre": autor.get("usuario", "") or "",
        "creado": creado or ahora,
        "actualizado": actualizado or ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_MARCA_ACTIVOS)
        con.execute(
            f"INSERT INTO marca_activos ({', '.join(_COLS_MARCA_ACTIVOS)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_MARCA_ACTIVOS),
        )
        con.commit()
    finally:
        con.close()
    return _fila_a_marca_activo(fila)


def listar_marca_activos(
    *, marca: str | None = None, tipo: str | None = None, solo_aprobados: bool = False
) -> list[dict[str, Any]]:
    """Activos de marca, filtros combinables (AND). Mas recientes primero."""
    clausulas: list[str] = []
    params: list[Any] = []
    if marca:
        clausulas.append("marca = ?")
        params.append(marca)
    if tipo:
        clausulas.append("tipo = ?")
        params.append(tipo)
    if solo_aprobados:
        clausulas.append("aprobado = 1")
    sql = _SELECT_MARCA_ACTIVOS
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY creado DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_marca_activo(f) for f in filas]


def obtener_marca_activo(activo_id: str) -> dict[str, Any] | None:
    """Un activo de marca por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(f"{_SELECT_MARCA_ACTIVOS} WHERE id = ?", (activo_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_marca_activo(fila) if fila is not None else None


def actualizar_marca_activo(activo_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Edita parcialmente; None si el id no existe. Filtra a la lista blanca."""
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_MARCA_ACTIVOS}
    if "aprobado" in cambios:
        cambios["aprobado"] = 1 if cambios["aprobado"] else 0
    if not cambios:
        return obtener_marca_activo(activo_id)
    ahora = datetime.now().isoformat(timespec="seconds")
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, activo_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE marca_activos SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(f"{_SELECT_MARCA_ACTIVOS} WHERE id = ?", (activo_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_marca_activo(fila) if fila is not None else None


def borrar_marca_activo(activo_id: str) -> dict[str, Any] | None:
    """Borra un activo de marca; devuelve el borrado (para limpiar el binario) o None."""
    item = obtener_marca_activo(activo_id)
    if item is None:
        return None
    con = _conectar()
    try:
        con.execute("DELETE FROM marca_activos WHERE id = ?", (activo_id,))
        con.commit()
    finally:
        con.close()
    return item
