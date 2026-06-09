"""Persistencia — dominio evergreen. Implementación de db.py (ver barrel `db.py`)."""
from __future__ import annotations

from ._db_comun import (
    UTC,
    Any,
    _conectar,
    datetime,
    uuid,
)
from .tiempo import ahora_iso

# --------------------------------------------------------------------------- #
# Taller EVERGREEN / brainstorming: ideas evergreen (propuesta -> aprobada/descartada)
# --------------------------------------------------------------------------- #
# La IA PROPONE ideas evergreen; una persona las aprueba o descarta; solo para las
# aprobadas se genera la pieza (`flujo='evergreen'` en el tablero). NO valida aqui
# (lo hace `api/evergreen`); este modulo es persistencia pura. Mismo patron que etiquetas.

_COLS_EVERGREEN_IDEA = (
    "id",
    "marca",
    "titulo",
    "descripcion",
    "estado",
    "origen",
    "generacion_id",
    "contenido_id",
    "creado",
    "actualizado",
)
_SELECT_EVERGREEN_IDEA = f"SELECT {', '.join(_COLS_EVERGREEN_IDEA)} FROM evergreen_ideas"
_CAMPOS_EDITABLES_EVERGREEN_IDEA: tuple[str, ...] = (
    "titulo",
    "descripcion",
    "estado",
    "contenido_id",
)


def _fila_a_evergreen_idea(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `evergreen_ideas` en dict."""
    return {col: fila[col] for col in _COLS_EVERGREEN_IDEA}


def crear_evergreen_idea(
    *,
    marca: str = "",
    titulo: str = "",
    descripcion: str = "",
    estado: str = "propuesta",
    origen: str = "ia",
    generacion_id: str = "",
    contenido_id: str = "",
    creado: str = "",
    actualizado: str = "",
    id: str = "",
) -> dict[str, Any]:
    """Inserta una idea de contenido evergreen y la devuelve. NO valida (lo hace la API)."""
    # Precisión de MICROSEGUNDOS en `creado`: el listado ordena por `creado DESC, id DESC`,
    # pero `id` es un uuid aleatorio (no monotónico), así que dos ideas creadas en el MISMO
    # segundo quedaban en orden indefinido ("recientes primero" no determinista). Los
    # microsegundos desempatan creaciones consecutivas sin añadir un campo de secuencia.
    ahora = datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="microseconds")
    fila = {
        "id": id or uuid.uuid4().hex[:12],
        "marca": marca or "",
        "titulo": titulo or "",
        "descripcion": descripcion or "",
        "estado": estado or "propuesta",
        "origen": origen or "ia",
        "generacion_id": generacion_id or "",
        "contenido_id": contenido_id or "",
        "creado": creado or ahora,
        "actualizado": actualizado or ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_EVERGREEN_IDEA)
        con.execute(
            f"INSERT INTO evergreen_ideas ({', '.join(_COLS_EVERGREEN_IDEA)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_EVERGREEN_IDEA),
        )
        con.commit()
    finally:
        con.close()
    return fila


def listar_evergreen_ideas(
    *, marca: str | None = None, estado: str | None = None
) -> list[dict[str, Any]]:
    """Lista ideas evergreen, recientes primero. Filtros opcionales por `marca`/`estado`."""
    clausulas: list[str] = []
    params: list[Any] = []
    if marca:
        clausulas.append("marca = ?")
        params.append(marca)
    if estado:
        clausulas.append("estado = ?")
        params.append(estado)
    sql = _SELECT_EVERGREEN_IDEA
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY creado DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_evergreen_idea(f) for f in filas]


def obtener_evergreen_idea(idea_id: str) -> dict[str, Any] | None:
    """Una idea evergreen por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(f"{_SELECT_EVERGREEN_IDEA} WHERE id = ?", (idea_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_evergreen_idea(fila) if fila is not None else None


def actualizar_evergreen_idea(idea_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Edita parcialmente una idea; None si no existe. Filtra a la lista blanca."""
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_EVERGREEN_IDEA}
    if not cambios:
        return obtener_evergreen_idea(idea_id)
    ahora = ahora_iso()
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, idea_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE evergreen_ideas SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(f"{_SELECT_EVERGREEN_IDEA} WHERE id = ?", (idea_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_evergreen_idea(fila) if fila is not None else None


def borrar_evergreen_idea(idea_id: str) -> bool:
    """Borra una idea evergreen. True si existia."""
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM evergreen_ideas WHERE id = ?", (idea_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def asignar_etiqueta(contenido_id: str, etiqueta_id: str) -> None:
    """Asigna una etiqueta a un contenido (idempotente: ignora si ya existe)."""
    con = _conectar()
    try:
        con.execute(
            "INSERT INTO contenido_etiquetas (contenido_id, etiqueta_id) VALUES (?, ?) "
            "ON CONFLICT DO NOTHING",
            (contenido_id, etiqueta_id),
        )
        con.commit()
    finally:
        con.close()


def quitar_etiqueta(contenido_id: str, etiqueta_id: str) -> bool:
    """Quita una etiqueta de un contenido. True si estaba asignada."""
    con = _conectar()
    try:
        cur = con.execute(
            "DELETE FROM contenido_etiquetas WHERE contenido_id = ? AND etiqueta_id = ?",
            (contenido_id, etiqueta_id),
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def etiquetas_por_contenido() -> dict[str, list[str]]:
    """Mapa `contenido_id -> [etiqueta_id, ...]` de TODAS las asignaciones (una lectura)."""
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT contenido_id, etiqueta_id FROM contenido_etiquetas"
        ).fetchall()
    finally:
        con.close()
    mapa: dict[str, list[str]] = {}
    for f in filas:
        mapa.setdefault(f["contenido_id"], []).append(f["etiqueta_id"])
    return mapa


def ids_contenido_con_etiqueta(etiqueta_id: str) -> set[str]:
    """Ids de contenido que llevan la etiqueta dada (para filtrar el tablero)."""
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT contenido_id FROM contenido_etiquetas WHERE etiqueta_id = ?",
            (etiqueta_id,),
        ).fetchall()
    finally:
        con.close()
    return {f["contenido_id"] for f in filas}
