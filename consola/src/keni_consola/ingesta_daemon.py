"""Daemon del MOTOR DE INGESTA PERSISTENTE (Ola A).

PROBLEMA QUE RESUELVE
=====================
El Radar v1 descargaba feeds EN VIVO por petición y con tope (30 items/feed): cobertura a
medias. Este daemon invierte el modelo: SIEMPRE activo, sondea en background los feeds
VENCIDOS (cadencia por feed/categoría), PERSISTE cada artículo en `noticias_items` (archivo a
nivel de artículo, dedup por (fuente_id, clave)) y programa el próximo sondeo. La UI/Plan leen
del store; nadie golpea la red por request.

SEGURO POR DISEÑO
=================
  - GATEADO EN VIVO: solo sondea con `KENI_INGESTA=1` (def OFF para CI/tests; ON en prod).
    El hilo arranca SIEMPRE y comprueba el flag cada ciclo (toggle en caliente).
  - SOLO LECTURA EXTERNA: descarga feeds RSS públicos (guard SSRF de `http_feed`) y persiste.
    No publica, no genera, no llama a `claude -p`.
  - ESCALABLE: tope de feeds por barrido (`KENI_INGESTA_BATCH`), descargas en paralelo
    ACOTADAS (`KENI_INGESTA_WORKERS`) y cadencia por feed -> escala a cientos de feeds.
  - BACKOFF: un feed que falla incrementa `errores_seguidos` y se pausa
    `intervalo * 2^errores` (con tope). En éxito se resetea.
  - SINGLE-FLIGHT cross-proceso (advisory lock): un segundo barrido solapado (deploy, varios
    daemons) no duplica trabajo; sale sin hacer nada.
  - BEST-EFFORT: ningún feed que falle aborta el barrido; se loguea y se sigue.

La lógica de planificación (`planificar_proximo`) es PURA: decide el `proximo_sondeo`,
`errores_seguidos` y `pausado_hasta` a partir del resultado, sin reloj ni BD (testeable).
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from . import agencias, config, daemon_util, db, generaciones, marcas, relevancia_marca, repos
from .dominio import (
    clustering,
    fusion_semantica,
    http_feed,
    ingesta,
    perfil_editorial,
    traduccion,
)

_log = logging.getLogger("keni_consola.ingesta_daemon")

# Tick corto: apagar aplica en <= esto y un feed vencido se recoge pronto.
_TICK_SEG = 30.0

# Tope de items a CLUSTERIZAR por barrido: el clustering es best-effort y ACOTADO. Si un
# barrido inserta más, el resto queda sin cluster y se recoge en el siguiente tick (siguen
# en la ventana). Evita un barrido caro tras un arranque en frío con miles de items pendientes.
_CLUSTER_BATCH = 500


def _intervalo_feed(feed: dict[str, Any]) -> int:
    """Intervalo (segundos) de un feed: su `intervalo_min` (>0) o el default por categoría."""
    propio = int(feed.get("intervalo_min") or 0)
    if propio > 0:
        return propio
    return config.ingesta_intervalo_categoria(str(feed.get("categoria") or ""))


def planificar_proximo(
    *,
    ahora: datetime,
    intervalo_seg: int,
    error: bool,
    errores_previos: int,
    backoff_tope_seg: int = config.INGESTA_BACKOFF_TOPE_SEG,
) -> dict[str, Any]:
    """Calcula la planificación tras un sondeo (PURA: sin reloj propio ni BD).

    En ÉXITO: resetea el contador de errores y programa `proximo_sondeo = ahora + intervalo`,
    sin pausa de backoff.
    En ERROR: incrementa `errores_seguidos` y pausa `pausado_hasta = ahora +
    min(intervalo * 2^errores, tope)` (backoff exponencial acotado). `proximo_sondeo` se fija a
    la misma pausa, de modo que el feed no se vuelve a elegir hasta que expire.

    Devuelve `{proximo_sondeo, errores_seguidos, pausado_hasta}` con ISO 8601 UTC.
    """
    intervalo = max(1, int(intervalo_seg))
    if not error:
        proximo = ahora + timedelta(seconds=intervalo)
        return {
            "proximo_sondeo": proximo.isoformat(),
            "errores_seguidos": 0,
            "pausado_hasta": "",
        }
    errores = max(0, int(errores_previos)) + 1
    # 2^errores acotado para no desbordar; el tope final lo pone `backoff_tope_seg`.
    factor = 2 ** min(errores, 20)
    espera = min(intervalo * factor, max(intervalo, int(backoff_tope_seg)))
    reanuda = ahora + timedelta(seconds=espera)
    return {
        "proximo_sondeo": reanuda.isoformat(),
        "errores_seguidos": errores,
        "pausado_hasta": reanuda.isoformat(),
    }


def _sondear_feed(
    feed: dict[str, Any], *, max_items: int
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Sondea UN feed: devuelve (feed, items_construidos, salud). No persiste (lo hace el barrido).

    Pensado para `http_feed.mapear_en_paralelo`: una función pura-de-red por feed que nunca
    lanza (la degradación honesta la hace `ingesta.items_de_feed`, que captura los fallos).
    """
    items, salud = ingesta.items_de_feed(feed, max_items=max_items)
    return feed, items, salud


def _palabras_relevancia(marca: str, perfil_activo: bool) -> frozenset[str]:
    """Keywords de relevancia de la marca: perfil editorial (Haiku) si está activo y existe; si no,
    el vocabulario semilla de `relevancia_marca`. Centraliza la elección perfil-vs-semilla."""
    if perfil_activo and marca:
        perfil = perfil_editorial.palabras(marca)
        if perfil:
            return perfil
    return relevancia_marca.palabras_de_marca(marca or None)


def _rendimiento_top_lineas() -> tuple[set[str], dict[str, str], list[dict[str, Any]]]:
    """Precalcula (1 vez por barrido) las líneas TOP por engagement y el catálogo de líneas.

    Gateado por `KENI_RENDIMIENTO_RANKING` (def OFF). Best-effort: ante cualquier fallo (sin
    métricas, sin Metricool) devuelve vacío y la señal queda inerte. Devuelve
    `(nombres_top, {etiqueta_id: nombre}, etiquetas_vertical)`.
    """
    if not config.rendimiento_ranking_activo():
        return set(), {}, []
    try:
        from . import metricas_linea
        from .dominio import rendimiento_tema

        data = metricas_linea.lineas_y_origenes("mes", None, None)
        top = rendimiento_tema.lineas_top(
            data.get("lineas", []),
            minimo_piezas=config.rendimiento_min_piezas(),
            n=config.rendimiento_top_n(),
        )
        etiquetas = [e for e in repos.listar_etiquetas(clase="vertical") if e.get("id")]
        id_a_nombre = {e["id"]: (e.get("nombre") or "") for e in etiquetas}
        return top, id_a_nombre, etiquetas
    except Exception:  # noqa: BLE001 -- la señal de rendimiento es opcional; nunca rompe la ingesta
        _log.warning("ingesta_daemon: no se pudo calcular el rendimiento por línea (señal inerte).", exc_info=True)
        return set(), {}, []


def _rendimiento_bonus(
    cluster: dict[str, Any],
    top_lineas: set[str],
    vert_id_a_nombre: dict[str, str],
    vert_etiquetas: list[dict[str, Any]],
) -> float:
    """Bonus [0,1] de una historia: 1.0 si su línea (clasificación léxica) está en el top. 0 si no."""
    from .dominio import clasificador_lineas, rendimiento_tema

    texto = f"{cluster.get('titulo', '')} {cluster.get('resumen', '')}"
    lid = clasificador_lineas.clasificar(texto, vert_etiquetas)
    nombre = vert_id_a_nombre.get(lid or "", "")
    return rendimiento_tema.bonus_de_historia(nombre, top_lineas)


def _registrar_actividad_ia(marca: str, etiqueta: str, salida: str) -> None:
    """Sella una GENERACIÓN-actividad (`tipo='noticias-ia'`) de un paso IA del pool (best-effort).

    Hace VISIBLES en «Actividad IA» los pasos Haiku del pool de noticias —fusión de historias
    (dedup) y encaje editorial— que antes corrían mudos. Es un registro ya COMPLETADO (no encola
    trabajo: el Haiku ya corrió); `salida` es el detalle humano de lo ocurrido. Un fallo al
    registrar NUNCA aborta el barrido: la actividad es observabilidad, no parte del trabajo.
    """
    try:
        generaciones.crear(
            {
                "tipo": "noticias-ia",
                "marca": marca,
                "etiqueta": etiqueta,
                "salida": (salida or "")[:4000],
                "estado": generaciones.ESTADO_COMPLETADO,
                "fase": generaciones.FASE_COMPLETADO,
                "fecha_fin": datetime.now(UTC).isoformat(),
            }
        )
    except Exception:  # noqa: BLE001 -- la actividad es best-effort; nunca rompe la ingesta
        _log.warning("ingesta_daemon: no se pudo registrar actividad IA (%s).", etiqueta, exc_info=True)


def paso_clustering() -> dict[str, Any]:
    """Agrupa en HISTORIAS los items recientes SIN cluster. Best-effort, ACOTADO a la ventana.

    Incremental: NO re-cluster el archivo entero. Carga (1) los clusters cuya `ultimo_visto`
    está en la ventana (`KENI_CLUSTER_VENTANA_H`) y (2) hasta `_CLUSTER_BATCH` items recientes
    sin `cluster_id`, en orden cronológico. Para cada item: lo une al cluster reciente que casa
    (misma url canónica o título fuzzy ≥ `KENI_CLUSTER_UMBRAL`) o crea uno nuevo. Al final,
    recalcula y `upsert`ea SOLO los clusters tocados (puntuándolos con su vocabulario de marca).

    Devuelve `{items, clusters_nuevos, clusters_tocados}`. Un fallo de un item se loguea y no
    aborta el paso. PURA la decisión (`clustering.asignar`); aquí solo orquesta I/O.
    """
    ventana_h = config.cluster_ventana_h()
    umbral = config.cluster_umbral()
    breaking_fuentes = config.cluster_breaking_fuentes()
    breaking_ventana_h = config.cluster_breaking_ventana_h()
    fuentes_baja = config.fuentes_baja_confianza()
    pesos = config.score_pesos()  # pesos editables del algoritmo de ponderación
    perfil_activo = config.perfil_editorial_activo()  # relevancia desde la línea editorial (Haiku)
    perfil_ttl = config.perfil_editorial_ttl_horas()
    perfil_refrescadas: set[str] = set()  # 1 refresco por marca por barrido (Haiku acotado)
    # Señal de RENDIMIENTO (Fase 2c, gateada): líneas top por engagement + clasificación léxica.
    top_lineas, vert_id_a_nombre, vert_etiquetas = _rendimiento_top_lineas()

    ahora = datetime.now(UTC)
    desde = (ahora - timedelta(hours=ventana_h)).isoformat()
    pendientes = repos.items_sin_cluster(desde, _CLUSTER_BATCH)
    if not pendientes:
        return {"items": 0, "clusters_nuevos": 0, "clusters_tocados": 0}

    # Índice de trabajo de los clusters de la ventana (vivo durante el paso, para que items del
    # MISMO barrido se unan entre sí sin re-consultar la BD). id -> dict-resumen del cluster.
    recientes = repos.clusters_recientes(ventana_h)
    indice: dict[str, dict[str, Any]] = {c["id"]: c for c in recientes}
    tocados: set[str] = set()
    nuevos = 0

    for item in pendientes:
        try:
            destino = clustering.asignar(item, list(indice.values()), umbral=umbral)
            if destino is None:
                # Cluster nuevo: lo funda este item (un cluster en blanco con su identidad).
                destino = uuid.uuid4().hex[:12]
                indice[destino] = {
                    "id": destino,
                    "titulo": item.get("titulo") or "",
                    "clave": clustering.clave_cluster(item),
                    "estado": "nuevo",
                    "contenido_id": "",
                    "creado": "",
                }
                nuevos += 1
            repos.asignar_cluster_item(item["id"], destino)
            tocados.add(destino)
        except Exception:  # noqa: BLE001 -- un item problemático no aborta el paso
            _log.exception("ingesta_daemon: fallo al clusterizar el item %s.", item.get("id"))

    # Recalcula + puntúa SOLO los clusters tocados, leyendo sus items ya persistidos.
    for cid in tocados:
        try:
            base = indice.get(cid) or repos.obtener_noticia_cluster(cid) or {"id": cid}
            items_cluster = repos.items_de_cluster(cid, limite=500)
            if not items_cluster:
                continue
            recalc = clustering.recalcular(
                base,
                items_cluster,
                breaking_fuentes=breaking_fuentes,
                breaking_ventana_h=breaking_ventana_h,
                fuentes_baja_confianza=fuentes_baja,
            )
            marca_c = recalc.get("marca") or ""
            # Relevancia desde la LÍNEA EDITORIAL (perfil Haiku) si está activa; si no, semilla.
            if perfil_activo and marca_c and marca_c not in perfil_refrescadas:
                perfil_refrescadas.add(marca_c)
                perfil_editorial.refrescar_si_corresponde(
                    marca_c, ttl_horas=perfil_ttl, ahora=ahora,
                    al_refrescar=lambda m, kws: _registrar_actividad_ia(
                        m,
                        f"Encaje editorial — {marcas.etiqueta_de(m)}: {len(kws)} temas clave",
                        "Perfil de cobertura de la marca extraído de su línea editorial por IA "
                        "(Haiku), para puntuar qué noticias le encajan:\n\n" + ", ".join(kws),
                    ),
                )
            palabras = _palabras_relevancia(marca_c, perfil_activo)
            # Señal de rendimiento (Fase 2c): 1 si la historia cae en una línea top por engagement.
            if top_lineas:
                recalc["bonus_rendimiento"] = _rendimiento_bonus(
                    recalc, top_lineas, vert_id_a_nombre, vert_etiquetas
                )
            score, _razon = clustering.puntuar(
                recalc, palabras_marca=palabras, ahora=ahora, pesos=pesos
            )
            recalc["score"] = score
            repos.upsert_noticia_cluster(recalc)
        except Exception:  # noqa: BLE001 -- recalcular un cluster no aborta el paso
            _log.exception("ingesta_daemon: fallo al recalcular el cluster %s.", cid)

    return {"items": len(pendientes), "clusters_nuevos": nuevos, "clusters_tocados": len(tocados)}


def _fusionar_grupo(
    ids: list[str],
    por_id: dict[str, dict[str, Any]],
    *,
    pesos: Any,
    breaking_fuentes: int,
    breaking_ventana_h: int,
    fuentes_baja: frozenset[str],
    perfil_activo: bool,
    ahora: datetime,
) -> bool:
    """Funde un grupo de historias en la CANÓNICA (más fuentes, desempate por score).

    Reasigna los items de las absorbidas a la canónica, borra las absorbidas (vacías) y recalcula
    + repuntúa la canónica (n_fuentes/score reales). Devuelve True si fusionó (≥2 historias).
    """
    clusters = [por_id[i] for i in ids if i in por_id]
    if len(clusters) < 2:
        return False
    canon = max(clusters, key=lambda c: (int(c.get("n_fuentes") or 0), float(c.get("score") or 0.0)))
    canon_id = str(canon["id"])
    for c in clusters:
        cid = str(c["id"])
        if cid == canon_id:
            continue
        for it in repos.items_de_cluster(cid, limite=500):
            repos.asignar_cluster_item(it["id"], canon_id)
        repos.borrar_noticia_cluster(cid)
    items = repos.items_de_cluster(canon_id, limite=500)
    if not items:
        return False
    base = repos.obtener_noticia_cluster(canon_id) or canon
    recalc = clustering.recalcular(
        base, items,
        breaking_fuentes=breaking_fuentes,
        breaking_ventana_h=breaking_ventana_h,
        fuentes_baja_confianza=fuentes_baja,
    )
    palabras = _palabras_relevancia(recalc.get("marca") or "", perfil_activo)
    recalc["score"], _razon = clustering.puntuar(recalc, palabras_marca=palabras, ahora=ahora, pesos=pesos)
    repos.upsert_noticia_cluster(recalc)
    return True


def paso_fusion_semantica(*, ejecutor: fusion_semantica.Ejecutor | None = None) -> dict[str, Any]:
    """Funde con IA (Haiku) las historias del MISMO evento, por marca. Gateado `KENI_FUSION_SEMANTICA`.

    Por marca, manda hasta `KENI_FUSION_SEMANTICA_MAX` historias `nuevo` recientes a Haiku para que
    agrupe las del mismo acontecimiento, y funde cada grupo (`_fusionar_grupo`). Best-effort: un
    fallo por marca/grupo se loguea y no aborta el paso. Devuelve `{grupos, fusionadas}`.
    """
    if not config.fusion_semantica_activa():
        return {"grupos": 0, "fusionadas": 0}
    ventana_h = config.cluster_ventana_h()
    maximo = config.fusion_semantica_max()
    pesos = config.score_pesos()
    breaking_fuentes = config.cluster_breaking_fuentes()
    breaking_ventana_h = config.cluster_breaking_ventana_h()
    fuentes_baja = config.fuentes_baja_confianza()
    perfil_activo = config.perfil_editorial_activo()
    ahora = datetime.now(UTC)

    try:
        recientes_todas = repos.clusters_recientes(ventana_h)
    except Exception:  # noqa: BLE001 -- sin pool legible, no se funde nada
        _log.exception("ingesta_daemon: no se pudieron leer historias para fusión.")
        return {"grupos": 0, "fusionadas": 0}

    por_marca: dict[str, list[dict[str, Any]]] = {}
    for c in recientes_todas:
        if (c.get("estado") or "nuevo") == "nuevo":
            por_marca.setdefault(c.get("marca") or "", []).append(c)

    grupos_total = 0
    fusionadas_total = 0
    for marca_f, recientes in por_marca.items():
        if len(recientes) < 2:
            continue
        lote = recientes[:maximo]
        por_id = {str(c["id"]): c for c in lote}
        try:
            grupos = fusion_semantica.proponer_fusiones(lote, ejecutor=ejecutor)
        except Exception:  # noqa: BLE001 -- un fallo de Haiku por marca no aborta el paso
            _log.exception("ingesta_daemon: fallo proponiendo fusiones de una marca.")
            continue
        grupos_marca = 0
        fusionadas_marca = 0
        descripciones: list[str] = []
        for grupo in grupos:
            try:
                if _fusionar_grupo(
                    grupo, por_id, pesos=pesos, breaking_fuentes=breaking_fuentes,
                    breaking_ventana_h=breaking_ventana_h, fuentes_baja=fuentes_baja,
                    perfil_activo=perfil_activo, ahora=ahora,
                ):
                    grupos_total += 1
                    fusionadas_total += len(grupo) - 1
                    grupos_marca += 1
                    fusionadas_marca += len(grupo) - 1
                    titulos = [str((por_id.get(i) or {}).get("titulo") or i).strip() for i in grupo]
                    descripciones.append(" + ".join(t for t in titulos if t))
            except Exception:  # noqa: BLE001 -- una fusión problemática no aborta el paso
                _log.exception("ingesta_daemon: fallo al fundir un grupo de historias.")
        # Actividad IA: deja constancia VISIBLE de la dedup semántica por marca (qué se unió).
        if grupos_marca:
            _registrar_actividad_ia(
                marca_f,
                f"Fusión de historias — {marcas.etiqueta_de(marca_f)}: "
                f"{fusionadas_marca} absorbida(s) en {grupos_marca} grupo(s)",
                "Historias del mismo acontecimiento unidas por IA (dedup semántico):\n\n"
                + "\n".join(f"• {d}" for d in descripciones),
            )
    if grupos_total:
        _log.info(
            "ingesta_daemon: fusión semántica: %d grupo(s), %d historia(s) absorbida(s).",
            grupos_total, fusionadas_total,
        )
    return {"grupos": grupos_total, "fusionadas": fusionadas_total}


def paso_traduccion(*, ejecutor: traduccion.Ejecutor | None = None) -> dict[str, Any]:
    """Traduce a ES los clusters EXTRANJEROS recientes sin traducir. Best-effort, ACOTADO.

    Selecciona hasta `KENI_TRAD_LOTE` clusters con `idioma != es`, `score >= KENI_TRAD_MIN_SCORE`,
    `traducido=0` dentro de la ventana reciente; los traduce+tropicaliza a MX con UNA sola
    llamada a Haiku (`traduccion.traducir_items`) y persiste `titulo_es`/`resumen_es` +
    `titulo_original` + `traducido=1` por cluster. Sin tope artificial total: cada barrido
    procesa un lote del backlog; lo que falte se coge en barridos sucesivos.

    `ejecutor` inyectable (tests): si es None se usa el subproceso real. Devuelve
    `{traducidos, candidatos}`. Un fallo de la traducción NO aborta el barrido.
    """
    ventana_h = config.cluster_ventana_h()
    min_score = config.trad_min_score()
    lote = config.trad_lote()
    candidatos = repos.clusters_extranjeros_sin_traducir(
        ventana_h, min_score=min_score, limite=lote
    )
    if not candidatos:
        return {"traducidos": 0, "candidatos": 0}

    # Payload para Haiku: id + titulo + resumen ORIGINALES (en idioma extranjero).
    items = [
        {"id": c["id"], "titulo": c.get("titulo") or "", "resumen": c.get("resumen") or ""}
        for c in candidatos
    ]
    traducciones = traduccion.traducir_items(items, ejecutor=ejecutor)
    por_id = {str(t.get("id") or ""): t for t in traducciones}
    originales = {c["id"]: c for c in candidatos}

    traducidos = 0
    for cid, original in originales.items():
        t = por_id.get(cid)
        if not t:
            continue
        try:
            repos.marcar_cluster_traducido(
                cid,
                titulo_es=str(t.get("titulo_es") or original.get("titulo") or ""),
                resumen_es=str(t.get("resumen_es") or ""),
                titulo_original=str(original.get("titulo") or ""),
            )
            traducidos += 1
        except Exception:  # noqa: BLE001 -- persistir una traducción no aborta el paso
            _log.exception("ingesta_daemon: fallo al guardar la traducción del cluster %s.", cid)

    return {"traducidos": traducidos, "candidatos": len(candidatos)}


# Agencias CONFIGURADAS a sondear en cada barrido. Lista fija para el piloto (no hay config
# per-marca ni env de "qué agencias"); `agencias.traer_items` degrada honesto a `[]` sin
# credencial, así que sondear una agencia no configurada es un no-op sin red ni coste.
_AGENCIAS = ("reuters", "afp")


def paso_agencias() -> dict[str, Any]:
    """Ingiere las AGENCIAS configuradas (Reuters/AFP) al pool `noticias_items`. Best-effort.

    Para cada agencia: `agencias.traer_items()` (que devuelve `[]` honesto sin credencial, sin
    tocar la red), se construye la fila de pool con `ingesta.noticia_item_de_agencia` y se
    persiste por el MISMO sumidero que el RSS (`repos.crear_noticias_items`, idempotente por
    UNIQUE(fuente_id, clave)). Una agencia que falla (red/auth/forma) se loguea y NO aborta el
    barrido ni las demás agencias. Sin credenciales vivas (AFP usa un token placeholder) el
    paso es un no-op honesto. Devuelve `{items}` con cuántas filas nuevas se insertaron.
    """
    nuevos = 0
    for ag in _AGENCIAS:
        try:
            crudos = agencias.traer_items(ag)
            pool = [
                fila
                for it in crudos
                if (fila := ingesta.noticia_item_de_agencia(it, agencia=ag)) is not None
            ]
            if pool:
                nuevos += repos.crear_noticias_items(pool)
        except Exception:  # noqa: BLE001 -- una agencia no debe tumbar el barrido
            _log.exception("ingesta_daemon: fallo ingiriendo la agencia %s.", ag)
    return {"items": nuevos}


def ejecutar_barrido() -> dict[str, Any]:
    """Un barrido: elige feeds vencidos, los sondea en paralelo, persiste y replanifica.

    Devuelve un resumen `{feeds, items_nuevos, errores}`. Best-effort de punta a punta: un
    feed que falla se anota y no aborta el resto; un fallo de persistencia de un feed se loguea
    y se sigue. Single-flight cross-proceso vía advisory lock (no duplica con un barrido
    solapado).
    """
    with db.lock_barrido("ingesta") as ok:
        if not ok:
            _log.debug("ingesta_daemon: otro barrido en curso; salgo (single-flight).")
            return {"feeds": 0, "items_nuevos": 0, "errores": 0}

        ahora = datetime.now(UTC)
        feeds = repos.feeds_vencidos(ahora.isoformat(), config.ingesta_batch())
        # Excepción por marca de "Crear noticias" (KENI_INGESTA::<marca>): salta los feeds de
        # marcas apagadas a mano. Los COMPARTIDOS (marca vacía) siempre corren —`marca_apagada`
        # con marca vacía es False. Best-effort: no toca clustering/traducción (pasos globales).
        feeds = [f for f in feeds if not config.marca_apagada(config.ENV_INGESTA, str(f.get("marca") or ""))]
        if not feeds:
            return {"feeds": 0, "items_nuevos": 0, "errores": 0}

        max_items = config.ingesta_max_items()
        resultados = http_feed.mapear_en_paralelo(
            lambda f: _sondear_feed(f, max_items=max_items),
            feeds,
            max_workers=config.ingesta_workers(),
        )

        max_errores = config.ingesta_max_errores()
        items_nuevos = 0
        errores = 0
        auto_desactivados = 0
        for feed, items, salud in resultados:
            hubo_error = bool(salud.get("error"))
            if hubo_error:
                errores += 1
            insertadas = 0
            if items:
                try:
                    insertadas = repos.crear_noticias_items(items)
                except Exception:  # noqa: BLE001 -- persistir un feed no debe abortar el barrido
                    _log.exception(
                        "ingesta_daemon: fallo al persistir items de feed %s.", feed.get("id")
                    )
            items_nuevos += insertadas

            plan = planificar_proximo(
                ahora=ahora,
                intervalo_seg=_intervalo_feed(feed),
                error=hubo_error,
                errores_previos=int(feed.get("errores_seguidos") or 0),
            )
            # AUTO-DESACTIVADO (Ola D): al alcanzar `max_errores` errores seguidos, el daemon
            # apaga el feed (activo=0 + desactivado_auto=1) y deja de sondearlo (queda visible
            # para reactivar). En ÉXITO se resetea (activo=1, desactivado_auto=0). Si no hay
            # cambio de estado, se pasan None para NO pisar `activo` (gestión manual del equipo).
            activo: bool | None = None
            desactivado_auto: bool | None = None
            if not hubo_error:
                # Recuperación: si el feed venía marcado auto-desactivado, lo reactiva.
                if feed.get("desactivado_auto"):
                    activo = True
                    desactivado_auto = False
            elif plan["errores_seguidos"] >= max_errores:
                activo = False
                desactivado_auto = True
                auto_desactivados += 1

            try:
                repos.registrar_sondeo_feed(
                    feed["id"],
                    conteo=int(salud.get("conteo") or 0),
                    error=str(salud.get("error") or ""),
                    proximo_sondeo=plan["proximo_sondeo"],
                    errores_seguidos=plan["errores_seguidos"],
                    pausado_hasta=plan["pausado_hasta"],
                    activo=activo,
                    desactivado_auto=desactivado_auto,
                )
            except Exception:  # noqa: BLE001 -- registrar salud es best-effort
                _log.exception(
                    "ingesta_daemon: fallo al registrar el sondeo de feed %s.", feed.get("id")
                )

        # Paso de AGENCIAS (Fase 2): vuelca al MISMO pool las notas de Reuters/AFP CONFIGURADAS,
        # antes del clustering para que se agrupen en el mismo barrido. Gateado por KENI_INGESTA
        # (este daemon) — sin toggle propio. Best-effort + no-op honesto sin credencial: nunca
        # rompe el barrido de RSS. Sus items entran al conteo de `items_nuevos`.
        agencias_resumen: dict[str, Any] = {"items": 0}
        try:
            agencias_resumen = paso_agencias()
        except Exception:  # noqa: BLE001 -- las agencias son aditivas; nunca tumban la ingesta
            _log.exception("ingesta_daemon: fallo en el paso de agencias.")
        items_nuevos += agencias_resumen["items"]

        # Paso de CLUSTERING (Ola B): agrupa en historias los items recién insertados (y
        # cualquier reciente sin cluster), recalcula y puntúa. Best-effort: un fallo del paso
        # se loguea y NO invalida el barrido de ingesta (que ya persistió los artículos).
        cluster_resumen: dict[str, Any] = {"items": 0, "clusters_nuevos": 0, "clusters_tocados": 0}
        try:
            cluster_resumen = paso_clustering()
        except Exception:  # noqa: BLE001 -- el clustering es aditivo; nunca tumba la ingesta
            _log.exception("ingesta_daemon: fallo en el paso de clustering.")

        # Paso de FUSIÓN SEMÁNTICA (Fase 2b): funde con Haiku las historias del mismo evento que el
        # léxico no unió (titulares distintos). Gateado `KENI_FUSION_SEMANTICA` (def OFF). Best-effort.
        try:
            paso_fusion_semantica()
        except Exception:  # noqa: BLE001 -- la fusión es aditiva; nunca tumba la ingesta
            _log.exception("ingesta_daemon: fallo en el paso de fusión semántica.")

        # Paso de TRADUCCIÓN (Ola D): traduce a ES, por lotes, los clusters EXTRANJEROS recientes
        # aún sin traducir. Best-effort: un fallo (subproceso, JSON, etc.) se loguea y NO invalida
        # el barrido. Sin tope artificial: cada barrido procesa un lote del backlog.
        trad_resumen: dict[str, Any] = {"traducidos": 0, "candidatos": 0}
        try:
            trad_resumen = paso_traduccion()
        except Exception:  # noqa: BLE001 -- la traducción es aditiva; nunca tumba la ingesta
            _log.exception("ingesta_daemon: fallo en el paso de traducción.")

        _log.info(
            "ingesta_daemon: barrido de %d feed(s) -> %d artículo(s) nuevo(s) (%d de agencias), "
            "%d error(es), %d auto-desactivado(s); clustering: %d item(s), %d historia(s) "
            "nueva(s); traducción: %d historia(s).",
            len(feeds), items_nuevos, agencias_resumen["items"], errores, auto_desactivados,
            cluster_resumen["items"], cluster_resumen["clusters_nuevos"],
            trad_resumen["traducidos"],
        )
        return {
            "feeds": len(feeds),
            "items_nuevos": items_nuevos,
            "errores": errores,
            "auto_desactivados": auto_desactivados,
            "agencias": agencias_resumen,
            "clustering": cluster_resumen,
            "traduccion": trad_resumen,
        }


def iniciar_ingesta() -> threading.Thread:
    """Arranca el hilo daemon del motor de ingesta (GATEADO EN VIVO).

    El hilo arranca SIEMPRE y comprueba `KENI_INGESTA` en cada ciclo: encender/apagar en
    runtime aplica sin reiniciar. Tick corto (30s) para recoger feeds vencidos pronto y ser
    responsivo al apagado. El hilo es daemon; un fallo de barrido se loguea y NO lo mata.
    """

    def bucle() -> None:
        daemon_util.bucle_gateado(
            activo_fn=config.gate_maquina(config.ingesta_activa),
            intervalo_seg_fn=lambda: _TICK_SEG,
            sweep_fn=ejecutar_barrido,
            tick_seg=_TICK_SEG,
            log=_log,
        )

    hilo = threading.Thread(target=bucle, name="ingesta-daemon", daemon=True)
    hilo.start()
    estado = "ACTIVO" if config.ingesta_activa() else "EN ESPERA (KENI_INGESTA off)"
    _log.info(
        "Ingesta daemon %s, tick %.0fs (batch=%d, workers=%d, max_items=%d).",
        estado, _TICK_SEG, config.ingesta_batch(), config.ingesta_workers(),
        config.ingesta_max_items(),
    )
    return hilo
