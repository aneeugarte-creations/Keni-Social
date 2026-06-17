"""Persistencia — dominio editor: catálogo de ETIQUETAS de plantillas POR MARCA.

Una etiqueta es el override LEGIBLE de una categoría de plantilla (texto libre normalizado a slug
en `categoria`): renombrar una etiqueta cambia solo su rótulo visible, conserva el slug y NO mueve
plantillas. La identidad es `(marca, slug)`; `etiqueta` es el rótulo (vacío = usar el rótulo por
defecto del catálogo del frontend). Implementación de db.py (ver barrel `db.py`).
"""
from __future__ import annotations

from ..tiempo import ahora_iso
from ._comun import Any, IntegrityError, _conectar, uuid

# --------------------------------------------------------------------------- #
# Etiquetas de plantilla (catálogo de categorías editable, por marca)         #
# --------------------------------------------------------------------------- #

_COLS_ETIQUETAS_PLANTILLA = (
    "id",
    "marca",
    "slug",
    "etiqueta",
    "creado",
    "actualizado",
)
_SELECT_ETIQUETAS_PLANTILLA = (
    f"SELECT {', '.join(_COLS_ETIQUETAS_PLANTILLA)} FROM etiquetas_plantilla"
)


def _fila_a_etiqueta_plantilla(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `etiquetas_plantilla` en dict (con defaults defensivos)."""
    item: dict[str, Any] = {col: fila[col] for col in _COLS_ETIQUETAS_PLANTILLA}
    item["marca"] = fila["marca"] or ""
    item["slug"] = fila["slug"] or ""
    item["etiqueta"] = fila["etiqueta"] or ""
    return item


def listar_etiquetas_plantilla(*, marca: str | None = None) -> list[dict[str, Any]]:
    """Etiquetas del catálogo, filtrables por marca. Orden estable por marca y slug."""
    sql = _SELECT_ETIQUETAS_PLANTILLA
    params: list[Any] = []
    if marca:
        sql += " WHERE marca = ?"
        params.append(marca)
    sql += " ORDER BY marca ASC, slug ASC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_etiqueta_plantilla(f) for f in filas]


def upsert_etiqueta_plantilla(*, marca: str, slug: str, etiqueta: str) -> dict[str, Any]:
    """Crea o actualiza el rótulo de la etiqueta `(marca, slug)` y la devuelve.

    Renombra el rótulo visible SIN tocar plantillas (el slug es la identidad). Idempotente por
    `(marca, slug)`: actualiza si existe, inserta si no (con reintento ante una carrera).
    """
    ahora = ahora_iso()
    con = _conectar()
    try:
        cur = con.execute(
            "UPDATE etiquetas_plantilla SET etiqueta = ?, actualizado = ? WHERE marca = ? AND slug = ?",
            (etiqueta, ahora, marca, slug),
        )
        if cur.rowcount == 0:
            try:
                con.execute(
                    f"INSERT INTO etiquetas_plantilla ({', '.join(_COLS_ETIQUETAS_PLANTILLA)}) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (uuid.uuid4().hex[:12], marca, slug, etiqueta, ahora, ahora),
                )
            except IntegrityError:
                # Carrera: otra escritura insertó `(marca, slug)` entre el UPDATE y el INSERT.
                con.execute(
                    "UPDATE etiquetas_plantilla SET etiqueta = ?, actualizado = ? WHERE marca = ? AND slug = ?",
                    (etiqueta, ahora, marca, slug),
                )
        con.commit()
        fila = con.execute(
            f"{_SELECT_ETIQUETAS_PLANTILLA} WHERE marca = ? AND slug = ?", (marca, slug)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_etiqueta_plantilla(fila)


def borrar_etiqueta_plantilla(*, marca: str, slug: str) -> bool:
    """Borra el rótulo de la etiqueta `(marca, slug)`. Devuelve si existía algo que borrar.

    No toca plantillas: si alguna sigue usando el slug, la galería la mostrará con el rótulo por
    defecto. El llamante (API) es quien decide si bloquear el borrado por estar en uso.
    """
    con = _conectar()
    try:
        cur = con.execute(
            "DELETE FROM etiquetas_plantilla WHERE marca = ? AND slug = ?", (marca, slug)
        )
        con.commit()
    finally:
        con.close()
    return (cur.rowcount or 0) > 0
