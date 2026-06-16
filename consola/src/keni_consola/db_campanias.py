"""Persistencia — dominio Campañas (filtro por hashtag). Implementación de db.py.

Una campaña no monitoriza piezas sueltas: define un FILTRO (marcas + lista de hashtags) y
su analítica se computa al vuelo sobre el listado de piezas del periodo (por cada marca),
cruzando por los hashtags del caption. `marcas` (ids de marca) y `hashtags` (tags sin '#',
con su casing) se persisten como arrays JSON; la normalización/validación la hace la capa
de negocio (`campanias.py`), no la DB. Las campañas son MULTIMARCA.
"""
from __future__ import annotations

from ._db_comun import (
    Any,
    _conectar,
    ahora_iso,
    uuid,
)
from ._db_json import a_json_lista, de_json_lista

_COLS_CAMPANIA = (
    "id",
    "marcas",
    "nombre",
    "hashtags",
    "activa",
    "fecha_creacion",
    "fecha_actualizacion",
)
_SELECT_CAMPANIA = f"SELECT {', '.join(_COLS_CAMPANIA)} FROM campanias"
_CAMPOS_EDITABLES_CAMPANIA = ("nombre", "marcas", "hashtags", "activa")


def _lista_json(valor: Any) -> list[str]:
    """Parsea un array JSON de strings (defensivo: lista vacía si no es válido)."""
    return [str(x) for x in de_json_lista(valor)]


def _fila_a_campania(fila: Any) -> dict[str, Any]:
    """Convierte una fila en dict (marcas/hashtags como listas, activa bool)."""
    cam = {col: fila[col] for col in _COLS_CAMPANIA}
    cam["marcas"] = _lista_json(fila["marcas"])
    cam["hashtags"] = _lista_json(fila["hashtags"])
    cam["activa"] = bool(fila["activa"])
    return cam


def crear_campania(
    *,
    marcas: list[str],
    nombre: str,
    hashtags: list[str],
    activa: bool = True,
) -> dict[str, Any]:
    """Inserta una campaña (multimarca) y la devuelve. NO valida (lo hace `campanias.py`)."""
    ahora = ahora_iso()
    fila = {
        "id": uuid.uuid4().hex[:12],
        "marcas": a_json_lista(list(marcas)),
        "nombre": nombre,
        "hashtags": a_json_lista(list(hashtags)),
        "activa": 1 if activa else 0,
        "fecha_creacion": ahora,
        "fecha_actualizacion": ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_CAMPANIA)
        con.execute(
            f"INSERT INTO campanias ({', '.join(_COLS_CAMPANIA)}) "
            f"VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_CAMPANIA),
        )
        con.commit()
    finally:
        con.close()
    return _fila_a_campania(fila)


def listar_campanias(marca: str | None = None) -> list[dict[str, Any]]:
    """Campañas (más recientes primero).

    `marca` (opcional) filtra a las campañas que INCLUYEN esa marca. Como `marcas` es un
    array JSON, el filtro se hace en Python tras leer (el volumen de campañas es pequeño).
    """
    sql = f"{_SELECT_CAMPANIA} ORDER BY fecha_creacion DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql).fetchall()
    finally:
        con.close()
    cams = [_fila_a_campania(f) for f in filas]
    if marca:
        cams = [c for c in cams if marca in c["marcas"]]
    return cams


def obtener_campania(campania_id: str) -> dict[str, Any] | None:
    """Una campaña por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_CAMPANIA} WHERE id = ?", (campania_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_campania(fila) if fila is not None else None


def actualizar_campania(
    campania_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente una campaña; None si el id no existe.

    Solo toca `nombre`/`marcas`/`hashtags`/`activa`. `marcas`/`hashtags` (si vienen) se
    serializan a JSON; `activa` a 0/1. NO valida (lo hace `campanias.py`).
    """
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_CAMPANIA}
    for clave in ("marcas", "hashtags"):
        if clave in cambios:
            cambios[clave] = a_json_lista(list(cambios[clave] or []))
    if "activa" in cambios:
        cambios["activa"] = 1 if cambios["activa"] else 0
    if not cambios:
        return obtener_campania(campania_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("fecha_actualizacion = ?")
    params: list[Any] = list(cambios.values())
    params.append(ahora_iso())
    params.append(campania_id)
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE campanias SET {', '.join(asignaciones)} WHERE id = ?",
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_CAMPANIA} WHERE id = ?", (campania_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_campania(fila) if fila is not None else None


def borrar_campania(campania_id: str) -> bool:
    """Borra una campaña; True si existía, False si no."""
    con = _conectar()
    try:
        cur = con.execute(
            "DELETE FROM campanias WHERE id = ?", (campania_id,)
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()
