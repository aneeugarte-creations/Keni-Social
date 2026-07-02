"""Persistencia — dominio Vistas guardadas de Analíticas. Implementación de db.py.

Una vista guardada es un PRESET nombrado del dashboard de Métricas: congela la
configuración de vista (`config`, el `VistaConfig` serializable de la capa de presentación)
junto con la marca (id canónico; '' = todas) y el periodo (token de `?periodo=`). Son
COMPARTIDAS por el equipo (piloto AMX): `autor_*` es solo atribución, no controla acceso.
La validación (marca permitida, nombre no vacío) la hace la capa API; aquí solo se persiste.
"""
from __future__ import annotations

from ._comun import (
    Any,
    _conectar,
    ahora_iso,
    uuid,
)
from ._json import a_json_dict, de_json_dict

_COLS_VISTA = (
    "id",
    "nombre",
    "marca",
    "periodo",
    "config",
    "autor_id",
    "autor_nombre",
    "fecha_creacion",
    "fecha_actualizacion",
)
_SELECT_VISTA = f"SELECT {', '.join(_COLS_VISTA)} FROM vistas_metricas"
_CAMPOS_EDITABLES_VISTA = ("nombre", "marca", "periodo", "config")


def _fila_a_vista(fila: Any) -> dict[str, Any]:
    """Convierte una fila en dict (config como dict deserializado)."""
    vista = {col: fila[col] for col in _COLS_VISTA}
    vista["config"] = de_json_dict(fila["config"])
    return vista


def crear_vista(
    *,
    nombre: str,
    marca: str,
    periodo: str,
    config: dict[str, Any],
    autor_id: str = "",
    autor_nombre: str = "",
) -> dict[str, Any]:
    """Inserta una vista guardada y la devuelve. NO valida (lo hace la capa API)."""
    ahora = ahora_iso()
    fila = {
        "id": uuid.uuid4().hex[:12],
        "nombre": nombre,
        "marca": marca,
        "periodo": periodo,
        "config": a_json_dict(config),
        "autor_id": autor_id,
        "autor_nombre": autor_nombre,
        "fecha_creacion": ahora,
        "fecha_actualizacion": ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_VISTA)
        con.execute(
            f"INSERT INTO vistas_metricas ({', '.join(_COLS_VISTA)}) "
            f"VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_VISTA),
        )
        con.commit()
    finally:
        con.close()
    return _fila_a_vista(fila)


def listar_vistas(marca: str | None = None) -> list[dict[str, Any]]:
    """Vistas guardadas (alfabéticas por nombre). `marca` (opcional) filtra por marca exacta."""
    sql = f"{_SELECT_VISTA} ORDER BY nombre ASC, id ASC"
    con = _conectar()
    try:
        filas = con.execute(sql).fetchall()
    finally:
        con.close()
    vistas = [_fila_a_vista(f) for f in filas]
    if marca is not None:
        vistas = [v for v in vistas if v["marca"] == marca]
    return vistas


def obtener_vista(vista_id: str) -> dict[str, Any] | None:
    """Una vista por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(f"{_SELECT_VISTA} WHERE id = ?", (vista_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_vista(fila) if fila is not None else None


def actualizar_vista(vista_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Edita parcialmente una vista; None si el id no existe.

    Solo toca `nombre`/`marca`/`periodo`/`config`. `config` (si viene) se serializa a JSON.
    NO valida (lo hace la capa API).
    """
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_VISTA}
    if "config" in cambios:
        cambios["config"] = a_json_dict(cambios["config"])
    if not cambios:
        return obtener_vista(vista_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("fecha_actualizacion = ?")
    params: list[Any] = list(cambios.values())
    params.append(ahora_iso())
    params.append(vista_id)
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE vistas_metricas SET {', '.join(asignaciones)} WHERE id = ?",
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(f"{_SELECT_VISTA} WHERE id = ?", (vista_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_vista(fila) if fila is not None else None


def borrar_vista(vista_id: str) -> bool:
    """Borra una vista; True si existía, False si no."""
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM vistas_metricas WHERE id = ?", (vista_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()
