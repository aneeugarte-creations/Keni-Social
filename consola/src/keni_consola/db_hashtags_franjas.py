"""Persistencia — dominio hashtags_franjas. Implementación de db.py (ver barrel `db.py`)."""
from __future__ import annotations

from ._db_comun import (
    Any,
    _conectar,
    uuid,
)
from ._db_json import a_json_lista, de_json_lista
from .tiempo import ahora_iso

# --- Grupos de hashtags ---------------------------------------------------- #
# `hashtags` se almacena como JSON serializado; el dict publico lo devuelve como lista de
# strings (paridad con `ficheros._parsear_grupo`, que NO incluye `creado`/`fecha_creacion`).
_COLS_GRUPO_HASHTAGS = ("id", "nombre", "marca", "hashtags", "creado")
_SELECT_GRUPO_HASHTAGS = f"SELECT {', '.join(_COLS_GRUPO_HASHTAGS)} FROM grupos_hashtags"


def _normalizar_hashtags(valor: Any) -> list[str]:
    """Lista de strings desde una lista o un JSON serializado (degrada a [])."""
    if isinstance(valor, str):
        valor = de_json_lista(valor)
    if not isinstance(valor, list):
        return []
    return [t for t in valor if isinstance(t, str)]


def _fila_a_grupo_hashtags(fila: Any) -> dict[str, Any]:
    """Fila de `grupos_hashtags` -> dict publico (`hashtags` lista; sin `creado`)."""
    return {
        "id": fila["id"],
        "nombre": fila["nombre"] or "",
        "marca": fila["marca"] or "",
        "hashtags": _normalizar_hashtags(fila["hashtags"]),
    }


def listar_grupos_hashtags(
    *, limite: int | None = None, desplazamiento: int | None = None
) -> list[dict[str, Any]]:
    """Grupos de hashtags (mas recientes primero), con paginacion opcional."""
    sql = _SELECT_GRUPO_HASHTAGS + " ORDER BY creado DESC, id DESC"
    params: list[Any] = []
    if limite is not None:
        sql += " LIMIT ?"
        params.append(int(limite))
    if desplazamiento:
        sql += " OFFSET ?"
        params.append(int(desplazamiento))
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_grupo_hashtags(f) for f in filas]


def contar_grupos_hashtags() -> int:
    """Total de grupos de hashtags (para el `total` de paginacion)."""
    con = _conectar()
    try:
        fila = con.execute("SELECT COUNT(*) AS n FROM grupos_hashtags").fetchone()
    finally:
        con.close()
    return int(fila["n"]) if fila is not None else 0


def obtener_grupo_hashtags(grupo_id: str) -> dict[str, Any] | None:
    """Un grupo de hashtags por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_GRUPO_HASHTAGS} WHERE id = ?", (grupo_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_grupo_hashtags(fila) if fila is not None else None


def crear_grupo_hashtags(
    nombre: str, marca: str = "", hashtags: list[str] | None = None
) -> dict[str, Any]:
    """Crea un grupo de hashtags y lo devuelve."""
    tags = _normalizar_hashtags(hashtags or [])
    grupo_id = uuid.uuid4().hex[:12]
    con = _conectar()
    try:
        # ON CONFLICT (nombre, marca) DO NOTHING: idempotente frente a un alta repetida del
        # mismo grupo en la misma marca (mismo patron que `rota_franjas`). Requiere el indice
        # unico `idx_grupos_hashtags_uniq` (lo crea `_crear_indices_unicos_idempotencia`);
        # PRECONDICION: una BD con duplicados previos impide crearlo -> limpiar antes.
        con.execute(
            "INSERT INTO grupos_hashtags (id, nombre, marca, hashtags, creado) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT (nombre, marca) DO NOTHING",
            (
                grupo_id,
                nombre or "",
                marca or "",
                a_json_lista(tags),
                ahora_iso(),
            ),
        )
        con.commit()
    finally:
        con.close()
    return {"id": grupo_id, "nombre": nombre or "", "marca": marca or "", "hashtags": tags}


def actualizar_grupo_hashtags(
    grupo_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente un grupo (nombre/marca/hashtags); None si no existe."""
    editables = ("nombre", "marca", "hashtags")
    cambios = {k: v for k, v in campos.items() if k in editables}
    if "hashtags" in cambios:
        cambios["hashtags"] = a_json_lista(_normalizar_hashtags(cambios["hashtags"]))
    if not cambios:
        return obtener_grupo_hashtags(grupo_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    params: list[Any] = [*cambios.values(), grupo_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE grupos_hashtags SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
    finally:
        con.close()
    return obtener_grupo_hashtags(grupo_id)


def borrar_grupo_hashtags(grupo_id: str) -> bool:
    """Borra un grupo de hashtags; True si existia, False si no."""
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM grupos_hashtags WHERE id = ?", (grupo_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()



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
