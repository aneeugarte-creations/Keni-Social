"""Persistencia — dominio editor: catálogo de media. Implementación de db.py (ver barrel `db.py`)."""
from __future__ import annotations

from ..tiempo import ahora_iso
from ._comun import Any, _conectar, uuid

# --------------------------------------------------------------------------- #
# Texto de MEDIOS interna (ola "activos")                                  #
# --------------------------------------------------------------------------- #
# Tabla `catalogo_media`: cataloga objetos del almacen de media (`media.py`) por su
# nombre (`objeto`, uuid+ext del servidor) con metadatos editoriales y etiquetas (JSON de
# strings). El binario lo guarda/sirve `media.py`; aqui solo el catalogo reutilizable.

_COLS_CATALOGO_MEDIA = (
    "id",
    "objeto",
    "tipo",
    "titulo",
    "descripcion",
    "marca",
    "etiquetas",
    "credito",
    "aprobado",
    "fuente",
    "grupo",
    "autor_id",
    "autor_nombre",
    "creado",
    "actualizado",
)
_SELECT_CATALOGO_MEDIA = (
    f"SELECT {', '.join(_COLS_CATALOGO_MEDIA)} FROM catalogo_media"
)

# Campos editables via `actualizar_media_catalogo` (lista blanca). `id`, `objeto`,
# `autor_*`, `creado` y `actualizado` no son editables (el objeto NO se reasigna; se
# cataloga uno nuevo si cambia el binario).
_CAMPOS_EDITABLES_CATALOGO_MEDIA: tuple[str, ...] = (
    "tipo",
    "titulo",
    "descripcion",
    "marca",
    "etiquetas",
    "credito",
    "aprobado",
    "fuente",
    "grupo",
)


def _fila_a_media_catalogo(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `catalogo_media` en dict (con defaults defensivos)."""
    item: dict[str, Any] = {col: fila[col] for col in _COLS_CATALOGO_MEDIA}
    item["aprobado"] = bool(fila["aprobado"])
    item["etiquetas"] = fila["etiquetas"] or "[]"
    item["tipo"] = fila["tipo"] or "imagen"
    item["fuente"] = fila["fuente"] or ""
    item["grupo"] = fila["grupo"] or ""
    return item


def crear_media_catalogo(
    *,
    objeto: str,
    tipo: str = "imagen",
    titulo: str = "",
    descripcion: str = "",
    marca: str = "",
    etiquetas: str = "[]",
    credito: str = "",
    aprobado: bool = True,
    fuente: str = "",
    grupo: str = "",
    autor: dict[str, str] | None = None,
    id: str = "",
    creado: str = "",
    actualizado: str = "",
) -> dict[str, Any]:
    """Cataloga un objeto de media en la galería y lo devuelve. NO valida (lo hace la API)."""
    autor = autor or {}
    ahora = ahora_iso()
    fila = {
        "id": id or uuid.uuid4().hex[:12],
        "objeto": objeto or "",
        "tipo": tipo or "imagen",
        "titulo": titulo or "",
        "descripcion": descripcion or "",
        "marca": marca or "",
        "etiquetas": etiquetas or "[]",
        "credito": credito or "",
        "aprobado": 1 if aprobado else 0,
        "fuente": fuente or "",
        "grupo": grupo or "",
        "autor_id": autor.get("id", "") or "",
        "autor_nombre": autor.get("usuario", "") or "",
        "creado": creado or ahora,
        "actualizado": actualizado or ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_CATALOGO_MEDIA)
        con.execute(
            f"INSERT INTO catalogo_media ({', '.join(_COLS_CATALOGO_MEDIA)}) "
            f"VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_CATALOGO_MEDIA),
        )
        con.commit()
    finally:
        con.close()
    return _fila_a_media_catalogo(fila)


def listar_media_catalogo(
    *,
    marca: str | None = None,
    tipo: str | None = None,
    fuente: str | None = None,
    grupo: str | None = None,
    solo_aprobados: bool = False,
    incluir_globales: bool = False,
) -> list[dict[str, Any]]:
    """Items de la galería de medios, filtros combinables (AND). Mas recientes primero.

    `incluir_globales` (def False): al filtrar por `marca`, suma también los artes GLOBALES
    (marca='') — "compartidos entre marcas" —, de modo que un arte global (p.ej. una foto
    generada por IA y catalogada para reutilizar) aparezca en la galería de CUALQUIER marca.
    `fuente`/`grupo` acotan a una CARPETA de la biblioteca unificada (portal|originales|
    fotografias) y a una carpeta lógica dentro de ella (p. ej. un partido).
    """
    clausulas: list[str] = []
    params: list[Any] = []
    if marca:
        if incluir_globales:
            clausulas.append("(marca = ? OR marca = '')")
        else:
            clausulas.append("marca = ?")
        params.append(marca)
    if tipo:
        clausulas.append("tipo = ?")
        params.append(tipo)
    if fuente:
        clausulas.append("fuente = ?")
        params.append(fuente)
    if grupo:
        clausulas.append("grupo = ?")
        params.append(grupo)
    if solo_aprobados:
        clausulas.append("aprobado = 1")
    sql = _SELECT_CATALOGO_MEDIA
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY creado DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_media_catalogo(f) for f in filas]


def obtener_media_catalogo(media_id: str) -> dict[str, Any] | None:
    """Un item del catálogo de medios por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_CATALOGO_MEDIA} WHERE id = ?", (media_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_media_catalogo(fila) if fila is not None else None


def existe_media_objeto(objeto: str) -> bool:
    """True si ya hay un item del catálogo catalogando ese `objeto` (UNIQUE)."""
    con = _conectar()
    try:
        fila = con.execute(
            "SELECT 1 FROM catalogo_media WHERE objeto = ?", (objeto,)
        ).fetchone()
    finally:
        con.close()
    return fila is not None


def actualizar_media_catalogo(
    media_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente; None si el id no existe. Filtra a la lista blanca."""
    cambios = {
        k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_CATALOGO_MEDIA
    }
    if "aprobado" in cambios:
        cambios["aprobado"] = 1 if cambios["aprobado"] else 0
    if not cambios:
        return obtener_media_catalogo(media_id)
    ahora = ahora_iso()
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, media_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE catalogo_media SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_CATALOGO_MEDIA} WHERE id = ?", (media_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_media_catalogo(fila) if fila is not None else None


def borrar_media_catalogo(media_id: str) -> dict[str, Any] | None:
    """Borra un item del catálogo de medios; devuelve el item borrado (para limpiar el binario) o None."""
    item = obtener_media_catalogo(media_id)
    if item is None:
        return None
    con = _conectar()
    try:
        con.execute("DELETE FROM catalogo_media WHERE id = ?", (media_id,))
        con.commit()
    finally:
        con.close()
    return item
