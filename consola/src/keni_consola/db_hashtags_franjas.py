"""Persistencia — dominio hashtags_franjas. Implementación de db.py (ver barrel `db.py`)."""
from __future__ import annotations

from ._db_comun import (
    Any,
    _conectar,
    datetime,
    json,
    uuid,
)

# --- Grupos de hashtags ---------------------------------------------------- #
# `hashtags` se almacena como JSON serializado; el dict publico lo devuelve como lista de
# strings (paridad con `ficheros._parsear_grupo`, que NO incluye `creado`/`fecha_creacion`).
_COLS_GRUPO_HASHTAGS = ("id", "nombre", "marca", "hashtags", "creado")
_SELECT_GRUPO_HASHTAGS = f"SELECT {', '.join(_COLS_GRUPO_HASHTAGS)} FROM grupos_hashtags"


def _normalizar_hashtags(valor: Any) -> list[str]:
    """Lista de strings desde una lista o un JSON serializado (degrada a [])."""
    if isinstance(valor, str):
        try:
            valor = json.loads(valor) if valor.strip() else []
        except (ValueError, TypeError):
            return []
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
                json.dumps(tags, ensure_ascii=False),
                datetime.now().isoformat(timespec="seconds"),
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
        cambios["hashtags"] = json.dumps(
            _normalizar_hashtags(cambios["hashtags"]), ensure_ascii=False
        )
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
_COLS_FRANJA_EDIT = ("id", "marca", "red", "dia_semana", "hora")
_SELECT_FRANJA_EDIT = f"SELECT {', '.join(_COLS_FRANJA_EDIT)} FROM franjas_editoriales"


def _fila_a_franja(fila: Any) -> dict[str, Any]:
    """Fila de `franjas_editoriales` -> dict publico."""
    return {
        "id": fila["id"],
        "marca": fila["marca"] or "",
        "red": fila["red"] or "",
        "dia_semana": int(fila["dia_semana"] or 0),
        "hora": fila["hora"] or "",
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
    dia_semana: int, hora: str, marca: str = "", red: str = ""
) -> dict[str, Any]:
    """Crea una franja editorial y la devuelve."""
    franja = {
        "id": uuid.uuid4().hex[:12],
        "marca": marca or "",
        "red": red or "",
        "dia_semana": int(dia_semana),
        "hora": hora or "",
    }
    con = _conectar()
    try:
        # ON CONFLICT (marca, red, dia_semana, hora) DO NOTHING: idempotente frente a un alta
        # repetida de la misma franja (mismo patron que `rota_franjas`). Requiere el indice
        # unico `idx_franjas_editoriales_uniq` (lo crea `_crear_indices_unicos_idempotencia`);
        # PRECONDICION: una BD con duplicados previos impide crearlo -> limpiar antes.
        con.execute(
            "INSERT INTO franjas_editoriales (id, marca, red, dia_semana, hora) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT (marca, red, dia_semana, hora) DO NOTHING",
            (franja["id"], franja["marca"], franja["red"], franja["dia_semana"], franja["hora"]),
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



# --------------------------------------------------------------------------- #
# Cadencias por (marca?, red?): scheduling por MARGEN entre posts               #
# --------------------------------------------------------------------------- #

_COLS_CADENCIA = ("id", "marca", "red", "margen_min", "hora_inicio", "hora_fin", "dias", "activo")
_SELECT_CADENCIA = f"SELECT {', '.join(_COLS_CADENCIA)} FROM cadencias"


def _fila_a_cadencia(fila: Any) -> dict[str, Any]:
    """Fila de `cadencias` -> dict publico (`dias` como lista de int, `activo` bool)."""
    crudo = fila["dias"] or ""
    dias = [int(p) for p in crudo.split(",") if p.strip() != ""]
    return {
        "id": fila["id"],
        "marca": fila["marca"] or "",
        "red": fila["red"] or "",
        "margen_min": int(fila["margen_min"] or 0),
        "hora_inicio": fila["hora_inicio"] or "",
        "hora_fin": fila["hora_fin"] or "",
        "dias": dias,
        "activo": bool(fila["activo"]),
    }


def listar_cadencias() -> list[dict[str, Any]]:
    """Todas las cadencias, ordenadas por marca/red/id (determinista)."""
    con = _conectar()
    try:
        filas = con.execute(
            f"{_SELECT_CADENCIA} ORDER BY marca ASC, red ASC, id ASC"
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_cadencia(f) for f in filas]


def guardar_cadencia(
    *,
    marca: str,
    red: str,
    margen_min: int,
    hora_inicio: str,
    hora_fin: str,
    dias: list[int],
    activo: bool,
) -> dict[str, Any]:
    """UPSERT de la cadencia de (marca, red) (UNIQUE). Devuelve la fila resultante."""
    dias_csv = ",".join(str(int(d)) for d in dias)
    con = _conectar()
    try:
        con.execute(
            "INSERT INTO cadencias (id, marca, red, margen_min, hora_inicio, hora_fin, dias, activo) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (marca, red) DO UPDATE SET "
            "margen_min=excluded.margen_min, hora_inicio=excluded.hora_inicio, "
            "hora_fin=excluded.hora_fin, dias=excluded.dias, activo=excluded.activo",
            (
                uuid.uuid4().hex[:12],
                marca or "",
                red or "",
                int(margen_min),
                hora_inicio,
                hora_fin,
                dias_csv,
                1 if activo else 0,
            ),
        )
        con.commit()
        fila = con.execute(
            f"{_SELECT_CADENCIA} WHERE marca = ? AND red = ?", (marca or "", red or "")
        ).fetchone()
    finally:
        con.close()
    return _fila_a_cadencia(fila)


def borrar_cadencia(cadencia_id: str) -> bool:
    """Borra una cadencia; True si existia, False si no."""
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM cadencias WHERE id = ?", (cadencia_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()
