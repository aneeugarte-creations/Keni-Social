"""Persistencia — dominio sugerencias (kanban de auto-desarrollo). Implementación de db.py.

Tabla `sugerencias`: una idea/mejora/bug del equipo que recorre el kanban de
auto-desarrollo (nueva → discovery → en_cola → building → revisión → hecha). Mismo
patrón que `db_idear.py` (evergreen_ideas): persistencia PURA, sin validación (la
máquina de estados vive en `keni_consola.sugerencias`).
"""
from __future__ import annotations

from ._comun import (
    UTC,
    Any,
    _conectar,
    datetime,
    uuid,
)
from ..tiempo import ahora_iso

_COLS_SUGERENCIA = (
    "id",
    "titulo",
    "detalle",
    "categoria",
    "autor",
    "autor_id",
    "estado",
    "complejidad",
    "spec",
    "plan",
    "fase",
    "gen_id",
    "rama",
    "worktree",
    "diff_resumen",
    "coste_usd",
    "preview_listo",
    "creada",
    "actualizada",
)
_SELECT_SUGERENCIA = f"SELECT {', '.join(_COLS_SUGERENCIA)} FROM sugerencias"
# Todo lo MUTABLE: el texto que edita el equipo (titulo/detalle/categoria), el estado del
# kanban y los campos que el motor de desarrollo va rellenando (complejidad/spec/plan/fase/
# gen_id/rama/worktree/diff_resumen/coste_usd). `id`/`autor`/`autor_id`/`creada` son inmutables.
_CAMPOS_EDITABLES_SUGERENCIA: tuple[str, ...] = (
    "titulo",
    "detalle",
    "categoria",
    "estado",
    "complejidad",
    "spec",
    "plan",
    "fase",
    "gen_id",
    "rama",
    "worktree",
    "diff_resumen",
    "coste_usd",
    "preview_listo",
)


def _fila_a_sugerencia(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `sugerencias` en dict (coste_usd float, preview_listo bool)."""
    s = {col: fila[col] for col in _COLS_SUGERENCIA}
    s["coste_usd"] = float(s["coste_usd"] or 0)
    s["preview_listo"] = bool(s["preview_listo"])
    return s


def crear_sugerencia(
    *,
    titulo: str = "",
    detalle: str = "",
    categoria: str = "idea",
    autor: str = "",
    autor_id: str = "",
    estado: str = "nueva",
    complejidad: str = "",
    spec: str = "",
    plan: str = "",
    fase: str = "",
    gen_id: str = "",
    rama: str = "",
    worktree: str = "",
    diff_resumen: str = "",
    coste_usd: float = 0.0,
    creada: str = "",
    actualizada: str = "",
    id: str = "",
) -> dict[str, Any]:
    """Inserta una sugerencia y la devuelve. NO valida (lo hace `keni_consola.sugerencias`)."""
    # Precisión de MICROSEGUNDOS en `creada`: el listado ordena por `creada DESC, id DESC` e
    # `id` es un uuid aleatorio (no monotónico), así que dos sugerencias del mismo segundo
    # quedarían en orden indefinido. Los microsegundos desempatan creaciones consecutivas.
    ahora = datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="microseconds")
    fila = {
        "id": id or uuid.uuid4().hex[:12],
        "titulo": titulo or "",
        "detalle": detalle or "",
        "categoria": categoria or "idea",
        "autor": autor or "",
        "autor_id": autor_id or "",
        "estado": estado or "nueva",
        "complejidad": complejidad or "",
        "spec": spec or "",
        "plan": plan or "",
        "fase": fase or "",
        "gen_id": gen_id or "",
        "rama": rama or "",
        "worktree": worktree or "",
        "diff_resumen": diff_resumen or "",
        "coste_usd": float(coste_usd or 0),
        "preview_listo": False,
        "creada": creada or ahora,
        "actualizada": actualizada or ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_SUGERENCIA)
        con.execute(
            f"INSERT INTO sugerencias ({', '.join(_COLS_SUGERENCIA)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_SUGERENCIA),
        )
        con.commit()
    finally:
        con.close()
    return fila


def listar_sugerencias(
    *, estado: str | None = None, categoria: str | None = None, autor_id: str | None = None
) -> list[dict[str, Any]]:
    """Lista sugerencias, recientes primero. Filtros opcionales por `estado`/`categoria`/`autor_id`.

    Con `autor_id` solo devuelve las de ESE dueño (cada persona ve únicamente las suyas; el
    tablero completo es del superadmin).
    """
    clausulas: list[str] = []
    params: list[Any] = []
    if estado:
        clausulas.append("estado = ?")
        params.append(estado)
    if categoria:
        clausulas.append("categoria = ?")
        params.append(categoria)
    if autor_id is not None:
        clausulas.append("autor_id = ?")
        params.append(autor_id)
    sql = _SELECT_SUGERENCIA
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY creada DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_sugerencia(f) for f in filas]


def obtener_sugerencia(sugerencia_id: str) -> dict[str, Any] | None:
    """Una sugerencia por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_SUGERENCIA} WHERE id = ?", (sugerencia_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_sugerencia(fila) if fila is not None else None


def actualizar_sugerencia(
    sugerencia_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente una sugerencia; None si no existe. Filtra a la lista blanca."""
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_SUGERENCIA}
    if not cambios:
        return obtener_sugerencia(sugerencia_id)
    if "coste_usd" in cambios:
        cambios["coste_usd"] = float(cambios["coste_usd"] or 0)
    ahora = ahora_iso()
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizada = ?")
    params: list[Any] = [*cambios.values(), ahora, sugerencia_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE sugerencias SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_SUGERENCIA} WHERE id = ?", (sugerencia_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_sugerencia(fila) if fila is not None else None


def borrar_sugerencia(sugerencia_id: str) -> bool:
    """Borra una sugerencia. True si existía."""
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM sugerencias WHERE id = ?", (sugerencia_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()
