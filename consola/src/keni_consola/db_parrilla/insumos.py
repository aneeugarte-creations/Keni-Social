"""Persistencia — insumos del día (cajones; tablas `insumos_lote` + `insumos_item`).

Contrato: docs/maquina-contenido/01-insumos-del-dia.md. Ver barrel `db.py`."""
from __future__ import annotations

from ._comun import UTC, Any, _conectar, datetime, uuid

# --------------------------------------------------------------------------- #
# Insumos del día (cajones) — tabla `insumos_lote` + `insumos_item`            #
# Contrato: docs/maquina-contenido/01-insumos-del-dia.md                       #
# --------------------------------------------------------------------------- #

_COLS_INSUMO_LOTE = (
    "id", "fecha", "cajon", "marca", "origen_texto", "origen_archivo",
    "estado", "error", "total_items", "creado_por", "creado",
)
_SELECT_INSUMO_LOTE = f"SELECT {', '.join(_COLS_INSUMO_LOTE)} FROM insumos_lote"

_COLS_INSUMO_ITEM = (
    "id", "lote_id", "fecha", "cajon", "marca", "linea",
    "titulo", "resumen", "hora", "lugar", "estado_material",
    "tipo", "idioma", "usado", "contenido_id", "orden", "creado",
)
_SELECT_INSUMO_ITEM = f"SELECT {', '.join(_COLS_INSUMO_ITEM)} FROM insumos_item"

_CAMPOS_EDITABLES_INSUMO_ITEM: tuple[str, ...] = (
    "titulo", "resumen", "marca", "linea", "hora", "lugar", "estado_material", "tipo",
)


def _fila_a_insumo_lote(fila: Any) -> dict[str, Any]:
    """Fila de `insumos_lote` -> dict público (`usado` y enteros normalizados)."""
    return {
        "id": fila["id"],
        "fecha": fila["fecha"] or "",
        "cajon": fila["cajon"] or "",
        "marca": fila["marca"] or "",
        "origen_texto": fila["origen_texto"] or "",
        "origen_archivo": fila["origen_archivo"] or "",
        "estado": fila["estado"] or "listo",
        "error": fila["error"] or "",
        "total_items": int(fila["total_items"] or 0),
        "creado_por": fila["creado_por"] or "",
        "creado": fila["creado"] or "",
    }


def _fila_a_insumo_item(fila: Any) -> dict[str, Any]:
    """Fila de `insumos_item` -> dict público (`usado` como bool)."""
    return {
        "id": fila["id"],
        "lote_id": fila["lote_id"] or "",
        "fecha": fila["fecha"] or "",
        "cajon": fila["cajon"] or "",
        "marca": fila["marca"] or "",
        "linea": fila["linea"] or "",
        "titulo": fila["titulo"] or "",
        "resumen": fila["resumen"] or "",
        "hora": fila["hora"] or "",
        "lugar": fila["lugar"] or "",
        "estado_material": fila["estado_material"] or "",
        "tipo": fila["tipo"] or "nota",
        "idioma": fila["idioma"] or "es",
        "usado": bool(fila["usado"]),
        "contenido_id": fila["contenido_id"] or "",
        "orden": int(fila["orden"] or 0),
        "creado": fila["creado"] or "",
    }


def crear_insumo_lote(
    *,
    fecha: str,
    cajon: str,
    marca: str = "",
    origen_texto: str = "",
    origen_archivo: str = "",
    estado: str = "listo",
    error: str = "",
    total_items: int = 0,
    creado_por: str = "",
) -> dict[str, Any]:
    """Crea un lote de insumos y lo devuelve."""
    ahora = datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="microseconds")
    lote_id = uuid.uuid4().hex[:16]
    fila = {
        "id": lote_id,
        "fecha": fecha or "",
        "cajon": cajon or "",
        "marca": marca or "",
        "origen_texto": origen_texto or "",
        "origen_archivo": origen_archivo or "",
        "estado": estado or "listo",
        "error": error or "",
        "total_items": int(total_items),
        "creado_por": creado_por or "",
        "creado": ahora,
    }
    marcadores = ", ".join("?" for _ in _COLS_INSUMO_LOTE)
    con = _conectar()
    try:
        con.execute(
            f"INSERT INTO insumos_lote ({', '.join(_COLS_INSUMO_LOTE)}) VALUES ({marcadores})",
            tuple(fila[c] for c in _COLS_INSUMO_LOTE),
        )
        con.commit()
    finally:
        con.close()
    return obtener_insumo_lote(lote_id) or _fila_a_insumo_lote(fila)


def actualizar_insumo_lote(lote_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Edita parcialmente un lote (estado/error/total_items). None si no existe."""
    permitidos = {"estado", "error", "total_items"}
    cambios = {k: v for k, v in campos.items() if k in permitidos}
    if not cambios:
        return obtener_insumo_lote(lote_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    params: list[Any] = [*cambios.values(), lote_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE insumos_lote SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
    finally:
        con.close()
    return obtener_insumo_lote(lote_id)


def obtener_insumo_lote(lote_id: str) -> dict[str, Any] | None:
    """Un lote por id; None si no existe."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_INSUMO_LOTE} WHERE id = ?", (lote_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_insumo_lote(fila) if fila is not None else None


def borrar_insumo_lote(lote_id: str) -> bool:
    """Borra el lote y todos sus ítems; True si existía, False si no."""
    con = _conectar()
    try:
        con.execute("DELETE FROM insumos_item WHERE lote_id = ?", (lote_id,))
        cur = con.execute("DELETE FROM insumos_lote WHERE id = ?", (lote_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def sanear_lotes_parseando_huerfanos(antes_de: str) -> int:
    """Reconcilia lotes ZOMBI atascados en `parseando` creados antes de `antes_de` (ISO).

    Un lote nace `parseando` y solo pasa a `listo`/`error` cuando el worker termina su
    callback (inserta ítems y actualiza el lote). Si el PROCESO muere entre el INSERT de
    los ítems y ese UPDATE (deploy, OOM, worker matado), el lote queda `parseando` PARA
    SIEMPRE: el SPA muestra "Procesando con Haiku…" indefinidamente y el lote ni siquiera
    es borrable (la UI solo ofrece borrar lotes terminales). Esto barre esos huérfanos:
    si ya tienen ítems insertados → `listo` (+ `total_items` real); si no → `error`.

    `antes_de` es un umbral ISO (típicamente `now - TTL`) para NO tocar un parseo realmente
    vivo. Devuelve cuántos lotes saneó. Idempotente: un segundo barrido no encuentra nada.
    """
    con = _conectar()
    try:
        filas = con.execute(
            f"{_SELECT_INSUMO_LOTE} WHERE estado = ? AND creado < ?",  # noqa: S608 -- allowlist fija
            ("parseando", antes_de),
        ).fetchall()
        saneados = 0
        for fila in filas:
            lote_id = fila["id"]
            n = con.execute(
                "SELECT COUNT(*) AS n FROM insumos_item WHERE lote_id = ?", (lote_id,)
            ).fetchone()["n"]
            if int(n or 0) > 0:
                con.execute(
                    "UPDATE insumos_lote SET estado = ?, total_items = ? WHERE id = ?",
                    ("listo", int(n), lote_id),
                )
            else:
                con.execute(
                    "UPDATE insumos_lote SET estado = ?, error = ? WHERE id = ?",
                    ("error", "Parseo interrumpido (worker reiniciado); sin ítems.", lote_id),
                )
            saneados += 1
        con.commit()
        return saneados
    finally:
        con.close()


def crear_insumo_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Inserta múltiples ítems en lote (bulk); devuelve los dicts insertados.

    Cada dict debe contener al menos: `lote_id`, `fecha`, `cajon`, `titulo`.
    Los campos ausentes reciben sus valores por defecto.
    """
    ahora = datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="microseconds")
    marcadores = ", ".join("?" for _ in _COLS_INSUMO_ITEM)
    insertados: list[dict[str, Any]] = []
    con = _conectar()
    try:
        for i, item in enumerate(items):
            item_id = uuid.uuid4().hex[:16]
            fila = {
                "id": item_id,
                "lote_id": item.get("lote_id") or "",
                "fecha": item.get("fecha") or "",
                "cajon": item.get("cajon") or "",
                "marca": item.get("marca") or "",
                "linea": item.get("linea") or "",
                "titulo": item.get("titulo") or "",
                "resumen": item.get("resumen") or "",
                "hora": item.get("hora") or "",
                "lugar": item.get("lugar") or "",
                "estado_material": item.get("estado_material") or "",
                "tipo": item.get("tipo") or "nota",
                "idioma": item.get("idioma") or "es",
                "usado": 0,
                "contenido_id": "",
                "orden": item.get("orden", i),
                "creado": ahora,
            }
            con.execute(
                f"INSERT INTO insumos_item ({', '.join(_COLS_INSUMO_ITEM)}) VALUES ({marcadores})",
                tuple(fila[c] for c in _COLS_INSUMO_ITEM),
            )
            insertados.append(_fila_a_insumo_item(fila))
        con.commit()
    finally:
        con.close()
    return insertados


def listar_insumo_items(
    *,
    fecha: str | None = None,
    cajon: str | None = None,
    marca: str | None = None,
    lote_id: str | None = None,
) -> list[dict[str, Any]]:
    """Lista ítems con filtros opcionales, ordenados por (orden ASC, creado ASC)."""
    sql = _SELECT_INSUMO_ITEM
    params: list[Any] = []
    condiciones: list[str] = []
    if fecha is not None:
        condiciones.append("fecha = ?")
        params.append(fecha)
    if cajon is not None:
        condiciones.append("cajon = ?")
        params.append(cajon)
    if marca is not None:
        condiciones.append("marca = ?")
        params.append(marca)
    if lote_id is not None:
        condiciones.append("lote_id = ?")
        params.append(lote_id)
    if condiciones:
        sql += " WHERE " + " AND ".join(condiciones)
    sql += " ORDER BY orden ASC, creado ASC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_insumo_item(f) for f in filas]


def obtener_insumo_item(item_id: str) -> dict[str, Any] | None:
    """Un ítem por id; None si no existe."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_INSUMO_ITEM} WHERE id = ?", (item_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_insumo_item(fila) if fila is not None else None


def actualizar_insumo_item(item_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Edita parcialmente un ítem (campos editables del contrato). None si no existe."""
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_INSUMO_ITEM}
    if not cambios:
        return obtener_insumo_item(item_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    params: list[Any] = [*cambios.values(), item_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE insumos_item SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
    finally:
        con.close()
    return obtener_insumo_item(item_id)


def marcar_insumo_item_usado(
    item_id: str, *, contenido_id: str
) -> dict[str, Any] | None:
    """Marca un ítem como usado y guarda el `contenido_id`. None si no existe."""
    con = _conectar()
    try:
        cur = con.execute(
            "UPDATE insumos_item SET usado = 1, contenido_id = ? WHERE id = ?",
            (contenido_id, item_id),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
    finally:
        con.close()
    return obtener_insumo_item(item_id)


def listar_lotes(
    *,
    fecha: str | None = None,
    cajon: str | None = None,
) -> list[dict[str, Any]]:
    """Lista lotes con filtros opcionales (fecha/cajón), más recientes primero."""
    sql = _SELECT_INSUMO_LOTE
    params: list[Any] = []
    condiciones: list[str] = []
    if fecha is not None:
        condiciones.append("fecha = ?")
        params.append(fecha)
    if cajon is not None:
        condiciones.append("cajon = ?")
        params.append(cajon)
    if condiciones:
        sql += " WHERE " + " AND ".join(condiciones)
    sql += " ORDER BY creado DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_insumo_lote(f) for f in filas]


def dias_con_insumos() -> list[dict[str, Any]]:
    """Fechas distintas con insumos + total de ítems y desglose por cajón.

    Devuelve lista de dicts `{fecha, total, por_cajon:{portal,corresponsales,reporteros,eventos_claro}}`,
    ordenada por fecha desc. Cuenta ítems (no lotes) para reflejar el volumen editorial real.
    """
    cajones_fijos = ("portal", "corresponsales", "reporteros", "eventos_claro")
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT fecha, cajon, COUNT(*) AS n FROM insumos_item GROUP BY fecha, cajon"
        ).fetchall()
    finally:
        con.close()

    # Agrupa por fecha.
    por_fecha: dict[str, dict[str, int]] = {}
    for f in filas:
        fecha = f["fecha"] or ""
        cajon = f["cajon"] or ""
        n = int(f["n"] or 0)
        if fecha not in por_fecha:
            por_fecha[fecha] = {}
        por_fecha[fecha][cajon] = por_fecha[fecha].get(cajon, 0) + n

    resultado: list[dict[str, Any]] = []
    for fecha in sorted(por_fecha.keys(), reverse=True):
        conteos = por_fecha[fecha]
        por_cajon = {c: conteos.get(c, 0) for c in cajones_fijos}
        resultado.append({
            "fecha": fecha,
            "total": sum(por_cajon.values()),
            "por_cajon": por_cajon,
        })
    return resultado
