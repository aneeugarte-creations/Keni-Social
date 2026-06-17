"""Persistencia — dominio noticias: clustering de historias (noticias_clusters)."""
from __future__ import annotations

from .._db_comun import UTC, Any, _conectar, datetime, json, timedelta, uuid
from ..tiempo import ahora_iso, iso_utc
from ._comun import (
    _desglose_a_dict,
    _desglose_a_json,
    _detalle_fuentes_a_json,
    _detalle_fuentes_a_lista,
)
from .items import _SELECT_NOTICIA_ITEM, _fila_a_noticia_item

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
    "publicacion_id",
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
    "marca_clasificada_por_ia",
    "verificacion_fuente",
    "verificar_hallazgos",
    "tema_macro",
    "creado",
    "actualizado",
)
_SELECT_NOTICIA_CLUSTER = f"SELECT {', '.join(_COLS_NOTICIA_CLUSTER)} FROM noticias_clusters"
# Verificación por corroboración (Ola D): valores válidos de `noticias_clusters.verificacion`.
VERIFICACIONES_CLUSTER: tuple[str, ...] = ("corroborada", "unica_fuente", "dudosa")


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
        "publicacion_id": fila["publicacion_id"] or "",
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
        # Encaje de marca por IA (ADR 0011): la marca la asignó el clasificador Haiku.
        "marca_clasificada_por_ia": bool(fila["marca_clasificada_por_ia"]),
        # Verificación (verificación de la fuente) sobre la HISTORIA (ADR 0011 F3): verificacion +
        # hallazgos; la admisión solo materializa contenido de las verificadas.
        "verificacion_fuente": fila["verificacion_fuente"] or "",
        "verificar_hallazgos": fila["verificar_hallazgos"] or "",
        # Macro-evento (Fase A): la historia pertenece a un gran evento (p. ej. "Cumbre del
        # G7") junto a otros clusters, SIN fusionarse con ellos. "" = sin macro-evento.
        "tema_macro": fila["tema_macro"] or "",
        "creado": fila["creado"] or "",
        "actualizado": fila["actualizado"] or "",
    }


def upsert_noticia_cluster(cluster: dict[str, Any]) -> dict[str, Any]:
    """Crea o actualiza un cluster por `id` (idempotente). Devuelve el cluster persistido.

    Si falta `id`, lo genera. `idiomas` se serializa a JSON. `creado` se fija solo en el alta;
    `actualizado` siempre se sella al instante actual. Los agregados (`n_items`/`n_fuentes`/
    `senal`/`score`/`breaking`/`titulo`/...) los calcula el dominio (`clustering`) y aquí solo
    se persisten. `estado`/`publicacion_id` se fijan SOLO en el alta: un upsert posterior NUNCA
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
        "publicacion_id": cluster.get("publicacion_id") or "",
        # Verificación: la recalcula el clustering en cada upsert (sí entra al SET de conflicto).
        "verificacion": cluster.get("verificacion") or "unica_fuente",
        # Traducción: el ALTA la nace vacía; el paso de traducir la escribe aparte
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
        # Encaje de marca por IA (ADR 0011): valor del ALTA; en conflicto NO se pisa (está en
        # `_NO_PISAR`), lo sella aparte `marcar_cluster_marca_ia` — como `traducido`. Así un
        # recalc (merge/fusión/rescore) sin el flag no borra el encaje IA ya hecho.
        "marca_clasificada_por_ia": 1 if cluster.get("marca_clasificada_por_ia") else 0,
        # Verificación (verificación de la fuente) sobre la historia (ADR 0011 F3): valor del ALTA; en
        # conflicto NO se pisa (está en `_NO_PISAR`), lo sella aparte `marcar_cluster_verificacion`. Así un
        # recalc (merge/fusión/rescore) sin el verificacion no borra una verificación ya hecha.
        "verificacion_fuente": cluster.get("verificacion_fuente") or "",
        "verificar_hallazgos": cluster.get("verificar_hallazgos") or "",
        # Macro-evento (Fase A): valor del ALTA; en conflicto NO se pisa (está en `_NO_PISAR`),
        # lo sella aparte `marcar_clusters_tema_macro` — como `traducido`. Así un recalc del
        # daemon sin el tema_macro no borra una asignación a macro-evento ya hecha.
        "tema_macro": cluster.get("tema_macro") or "",
        "creado": cluster.get("creado") or ahora,
        "actualizado": ahora,
    }
    # En conflicto por id, actualiza casi todo MENOS `id`/`creado`, los campos de TRADUCCIÓN
    # (que escribe `marcar_cluster_traducido`) y `estado`/`publicacion_id` (que muta SOLO
    # `actualizar_noticia_cluster`): un recalc del daemon con datos leídos ANTES de que el
    # pipeline promoviera la historia (TOCTOU daemon↔pipeline) ya no puede revertir un cluster
    # 'usado' a 'nuevo' ni borrar su enlace al tema (lo que duplicaba el tema en el tablero).
    _NO_PISAR = (
        "id", "creado", "titulo_es", "resumen_es", "titulo_original", "idioma", "traducido",
        "estado", "publicacion_id", "marca_clasificada_por_ia", "verificacion_fuente", "verificar_hallazgos",
        "tema_macro",
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
    desempate). Devuelve `(clusters, total)`.
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


def cluster_por_contenido(publicacion_id: str) -> dict[str, Any] | None:
    """La historia que se promovió a un tema del pipeline (`publicacion_id` -> cluster), o None.

    Lookup REVERSO del enlace que sella `crear_tema_de_cluster` (cluster.publicacion_id apunta al
    tema). La vista de pipelines lo usa para mostrar la PROCEDENCIA IA del tema (corroboración,
    score, verificación) en las etapas Jerarquización/Ingesta. Si por algún motivo varias
    historias apuntaran al mismo tema (no debería), gana la actualizada más recientemente.
    """
    if not publicacion_id:
        return None
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_NOTICIA_CLUSTER} WHERE publicacion_id = ? "
            "ORDER BY actualizado DESC, id DESC LIMIT 1",
            (publicacion_id,),
        ).fetchone()
    finally:
        con.close()
    return _fila_a_noticia_cluster(fila) if fila is not None else None


def clusters_por_contenidos(publicacion_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Mapa `publicacion_id -> historia` para un lote de temas (1 query; los "" se ignoran).

    Versión por LOTE de `cluster_por_contenido` para la LISTA de pipelines (evita N consultas).
    Un tema que no nació de una historia no aparece en el mapa. Ante empates (varias historias
    por tema, no debería), gana la primera que devuelve la consulta (orden `actualizado` desc).
    """
    ids = [i for i in dict.fromkeys(publicacion_ids) if i]
    if not ids:
        return {}
    marcadores = ",".join("?" for _ in ids)
    con = _conectar()
    try:
        filas = con.execute(  # noqa: S608 -- marcadores parametrizados; ids deduplicados/depurados
            f"{_SELECT_NOTICIA_CLUSTER} WHERE publicacion_id IN ({marcadores}) "
            "ORDER BY actualizado DESC, id DESC",
            tuple(ids),
        ).fetchall()
    finally:
        con.close()
    out: dict[str, dict[str, Any]] = {}
    for fila in filas:
        cluster = _fila_a_noticia_cluster(fila)
        cid = cluster["publicacion_id"]
        if cid and cid not in out:  # la primera (más reciente) gana
            out[cid] = cluster
    return out


def actualizar_noticia_cluster(
    cluster_id: str,
    *,
    estado: str | None = None,
    publicacion_id: str | None = None,
) -> dict[str, Any] | None:
    """Edita `estado` / `publicacion_id` de una historia (None si no existe)."""
    cambios: dict[str, Any] = {}
    if estado is not None:
        cambios["estado"] = estado
    if publicacion_id is not None:
        cambios["publicacion_id"] = publicacion_id
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
    """Clusters EXTRANJEROS recientes aún sin traducir (Ola D), para el paso de traducir.

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


def marcar_cluster_marca_ia(cluster_id: str) -> None:
    """Sella `marca_clasificada_por_ia=1` (ADR 0011): la marca la asignó el clasificador IA.

    Aparte del upsert (la columna está en `_NO_PISAR`) para que un recalc posterior sin el flag
    no lo borre — mismo patrón que `marcar_cluster_traducido`. Best-effort: si el cluster no
    existe, no hace nada.
    """
    con = _conectar()
    try:
        con.execute(
            "UPDATE noticias_clusters SET marca_clasificada_por_ia = 1, actualizado = ? "
            "WHERE id = ?",
            (ahora_iso(), cluster_id),
        )
        con.commit()
    finally:
        con.close()


def marcar_cluster_verificacion(cluster_id: str, verificacion: str, hallazgos: str = "") -> None:
    """Sella la VERIFICACIÓN (verificación de la fuente) de la HISTORIA (ADR 0011 F3).

    Escribe `verificacion_fuente` (+ `verificar_hallazgos`) en el cluster ANTES de materializar contenido de
    producción: la admisión solo promueve las verificadas (`no_verificado`/`saltada`) y hereda
    el verificacion al `contenido`. Aparte del upsert (ambas columnas están en `_NO_PISAR`) para
    que un recalc del daemon sin el verificacion no lo borre — mismo patrón que
    `marcar_cluster_marca_ia`/`marcar_cluster_traducido`. Best-effort: si el cluster no existe,
    no hace nada.
    """
    con = _conectar()
    try:
        con.execute(
            "UPDATE noticias_clusters SET verificacion_fuente = ?, verificar_hallazgos = ?, actualizado = ? "
            "WHERE id = ?",
            (verificacion or "", hallazgos or "", ahora_iso(), cluster_id),
        )
        con.commit()
    finally:
        con.close()


def marcar_clusters_tema_macro(ids: list[str], tema: str) -> int:
    """Asigna el MACRO-EVENTO `tema` a un lote de clusters por id (Fase A). Devuelve nº filas.

    Agrupa varias HISTORIAS distintas bajo un mismo gran evento (p. ej. "Cumbre del G7") SIN
    fusionarlas: cada cluster conserva su identidad y solo comparte `tema_macro`. Aparte del
    upsert (la columna está en `_NO_PISAR`) para que un recalc posterior del daemon no la
    borre — mismo patrón que `marcar_cluster_marca_ia`/`marcar_cluster_traducido`. `ids` vacío
    -> 0 sin tocar BD. `tema` vacío desvincula los clusters del macro-evento.
    """
    pedidos = [i for i in dict.fromkeys(ids) if i]
    if not pedidos:
        return 0
    marcadores = ",".join("?" for _ in pedidos)
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE noticias_clusters SET tema_macro = ?, actualizado = ? "  # noqa: S608 -- marcadores parametrizados
            f"WHERE id IN ({marcadores})",
            (tema or "", ahora_iso(), *pedidos),
        )
        con.commit()
        return cur.rowcount or 0
    finally:
        con.close()


def contar_clusters_admision_verificacion(marca: str, estados: tuple[str, ...]) -> int:
    """Cuántas HISTORIAS `nuevo` de la marca están en la ADMISIÓN de verificación (ADR 0011 F3).

    La admisión son los clusters aún sin promover (`estado='nuevo'`) cuyo `verificacion_fuente` está en
    `estados` (p. ej. en_curso + verificadas-pendientes). Acota cuánta verificación se lanza por tick para
    que la verificación no recorra todo el pool: el presupuesto de verificación = tope en curso − admisión.
    0 ante cualquier fallo o `estados` vacío.
    """
    if not estados:
        return 0
    marcadores = ",".join("?" for _ in estados)
    con = _conectar()
    try:
        fila = con.execute(  # noqa: S608 -- marcadores parametrizados; estados de allowlist interna
            f"SELECT COUNT(*) AS n FROM noticias_clusters "
            f"WHERE marca = ? AND estado = 'nuevo' AND verificacion_fuente IN ({marcadores})",
            (marca, *estados),
        ).fetchone()
    finally:
        con.close()
    return int(fila["n"]) if fila is not None else 0


def reparar_verificacion_clusters_en_curso(umbral_iso: str) -> int:
    """Resetea a "" el `verificacion_fuente='en_curso'` atascado de los clusters (limpiador de verificación).

    Si una verificación de la fuente sobre un cluster se interrumpe (deploy/OOM/cuelgue), el cluster quedaría
    `en_curso` para siempre: ni se re-verificación ni se admite. Devuelve los `en_curso` más viejos que
    `umbral_iso` a "" para que el barrido los vuelva a verificar. Mismo patrón que
    `reparar_verificacion_en_curso_sueltos` sobre `contenido`. Devuelve cuántos corrigió.
    """
    con = _conectar()
    try:
        cur = con.execute(
            "UPDATE noticias_clusters SET verificacion_fuente = '', actualizado = ? "
            "WHERE verificacion_fuente = 'en_curso' AND actualizado <> '' AND actualizado < ?",
            (ahora_iso(), umbral_iso),
        )
        con.commit()
        return cur.rowcount or 0
    finally:
        con.close()


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


def cuerpos_de_cluster(cluster_id: str, *, limite: int = 200) -> dict[str, str]:
    """`{url: cuerpo}` de los items de un cluster que tengan cuerpo (content:encoded archivado).

    Consulta dedicada (NO pasa por `_fila_a_noticia_item`, que excluye el cuerpo del path
    caliente de listado): el pipeline la usa al promover una historia para redactar sobre el
    texto real de cada fuente. Solo devuelve los items con `cuerpo` y `url` no vacíos.
    """
    if not cluster_id:
        return {}
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT url, cuerpo FROM noticias_items "
            "WHERE cluster_id = ? AND cuerpo <> '' AND url <> '' "
            "ORDER BY capturado_en DESC, creado DESC, id DESC LIMIT ?",
            (cluster_id, max(1, int(limite))),
        ).fetchall()
    finally:
        con.close()
    return {(f["url"] or ""): (f["cuerpo"] or "") for f in filas if f["url"] and f["cuerpo"]}


def cluster_por_url_canonica(url_recortada: str, desde: str) -> str:
    """Cluster reciente que YA contiene un item con esta URL canónica (sin query); '' si no.

    Cruce exacto del clustering a nivel de ITEM: la `clave` del cluster solo guarda la url de
    su representativo, así que dos fuentes que enlazan el MISMO recurso podían no casar si el
    representativo era otro. `url_recortada` = `clustering.url_canonica_clustering` (host+path
    SIN query); los items guardan la canónica de dedup (CON query útil), por eso se cruza por
    igualdad o por prefijo `?`. Acotado a la ventana (`capturado_en >= desde`).
    """
    if not url_recortada:
        return ""
    con = _conectar()
    try:
        fila = con.execute(
            "SELECT cluster_id FROM noticias_items "
            "WHERE cluster_id <> '' AND capturado_en >= ? "
            "AND (url_canonica = ? OR url_canonica LIKE ?) "
            "ORDER BY capturado_en DESC LIMIT 1",
            (desde, url_recortada, url_recortada + "?%"),
        ).fetchone()
    finally:
        con.close()
    return str(fila["cluster_id"]) if fila is not None else ""


def items_sin_cluster(desde: str, limite: int) -> list[dict[str, Any]]:
    """Items de archivo recientes SIN cluster asignado (para el paso de agrupar del daemon).

    Filtra `cluster_id = ''`, `capturado_en >= desde` (ventana reciente: clustering acotado,
    nunca el archivo entero) y `estado <> 'descartado'`. MÁS ANTIGUOS primero, para agrupar en
    orden cronológico (el primero de una historia funda el cluster; los siguientes se unen).
    `limite` acota el trabajo.

    El filtro de descartados es COHERENTE con `marcar_items_cluster_usados`: un item apartado
    (p. ej. la gemela de un cajón que se descartó/borró en bloque) NO debe volver a clusterizar
    ni alimentar historias vivas; si no, el auto-feed lo convertiría en pieza igualmente.
    """
    con = _conectar()
    try:
        filas = con.execute(
            f"{_SELECT_NOTICIA_ITEM} WHERE cluster_id = '' AND capturado_en >= ? "
            "AND estado <> 'descartado' "
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
    agrupar (~cientos de round-trips por barrido) por un round-trip por cluster tocado.
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
    paso de agrupar (si siguen en la ventana) o los deja a tiro del GC (si ya no). Solo toca
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
    `{score, score_razon?, score_desglose?, breaking?, velocidad?}` para refrescar también la
    razón/el desglose y el flag breaking/velocidad VIVOS (anclados en ahora, decaen con el
    reloj; si no se refrescaran, el umbral trataría como última hora una historia de ayer).
    Devuelve nº filas.
    """
    ahora = ahora_iso()
    n = 0
    con = _conectar()
    try:
        for cid, valor in scores.items():
            if not cid:
                continue
            if isinstance(valor, dict):
                sets = ["score = ?", "score_razon = ?", "score_desglose = ?", "actualizado = ?"]
                params: list[Any] = [
                    float(valor.get("score") or 0.0),
                    (str(valor.get("score_razon") or ""))[:500],
                    _desglose_a_json(valor.get("score_desglose")),
                    ahora,
                ]
                if "breaking" in valor:
                    sets.append("breaking = ?")
                    params.append(int(valor.get("breaking") or 0))
                if "velocidad" in valor:
                    sets.append("velocidad = ?")
                    params.append(float(valor.get("velocidad") or 0.0))
                cur = con.execute(
                    f"UPDATE noticias_clusters SET {', '.join(sets)} WHERE id = ?",  # noqa: S608 -- columnas de allowlist
                    (*params, cid),
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


def marcar_items_cluster_usados(cluster_id: str, publicacion_id: str) -> None:
    """Marca TODOS los items de un cluster como `usado` + enlaza el `publicacion_id` (una escritura)."""
    con = _conectar()
    try:
        con.execute(
            "UPDATE noticias_items SET estado = 'usado', publicacion_id = ? "
            "WHERE cluster_id = ? AND estado <> 'descartado'",
            (publicacion_id, cluster_id),
        )
        con.commit()
    finally:
        con.close()
