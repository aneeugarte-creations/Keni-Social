"""Persistencia — dominio noticias: noticias de algoritmo (items ingeridos + clasificados)."""
from __future__ import annotations

from .._comun import UTC, Any, _conectar, datetime, json, uuid

# --- Noticias de algoritmo (items ingeridos + clasificados) ---------------- #
_COLS_NOTICIA_ALGO = (
    "id", "fuente_id", "fuente_nombre", "plataforma", "tipo", "titulo", "resumen",
    "enlace", "fecha", "clave", "importancia", "nivel", "senales", "es_cambio",
    "aplicada", "archivada", "sugerida", "creado",
)
_SELECT_NOTICIA_ALGO = f"SELECT {', '.join(_COLS_NOTICIA_ALGO)} FROM noticias_algoritmo"


def _fila_a_noticia_algo(fila: Any) -> dict[str, Any]:
    """Fila de `noticias_algoritmo` -> dict publico (`senales` como lista; flags bool)."""
    try:
        senales = json.loads(fila["senales"] or "[]")
    except (json.JSONDecodeError, ValueError, TypeError):
        senales = []
    return {
        "id": fila["id"],
        "fuente_id": fila["fuente_id"] or "",
        "fuente_nombre": fila["fuente_nombre"] or "",
        "plataforma": fila["plataforma"] or "general",
        "tipo": fila["tipo"] or "agregador",
        "titulo": fila["titulo"] or "",
        "resumen": fila["resumen"] or "",
        "enlace": fila["enlace"] or "",
        "fecha": fila["fecha"] or "",
        "clave": fila["clave"] or "",
        "importancia": int(fila["importancia"] or 0),
        "nivel": fila["nivel"] or "baja",
        "senales": senales if isinstance(senales, list) else [],
        "es_cambio": bool(fila["es_cambio"]),
        "aplicada": bool(fila["aplicada"]),
        "archivada": bool(fila["archivada"]),
        "sugerida": bool(fila["sugerida"]),
        "creado": fila["creado"] or "",
    }


def guardar_noticia_algoritmo(noticia: dict[str, Any]) -> str:
    """Inserta o ACTUALIZA una noticia clasificada (dedup por fuente_id+clave).

    Recibe una noticia YA clasificada (la clasificacion vive en `algoritmos.py`, no aqui).
    Si ya existe (misma fuente+clave) refresca la clasificacion y los textos, pero PRESERVA
    `id`/`creado` y las marcas humanas (`aplicada`/`archivada`). Devuelve "insertada" o
    "actualizada". Exige `clave` no vacia (sin identidad estable no se puede deduplicar)."""
    clave = (noticia.get("clave") or "").strip()
    fuente_id = noticia.get("fuente_id") or ""
    if not clave:
        return "omitida"
    senales = noticia.get("senales") or []
    senales_json = json.dumps(senales) if isinstance(senales, list) else "[]"
    con = _conectar()
    try:
        existente = con.execute(
            "SELECT id FROM noticias_algoritmo WHERE fuente_id = ? AND clave = ?",
            (fuente_id, clave),
        ).fetchone()
        if existente is not None:
            con.execute(
                "UPDATE noticias_algoritmo SET fuente_nombre = ?, plataforma = ?, tipo = ?, "
                "titulo = ?, resumen = ?, enlace = ?, fecha = ?, importancia = ?, nivel = ?, "
                "senales = ?, es_cambio = ? WHERE id = ?",
                (
                    noticia.get("fuente_nombre") or "",
                    noticia.get("plataforma") or "general",
                    noticia.get("tipo") or "agregador",
                    noticia.get("titulo") or "",
                    noticia.get("resumen") or "",
                    noticia.get("enlace") or "",
                    noticia.get("fecha") or "",
                    int(noticia.get("importancia") or 0),
                    noticia.get("nivel") or "baja",
                    senales_json,
                    1 if noticia.get("es_cambio") else 0,
                    existente["id"],
                ),
            )
            con.commit()
            return "actualizada"
        fila = {
            "id": uuid.uuid4().hex[:12],
            "fuente_id": fuente_id,
            "fuente_nombre": noticia.get("fuente_nombre") or "",
            "plataforma": noticia.get("plataforma") or "general",
            "tipo": noticia.get("tipo") or "agregador",
            "titulo": noticia.get("titulo") or "",
            "resumen": noticia.get("resumen") or "",
            "enlace": noticia.get("enlace") or "",
            "fecha": noticia.get("fecha") or "",
            "clave": clave,
            "importancia": int(noticia.get("importancia") or 0),
            "nivel": noticia.get("nivel") or "baja",
            "senales": senales_json,
            "es_cambio": 1 if noticia.get("es_cambio") else 0,
            "aplicada": 0,
            "archivada": 0,
            "sugerida": 0,
            "creado": datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="microseconds"),
        }
        marcadores = ", ".join("?" for _ in _COLS_NOTICIA_ALGO)
        con.execute(
            f"INSERT INTO noticias_algoritmo ({', '.join(_COLS_NOTICIA_ALGO)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_NOTICIA_ALGO),
        )
        con.commit()
        return "insertada"
    finally:
        con.close()


def listar_noticias_algoritmo(
    *,
    plataforma: str | None = None,
    nivel: str | None = None,
    solo_cambios: bool = False,
    solo_no_sugeridas: bool = False,
    incluir_archivadas: bool = False,
    limite: int | None = None,
) -> list[dict[str, Any]]:
    """Noticias de algoritmo ordenadas por importancia (luego fecha, luego ingesta)."""
    sql = _SELECT_NOTICIA_ALGO
    condiciones: list[str] = []
    params: list[Any] = []
    if not incluir_archivadas:
        condiciones.append("archivada = 0")
    if plataforma:
        condiciones.append("plataforma = ?")
        params.append(plataforma)
    if nivel:
        condiciones.append("nivel = ?")
        params.append(nivel)
    if solo_cambios:
        condiciones.append("es_cambio = 1")
    if solo_no_sugeridas:
        condiciones.append("sugerida = 0")
    if condiciones:
        sql += " WHERE " + " AND ".join(condiciones)
    sql += " ORDER BY importancia DESC, fecha DESC, creado DESC, id DESC"
    if limite is not None:
        sql += " LIMIT ?"
        params.append(int(limite))
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()  # noqa: S608 -- condiciones de allowlist
    finally:
        con.close()
    return [_fila_a_noticia_algo(f) for f in filas]


def obtener_noticia_algoritmo(noticia_id: str) -> dict[str, Any] | None:
    """Una noticia de algoritmo por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(f"{_SELECT_NOTICIA_ALGO} WHERE id = ?", (noticia_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_noticia_algo(fila) if fila is not None else None


def marcar_noticia_algoritmo(
    noticia_id: str,
    *,
    aplicada: bool | None = None,
    archivada: bool | None = None,
    sugerida: bool | None = None,
) -> dict[str, Any] | None:
    """Marca una noticia como aplicada-a-texto / archivada / ya-sugerida (None si no existe)."""
    cambios: dict[str, Any] = {}
    if aplicada is not None:
        cambios["aplicada"] = 1 if aplicada else 0
    if archivada is not None:
        cambios["archivada"] = 1 if archivada else 0
    if sugerida is not None:
        cambios["sugerida"] = 1 if sugerida else 0
    if not cambios:
        return obtener_noticia_algoritmo(noticia_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    params: list[Any] = [*cambios.values(), noticia_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE noticias_algoritmo SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
    finally:
        con.close()
    return obtener_noticia_algoritmo(noticia_id)
