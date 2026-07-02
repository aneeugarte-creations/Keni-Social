"""Persistencia — dominio editor: motor de video (composiciones + subtítulos). Ver barrel `db.py`."""
from __future__ import annotations

from ...tiempo import ahora_iso
from ._comun import Any, _conectar, uuid

# --------------------------------------------------------------------------- #
# Motor de video: composiciones + subtitulos (Ola VIDEO)                        #
# --------------------------------------------------------------------------- #

# Estados validos de una composicion: 'borrador' (en edicion) | 'listo' (lista para producir).
ESTADOS_VIDEO_COMPOSICION = ("borrador", "listo")

_COLS_VIDEO_COMPOSICIONES = (
    "id",
    "publicacion_id",
    "marca",
    "titulo",
    "estado",
    "documento",
    "creado",
    "actualizado",
)
_SELECT_VIDEO_COMPOSICIONES = (
    f"SELECT {', '.join(_COLS_VIDEO_COMPOSICIONES)} FROM video_composiciones"
)
_CAMPOS_EDITABLES_VIDEO_COMPOSICIONES: tuple[str, ...] = (
    "publicacion_id",
    "marca",
    "titulo",
    "estado",
    "documento",
)


def _fila_a_video_composicion(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `video_composiciones` en dict (con defaults defensivos)."""
    item: dict[str, Any] = {col: fila[col] for col in _COLS_VIDEO_COMPOSICIONES}
    item["documento"] = fila["documento"] or "{}"
    item["titulo"] = fila["titulo"] or ""
    item["estado"] = fila["estado"] if fila["estado"] in ESTADOS_VIDEO_COMPOSICION else "borrador"
    return item


def crear_video_composicion(
    *,
    marca: str,
    documento: str = "{}",
    publicacion_id: str = "",
    titulo: str = "",
    estado: str = "borrador",
    id: str = "",
    creado: str = "",
    actualizado: str = "",
) -> dict[str, Any]:
    """Crea una composicion de video y la devuelve. NO valida el documento (lo hace la API/shared)."""
    ahora = ahora_iso()
    fila = {
        "id": id or uuid.uuid4().hex[:12],
        "publicacion_id": publicacion_id or "",
        "marca": marca or "",
        "titulo": titulo or "",
        "estado": estado if estado in ESTADOS_VIDEO_COMPOSICION else "borrador",
        "documento": documento or "{}",
        "creado": creado or ahora,
        "actualizado": actualizado or ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_VIDEO_COMPOSICIONES)
        con.execute(
            f"INSERT INTO video_composiciones ({', '.join(_COLS_VIDEO_COMPOSICIONES)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_VIDEO_COMPOSICIONES),
        )
        con.commit()
    finally:
        con.close()
    return _fila_a_video_composicion(fila)


def listar_video_composiciones(
    *, marca: str | None = None, publicacion_id: str | None = None
) -> list[dict[str, Any]]:
    """Composiciones de video, filtros combinables (AND). Mas recientes primero."""
    clausulas: list[str] = []
    params: list[Any] = []
    if marca:
        clausulas.append("marca = ?")
        params.append(marca)
    if publicacion_id:
        clausulas.append("publicacion_id = ?")
        params.append(publicacion_id)
    sql = _SELECT_VIDEO_COMPOSICIONES
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY creado DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_video_composicion(f) for f in filas]


def obtener_video_composicion(composicion_id: str) -> dict[str, Any] | None:
    """Una composicion de video por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_VIDEO_COMPOSICIONES} WHERE id = ?", (composicion_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_video_composicion(fila) if fila is not None else None


def actualizar_video_composicion(composicion_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Edita parcialmente; None si el id no existe. Filtra a la lista blanca."""
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_VIDEO_COMPOSICIONES}
    # `estado` fuera del enum se descarta (no rompe; conserva el anterior), igual que subtitulos.
    if "estado" in cambios and cambios["estado"] not in ESTADOS_VIDEO_COMPOSICION:
        del cambios["estado"]
    if not cambios:
        return obtener_video_composicion(composicion_id)
    ahora = ahora_iso()
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, composicion_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE video_composiciones SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_VIDEO_COMPOSICIONES} WHERE id = ?", (composicion_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_video_composicion(fila) if fila is not None else None


def borrar_video_composicion(composicion_id: str) -> bool:
    """Borra una composicion de video y sus subtitulos asociados; True si existia, False si no.

    `video_subtitulos` no tiene FK declarada (mismo estilo que el resto del esquema), asi que la
    limpieza de la pista de subtitulos es explicita (borrado en cascada manual).
    """
    con = _conectar()
    try:
        con.execute(
            "DELETE FROM video_subtitulos WHERE composicion_id = ?", (composicion_id,)
        )
        cur = con.execute("DELETE FROM video_composiciones WHERE id = ?", (composicion_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# Estados validos de un subtitulo de video (contrato; ver 08-video-engine.md).
ESTADOS_VIDEO_SUBTITULO = ("pendiente", "transcrito", "editado", "listo")

_COLS_VIDEO_SUBTITULOS = (
    "id",
    "composicion_id",
    "idioma",
    "estado",
    "segmentos",
    "ass",
    "transcrito_en",
    "actualizado",
)
_SELECT_VIDEO_SUBTITULOS = f"SELECT {', '.join(_COLS_VIDEO_SUBTITULOS)} FROM video_subtitulos"
_CAMPOS_EDITABLES_VIDEO_SUBTITULOS: tuple[str, ...] = (
    "idioma",
    "estado",
    "segmentos",
    "ass",
    "transcrito_en",
)


def _fila_a_video_subtitulo(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `video_subtitulos` en dict (con defaults defensivos)."""
    item: dict[str, Any] = {col: fila[col] for col in _COLS_VIDEO_SUBTITULOS}
    item["idioma"] = fila["idioma"] or "es-MX"
    item["estado"] = fila["estado"] if fila["estado"] in ESTADOS_VIDEO_SUBTITULO else "pendiente"
    return item


def crear_video_subtitulo(
    *,
    composicion_id: str,
    idioma: str = "es-MX",
    estado: str = "pendiente",
    segmentos: str = "",
    ass: str = "",
    transcrito_en: str = "",
    id: str = "",
    actualizado: str = "",
) -> dict[str, Any]:
    """Crea una fila de subtitulos para una composicion y la devuelve."""
    ahora = ahora_iso()
    fila = {
        "id": id or uuid.uuid4().hex[:12],
        "composicion_id": composicion_id or "",
        "idioma": idioma or "es-MX",
        "estado": estado if estado in ESTADOS_VIDEO_SUBTITULO else "pendiente",
        "segmentos": segmentos or "",
        "ass": ass or "",
        "transcrito_en": transcrito_en or "",
        "actualizado": actualizado or ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_VIDEO_SUBTITULOS)
        con.execute(
            f"INSERT INTO video_subtitulos ({', '.join(_COLS_VIDEO_SUBTITULOS)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_VIDEO_SUBTITULOS),
        )
        con.commit()
    finally:
        con.close()
    return _fila_a_video_subtitulo(fila)


def listar_video_subtitulos(
    *, composicion_id: str | None = None, estado: str | None = None
) -> list[dict[str, Any]]:
    """Subtitulos de video, filtros combinables (AND). Mas recientes primero."""
    clausulas: list[str] = []
    params: list[Any] = []
    if composicion_id:
        clausulas.append("composicion_id = ?")
        params.append(composicion_id)
    if estado:
        clausulas.append("estado = ?")
        params.append(estado)
    sql = _SELECT_VIDEO_SUBTITULOS
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY actualizado DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_video_subtitulo(f) for f in filas]


def obtener_video_subtitulo(subtitulo_id: str) -> dict[str, Any] | None:
    """Un subtitulo de video por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_VIDEO_SUBTITULOS} WHERE id = ?", (subtitulo_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_video_subtitulo(fila) if fila is not None else None


def actualizar_video_subtitulo(subtitulo_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Edita parcialmente; None si el id no existe. Filtra a la lista blanca."""
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_VIDEO_SUBTITULOS}
    if "estado" in cambios and cambios["estado"] not in ESTADOS_VIDEO_SUBTITULO:
        cambios.pop("estado")
    if not cambios:
        return obtener_video_subtitulo(subtitulo_id)
    ahora = ahora_iso()
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, subtitulo_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE video_subtitulos SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_VIDEO_SUBTITULOS} WHERE id = ?", (subtitulo_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_video_subtitulo(fila) if fila is not None else None
