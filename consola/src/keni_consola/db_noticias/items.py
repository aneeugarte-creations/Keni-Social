"""Persistencia — dominio noticias: archivo de artículos (noticias_items) + salud de feeds."""
from __future__ import annotations

from .._db_comun import UTC, Any, _conectar, datetime, timedelta, uuid
from ..tiempo import ahora_iso, iso_utc
from .fuentes_rss import _SELECT_FUENTE_RSS, _fila_a_fuente_rss

# --------------------------------------------------------------------------- #
# MOTOR DE INGESTA PERSISTENTE (Ola A): archivo a nivel de artículo            #
# --------------------------------------------------------------------------- #
# `noticias_items` es el ARCHIVO: una fila por artículo de feed, persistido una vez (dedup por
# (fuente_id, clave)). Lo alimenta el `ingesta_daemon` en background; el Radar/Plan y la UI
# leen de aqui. El bulk-insert usa `ON CONFLICT DO NOTHING` sobre el indice unico, asi
# re-ingerir el mismo artículo es inofensivo. La planificación de feeds (`feeds_vencidos`,
# `registrar_sondeo_feed`) vive en las columnas de `fuentes_rss` (mismas conexiones).

_COLS_NOTICIA_ITEM: tuple[str, ...] = (
    "id",
    "fuente_id",
    "fuente_nombre",
    "categoria",
    "marca",
    "titulo",
    "resumen",
    "url",
    "url_canonica",
    "idioma",
    "autor",
    "imagen",
    "publicado_en",
    "capturado_en",
    "clave",
    "cluster_id",
    "senal",
    "geo",
    "estado",
    "contenido_id",
    "fuente_peso",
    "creado",
)
_SELECT_NOTICIA_ITEM = f"SELECT {', '.join(_COLS_NOTICIA_ITEM)} FROM noticias_items"
# Estados validos de un item de archivo.
ESTADOS_NOTICIA_ITEM: tuple[str, ...] = ("nuevo", "usado", "descartado")


def _fila_a_noticia_item(fila: Any) -> dict[str, Any]:
    """Fila de `noticias_items` -> dict publico (snake_case, tipos saneados)."""
    return {
        "id": fila["id"],
        "fuente_id": fila["fuente_id"] or "",
        "fuente_nombre": fila["fuente_nombre"] or "",
        "categoria": fila["categoria"] or "",
        "marca": fila["marca"] or "",
        "titulo": fila["titulo"] or "",
        "resumen": fila["resumen"] or "",
        "url": fila["url"] or "",
        "url_canonica": fila["url_canonica"] or "",
        "idioma": fila["idioma"] or "",
        "autor": fila["autor"] or "",
        "imagen": fila["imagen"] or "",
        "publicado_en": fila["publicado_en"] or "",
        "capturado_en": fila["capturado_en"] or "",
        "clave": fila["clave"] or "",
        "cluster_id": fila["cluster_id"] or "",
        "senal": int(fila["senal"] or 0),
        "geo": fila["geo"] or "",
        "estado": fila["estado"] or "nuevo",
        "contenido_id": fila["contenido_id"] or "",
        # Peso de la fuente del item, denormalizado al archivar (ranking ponderado).
        "fuente_peso": float(fila["fuente_peso"] or 1.0),
        "creado": fila["creado"] or "",
    }


def crear_noticias_items(items: list[dict[str, Any]]) -> int:
    """Inserta en bloque items de archivo; ignora duplicados ((fuente_id, clave)).

    Cada dict debe traer al menos `clave` (sin ella no hay identidad estable: se omite). Los
    campos ausentes caen a su default. Devuelve cuántas filas se INSERTARON realmente
    (`ON CONFLICT DO NOTHING` no cuenta los duplicados). Idempotente: re-ingerir es inofensivo.
    """
    candidatos = [it for it in items if (it.get("clave") or "").strip()]
    if not candidatos:
        return 0
    ahora = ahora_iso()
    # `cuerpo` NO está en `_COLS_NOTICIA_ITEM` (queda fuera del SELECT/serializer del listado, que
    # es path caliente y no necesita el cuerpo): se inserta aparte, solo lo lee el pipeline.
    cols_insert = (*_COLS_NOTICIA_ITEM, "cuerpo")
    marcadores = ", ".join("?" for _ in cols_insert)
    insertadas = 0
    con = _conectar()
    try:
        for it in candidatos:
            fila = {
                "id": it.get("id") or uuid.uuid4().hex[:12],
                "fuente_id": it.get("fuente_id") or "",
                "fuente_nombre": it.get("fuente_nombre") or "",
                "categoria": it.get("categoria") or "",
                "marca": it.get("marca") or "",
                "titulo": it.get("titulo") or "",
                "resumen": it.get("resumen") or "",
                "cuerpo": it.get("cuerpo") or "",
                "url": it.get("url") or "",
                "url_canonica": it.get("url_canonica") or "",
                "idioma": it.get("idioma") or "",
                "autor": it.get("autor") or "",
                "imagen": it.get("imagen") or "",
                "publicado_en": it.get("publicado_en") or "",
                "capturado_en": it.get("capturado_en") or ahora,
                "clave": (it.get("clave") or "").strip(),
                "cluster_id": it.get("cluster_id") or "",
                "senal": int(it.get("senal") or 0),
                "geo": it.get("geo") or "",
                "estado": it.get("estado") or "nuevo",
                "contenido_id": it.get("contenido_id") or "",
                "fuente_peso": float(it.get("fuente_peso") or 1.0),
                "creado": it.get("creado") or ahora,
            }
            cur = con.execute(
                f"INSERT INTO noticias_items ({', '.join(cols_insert)}) "
                f"VALUES ({marcadores}) "
                "ON CONFLICT (fuente_id, clave) DO NOTHING",
                tuple(fila[col] for col in cols_insert),
            )
            if cur.rowcount and cur.rowcount > 0:
                insertadas += 1
        con.commit()
    finally:
        con.close()
    return insertadas


def listar_noticias_items(
    *,
    marca: str | None = None,
    desde: str | None = None,
    q: str | None = None,
    estado: str | None = None,
    limite: int = 50,
    desplazamiento: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Items de archivo filtrables, MÁS NUEVOS primero (`capturado_en` desc) + total.

    Filtros: `marca` ('' / None = todas), `desde` (ISO; `capturado_en >= desde`), `q` (subcadena
    insensible sobre titulo+resumen), `estado`. Ya NO se filtra por `categoria` (el eje de la UI es
    marca/línea editorial). Devuelve `(items, total)` donde `total` cuenta los que pasan los
    filtros (para la paginación), no solo la página.
    """
    condiciones: list[str] = []
    params: list[Any] = []
    if marca:
        condiciones.append("marca = ?")
        params.append(marca)
    if desde:
        condiciones.append("capturado_en >= ?")
        params.append(desde)
    if estado:
        condiciones.append("estado = ?")
        params.append(estado)
    if q and q.strip():
        condiciones.append("(LOWER(titulo) LIKE ? OR LOWER(resumen) LIKE ?)")
        patron = f"%{q.strip().lower()}%"
        params.extend([patron, patron])
    where = (" WHERE " + " AND ".join(condiciones)) if condiciones else ""
    sql = (
        f"{_SELECT_NOTICIA_ITEM}{where} "
        "ORDER BY capturado_en DESC, creado DESC, id DESC LIMIT ? OFFSET ?"
    )
    con = _conectar()
    try:
        filas = con.execute(  # noqa: S608 -- condiciones de allowlist; valores parametrizados
            sql, (*params, max(1, int(limite)), max(0, int(desplazamiento)))
        ).fetchall()
        fila_total = con.execute(  # noqa: S608 -- idem
            f"SELECT COUNT(*) AS n FROM noticias_items{where}", tuple(params)
        ).fetchone()
    finally:
        con.close()
    total = int(fila_total["n"]) if fila_total is not None else 0
    return [_fila_a_noticia_item(f) for f in filas], total


def obtener_noticia_item(item_id: str) -> dict[str, Any] | None:
    """Un item de archivo por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(f"{_SELECT_NOTICIA_ITEM} WHERE id = ?", (item_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_noticia_item(fila) if fila is not None else None


def noticia_item_por_clave(fuente_id: str, clave: str) -> dict[str, Any] | None:
    """Un item de archivo por su IDENTIDAD de dedup `(fuente_id, clave)`; None si no existe.

    Es el mismo par del UNIQUE del pool: permite a los cajones encontrar la fila
    gemela que el parseo volcó (`fuente_id="cajon-*"` + hash del título) para
    descartarla o detectar que el auto-feed ya la recogió.
    """
    if not fuente_id or not clave:
        return None
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_NOTICIA_ITEM} WHERE fuente_id = ? AND clave = ? LIMIT 1",
            (fuente_id, clave),
        ).fetchone()
    finally:
        con.close()
    return _fila_a_noticia_item(fila) if fila is not None else None


def actualizar_noticia_item(
    item_id: str,
    *,
    estado: str | None = None,
    contenido_id: str | None = None,
    cluster_id: str | None = None,
) -> dict[str, Any] | None:
    """Edita `estado` / `contenido_id` / `cluster_id` de un item (None si no existe)."""
    cambios: dict[str, Any] = {}
    if estado is not None:
        cambios["estado"] = estado
    if contenido_id is not None:
        cambios["contenido_id"] = contenido_id
    if cluster_id is not None:
        cambios["cluster_id"] = cluster_id
    if not cambios:
        return obtener_noticia_item(item_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    params: list[Any] = [*cambios.values(), item_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE noticias_items SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
    finally:
        con.close()
    return obtener_noticia_item(item_id)


def feeds_vencidos(ahora: str, limite: int) -> list[dict[str, Any]]:
    """Feeds RSS ACTIVOS listos para sondear AHORA (planificación del motor de ingesta).

    Un feed está vencido si `activo=1`, `proximo_sondeo` está vacío ('' = sondear ya) o es
    `<= ahora`, y NO está pausado por backoff (`pausado_hasta` vacío o `<= ahora`). Se ordena
    por `prioridad DESC` (las prioritarias primero) y luego por `proximo_sondeo` (las más
    atrasadas antes). `ahora` es un ISO comparable lexicográficamente con las columnas ISO.
    """
    con = _conectar()
    try:
        filas = con.execute(
            f"{_SELECT_FUENTE_RSS} WHERE activo = 1 "
            "AND (proximo_sondeo = '' OR proximo_sondeo <= ?) "
            "AND (pausado_hasta = '' OR pausado_hasta <= ?) "
            "ORDER BY prioridad DESC, proximo_sondeo ASC, creado ASC LIMIT ?",
            (ahora, ahora, max(1, int(limite))),
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_fuente_rss(f) for f in filas]


def registrar_sondeo_feed(
    feed_id: str,
    *,
    conteo: int = 0,
    error: str = "",
    proximo_sondeo: str = "",
    errores_seguidos: int = 0,
    pausado_hasta: str = "",
    activo: bool | None = None,
    desactivado_auto: bool | None = None,
    filtrados: int = 0,
) -> None:
    """Anota el resultado de un sondeo de feed (salud + planificación). Best-effort.

    Actualiza la salud (`ultima_actualizacion`/`ultimo_conteo`/`ultimo_error`) y la
    planificación (`proximo_sondeo`/`errores_seguidos`/`pausado_hasta`) en una sola escritura.
    El daemon calcula los valores (intervalo por categoría, backoff exponencial) y los pasa ya
    resueltos; aquí solo se persisten.

    AUTO-DESACTIVADO (Ola D): si el daemon decide apagar el feed por errores seguidos, pasa
    `activo=False` + `desactivado_auto=True`; si se recupera, NO los pasa (None = no tocar). Solo
    se incluyen en el UPDATE cuando no son None, así un sondeo normal no pisa el `activo`.
    """
    asignaciones = [
        "ultima_actualizacion = ?", "ultimo_conteo = ?", "ultimo_error = ?",
        "proximo_sondeo = ?", "errores_seguidos = ?", "pausado_hasta = ?",
        "ultimo_filtrados = ?",
    ]
    params: list[Any] = [
        ahora_iso(),
        int(conteo),
        error or "",
        proximo_sondeo or "",
        int(errores_seguidos or 0),
        pausado_hasta or "",
        int(filtrados or 0),
    ]
    if activo is not None:
        asignaciones.append("activo = ?")
        params.append(1 if activo else 0)
    if desactivado_auto is not None:
        asignaciones.append("desactivado_auto = ?")
        params.append(1 if desactivado_auto else 0)
    params.append(feed_id)
    con = _conectar()
    try:
        con.execute(
            f"UPDATE fuentes_rss SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
    finally:
        con.close()


def resumen_cobertura() -> dict[str, Any]:
    """Resumen de salud del motor de ingesta (para `/api/noticias/cobertura`).

    Devuelve nº de feeds activos, feeds con error (último sondeo falló), items capturados en
    las últimas 24h por categoría, total de items, y el último sondeo registrado. Todo en una
    conexión, sin tocar la red.
    """
    hace_24h = iso_utc(datetime.now(UTC) - timedelta(hours=24))
    con = _conectar()
    try:
        feeds_activos = int(
            (con.execute(
                "SELECT COUNT(*) AS n FROM fuentes_rss WHERE activo = 1"
            ).fetchone() or {"n": 0})["n"] or 0
        )
        feeds_error = int(
            (con.execute(
                "SELECT COUNT(*) AS n FROM fuentes_rss WHERE activo = 1 AND ultimo_error <> ''"
            ).fetchone() or {"n": 0})["n"] or 0
        )
        total_items = int(
            (con.execute("SELECT COUNT(*) AS n FROM noticias_items").fetchone() or {"n": 0})["n"]
            or 0
        )
        filas_cat = con.execute(
            "SELECT categoria, COUNT(*) AS n FROM noticias_items "
            "WHERE capturado_en >= ? GROUP BY categoria ORDER BY n DESC",
            (hace_24h,),
        ).fetchall()
        fila_ultimo = con.execute(
            "SELECT MAX(ultima_actualizacion) AS u FROM fuentes_rss "
            "WHERE ultima_actualizacion <> ''"
        ).fetchone()
    finally:
        con.close()
    items_24h_por_categoria = {
        (f["categoria"] or "(sin categoría)"): int(f["n"] or 0) for f in filas_cat
    }
    return {
        "feeds_activos": feeds_activos,
        "feeds_con_error": feeds_error,
        "items_total": total_items,
        "items_24h": sum(items_24h_por_categoria.values()),
        "items_24h_por_categoria": items_24h_por_categoria,
        "ultimo_sondeo": (fila_ultimo["u"] if fila_ultimo is not None else "") or "",
    }


def salud_feeds(marca: str | None = None) -> list[dict[str, Any]]:
    """Salud por feed para `/api/noticias/salud` (Ola D): un dict por feed con frescura + items 24h.

    Para cada `fuentes_rss` (opcionalmente filtrada por `marca`) devuelve sus campos públicos
    MÁS dos agregados calculados de `noticias_items`:
      - `items_24h`: nº de items capturados en las últimas 24h con ese `fuente_id`.
      - `ultimo_item`: `MAX(capturado_en)` de ese feed ('' si nunca capturó nada).
    El daemon/API derivan `frescura_min` y `stale` de `ultimo_item`. Una sola conexión; sin red.
    Incluye feeds inactivos/auto-desactivados (la UI los muestra para reactivar).
    """
    hace_24h = iso_utc(datetime.now(UTC) - timedelta(hours=24))
    cond = ""
    params: list[Any] = []
    if marca:
        cond = " WHERE marca = ?"
        params.append(marca)
    con = _conectar()
    try:
        feeds = con.execute(  # noqa: S608 -- cond de allowlist; valor parametrizado
            f"{_SELECT_FUENTE_RSS}{cond} ORDER BY creado DESC, id DESC", tuple(params)
        ).fetchall()
        filas_24h = con.execute(
            "SELECT fuente_id, COUNT(*) AS n FROM noticias_items "
            "WHERE capturado_en >= ? GROUP BY fuente_id",
            (hace_24h,),
        ).fetchall()
        filas_ult = con.execute(
            "SELECT fuente_id, MAX(capturado_en) AS u FROM noticias_items GROUP BY fuente_id"
        ).fetchall()
    finally:
        con.close()
    por_24h = {f["fuente_id"]: int(f["n"] or 0) for f in filas_24h}
    por_ult = {f["fuente_id"]: (f["u"] or "") for f in filas_ult}
    salida: list[dict[str, Any]] = []
    for f in feeds:
        d = _fila_a_fuente_rss(f)
        d["items_24h"] = por_24h.get(d["id"], 0)
        d["ultimo_item"] = por_ult.get(d["id"], "")
        salida.append(d)
    return salida


def conteos_items_recientes(
    marca: str | None = None, *, horas: int = 24
) -> dict[str, dict[str, int]]:
    """Distribuciones de items recientes para `/salud`: por categoría y por idioma (Ola D).

    Cuenta los `noticias_items` capturados en las últimas `horas` (opcionalmente filtrados por
    `marca`) agrupados por `categoria` y por `idioma`. Sirve para `por_categoria`/`por_idioma`
    del resumen y para detectar HUECOS (categorías/regiones esperadas sin items frescos).
    Devuelve `{"por_categoria": {cat: n}, "por_idioma": {lang: n}}`.
    """
    desde = iso_utc(datetime.now(UTC) - timedelta(hours=max(1, int(horas))))
    cond = "capturado_en >= ?"
    params: list[Any] = [desde]
    if marca:
        cond += " AND marca = ?"
        params.append(marca)
    con = _conectar()
    try:
        filas_cat = con.execute(  # noqa: S608 -- cond de allowlist; valores parametrizados
            f"SELECT categoria, COUNT(*) AS n FROM noticias_items WHERE {cond} "
            "GROUP BY categoria ORDER BY n DESC",
            tuple(params),
        ).fetchall()
        filas_idi = con.execute(  # noqa: S608 -- idem
            f"SELECT idioma, COUNT(*) AS n FROM noticias_items WHERE {cond} "
            "GROUP BY idioma ORDER BY n DESC",
            tuple(params),
        ).fetchall()
    finally:
        con.close()
    por_categoria = {
        (f["categoria"] or "(sin categoría)"): int(f["n"] or 0) for f in filas_cat
    }
    por_idioma = {(f["idioma"] or "(sin idioma)"): int(f["n"] or 0) for f in filas_idi}
    return {"por_categoria": por_categoria, "por_idioma": por_idioma}


def stats_fuentes(marca: str | None = None, *, dias: int = 7) -> list[dict[str, Any]]:
    """RENDIMIENTO editorial por fuente en los últimos `dias`: qué fuentes aportan de verdad.

    Por `fuente_id` con items capturados en la ventana:
      - `items`: artículos aportados.
      - `historias`: clusters distintos en los que participó.
      - `primeras`: historias que ABRIÓ (cluster.primera_fuente = fuente).
      - `usadas`: historias suyas que acabaron usadas (promovidas al tablero).
      - `peso`: peso editorial observado (máx de sus items: cubre agencias sin fila en
        `fuentes_rss`).
    Con `marca`, cuenta los items de ESA marca + los compartidos (marca vacía) — el mismo
    criterio que el listado de fuentes. `tasa_uso` la deriva el llamante (usadas/historias).
    Orden: más historias primero. Una sola conexión; sin red.
    """
    desde = iso_utc(datetime.now(UTC) - timedelta(days=max(1, int(dias))))
    cond = "i.capturado_en >= ?"
    params: list[Any] = [desde]
    if marca:
        cond += " AND (i.marca = ? OR i.marca = '')"
        params.append(marca)
    con = _conectar()
    try:
        filas = con.execute(  # noqa: S608 -- cond de allowlist; valores parametrizados
            "SELECT i.fuente_id AS fuente_id, "
            "  MAX(i.fuente_nombre) AS fuente_nombre, "
            "  MAX(i.fuente_peso) AS peso, "
            "  COUNT(*) AS items, "
            "  COUNT(DISTINCT c.id) AS historias, "
            "  COUNT(DISTINCT c.id) FILTER (WHERE c.primera_fuente = i.fuente_id) AS primeras, "
            "  COUNT(DISTINCT c.id) FILTER (WHERE c.estado = 'usado') AS usadas "
            "FROM noticias_items i "
            "LEFT JOIN noticias_clusters c ON c.id = i.cluster_id "
            f"WHERE {cond} AND i.fuente_id <> '' "
            "GROUP BY i.fuente_id "
            "ORDER BY historias DESC, items DESC, fuente_id",
            tuple(params),
        ).fetchall()
    finally:
        con.close()
    return [
        {
            "fuente_id": f["fuente_id"],
            "fuente_nombre": f["fuente_nombre"] or "",
            "peso": float(f["peso"] or 1.0),
            "items": int(f["items"] or 0),
            "historias": int(f["historias"] or 0),
            "primeras": int(f["primeras"] or 0),
            "usadas": int(f["usadas"] or 0),
        }
        for f in filas
    ]
