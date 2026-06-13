"""Persistencia — dominio noticias: sugerencias editoriales (job diario)."""
from __future__ import annotations

from .._db_comun import UTC, Any, _conectar, datetime, json, uuid

# --- Sugerencias editoriales (generadas por el job diario) ----------------- #
_COLS_SUGERENCIA_EDITORIAL = (
    "id", "plataforma", "tipo", "titulo", "detalle", "ficha_id", "noticia_ids", "estado", "creado",
)
_SELECT_SUGERENCIA_EDITORIAL = (
    f"SELECT {', '.join(_COLS_SUGERENCIA_EDITORIAL)} FROM sugerencias_editoriales"
)
ESTADOS_SUGERENCIA_EDITORIAL = ("nueva", "aplicada", "descartada")


def _fila_a_sugerencia_editorial(fila: Any) -> dict[str, Any]:
    """Fila de `sugerencias_editoriales` -> dict publico (`noticia_ids` como lista)."""
    try:
        ids = json.loads(fila["noticia_ids"] or "[]")
    except (json.JSONDecodeError, ValueError, TypeError):
        ids = []
    return {
        "id": fila["id"],
        "plataforma": fila["plataforma"] or "general",
        "tipo": fila["tipo"] or "editorial",
        "titulo": fila["titulo"] or "",
        "detalle": fila["detalle"] or "",
        "ficha_id": fila["ficha_id"] or "",
        "noticia_ids": ids if isinstance(ids, list) else [],
        "estado": fila["estado"] or "nueva",
        "creado": fila["creado"] or "",
    }


def crear_sugerencia_editorial(
    *,
    plataforma: str,
    tipo: str,
    titulo: str,
    detalle: str,
    ficha_id: str = "",
    noticia_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Crea una sugerencia editorial (estado 'nueva') y la devuelve."""
    fila = {
        "id": uuid.uuid4().hex[:12],
        "plataforma": plataforma or "general",
        "tipo": tipo or "editorial",
        "titulo": titulo or "",
        "detalle": detalle or "",
        "ficha_id": ficha_id or "",
        "noticia_ids": json.dumps(noticia_ids or []),
        "estado": "nueva",
        "creado": datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="microseconds"),
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_SUGERENCIA_EDITORIAL)
        con.execute(
            f"INSERT INTO sugerencias_editoriales ({', '.join(_COLS_SUGERENCIA_EDITORIAL)}) "
            f"VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_SUGERENCIA_EDITORIAL),
        )
        con.commit()
    finally:
        con.close()
    return obtener_sugerencia_editorial(fila["id"]) or _fila_a_sugerencia_editorial(fila)


def listar_sugerencias_editoriales(
    *, estado: str | None = None, limite: int | None = None
) -> list[dict[str, Any]]:
    """Sugerencias editoriales (mas recientes primero), filtrables por estado."""
    sql = _SELECT_SUGERENCIA_EDITORIAL
    params: list[Any] = []
    if estado:
        sql += " WHERE estado = ?"
        params.append(estado)
    sql += " ORDER BY creado DESC, id DESC"
    if limite is not None:
        sql += " LIMIT ?"
        params.append(int(limite))
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()  # noqa: S608 -- estado de allowlist
    finally:
        con.close()
    return [_fila_a_sugerencia_editorial(f) for f in filas]


def contar_sugerencias_editoriales(*, estado: str | None = None) -> int:
    """Total de sugerencias editoriales (para el contador del panel), filtrable por estado."""
    sql = "SELECT COUNT(*) AS n FROM sugerencias_editoriales"
    params: list[Any] = []
    if estado:
        sql += " WHERE estado = ?"
        params.append(estado)
    con = _conectar()
    try:
        fila = con.execute(sql, tuple(params)).fetchone()  # noqa: S608 -- estado de allowlist
    finally:
        con.close()
    return int(fila["n"]) if fila is not None else 0


def obtener_sugerencia_editorial(sugerencia_id: str) -> dict[str, Any] | None:
    """Una sugerencia editorial por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_SUGERENCIA_EDITORIAL} WHERE id = ?", (sugerencia_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_sugerencia_editorial(fila) if fila is not None else None


def actualizar_estado_sugerencia_editorial(
    sugerencia_id: str, estado: str
) -> dict[str, Any] | None:
    """Cambia el estado de una sugerencia (nueva/aplicada/descartada). None si no existe."""
    con = _conectar()
    try:
        cur = con.execute(
            "UPDATE sugerencias_editoriales SET estado = ? WHERE id = ?",
            (estado, sugerencia_id),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
    finally:
        con.close()
    return obtener_sugerencia_editorial(sugerencia_id)
