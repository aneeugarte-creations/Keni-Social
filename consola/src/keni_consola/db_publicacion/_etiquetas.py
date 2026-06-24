"""Persistencia — etiquetas editoriales (`etiquetas`). Implementación de db.py (ver barrel)."""
from __future__ import annotations

from .._db_comun import (
    ahora_iso,
    Any,
    _conectar,
    uuid,
)

__all__ = [
    "_COLS_ETIQUETA",
    "_SELECT_ETIQUETA",
    "_CAMPOS_EDITABLES_ETIQUETA",
    "_fila_a_etiqueta",
    "crear_etiqueta",
    "listar_etiquetas",
    "obtener_etiqueta",
    "existe_etiqueta_nombre",
    "obtener_etiqueta_por_nombre",
    "actualizar_etiqueta",
    "borrar_etiqueta",
]

# --------------------------------------------------------------------------- #
# Etiquetas editoriales (campaña / categoria / tipo) y su N:M con `contenido`     #
# --------------------------------------------------------------------------- #
# Una etiqueta clasifica transversalmente las piezas del tablero. `marca = ''` =
# etiqueta GLOBAL. La capa API valida `clase`/`marca`/unicidad; db.py NO valida.

_COLS_ETIQUETA = (
    "id",
    "nombre",
    "clase",
    "marca",
    "color",
    "keywords",
    "hashtags",
    "activo",
    "ttl_dias",
    "es_evergreen",
    "grupo",
    "cadencia",
    "creado",
    "actualizado",
)
_SELECT_ETIQUETA = f"SELECT {', '.join(_COLS_ETIQUETA)} FROM etiquetas"
_CAMPOS_EDITABLES_ETIQUETA: tuple[str, ...] = (
    "nombre",
    "clase",
    "marca",
    "color",
    "keywords",
    "hashtags",
    "activo",
    "ttl_dias",
    "es_evergreen",
    "grupo",
    "cadencia",
)


def _fila_a_etiqueta(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `etiquetas` en dict (con `activo`/`es_evergreen` como bool)."""
    et: dict[str, Any] = {col: fila[col] for col in _COLS_ETIQUETA}
    et["activo"] = bool(fila["activo"])
    et["ttl_dias"] = int(fila["ttl_dias"] or 0)
    et["es_evergreen"] = bool(fila["es_evergreen"])
    et["grupo"] = fila["grupo"] or ""
    et["cadencia"] = fila["cadencia"] or "normal"
    return et


def crear_etiqueta(
    *,
    nombre: str,
    clase: str = "campania",
    marca: str = "",
    color: str = "",
    keywords: str = "",
    hashtags: str = "",
    activo: bool = True,
    ttl_dias: int = 0,
    es_evergreen: bool = False,
    grupo: str = "",
    cadencia: str = "normal",
    creado: str = "",
    actualizado: str = "",
    id: str = "",
) -> dict[str, Any]:
    """Inserta una etiqueta editorial y la devuelve. NO valida (lo hace la API)."""
    ahora = ahora_iso()
    fila = {
        "id": id or uuid.uuid4().hex[:12],
        "nombre": nombre or "",
        "clase": clase or "campania",
        "marca": marca or "",
        "color": color or "",
        "keywords": keywords or "",
        "hashtags": hashtags or "",
        "activo": 1 if activo else 0,
        "ttl_dias": max(0, int(ttl_dias or 0)),
        "es_evergreen": 1 if es_evergreen else 0,
        "grupo": grupo or "",
        "cadencia": cadencia or "normal",
        "creado": creado or ahora,
        "actualizado": actualizado or ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_ETIQUETA)
        con.execute(
            f"INSERT INTO etiquetas ({', '.join(_COLS_ETIQUETA)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_ETIQUETA),
        )
        con.commit()
    finally:
        con.close()
    # Mismo serializador que `obtener`/`listar`: `activo`/`es_evergreen` salen como bool.
    return _fila_a_etiqueta(fila)


def listar_etiquetas(
    *, marca: str | None = None, clase: str | None = None, solo_activas: bool = False
) -> list[dict[str, Any]]:
    """Lista etiquetas. `marca`: incluye las de esa marca Y las globales (marca='').

    Sin `marca` devuelve TODAS (de cualquier marca). `solo_activas` excluye las ocultas.
    """
    clausulas: list[str] = []
    params: list[Any] = []
    if marca is not None:
        clausulas.append("(marca = ? OR marca = '')")
        params.append(marca)
    if clase:
        clausulas.append("clase = ?")
        params.append(clase)
    if solo_activas:
        clausulas.append("activo = 1")
    sql = _SELECT_ETIQUETA
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY clase ASC, nombre ASC, id ASC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_etiqueta(f) for f in filas]


def obtener_etiqueta(etiqueta_id: str) -> dict[str, Any] | None:
    """Una etiqueta por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(f"{_SELECT_ETIQUETA} WHERE id = ?", (etiqueta_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_etiqueta(fila) if fila is not None else None


def existe_etiqueta_nombre(
    nombre: str, clase: str, marca: str, *, excluir_id: str = ""
) -> bool:
    """True si ya hay una etiqueta con ese (nombre, clase, marca) — unicidad case-insensitive."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_ETIQUETA} WHERE LOWER(nombre) = LOWER(?) AND clase = ? "
            "AND marca = ? AND id != ?",
            (nombre, clase, marca, excluir_id),
        ).fetchone()
    finally:
        con.close()
    return fila is not None


def obtener_etiqueta_por_nombre(nombre: str, clase: str, marca: str) -> dict[str, Any] | None:
    """Devuelve la etiqueta por (nombre, clase, marca) — case-insensitive. None si no existe."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_ETIQUETA} WHERE LOWER(nombre) = LOWER(?) AND clase = ? AND marca = ?",
            (nombre, clase, marca),
        ).fetchone()
    finally:
        con.close()
    return _fila_a_etiqueta(fila) if fila is not None else None


def actualizar_etiqueta(
    etiqueta_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente una etiqueta; None si no existe. Filtra a la lista blanca."""
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_ETIQUETA}
    if "activo" in cambios:
        cambios["activo"] = 1 if cambios["activo"] else 0
    if "es_evergreen" in cambios:
        cambios["es_evergreen"] = 1 if cambios["es_evergreen"] else 0
    if "ttl_dias" in cambios:
        cambios["ttl_dias"] = max(0, int(cambios["ttl_dias"] or 0))
    if not cambios:
        return obtener_etiqueta(etiqueta_id)
    ahora = ahora_iso()
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, etiqueta_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE etiquetas SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(f"{_SELECT_ETIQUETA} WHERE id = ?", (etiqueta_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_etiqueta(fila) if fila is not None else None


def borrar_etiqueta(etiqueta_id: str) -> bool:
    """Borra una etiqueta y todas SUS asignaciones (cascada). True si existia."""
    con = _conectar()
    try:
        con.execute(
            "DELETE FROM publicacion_etiquetas WHERE etiqueta_id = ?", (etiqueta_id,)
        )
        cur = con.execute("DELETE FROM etiquetas WHERE id = ?", (etiqueta_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()
