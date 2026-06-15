"""Persistencia — dominio noticias: Fuentes RSS y pool de items vistos."""
from __future__ import annotations

from .._db_comun import UTC, Any, _conectar, datetime, timedelta, uuid
from ..tiempo import ahora_iso, hoy_utc, iso_utc

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

    Canon UTC sin offset (`tiempo.ahora_iso`); formato unificado.
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
    """GC del pool por RELEVANCIA (no por edad sola): borra la basura de baja relevancia.

    CONSERVADOR. Borra SOLO lo que no aporta y nadie va a trabajar:
      - clusters `estado='nuevo'`, SIN `contenido_id` (no llevados al tablero), de UNA sola fuente
        (`n_fuentes <= 1`), con `score < score_umbral` Y sin actividad reciente
        (`ultimo_visto < ahora - inactividad_horas`). Se CONSERVAN: usados/ligados a contenido,
        corroborados (multi-fuente), de score alto, o recientes.
      - items `estado='nuevo'`, SIN `contenido_id`, viejos (`capturado_en < cutoff`) y
        SUELTOS (sin cluster o cuyo cluster ya no existe — p. ej. recién purgado). Los items de
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
        # Tras borrar clusters, los items sueltos (cluster inexistente) caen en `cond_items`.
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
