"""Persistencia — dominio noticias. Implementación de db.py (ver barrel `db.py`)."""
from __future__ import annotations

from ._db_comun import (
    UTC,
    Any,
    _conectar,
    datetime,
    json,
    timedelta,
    uuid,
)
from .tiempo import ahora_iso, hoy_utc, iso_utc

# --- Fuentes RSS ----------------------------------------------------------- #
# El dict publico (paridad con `ficheros._parsear_fuente`) NO incluye `creado` (orden
# interno): solo `id, nombre, url, marca, fecha, activo(bool), incluir, excluir, redes_def,
# ultima_actualizacion, ultimo_error, ultimo_conteo(int)`.
_COLS_FUENTE_RSS = (
    "id",
    "nombre",
    "url",
    "marca",
    "fecha",
    "activo",
    "incluir",
    "excluir",
    "redes_def",
    "ultima_actualizacion",
    "ultimo_error",
    "ultimo_conteo",
    "propia",
    "intervalo_min",
    "categoria",
    "prioridad",
    "proximo_sondeo",
    "errores_seguidos",
    "pausado_hasta",
    "desactivado_auto",
    "ultimo_filtrados",
    "peso",
    "creado",
)
_SELECT_FUENTE_RSS = f"SELECT {', '.join(_COLS_FUENTE_RSS)} FROM fuentes_rss"
_CAMPOS_EDITABLES_FUENTE_RSS: tuple[str, ...] = (
    "nombre", "url", "marca", "activo", "incluir", "excluir", "redes_def", "propia",
    "intervalo_min", "categoria", "prioridad",
    # Ola D: reactivar un feed auto-desactivado (resetear estado del motor de ingesta).
    "desactivado_auto", "errores_seguidos", "proximo_sondeo", "pausado_hasta",
    # Peso editorial (ranking ponderado): editable desde la UI de Fuentes.
    "peso",
)


def _fila_a_fuente_rss(fila: Any) -> dict[str, Any]:
    """Fila de `fuentes_rss` -> dict publico (sin `creado`; `activo` bool, `ultimo_conteo` int)."""
    return {
        "id": fila["id"],
        "nombre": fila["nombre"] or "",
        "url": fila["url"] or "",
        "marca": fila["marca"] or "",
        "fecha": fila["fecha"] or "",
        "activo": bool(fila["activo"]),
        "incluir": fila["incluir"] or "",
        "excluir": fila["excluir"] or "",
        "redes_def": fila["redes_def"] or "",
        "ultima_actualizacion": fila["ultima_actualizacion"] or "",
        "ultimo_error": fila["ultimo_error"] or "",
        "ultimo_conteo": int(fila["ultimo_conteo"] or 0),
        # Sitio de marca PROPIA: habilita reutilizar la imagen original del artículo.
        "propia": bool(fila["propia"]),
        # Planificación del motor de ingesta (Ola A).
        "intervalo_min": int(fila["intervalo_min"] or 0),
        "categoria": fila["categoria"] or "",
        "prioridad": int(fila["prioridad"] or 0),
        "proximo_sondeo": fila["proximo_sondeo"] or "",
        "errores_seguidos": int(fila["errores_seguidos"] or 0),
        "pausado_hasta": fila["pausado_hasta"] or "",
        # Auto-desactivado por el motor (Ola D): True si el daemon lo apagó por errores seguidos.
        "desactivado_auto": bool(fila["desactivado_auto"]),
        # Filtro de ENTRADA por vocabulario de marca: items descartados en el último sondeo.
        "ultimo_filtrados": int(fila["ultimo_filtrados"] or 0),
        # Peso editorial de la fuente (pondera la corroboración del ranking de historias).
        "peso": float(fila["peso"] or 1.0),
    }


def listar_fuentes_rss(
    *,
    marca: str | None = None,
    limite: int | None = None,
    desplazamiento: int | None = None,
) -> list[dict[str, Any]]:
    """Fuentes RSS (mas recientes primero), con paginacion opcional.

    Si se pasa `marca`, devuelve las fuentes de ESA marca MAS las COMPARTIDAS
    (`marca` vacia/NULL); con `marca=None` devuelve todas (admin "todas").
    """
    sql = _SELECT_FUENTE_RSS
    params: list[Any] = []
    if marca:
        # Marca seleccionada: propias de la marca + compartidas (vacia/NULL).
        sql += " WHERE (marca = ? OR marca IS NULL OR marca = '')"
        params.append(marca)
    sql += " ORDER BY creado DESC, fecha DESC, id DESC"
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
    return [_fila_a_fuente_rss(f) for f in filas]


def categoria_promovida_de_contenido(contenido_id: str) -> str:
    """Categoría del PLAN con la que nació un contenido promovido de una historia.

    'breaking' si su cluster es breaking; si no, la categoría del feed del cluster (en
    minúsculas). '' si el contenido no vino de una historia (alta manual/equipo) o el
    cluster ya no existe. Para los HORARIOS por categoría del plan (franjas editoriales).
    """
    if not contenido_id:
        return ""
    con = _conectar()
    try:
        fila = con.execute(
            "SELECT CASE WHEN breaking = 1 THEN 'breaking' "
            "ELSE LOWER(COALESCE(categoria, '')) END AS cat "
            "FROM noticias_clusters WHERE contenido_id = ? LIMIT 1",
            (contenido_id,),
        ).fetchone()
    finally:
        con.close()
    return str(fila["cat"]) if fila is not None else ""


def contar_fuentes_rss() -> int:
    """Total de fuentes RSS (para el `total` de paginacion)."""
    con = _conectar()
    try:
        fila = con.execute("SELECT COUNT(*) AS n FROM fuentes_rss").fetchone()
    finally:
        con.close()
    return int(fila["n"]) if fila is not None else 0


def obtener_fuente_rss(fuente_id: str) -> dict[str, Any] | None:
    """Una fuente RSS por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(f"{_SELECT_FUENTE_RSS} WHERE id = ?", (fuente_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_fuente_rss(fila) if fila is not None else None


def crear_fuente_rss(
    nombre: str,
    url: str,
    marca: str = "",
    *,
    incluir: str = "",
    excluir: str = "",
    redes_def: str = "",
    propia: bool = False,
    categoria: str = "",
    prioridad: int = 0,
    intervalo_min: int = 0,
    peso: float = 1.0,
) -> dict[str, Any]:
    """Crea una fuente RSS (activa, salud vacia) y la devuelve.

    `categoria`/`prioridad`/`intervalo_min` alimentan la planificación del motor de ingesta
    (Ola A); `proximo_sondeo` nace '' para que el primer barrido la sondee de inmediato.
    `peso` es el peso editorial de la fuente (pondera la corroboración del ranking).
    """
    # Microsegundos (no segundos): el listado ordena por `creado DESC` y dos fuentes creadas
    # en el mismo segundo empataban, dejando el orden al `id` (uuid aleatorio) -> test flaky.
    ahora = datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="microseconds")
    fila = {
        "id": uuid.uuid4().hex[:12],
        "nombre": nombre or "",
        "url": url or "",
        "marca": marca or "",
        "fecha": hoy_utc().isoformat(),
        "activo": 1,
        "incluir": incluir or "",
        "excluir": excluir or "",
        "redes_def": redes_def or "",
        "ultima_actualizacion": "",
        "ultimo_error": "",
        "ultimo_conteo": 0,
        "propia": 1 if propia else 0,
        "intervalo_min": int(intervalo_min or 0),
        "categoria": categoria or "",
        "prioridad": int(prioridad or 0),
        "proximo_sondeo": "",
        "errores_seguidos": 0,
        "pausado_hasta": "",
        "desactivado_auto": 0,
        "ultimo_filtrados": 0,
        "peso": float(peso or 1.0),
        "creado": ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_FUENTE_RSS)
        # Sin ON CONFLICT: se permite la MISMA URL en varias fuentes (distinta marca/filtros/
        # nombre). Ver nota en `_INDICES_UNICOS_IDEMPOTENCIA`.
        con.execute(
            f"INSERT INTO fuentes_rss ({', '.join(_COLS_FUENTE_RSS)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_FUENTE_RSS),
        )
        con.commit()
    finally:
        con.close()
    return obtener_fuente_rss(fila["id"]) or _fila_a_fuente_rss(fila)


def actualizar_fuente_rss(
    fuente_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente una fuente (nombre/url/marca/activo/incluir/excluir/redes_def)."""
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_FUENTE_RSS}
    if "activo" in cambios:
        cambios["activo"] = 1 if cambios["activo"] else 0
    if "propia" in cambios:
        cambios["propia"] = 1 if cambios["propia"] else 0
    if "desactivado_auto" in cambios:
        cambios["desactivado_auto"] = 1 if cambios["desactivado_auto"] else 0
    if not cambios:
        return obtener_fuente_rss(fuente_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    params: list[Any] = [*cambios.values(), fuente_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE fuentes_rss SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
    finally:
        con.close()
    return obtener_fuente_rss(fuente_id)


def registrar_salud_fuente_rss(fuente_id: str, *, conteo: int, error: str = "") -> None:
    """Anota la salud de una fuente (instante UTC + conteo + error). Best-effort.

    Canon UTC sin offset (`tiempo.ahora_iso`): la columna `ultima_actualizacion` mezclaba
    fechas locales sin hora con instantes UTC (`registrar_sondeo_feed`), y el `MAX()` /
    las comparaciones de frescura salían de relojes distintos. Formato unificado.
    """
    con = _conectar()
    try:
        con.execute(
            "UPDATE fuentes_rss SET ultima_actualizacion = ?, ultimo_conteo = ?, "
            "ultimo_error = ? WHERE id = ?",
            (ahora_iso(), int(conteo), error or "", fuente_id),
        )
        con.commit()
    finally:
        con.close()


def borrar_fuente_rss(fuente_id: str) -> bool:
    """Borra una fuente RSS y sus items vistos; True si existia, False si no."""
    con = _conectar()
    try:
        con.execute("DELETE FROM rss_items_vistos WHERE fuente_id = ?", (fuente_id,))
        cur = con.execute("DELETE FROM fuentes_rss WHERE id = ?", (fuente_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def purgar_pool_irrelevante(
    *, score_umbral: float, inactividad_horas: int, dry_run: bool = False
) -> dict[str, int]:
    """GC del pool por RELEVANCIA (no por edad sola): borra el ruido de baja relevancia.

    CONSERVADOR. Borra SOLO lo que no aporta y nadie va a trabajar:
      - clusters `estado='nuevo'`, SIN `contenido_id` (no llevados al tablero), de UNA sola fuente
        (`n_fuentes <= 1`), con `score < score_umbral` Y sin actividad reciente
        (`ultimo_visto < ahora - inactividad_horas`). Se CONSERVAN: usados/ligados a contenido,
        corroborados (multi-fuente), de score alto, o recientes.
      - items `estado='nuevo'`, SIN `contenido_id`, viejos (`capturado_en < cutoff`) y
        HUÉRFANOS (sin cluster o cuyo cluster ya no existe — p. ej. recién purgado). Los items de
        clusters que SOBREVIVEN se conservan.
    NO es un TTL: la antigüedad es solo UNA condición junto a la baja relevancia. `dry_run=True`
    cuenta sin borrar. Devuelve `{clusters, items, dry_run}`.
    """
    cutoff = iso_utc(datetime.now(UTC) - timedelta(hours=max(1, int(inactividad_horas))))
    cond_clusters = (
        "estado = 'nuevo' AND (contenido_id IS NULL OR contenido_id = '') "
        "AND n_fuentes <= 1 AND score < ? AND ultimo_visto <> '' AND ultimo_visto < ?"
    )
    cond_items = (
        "estado = 'nuevo' AND (contenido_id IS NULL OR contenido_id = '') "
        "AND capturado_en <> '' AND capturado_en < ? "
        "AND (cluster_id = '' OR cluster_id NOT IN (SELECT id FROM noticias_clusters))"
    )
    con = _conectar()
    try:
        if dry_run:
            n_cl = con.execute(  # noqa: S608 -- condición estática; valores parametrizados
                f"SELECT COUNT(*) AS n FROM noticias_clusters WHERE {cond_clusters}",
                (score_umbral, cutoff),
            ).fetchone()["n"]
            n_it = con.execute(  # noqa: S608 -- idem
                f"SELECT COUNT(*) AS n FROM noticias_items WHERE {cond_items}", (cutoff,)
            ).fetchone()["n"]
            return {"clusters": int(n_cl or 0), "items": int(n_it or 0), "dry_run": 1}
        cur_cl = con.execute(  # noqa: S608 -- condición estática; valores parametrizados
            f"DELETE FROM noticias_clusters WHERE {cond_clusters}", (score_umbral, cutoff)
        )
        # Tras borrar clusters, los items huérfanos (cluster inexistente) caen en `cond_items`.
        cur_it = con.execute(  # noqa: S608 -- idem
            f"DELETE FROM noticias_items WHERE {cond_items}", (cutoff,)
        )
        con.commit()
        return {"clusters": cur_cl.rowcount, "items": cur_it.rowcount, "dry_run": 0}
    finally:
        con.close()


def caducar_pool(
    *, ttl_horas: int, retencion_horas: int = 0
) -> dict[str, int]:
    """CADUCIDAD del pool: lo viejo expira SOLO (TTL), y lo expirado se purga tras la retención.

    Complementa al GC por relevancia (`purgar_pool_irrelevante`, que es selectivo y gateado):
    esto es el RELOJ del feed — un feed de noticias es perecedero por diseño.

      1. TTL (soft): historias `estado='nuevo'`, SIN `contenido_id`, sin actividad en
         `ttl_horas` (su `ultimo_visto` —o `creado` si nunca vieron item— quedó atrás)
         pasan a `estado='descartado'`: salen del panel, del ranking y de la promoción.
         REVERSIBLE (es un estado) y conservador: lo usado/ligado al tablero NUNCA caduca.
      2. RETENCIÓN (hard): historias `descartado` SIN `contenido_id` y sin actividad en
         `retencion_horas` se BORRAN junto a sus items, y los items sueltos `nuevo` sin
         contenido más viejos que la retención también (el archivo no crece sin techo).
         `retencion_horas=0` desactiva el borrado (solo TTL).

    `ttl_horas <= 0` = no-op total. Devuelve `{caducadas, purgadas, items_purgados}`.
    """
    if int(ttl_horas) <= 0:
        return {"caducadas": 0, "purgadas": 0, "items_purgados": 0}
    ahora = datetime.now(UTC)
    corte_ttl = iso_utc(ahora - timedelta(hours=int(ttl_horas)))
    con = _conectar()
    try:
        cur_ttl = con.execute(
            "UPDATE noticias_clusters SET estado = 'descartado', actualizado = ? "
            "WHERE estado = 'nuevo' AND (contenido_id IS NULL OR contenido_id = '') "
            "AND ((ultimo_visto <> '' AND ultimo_visto < ?) "
            "     OR (ultimo_visto = '' AND creado <> '' AND creado < ?))",
            (ahora_iso(), corte_ttl, corte_ttl),
        )
        purgadas = 0
        items_purgados = 0
        if int(retencion_horas) > 0:
            corte_ret = iso_utc(ahora - timedelta(hours=int(retencion_horas)))
            # Items de las historias a purgar (la historia se borra con TODO su rastro).
            cond_purga = (
                "estado = 'descartado' AND (contenido_id IS NULL OR contenido_id = '') "
                "AND ((ultimo_visto <> '' AND ultimo_visto < ?) "
                "     OR (ultimo_visto = '' AND creado <> '' AND creado < ?))"
            )
            cur_items = con.execute(  # noqa: S608 -- condición estática; valores parametrizados
                "DELETE FROM noticias_items WHERE cluster_id IN "
                f"(SELECT id FROM noticias_clusters WHERE {cond_purga})",
                (corte_ret, corte_ret),
            )
            items_purgados += cur_items.rowcount or 0
            cur_purga = con.execute(  # noqa: S608 -- idem
                f"DELETE FROM noticias_clusters WHERE {cond_purga}", (corte_ret, corte_ret)
            )
            purgadas = cur_purga.rowcount or 0
            # Items SUELTOS (sin cluster) `nuevo` sin contenido más viejos que la retención:
            # nunca volverán a clusterizar (fuera de la ventana) ni a usarse; techo del archivo.
            cur_sueltos = con.execute(
                "DELETE FROM noticias_items WHERE cluster_id = '' AND estado = 'nuevo' "
                "AND (contenido_id IS NULL OR contenido_id = '') "
                "AND capturado_en <> '' AND capturado_en < ?",
                (corte_ret,),
            )
            items_purgados += cur_sueltos.rowcount or 0
        con.commit()
        return {
            "caducadas": cur_ttl.rowcount or 0,
            "purgadas": purgadas,
            "items_purgados": items_purgados,
        }
    finally:
        con.close()


def borrar_noticia_cluster(cluster_id: str) -> bool:
    """Borra la fila de un cluster (historia). True si existía. Best-effort, sin cascada.

    Pensado para la FUSIÓN semántica: tras reasignar los items del cluster absorbido al canónico
    (`asignar_cluster_item`), se borra la fila vacía. NO toca `noticias_items` (sus items ya
    apuntan a otro cluster); si quedara alguno apuntando aquí, el clustering/GC lo recoloca.
    """
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM noticias_clusters WHERE id = ?", (cluster_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def borrar_clusters_con_items(cluster_ids: list[str]) -> int:
    """Borra HARD varias historias (clusters) Y sus artículos del archivo. Devuelve nº borradas.

    A diferencia de `borrar_noticia_cluster` (que solo quita la fila del cluster), esta SÍ borra
    los `noticias_items` de esos clusters: si no, el clustering los reagruparía y la historia
    reaparecería. Idempotente: ignora ids vacíos/repetidos/inexistentes.
    """
    ids = [i for i in dict.fromkeys(cluster_ids) if i]
    if not ids:
        return 0
    marcadores = ",".join("?" for _ in ids)
    con = _conectar()
    try:
        con.execute(f"DELETE FROM noticias_items WHERE cluster_id IN ({marcadores})", tuple(ids))
        cur = con.execute(f"DELETE FROM noticias_clusters WHERE id IN ({marcadores})", tuple(ids))
        con.commit()
        return cur.rowcount or 0
    finally:
        con.close()


def vaciar_clusters(marca: str | None = None, estado: str | None = None) -> int:
    """Borra HARD TODAS las historias que casan `marca`/`estado` Y sus artículos. Devuelve nº borradas.

    Es el "dejar a 0": vacía el pool de la marca (y, si se pasa, solo de un estado). SIN filtro de
    estado borra ADEMÁS los artículos sueltos (sin cluster) de la marca, para que el clustering no
    reforme historias y la marca quede de verdad en 0. CON filtro de estado solo toca los clusters
    de ese estado y sus artículos (los items no tienen estado; van por pertenencia al cluster).
    """
    cond: list[str] = []
    params: list[Any] = []
    if marca:
        cond.append("marca = ?")
        params.append(marca)
    if estado:
        cond.append("estado = ?")
        params.append(estado)
    where = (" WHERE " + " AND ".join(cond)) if cond else ""
    con = _conectar()
    try:
        if estado:
            # Los items no tienen estado: se borran por pertenencia a los clusters que se van.
            con.execute(
                "DELETE FROM noticias_items WHERE cluster_id IN "
                f"(SELECT id FROM noticias_clusters{where})",
                tuple(params),
            )
        elif marca:
            # A 0 de verdad: TODOS los artículos de la marca (en cluster + sueltos).
            con.execute("DELETE FROM noticias_items WHERE marca = ?", (marca,))
        else:
            con.execute("DELETE FROM noticias_items")
        cur = con.execute(f"DELETE FROM noticias_clusters{where}", tuple(params))
        con.commit()
        return cur.rowcount or 0
    finally:
        con.close()


def marcar_item(fuente_id: str, clave: str, usado: bool) -> None:
    """Marca/desmarca un item de una fuente como usado (idempotente).

    NO exige que la fuente exista (paridad con el file-backed): es una tabla de claves
    vistas sin FK. `usado=True` inserta (ON CONFLICT DO NOTHING); `usado=False` borra.
    """
    con = _conectar()
    try:
        if usado:
            con.execute(
                "INSERT INTO rss_items_vistos (fuente_id, clave) VALUES (?, ?) "
                "ON CONFLICT DO NOTHING",
                (fuente_id, clave),
            )
        else:
            con.execute(
                "DELETE FROM rss_items_vistos WHERE fuente_id = ? AND clave = ?",
                (fuente_id, clave),
            )
        con.commit()
    finally:
        con.close()


def claves_vistas(fuente_id: str) -> set[str]:
    """Conjunto de claves ya marcadas como usadas para una fuente (vacio si ninguna)."""
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT clave FROM rss_items_vistos WHERE fuente_id = ?", (fuente_id,)
        ).fetchall()
    finally:
        con.close()
    return {f["clave"] for f in filas}



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
    marcadores = ", ".join("?" for _ in _COLS_NOTICIA_ITEM)
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
                f"INSERT INTO noticias_items ({', '.join(_COLS_NOTICIA_ITEM)}) "
                f"VALUES ({marcadores}) "
                "ON CONFLICT (fuente_id, clave) DO NOTHING",
                tuple(fila[col] for col in _COLS_NOTICIA_ITEM),
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



# --- Clustering de HISTORIAS (Ola B): noticias_clusters -------------------- #
# Una historia = la misma noticia contada por varias fuentes y en el tiempo. El daemon de
# ingesta asigna `cluster_id` a los items recién insertados y `upsert`ea el cluster recalculado.
ESTADOS_NOTICIA_CLUSTER: tuple[str, ...] = ("nuevo", "usado", "descartado")

_COLS_NOTICIA_CLUSTER: tuple[str, ...] = (
    "id",
    "titulo",
    "resumen",
    "marca",
    "categoria",
    "geo",
    "clave",
    "n_items",
    "n_fuentes",
    "idiomas",
    "senal",
    "score",
    "score_razon",
    "score_desglose",
    "breaking",
    "primer_visto",
    "ultimo_visto",
    "estado",
    "contenido_id",
    "verificacion",
    "titulo_es",
    "resumen_es",
    "titulo_original",
    "idioma",
    "traducido",
    "peso_fuentes",
    "velocidad",
    "primera_fuente",
    "primera_fuente_nombre",
    "fuentes_detalle",
    "creado",
    "actualizado",
)
_SELECT_NOTICIA_CLUSTER = f"SELECT {', '.join(_COLS_NOTICIA_CLUSTER)} FROM noticias_clusters"
# Verificación por corroboración (Ola D): valores válidos de `noticias_clusters.verificacion`.
VERIFICACIONES_CLUSTER: tuple[str, ...] = ("corroborada", "unica_fuente", "dudosa")


def _desglose_a_json(valor: Any) -> str:
    """Serializa `score_desglose` para la columna: dict -> JSON; str -> tal cual; resto -> ''."""
    if isinstance(valor, dict):
        try:
            return json.dumps(valor, ensure_ascii=False)
        except (TypeError, ValueError):
            return ""
    return valor if isinstance(valor, str) else ""


def _desglose_a_dict(crudo: Any) -> dict[str, Any]:
    """Deserializa `score_desglose` (JSON) a dict; {} si está vacío o malformado. Best-effort."""
    try:
        datos = json.loads(crudo or "{}")
    except (ValueError, TypeError):
        return {}
    return datos if isinstance(datos, dict) else {}


def _detalle_fuentes_a_json(valor: Any) -> str:
    """Serializa `fuentes_detalle` para la columna: lista -> JSON; str -> tal cual; resto -> ''."""
    if isinstance(valor, list):
        try:
            return json.dumps(valor, ensure_ascii=False)
        except (TypeError, ValueError):
            return ""
    return valor if isinstance(valor, str) else ""


def _detalle_fuentes_a_lista(crudo: Any) -> list[dict[str, Any]]:
    """Deserializa `fuentes_detalle` (JSON) a lista de dicts; [] si vacío o malformado."""
    try:
        datos = json.loads(crudo or "[]")
    except (ValueError, TypeError):
        return []
    if not isinstance(datos, list):
        return []
    return [d for d in datos if isinstance(d, dict)]


def _fila_a_noticia_cluster(fila: Any) -> dict[str, Any]:
    """Fila de `noticias_clusters` -> dict publico (snake_case; `idiomas` deserializado)."""
    try:
        idiomas = json.loads(fila["idiomas"] or "[]")
        if not isinstance(idiomas, list):
            idiomas = []
    except (ValueError, TypeError):
        idiomas = []
    return {
        "id": fila["id"],
        "titulo": fila["titulo"] or "",
        "resumen": fila["resumen"] or "",
        "marca": fila["marca"] or "",
        "categoria": fila["categoria"] or "",
        "geo": fila["geo"] or "",
        "clave": fila["clave"] or "",
        "n_items": int(fila["n_items"] or 0),
        "n_fuentes": int(fila["n_fuentes"] or 0),
        "idiomas": idiomas,
        "senal": int(fila["senal"] or 0),
        "score": float(fila["score"] or 0.0),
        # Relevancia EXPLICABLE: razón humana del score + desglose por señal (JSON -> dict).
        "score_razon": fila["score_razon"] or "",
        "score_desglose": _desglose_a_dict(fila["score_desglose"]),
        "breaking": int(fila["breaking"] or 0),
        "primer_visto": fila["primer_visto"] or "",
        "ultimo_visto": fila["ultimo_visto"] or "",
        "estado": fila["estado"] or "nuevo",
        "contenido_id": fila["contenido_id"] or "",
        # Auto-verificación por corroboración (Ola D).
        "verificacion": fila["verificacion"] or "unica_fuente",
        # Traducción completa de historias extranjeras (Ola D).
        "titulo_es": fila["titulo_es"] or "",
        "resumen_es": fila["resumen_es"] or "",
        "titulo_original": fila["titulo_original"] or "",
        "idioma": fila["idioma"] or "",
        "traducido": bool(fila["traducido"]),
        # Tracking de fuentes (ranking ponderado): masa de corroboración, velocidad, quién
        # abrió la historia y el timeline de outlets (JSON -> lista).
        "peso_fuentes": float(fila["peso_fuentes"] or 0.0),
        "velocidad": float(fila["velocidad"] or 0.0),
        "primera_fuente": fila["primera_fuente"] or "",
        "primera_fuente_nombre": fila["primera_fuente_nombre"] or "",
        "fuentes_detalle": _detalle_fuentes_a_lista(fila["fuentes_detalle"]),
        "creado": fila["creado"] or "",
        "actualizado": fila["actualizado"] or "",
    }


def upsert_noticia_cluster(cluster: dict[str, Any]) -> dict[str, Any]:
    """Crea o actualiza un cluster por `id` (idempotente). Devuelve el cluster persistido.

    Si falta `id`, lo genera. `idiomas` se serializa a JSON. `creado` se fija solo en el alta;
    `actualizado` siempre se sella al instante actual. Los agregados (`n_items`/`n_fuentes`/
    `senal`/`score`/`breaking`/`titulo`/...) los calcula el dominio (`clustering`) y aquí solo
    se persisten. `estado`/`contenido_id` se fijan SOLO en el alta: un upsert posterior NUNCA
    los pisa (mutarlos es trabajo exclusivo de `actualizar_noticia_cluster`; protege contra el
    TOCTOU daemon↔pipeline que revertía clusters promovidos a 'nuevo').
    """
    ahora = ahora_iso()
    cid = (cluster.get("id") or "").strip() or uuid.uuid4().hex[:12]
    idiomas = cluster.get("idiomas") or []
    if not isinstance(idiomas, list):
        idiomas = []
    fila = {
        "id": cid,
        "titulo": (cluster.get("titulo") or "")[:300],
        "resumen": (cluster.get("resumen") or "")[:2000],
        "marca": cluster.get("marca") or "",
        "categoria": cluster.get("categoria") or "",
        "geo": cluster.get("geo") or "",
        "clave": cluster.get("clave") or "",
        "n_items": int(cluster.get("n_items") or 0),
        "n_fuentes": int(cluster.get("n_fuentes") or 0),
        "idiomas": json.dumps(idiomas, ensure_ascii=False),
        "senal": int(cluster.get("senal") or 0),
        "score": float(cluster.get("score") or 0.0),
        # Explicación del score (la escribe el daemon al puntuar; el dict público la trae como
        # dict, aquí se serializa a JSON). SÍ entra al SET de conflicto: cada re-puntuación la
        # refresca junto al score (si no, la razón explicaría un score viejo).
        "score_razon": (cluster.get("score_razon") or "")[:500],
        "score_desglose": _desglose_a_json(cluster.get("score_desglose")),
        "breaking": int(cluster.get("breaking") or 0),
        "primer_visto": cluster.get("primer_visto") or "",
        "ultimo_visto": cluster.get("ultimo_visto") or "",
        "estado": cluster.get("estado") or "nuevo",
        "contenido_id": cluster.get("contenido_id") or "",
        # Verificación: la recalcula el clustering en cada upsert (sí entra al SET de conflicto).
        "verificacion": cluster.get("verificacion") or "unica_fuente",
        # Traducción: el ALTA la nace vacía; el paso de traducción la escribe aparte
        # (`marcar_cluster_traducido`). NO entra al SET de conflicto, así un recalc del cluster
        # NO pisa una traducción ya hecha (best-effort, persistente entre barridos).
        "titulo_es": cluster.get("titulo_es") or "",
        "resumen_es": cluster.get("resumen_es") or "",
        "titulo_original": cluster.get("titulo_original") or "",
        "idioma": cluster.get("idioma") or "",
        "traducido": 1 if cluster.get("traducido") else 0,
        # Tracking de fuentes: los recalcula el clustering en cada barrido (SÍ entran al SET
        # de conflicto, como el score: si no, explicarían una corroboración vieja).
        "peso_fuentes": float(cluster.get("peso_fuentes") or 0.0),
        "velocidad": float(cluster.get("velocidad") or 0.0),
        "primera_fuente": cluster.get("primera_fuente") or "",
        "primera_fuente_nombre": cluster.get("primera_fuente_nombre") or "",
        "fuentes_detalle": _detalle_fuentes_a_json(cluster.get("fuentes_detalle")),
        "creado": cluster.get("creado") or ahora,
        "actualizado": ahora,
    }
    # En conflicto por id, actualiza casi todo MENOS `id`/`creado`, los campos de TRADUCCIÓN
    # (que escribe `marcar_cluster_traducido`) y `estado`/`contenido_id` (que muta SOLO
    # `actualizar_noticia_cluster`): un recalc del daemon con datos leídos ANTES de que el
    # pipeline promoviera la historia (TOCTOU daemon↔pipeline) ya no puede revertir un cluster
    # 'usado' a 'nuevo' ni borrar su enlace al tema (lo que duplicaba el tema en el tablero).
    _NO_PISAR = (
        "id", "creado", "titulo_es", "resumen_es", "titulo_original", "idioma", "traducido",
        "estado", "contenido_id",
    )
    actualizables = [c for c in _COLS_NOTICIA_CLUSTER if c not in _NO_PISAR]
    set_clause = ", ".join(f"{c} = excluded.{c}" for c in actualizables)
    marcadores = ", ".join("?" for _ in _COLS_NOTICIA_CLUSTER)
    con = _conectar()
    try:
        con.execute(
            f"INSERT INTO noticias_clusters ({', '.join(_COLS_NOTICIA_CLUSTER)}) "
            f"VALUES ({marcadores}) "
            f"ON CONFLICT (id) DO UPDATE SET {set_clause}",  # noqa: S608 -- columnas de allowlist
            tuple(fila[c] for c in _COLS_NOTICIA_CLUSTER),
        )
        con.commit()
    finally:
        con.close()
    return obtener_noticia_cluster(cid) or _fila_a_noticia_cluster(fila)


def listar_noticia_clusters(
    *,
    marca: str | None = None,
    desde: str | None = None,
    estado: str | None = None,
    limite: int = 50,
    desplazamiento: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Historias filtrables, MÁS RELEVANTES primero (`score` desc) + total.

    Filtros: `marca` ('' / None = todas), `desde` (ISO; `ultimo_visto >= desde`), `estado`. Orden
    `score DESC, ultimo_visto DESC` (jerarquización por el algoritmo de ponderación; recencia como
    desempate). Ya NO se filtra por `categoria` (la jerarquización es por marca/línea editorial).
    Devuelve `(clusters, total)`.
    """
    condiciones: list[str] = []
    params: list[Any] = []
    if marca:
        condiciones.append("marca = ?")
        params.append(marca)
    if desde:
        condiciones.append("ultimo_visto >= ?")
        params.append(desde)
    if estado:
        condiciones.append("estado = ?")
        params.append(estado)
    where = (" WHERE " + " AND ".join(condiciones)) if condiciones else ""
    sql = (
        f"{_SELECT_NOTICIA_CLUSTER}{where} "
        "ORDER BY score DESC, ultimo_visto DESC, id DESC LIMIT ? OFFSET ?"
    )
    con = _conectar()
    try:
        filas = con.execute(  # noqa: S608 -- condiciones de allowlist; valores parametrizados
            sql, (*params, max(1, int(limite)), max(0, int(desplazamiento)))
        ).fetchall()
        fila_total = con.execute(  # noqa: S608 -- idem
            f"SELECT COUNT(*) AS n FROM noticias_clusters{where}", tuple(params)
        ).fetchone()
    finally:
        con.close()
    total = int(fila_total["n"]) if fila_total is not None else 0
    return [_fila_a_noticia_cluster(f) for f in filas], total


def obtener_noticia_cluster(cluster_id: str) -> dict[str, Any] | None:
    """Una historia por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_NOTICIA_CLUSTER} WHERE id = ?", (cluster_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_noticia_cluster(fila) if fila is not None else None


def cluster_por_contenido(contenido_id: str) -> dict[str, Any] | None:
    """La historia que se promovió a un tema del pipeline (`contenido_id` -> cluster), o None.

    Lookup REVERSO del enlace que sella `crear_tema_de_cluster` (cluster.contenido_id apunta al
    tema). La vista de pipelines lo usa para mostrar la PROCEDENCIA IA del tema (corroboración,
    score, verificación) en las etapas Jerarquización/Ingesta. Si por algún motivo varias
    historias apuntaran al mismo tema (no debería), gana la actualizada más recientemente.
    """
    if not contenido_id:
        return None
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_NOTICIA_CLUSTER} WHERE contenido_id = ? "
            "ORDER BY actualizado DESC, id DESC LIMIT 1",
            (contenido_id,),
        ).fetchone()
    finally:
        con.close()
    return _fila_a_noticia_cluster(fila) if fila is not None else None


def clusters_por_contenidos(contenido_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Mapa `contenido_id -> historia` para un lote de temas (1 query; los "" se ignoran).

    Versión por LOTE de `cluster_por_contenido` para la LISTA de pipelines (evita N consultas).
    Un tema que no nació de una historia no aparece en el mapa. Ante empates (varias historias
    por tema, no debería), gana la primera que devuelve la consulta (orden `actualizado` desc).
    """
    ids = [i for i in dict.fromkeys(contenido_ids) if i]
    if not ids:
        return {}
    marcadores = ",".join("?" for _ in ids)
    con = _conectar()
    try:
        filas = con.execute(  # noqa: S608 -- marcadores parametrizados; ids deduplicados/saneados
            f"{_SELECT_NOTICIA_CLUSTER} WHERE contenido_id IN ({marcadores}) "
            "ORDER BY actualizado DESC, id DESC",
            tuple(ids),
        ).fetchall()
    finally:
        con.close()
    out: dict[str, dict[str, Any]] = {}
    for fila in filas:
        cluster = _fila_a_noticia_cluster(fila)
        cid = cluster["contenido_id"]
        if cid and cid not in out:  # la primera (más reciente) gana
            out[cid] = cluster
    return out


def actualizar_noticia_cluster(
    cluster_id: str,
    *,
    estado: str | None = None,
    contenido_id: str | None = None,
) -> dict[str, Any] | None:
    """Edita `estado` / `contenido_id` de una historia (None si no existe)."""
    cambios: dict[str, Any] = {}
    if estado is not None:
        cambios["estado"] = estado
    if contenido_id is not None:
        cambios["contenido_id"] = contenido_id
    if not cambios:
        return obtener_noticia_cluster(cluster_id)
    cambios["actualizado"] = ahora_iso()
    asignaciones = [f"{k} = ?" for k in cambios]
    params: list[Any] = [*cambios.values(), cluster_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE noticias_clusters SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
    finally:
        con.close()
    return obtener_noticia_cluster(cluster_id)


def clusters_recientes(ventana_h: int, marca: str | None = None) -> list[dict[str, Any]]:
    """Clusters cuya `ultimo_visto` cae dentro de la ventana reciente (para asignación).

    El daemon de ingesta carga estos para decidir a cuál unir un item nuevo (clustering
    incremental ACOTADO por la ventana: nunca re-cluster el archivo entero). Excluye los
    `descartado` (no se reabren). `marca` opcional acota a una marca. Orden `ultimo_visto` desc.
    """
    corte = iso_utc(datetime.now(UTC) - timedelta(hours=max(1, int(ventana_h))))
    condiciones = ["ultimo_visto >= ?", "estado <> 'descartado'"]
    params: list[Any] = [corte]
    if marca:
        condiciones.append("marca = ?")
        params.append(marca)
    where = " WHERE " + " AND ".join(condiciones)
    con = _conectar()
    try:
        filas = con.execute(  # noqa: S608 -- condiciones de allowlist; valores parametrizados
            f"{_SELECT_NOTICIA_CLUSTER}{where} ORDER BY ultimo_visto DESC",
            tuple(params),
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_noticia_cluster(f) for f in filas]


def clusters_extranjeros_sin_traducir(
    ventana_h: int, *, min_score: float = 0.0, limite: int = 40
) -> list[dict[str, Any]]:
    """Clusters EXTRANJEROS recientes aún sin traducir (Ola D), para el paso de traducción.

    Selecciona clusters con `traducido = 0`, `idioma` no vacío y distinto de español
    (no empieza por 'es'), `score >= min_score`, `ultimo_visto` dentro de la ventana, y estado
    distinto de `descartado`. MÁS RELEVANTES primero (`score DESC`), `limite` acota el lote por
    barrido (el backlog se procesa en barridos sucesivos; sin tope artificial). PURA salvo I/O.
    """
    corte = iso_utc(datetime.now(UTC) - timedelta(hours=max(1, int(ventana_h))))
    con = _conectar()
    try:
        filas = con.execute(
            f"{_SELECT_NOTICIA_CLUSTER} WHERE traducido = 0 AND idioma <> '' "
            # `es%%`: el `%` literal va DOBLADO porque psycopg interpreta `%` como inicio de
            # placeholder (el shim `?`->`%s` no escapa los `%` del SQL). En Postgres `%%`->`%`
            # (un comodín LIKE); en SQLite `%%` son dos comodines contiguos (equivalentes a uno).
            "AND idioma NOT LIKE 'es%%' AND score >= ? AND ultimo_visto >= ? "
            "AND estado <> 'descartado' "
            "ORDER BY score DESC, ultimo_visto DESC LIMIT ?",
            (float(min_score), corte, max(1, int(limite))),
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_noticia_cluster(f) for f in filas]


def marcar_cluster_traducido(
    cluster_id: str,
    *,
    titulo_es: str,
    resumen_es: str,
    titulo_original: str = "",
) -> dict[str, Any] | None:
    """Guarda la traducción ES de un cluster y lo marca `traducido=1` (Ola D). Best-effort.

    Conserva `idioma` (ya fijado por el clustering) y guarda el `titulo_original` para mostrar
    "traducido de {idioma}". No toca los agregados ni el estado. None si el cluster no existe.
    """
    con = _conectar()
    try:
        cur = con.execute(
            "UPDATE noticias_clusters SET titulo_es = ?, resumen_es = ?, titulo_original = ?, "
            "traducido = 1, actualizado = ? WHERE id = ?",
            (
                (titulo_es or "")[:300],
                (resumen_es or "")[:2000],
                (titulo_original or "")[:300],
                ahora_iso(),
                cluster_id,
            ),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
    finally:
        con.close()
    return obtener_noticia_cluster(cluster_id)


def items_de_cluster(cluster_id: str, *, limite: int = 200) -> list[dict[str, Any]]:
    """Items de archivo de una historia, MÁS RECIENTES primero (`capturado_en` desc)."""
    con = _conectar()
    try:
        filas = con.execute(
            f"{_SELECT_NOTICIA_ITEM} WHERE cluster_id = ? "
            "ORDER BY capturado_en DESC, creado DESC, id DESC LIMIT ?",
            (cluster_id, max(1, int(limite))),
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_noticia_item(f) for f in filas]


def items_sin_cluster(desde: str, limite: int) -> list[dict[str, Any]]:
    """Items de archivo recientes SIN cluster asignado (para el paso de clustering del daemon).

    Filtra `cluster_id = ''` y `capturado_en >= desde` (ventana reciente: clustering acotado,
    nunca el archivo entero). MÁS ANTIGUOS primero, para agrupar en orden cronológico (el
    primero de una historia funda el cluster; los siguientes se unen). `limite` acota el trabajo.
    """
    con = _conectar()
    try:
        filas = con.execute(
            f"{_SELECT_NOTICIA_ITEM} WHERE cluster_id = '' AND capturado_en >= ? "
            "ORDER BY capturado_en ASC, creado ASC, id ASC LIMIT ?",
            (desde, max(1, int(limite))),
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_noticia_item(f) for f in filas]


def asignar_cluster_item(item_id: str, cluster_id: str) -> None:
    """Fija `noticias_items.cluster_id` de un item (best-effort, una escritura)."""
    con = _conectar()
    try:
        con.execute(
            "UPDATE noticias_items SET cluster_id = ? WHERE id = ?",
            (cluster_id, item_id),
        )
        con.commit()
    finally:
        con.close()


def asignar_cluster_items(asignaciones: dict[str, list[str]]) -> None:
    """Fija `cluster_id` para LOTES de items en UNA conexión: un UPDATE por cluster (IN (...)).

    `asignaciones` = `{cluster_id: [item_ids]}`. Sustituye el UPDATE-por-item del paso de
    clustering (~cientos de round-trips por barrido) por un round-trip por cluster tocado.
    Idempotente y best-effort: ids inexistentes simplemente no actualizan nada.
    """
    pares = {
        cid: [i for i in dict.fromkeys(ids) if i]
        for cid, ids in asignaciones.items()
        if cid
    }
    pares = {cid: ids for cid, ids in pares.items() if ids}
    if not pares:
        return
    con = _conectar()
    try:
        for cid, ids in pares.items():
            marcadores = ",".join("?" for _ in ids)
            con.execute(
                f"UPDATE noticias_items SET cluster_id = ? WHERE id IN ({marcadores})",  # noqa: S608 -- marcadores parametrizados
                (cid, *ids),
            )
        con.commit()
    finally:
        con.close()


def limpiar_items_cluster_colgante() -> int:
    """REPARA items cuyo `cluster_id` apunta a un cluster que ya no existe: los devuelve a ''.

    Si el proceso muere entre asignar `cluster_id` a los items y persistir el cluster (o un
    cluster se borró dejando items detrás), esos items quedaban invisibles PARA SIEMPRE (ni
    `items_sin_cluster` ni `items_de_cluster` los recogían). Re-ponerlos a '' los devuelve al
    paso de clustering (si siguen en la ventana) o los deja a tiro del GC (si ya no). Solo toca
    items `estado='nuevo'` (los usados/descartados conservan su rastro). Devuelve nº reparados.
    """
    con = _conectar()
    try:
        cur = con.execute(
            "UPDATE noticias_items SET cluster_id = '' "
            "WHERE estado = 'nuevo' AND cluster_id <> '' "
            "AND cluster_id NOT IN (SELECT id FROM noticias_clusters)"
        )
        con.commit()
        return cur.rowcount or 0
    finally:
        con.close()


def actualizar_scores_clusters(scores: dict[str, float | dict[str, Any]]) -> int:
    """Actualiza el `score` (+ su explicación + `actualizado`) de un lote de clusters en una conexión.

    Para el RE-SCORE periódico de la ventana (la frescura decae con el tiempo aunque no entren
    items nuevos): toca únicamente el score y su explicación, sin pisar agregados ni estado.
    Cada valor puede ser un float (solo score; la explicación persistida se conserva) o un dict
    `{score, score_razon?, score_desglose?}` para refrescar también la razón/el desglose (si no,
    la razón explicaría un score viejo). Devuelve nº filas.
    """
    ahora = ahora_iso()
    n = 0
    con = _conectar()
    try:
        for cid, valor in scores.items():
            if not cid:
                continue
            if isinstance(valor, dict):
                cur = con.execute(
                    "UPDATE noticias_clusters SET score = ?, score_razon = ?, "
                    "score_desglose = ?, actualizado = ? WHERE id = ?",
                    (
                        float(valor.get("score") or 0.0),
                        (str(valor.get("score_razon") or ""))[:500],
                        _desglose_a_json(valor.get("score_desglose")),
                        ahora,
                        cid,
                    ),
                )
            else:
                cur = con.execute(
                    "UPDATE noticias_clusters SET score = ?, actualizado = ? WHERE id = ?",
                    (float(valor), ahora, cid),
                )
            n += cur.rowcount or 0
        con.commit()
    finally:
        con.close()
    return n


def marcar_items_cluster_usados(cluster_id: str, contenido_id: str) -> None:
    """Marca TODOS los items de un cluster como `usado` + enlaza el `contenido_id` (una escritura)."""
    con = _conectar()
    try:
        con.execute(
            "UPDATE noticias_items SET estado = 'usado', contenido_id = ? "
            "WHERE cluster_id = ? AND estado <> 'descartado'",
            (contenido_id, cluster_id),
        )
        con.commit()
    finally:
        con.close()



# --- Tipos de fuente (catálogo) ------------------------------------------- #
# `fuentes_rss` es la ÚNICA tabla de fuentes (la fuente de verdad del motor de ingesta); la
# API la presenta como catálogo de tipo 'rss'. Esta allowlist deja la puerta a los tipos de
# aportación (idea/interna) que hoy producen items del tablero, no filas de fuente.
_TIPOS_FUENTE: tuple[str, ...] = ("rss", "idea", "interna")



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
    """Total de fuentes de algoritmo (para decidir si sembrar las semilla)."""
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
