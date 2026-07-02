"""Persistencia — dominio noticias: fuentes de algoritmo (inteligencia de plataforma)."""
from __future__ import annotations

from .._comun import UTC, Any, _conectar, datetime, uuid
from ...tiempo import ahora_iso

# --- Fuentes de algoritmo (inteligencia de plataforma) --------------------- #
# Mismo patron que `fuentes_rss` pero con `plataforma`/`tipo` en vez de marca/filtros: son
# fuentes de INDUSTRIA (blogs oficiales + agregadores), no de contenido de marca.
_COLS_FUENTE_ALGO = (
    "id", "nombre", "url", "plataforma", "tipo", "activo",
    "ultima_actualizacion", "ultimo_error", "ultimo_conteo", "creado",
)
_SELECT_FUENTE_ALGO = f"SELECT {', '.join(_COLS_FUENTE_ALGO)} FROM fuentes_algoritmo"
_CAMPOS_EDITABLES_FUENTE_ALGO: tuple[str, ...] = ("nombre", "url", "plataforma", "tipo", "activo")


def _fila_a_fuente_algo(fila: Any) -> dict[str, Any]:
    """Fila de `fuentes_algoritmo` -> dict publico (sin `creado`; `activo` bool)."""
    return {
        "id": fila["id"],
        "nombre": fila["nombre"] or "",
        "url": fila["url"] or "",
        "plataforma": fila["plataforma"] or "general",
        "tipo": fila["tipo"] or "agregador",
        "activo": bool(fila["activo"]),
        "ultima_actualizacion": fila["ultima_actualizacion"] or "",
        "ultimo_error": fila["ultimo_error"] or "",
        "ultimo_conteo": int(fila["ultimo_conteo"] or 0),
    }


def listar_fuentes_algoritmo() -> list[dict[str, Any]]:
    """Fuentes de algoritmo (mas recientes primero)."""
    con = _conectar()
    try:
        filas = con.execute(
            _SELECT_FUENTE_ALGO + " ORDER BY creado DESC, id DESC"
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_fuente_algo(f) for f in filas]


def contar_fuentes_algoritmo() -> int:
    """Total de fuentes de algoritmo (para decidir si cargar las fuentes por defecto)."""
    con = _conectar()
    try:
        fila = con.execute("SELECT COUNT(*) AS n FROM fuentes_algoritmo").fetchone()
    finally:
        con.close()
    return int(fila["n"]) if fila is not None else 0


def obtener_fuente_algoritmo(fuente_id: str) -> dict[str, Any] | None:
    """Una fuente de algoritmo por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(f"{_SELECT_FUENTE_ALGO} WHERE id = ?", (fuente_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_fuente_algo(fila) if fila is not None else None


def crear_fuente_algoritmo(
    nombre: str, url: str, *, plataforma: str = "general", tipo: str = "agregador"
) -> dict[str, Any]:
    """Crea una fuente de algoritmo (activa, salud vacia) y la devuelve."""
    ahora = datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="microseconds")
    fila = {
        "id": uuid.uuid4().hex[:12],
        "nombre": nombre or "",
        "url": url or "",
        "plataforma": plataforma or "general",
        "tipo": tipo or "agregador",
        "activo": 1,
        "ultima_actualizacion": "",
        "ultimo_error": "",
        "ultimo_conteo": 0,
        "creado": ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_FUENTE_ALGO)
        con.execute(
            f"INSERT INTO fuentes_algoritmo ({', '.join(_COLS_FUENTE_ALGO)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_FUENTE_ALGO),
        )
        con.commit()
    finally:
        con.close()
    return obtener_fuente_algoritmo(fila["id"]) or _fila_a_fuente_algo(fila)


def actualizar_fuente_algoritmo(
    fuente_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente una fuente (nombre/url/plataforma/tipo/activo)."""
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_FUENTE_ALGO}
    if "activo" in cambios:
        cambios["activo"] = 1 if cambios["activo"] else 0
    if not cambios:
        return obtener_fuente_algoritmo(fuente_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    params: list[Any] = [*cambios.values(), fuente_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE fuentes_algoritmo SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
    finally:
        con.close()
    return obtener_fuente_algoritmo(fuente_id)


def registrar_salud_fuente_algoritmo(fuente_id: str, *, conteo: int, error: str = "") -> None:
    """Anota la salud de una fuente de algoritmo (instante UTC + conteo + error).

    Canon UTC sin offset (`tiempo.ahora_iso`), unificado con el resto de columnas de salud.
    """
    con = _conectar()
    try:
        con.execute(
            "UPDATE fuentes_algoritmo SET ultima_actualizacion = ?, ultimo_conteo = ?, "
            "ultimo_error = ? WHERE id = ?",
            (ahora_iso(), int(conteo), error or "", fuente_id),
        )
        con.commit()
    finally:
        con.close()


def borrar_fuente_algoritmo(fuente_id: str) -> bool:
    """Borra una fuente de algoritmo y sus noticias; True si existia."""
    con = _conectar()
    try:
        con.execute("DELETE FROM noticias_algoritmo WHERE fuente_id = ?", (fuente_id,))
        cur = con.execute("DELETE FROM fuentes_algoritmo WHERE id = ?", (fuente_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()
