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
  - GATEADO EN VIVO: solo sondea con `KENI_PIPELINE_SELECCION=1` (def OFF para CI/tests; ON en prod).
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
import time
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
from .tiempo import ahora_iso, iso_utc

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

    Devuelve `{proximo_sondeo, errores_seguidos, pausado_hasta}` en el canon UTC sin
    offset de `tiempo.iso_utc` (los compara `feeds_vencidos` como texto).
    """
    intervalo = max(1, int(intervalo_seg))
    if not error:
        proximo = ahora + timedelta(seconds=intervalo)
        return {
            "proximo_sondeo": iso_utc(proximo),
            "errores_seguidos": 0,
            "pausado_hasta": "",
        }
    errores = max(0, int(errores_previos)) + 1
    # 2^errores acotado para no desbordar; el tope final lo pone `backoff_tope_seg`.
    factor = 2 ** min(errores, 20)
    espera = min(intervalo * factor, max(intervalo, int(backoff_tope_seg)))
    reanuda = ahora + timedelta(seconds=espera)
    return {
        "proximo_sondeo": iso_utc(reanuda),
        "errores_seguidos": errores,
        "pausado_hasta": iso_utc(reanuda),
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
    el vocabulario semilla de `relevancia_marca`. Centraliza la elección perfil-vs-semilla.

    Respeta el toggle POR MARCA de `KENI_PIPELINE_RANKING`: una marca con el Ranking apagado
    vuelve al vocabulario SEMILLA aunque tenga un perfil Haiku cacheado (antes el toggle solo
    frenaba el refresco, pero el perfil viejo seguía mandando en el score).
    """
    if (
        perfil_activo and marca
        and not config.marca_apagada(config.ENV_PIPELINE_RANKING, marca)
    ):
        perfil = perfil_editorial.palabras(marca)
        if perfil:
            return perfil
    return relevancia_marca.palabras_de_marca(marca or None)


def _rendimiento_top_lineas(marca: str) -> tuple[set[str], dict[str, str], list[dict[str, Any]]]:
    """Precalcula (1 vez por marca y barrido) las líneas TOP por engagement DE ESA MARCA.

    Por MARCA (antes era global: las líneas top se calculaban con las métricas de TODAS las
    marcas, y el éxito de una marca premiaba historias de otra). Gateado por
    `KENI_RENDIMIENTO_RANKING` (def OFF). Best-effort: ante cualquier fallo (sin métricas, sin
    Metricool) devuelve vacío y la señal queda inerte. Devuelve
    `(nombres_top, {etiqueta_id: nombre}, etiquetas_vertical)`.
    """
    if not config.rendimiento_ranking_activo():
        return set(), {}, []
    try:
        from . import metricas_linea
        from .dominio import rendimiento_tema

        data = metricas_linea.lineas_y_origenes(
            "mes", marca or None, marcas.id_metricas_de(marca) if marca else None
        )
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


def _registrar_actividad_ia(marca: str, etiqueta: str, salida: str, *, prompt: str = "") -> None:
    """Sella una GENERACIÓN-actividad (`tipo='noticias-ia'`) de un paso IA del pool (best-effort).

    Hace VISIBLES en «Actividad IA» (y en la etapa Ranking del pipeline) los pasos Haiku del pool
    —fusión de historias (dedup) y encaje editorial— que antes corrían mudos. Es un registro ya
    COMPLETADO (no encola trabajo: el Haiku ya corrió). `prompt` y `salida` son los REALES de la
    llamada a Haiku (transparencia: qué se pidió y qué respondió token a token); si no se pasan,
    queda solo el resumen. Un fallo al registrar NUNCA aborta el barrido (es observabilidad).
    """
    try:
        generaciones.crear(
            {
                "tipo": "noticias-ia",
                "marca": marca,
                "etiqueta": etiqueta,
                "prompt": (prompt or "")[:20000],
                "salida": (salida or "")[:20000],
                "estado": generaciones.ESTADO_COMPLETADO,
                "fase": generaciones.FASE_COMPLETADO,
                "fecha_fin": ahora_iso(),
            }
        )
    except Exception:  # noqa: BLE001 -- la actividad es best-effort; nunca rompe la ingesta
        _log.warning("ingesta_daemon: no se pudo registrar actividad IA (%s).", etiqueta, exc_info=True)


def paso_clustering() -> dict[str, Any]:
    """Agrupa en HISTORIAS los items recientes SIN cluster. Best-effort, ACOTADO a la ventana.

    Incremental: NO re-cluster el archivo entero. Carga (1) los clusters cuya `ultimo_visto`
    está en la ventana (`KENI_CLUSTER_VENTANA_H`) y (2) hasta `_CLUSTER_BATCH` items recientes
    sin `cluster_id`, en orden cronológico. Para cada item: lo une al cluster reciente que casa
    (misma url canónica o título fuzzy ≥ `KENI_CLUSTER_UMBRAL`) o crea uno nuevo. La decisión
    usa `clustering.Asignador` (claves fuzzy precomputadas + blocking por tokens: O(items ×
    candidatos), no O(items × clusters)). Las asignaciones se escriben en LOTE (un UPDATE por
    cluster tocado, no uno por item). Al final, recalcula y `upsert`ea SOLO los clusters tocados
    (puntuándolos con su vocabulario de marca; si la marca dominante queda VACÍA —historias
    solo-Trends/agencias— se intenta el encaje por vocabulario de cada marca).

    Durabilidad: un cluster NUEVO se persiste (stub) ANTES de asignarle items, así un proceso
    que muera a mitad no deja items apuntando a un cluster que solo existía en memoria; además,
    al inicio se REPARAN los items con `cluster_id` colgante de barridos anteriores.

    Devuelve `{items, clusters_nuevos, clusters_tocados, clusters_ventana}` (`clusters_ventana`
    = los clusters de la ventana ya actualizados, para que el barrido los REUTILICE en la
    fusión/re-score sin re-leer la BD). Un fallo de un item se loguea y no aborta el paso.
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
    # Señal de RENDIMIENTO (Fase 2c, gateada): líneas top por engagement, POR MARCA y perezoso.
    rendimiento_activo = config.rendimiento_ranking_activo()
    rend_cache: dict[str, tuple[set[str], dict[str, str], list[dict[str, Any]]]] = {}

    # REPARACIÓN: items con `cluster_id` colgante (cluster que ya no existe, p. ej. proceso
    # muerto a mitad de un barrido antiguo) vuelven a '' y se re-clusterizan. Best-effort.
    try:
        reparados = repos.limpiar_items_cluster_colgante()
        if reparados:
            _log.info("ingesta_daemon: %d item(s) con cluster colgante reparados.", reparados)
    except Exception:  # noqa: BLE001 -- la reparación es best-effort; nunca aborta el paso
        _log.warning("ingesta_daemon: no se pudieron reparar items colgantes.", exc_info=True)

    ahora = datetime.now(UTC)
    desde = iso_utc(ahora - timedelta(hours=ventana_h))
    pendientes = repos.items_sin_cluster(desde, _CLUSTER_BATCH)
    if not pendientes:
        return {"items": 0, "clusters_nuevos": 0, "clusters_tocados": 0}

    # Índice de trabajo de los clusters de la ventana (vivo durante el paso, para que items del
    # MISMO barrido se unan entre sí sin re-consultar la BD). id -> dict-resumen del cluster.
    recientes = repos.clusters_recientes(ventana_h)
    indice: dict[str, dict[str, Any]] = {c["id"]: c for c in recientes}
    asignador = clustering.Asignador(recientes, umbral=umbral)
    tocados: set[str] = set()
    asignaciones: dict[str, list[str]] = {}  # cluster_id -> item_ids (escritura en lote)
    nuevos = 0

    for item in pendientes:
        try:
            destino = asignador.asignar(item)
            if destino is None:
                # Cluster nuevo: lo funda este item (un cluster en blanco con su identidad).
                # Se PERSISTE el stub ANTES de asignarle items (durabilidad ante caída).
                destino = uuid.uuid4().hex[:12]
                stub = {
                    "id": destino,
                    "titulo": item.get("titulo") or "",
                    "clave": clustering.clave_cluster(item),
                    "estado": "nuevo",
                    "contenido_id": "",
                    "creado": "",
                }
                repos.upsert_noticia_cluster(stub)
                indice[destino] = stub
                asignador.agregar(stub)
                nuevos += 1
            asignaciones.setdefault(destino, []).append(item["id"])
            tocados.add(destino)
        except Exception:  # noqa: BLE001 -- un item problemático no aborta el paso
            _log.exception("ingesta_daemon: fallo al clusterizar el item %s.", item.get("id"))

    # Asignación en LOTE: un UPDATE por cluster tocado (antes, uno por item: ~500 round-trips).
    try:
        repos.asignar_cluster_items(asignaciones)
    except Exception:  # noqa: BLE001 -- si el lote falla, los items siguen sin cluster (reintento próximo tick)
        _log.exception("ingesta_daemon: fallo al asignar items a clusters (lote).")
        return {
            "items": len(pendientes), "clusters_nuevos": nuevos, "clusters_tocados": 0,
            "clusters_ventana": list(indice.values()),
        }

    vocabularios: dict[str, frozenset[str]] | None = None  # perezoso (encaje sin marca)

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
            if not marca_c:
                # Encaje por VOCABULARIO: una historia formada SOLO por items sin marca
                # (Trends/agencias) quedaba con marca='' e INVISIBLE para la promoción por
                # marca. Se le asigna la marca cuyo vocabulario mejor casa (sobre umbral);
                # si ninguna pasa, queda sin marca como antes (honesto).
                if vocabularios is None:
                    vocabularios = {
                        m: _palabras_relevancia(m, perfil_activo) for m in marcas.ids()
                    }
                marca_c = clustering.marca_por_vocabulario(recalc, vocabularios)
                if marca_c:
                    recalc["marca"] = marca_c
            # Relevancia desde la LÍNEA EDITORIAL (perfil Haiku) si está activa (maestro + por-marca:
            # el toggle "Ranking"); si no, semilla.
            if (
                perfil_activo and marca_c and marca_c not in perfil_refrescadas
                and not config.marca_apagada(config.ENV_PIPELINE_RANKING, marca_c)
            ):
                perfil_refrescadas.add(marca_c)
                perfil_editorial.refrescar_si_corresponde(
                    marca_c, ttl_horas=perfil_ttl, ahora=ahora,
                    al_refrescar=lambda m, kws, prompt, salida: _registrar_actividad_ia(
                        m,
                        f"Encaje editorial — {marcas.etiqueta_de(m)}: {len(kws)} temas clave",
                        salida,  # la respuesta REAL de Haiku (keywords del perfil)
                        prompt=prompt,
                    ),
                )
            palabras = _palabras_relevancia(marca_c, perfil_activo)
            # Señal de rendimiento (Fase 2c): 1 si la historia cae en una línea top POR MARCA.
            if rendimiento_activo and marca_c:
                if marca_c not in rend_cache:
                    rend_cache[marca_c] = _rendimiento_top_lineas(marca_c)
                top_lineas, vert_id_a_nombre, vert_etiquetas = rend_cache[marca_c]
                if top_lineas:
                    recalc["bonus_rendimiento"] = _rendimiento_bonus(
                        recalc, top_lineas, vert_id_a_nombre, vert_etiquetas
                    )
            score, _razon = clustering.puntuar(
                recalc, palabras_marca=palabras, ahora=ahora, pesos=pesos
            )
            recalc["score"] = score
            indice[cid] = repos.upsert_noticia_cluster(recalc)
        except Exception:  # noqa: BLE001 -- recalcular un cluster no aborta el paso
            _log.exception("ingesta_daemon: fallo al recalcular el cluster %s.", cid)

    return {
        "items": len(pendientes),
        "clusters_nuevos": nuevos,
        "clusters_tocados": len(tocados),
        "clusters_ventana": list(indice.values()),
    }


# Re-score periódico de la ventana: como MÍNIMO cada tantos segundos se repuntúa la ventana
# completa, aunque no entren items nuevos (la frescura decae con el reloj).
_RESCORE_INTERVALO_SEG = 900.0
_ultimo_rescore = 0.0  # time.monotonic() de la última pasada completada


def paso_rescore(
    clusters_ventana: list[dict[str, Any]] | None = None, *, forzar: bool = False
) -> dict[str, Any]:
    """Re-puntúa periódicamente las historias `nuevo` de la ventana (score que ENVEJECE).

    DECISIÓN (score congelado): la FRESCURA (peso 0.25) solo se evaluaba al re-puntuar — es
    decir, cuando un item nuevo tocaba el cluster — y el score quedaba PERSISTIDO; el listado,
    la promoción CI y el GC ordenan/filtran por ese score obsoleto, así que una historia de
    hace 3 días podía outrankear a las nuevas para siempre. De las dos opciones (A: re-score
    periódico de la ventana en el barrido; B: persistir `score_base` sin frescura y computar
    `score_base + w·frescura(ultimo_visto, now())` en cada ORDER BY) elegimos la A: `puntuar`
    es pura, los clusters de la ventana ya se cargan por barrido, y el score persistido sigue
    siendo LA verdad única que leen UI/promoción/GC sin tocar esquema ni consultas.

    Throttle: como mucho una pasada por `_RESCORE_INTERVALO_SEG` (la frescura decae despacio).
    Solo escribe los scores que CAMBIAN (≥ 0.001), en una sola conexión. Best-effort.
    """
    global _ultimo_rescore
    ahora_mono = time.monotonic()
    if not forzar and _ultimo_rescore and (ahora_mono - _ultimo_rescore) < _RESCORE_INTERVALO_SEG:
        return {"revisados": 0, "actualizados": 0}
    try:
        clusters = (
            clusters_ventana
            if clusters_ventana is not None
            else repos.clusters_recientes(config.cluster_ventana_h())
        )
    except Exception:  # noqa: BLE001 -- sin pool legible no se re-puntúa nada (no actualiza el throttle)
        _log.warning("ingesta_daemon: no se pudo leer la ventana para el re-score.", exc_info=True)
        return {"revisados": 0, "actualizados": 0}

    pesos = config.score_pesos()
    perfil_activo = config.perfil_editorial_activo()
    rendimiento_activo = config.rendimiento_ranking_activo()
    ahora = datetime.now(UTC)
    palabras_cache: dict[str, frozenset[str]] = {}
    rend_cache: dict[str, tuple[set[str], dict[str, str], list[dict[str, Any]]]] = {}
    cambios: dict[str, float] = {}
    revisados = 0
    for c in clusters:
        if (c.get("estado") or "nuevo") != "nuevo":
            continue  # usados/descartados ya no compiten en el ranking
        revisados += 1
        try:
            marca_c = str(c.get("marca") or "")
            if marca_c not in palabras_cache:
                palabras_cache[marca_c] = _palabras_relevancia(marca_c, perfil_activo)
            cl = dict(c)
            # `bonus_rendimiento` no se persiste: se recomputa si la señal está activa.
            if rendimiento_activo and marca_c:
                if marca_c not in rend_cache:
                    rend_cache[marca_c] = _rendimiento_top_lineas(marca_c)
                top_lineas, vert_id_a_nombre, vert_etiquetas = rend_cache[marca_c]
                if top_lineas:
                    cl["bonus_rendimiento"] = _rendimiento_bonus(
                        cl, top_lineas, vert_id_a_nombre, vert_etiquetas
                    )
            score, _razon = clustering.puntuar(
                cl, palabras_marca=palabras_cache[marca_c], ahora=ahora, pesos=pesos
            )
            if abs(score - float(c.get("score") or 0.0)) >= 0.001:
                cambios[str(c["id"])] = score
        except Exception:  # noqa: BLE001 -- una historia problemática no aborta la pasada
            _log.exception("ingesta_daemon: fallo al re-puntuar el cluster %s.", c.get("id"))

    actualizados = 0
    if cambios:
        try:
            actualizados = repos.actualizar_scores_clusters(cambios)
        except Exception:  # noqa: BLE001 -- persistir el re-score es best-effort
            _log.exception("ingesta_daemon: fallo al persistir el re-score de la ventana.")
            return {"revisados": revisados, "actualizados": 0}
    _ultimo_rescore = ahora_mono
    if actualizados:
        _log.info("ingesta_daemon: re-score de la ventana: %d historia(s) repuntuadas.", actualizados)
    return {"revisados": revisados, "actualizados": actualizados}


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

    Salvaguardas:
      - ANTI-TOCTOU: antes de absorber, RE-LEE cada cluster absorbible; si entre la lectura del
        lote y ahora adquirió `contenido_id` o dejó de ser `nuevo` (el pipeline lo promovió),
        NO se absorbe (se conserva intacto).
      - SIN HUÉRFANOS: los items se reasignan en LOTES de 500 HASTA VACIAR el cluster (antes el
        tope de 500 dejaba items colgando del cluster borrado si había más).
    """
    clusters = [por_id[i] for i in ids if i in por_id]
    if len(clusters) < 2:
        return False
    canon = max(clusters, key=lambda c: (int(c.get("n_fuentes") or 0), float(c.get("score") or 0.0)))
    canon_id = str(canon["id"])
    absorbidas = 0
    for c in clusters:
        cid = str(c["id"])
        if cid == canon_id:
            continue
        # Re-verificación anti-TOCTOU: el absorbido pudo ser promovido entre lectura y fusión.
        actual = repos.obtener_noticia_cluster(cid)
        if actual is None:
            continue
        if (actual.get("contenido_id") or "") or (actual.get("estado") or "nuevo") != "nuevo":
            continue
        # Reasigna TODOS los items, por lotes, hasta vaciar (cota dura de seguridad: 100 lotes).
        for _ in range(100):
            lote = repos.items_de_cluster(cid, limite=500)
            if not lote:
                break
            repos.asignar_cluster_items({canon_id: [it["id"] for it in lote]})
        repos.borrar_noticia_cluster(cid)
        absorbidas += 1
    if not absorbidas:
        return False
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


def paso_fusion_semantica(
    *,
    ejecutor: fusion_semantica.Ejecutor | None = None,
    recientes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Funde con IA (Haiku) las historias del MISMO evento, por marca. Gateado `KENI_PIPELINE_FUSION`.

    Por marca, manda hasta `KENI_FUSION_SEMANTICA_MAX` historias `nuevo` recientes a Haiku para que
    agrupe las del mismo acontecimiento, y funde cada grupo (`_fusionar_grupo`). Best-effort: un
    fallo por marca/grupo se loguea y no aborta el paso. Devuelve `{grupos, fusionadas}`.

    `recientes` (opcional): los clusters de la ventana YA cargados por el paso de clustering del
    MISMO barrido (evita re-leer la BD). None = leer de `repos.clusters_recientes`.
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

    if recientes is not None:
        recientes_todas = recientes
    else:
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
        # Excepción por marca (toggle "Fusión"): si está apagada para esta marca, no se funde.
        if config.marca_apagada(config.ENV_PIPELINE_FUSION, marca_f):
            continue
        lote = recientes[:maximo]
        por_id = {str(c["id"]): c for c in lote}
        # Capturamos el PROMPT y la SALIDA reales de Haiku (para la transparencia de la actividad).
        haiku: dict[str, str] = {"prompt": "", "salida": ""}
        try:
            grupos = fusion_semantica.proponer_fusiones(
                lote, ejecutor=ejecutor,
                al_ejecutar=lambda p, s, _h=haiku: _h.update(prompt=p, salida=s),
            )
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
        # Actividad IA: deja constancia VISIBLE de la dedup semántica por marca, con el Haiku REAL
        # (prompt + salida) y un resumen humano de qué historias se unieron.
        if grupos_marca:
            resumen = (
                "Historias del mismo acontecimiento unidas por IA (dedup semántico):\n"
                + "\n".join(f"• {d}" for d in descripciones)
            )
            salida_real = haiku["salida"].strip()
            salida = (f"{salida_real}\n\n— — —\n{resumen}" if salida_real else resumen)
            _registrar_actividad_ia(
                marca_f,
                f"Fusión de historias — {marcas.etiqueta_de(marca_f)}: "
                f"{fusionadas_marca} absorbida(s) en {grupos_marca} grupo(s)",
                salida,
                prompt=haiku["prompt"],
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
        feeds = repos.feeds_vencidos(iso_utc(ahora), config.ingesta_batch())
        # Excepción por marca de "Crear noticias" (KENI_PIPELINE_SELECCION::<marca>): salta los feeds de
        # marcas apagadas a mano. Los COMPARTIDOS (marca vacía) siempre corren —`marca_apagada`
        # con marca vacía es False. Best-effort: no toca clustering/traducción (pasos globales).
        feeds = [f for f in feeds if not config.marca_apagada(config.ENV_PIPELINE_SELECCION, str(f.get("marca") or ""))]

        # OJO: sin feeds RSS vencidos el barrido NO termina aquí: los pasos post-RSS (agencias,
        # clustering, fusión, re-score, traducción) corren IGUAL. Antes un `return` temprano
        # dejaba los items de Trends/agencias sin clusterizar indefinidamente si ningún RSS
        # estaba vencido (Trends inserta por su propio daemon, fuera de este planificador).
        max_items = config.ingesta_max_items()
        resultados = []
        if feeds:
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
        # antes del clustering para que se agrupen en el mismo barrido. Gateado por KENI_PIPELINE_SELECCION
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
        # Ventana ya cargada/actualizada por el clustering (si la hay): se REUTILIZA en el
        # re-score y la fusión del mismo barrido, sin re-leer la BD.
        clusters_ventana = cluster_resumen.pop("clusters_ventana", None)

        # Paso de RE-SCORE (score que envejece): repuntúa periódicamente la ventana para que
        # la frescura DECAIGA aunque no entren items nuevos (ver `paso_rescore`). Best-effort.
        try:
            paso_rescore(clusters_ventana)
        except Exception:  # noqa: BLE001 -- el re-score es aditivo; nunca tumba la ingesta
            _log.exception("ingesta_daemon: fallo en el paso de re-score.")

        # Paso de FUSIÓN SEMÁNTICA (Fase 2b): funde con Haiku las historias del mismo evento que el
        # léxico no unió (titulares distintos). Gateado `KENI_PIPELINE_FUSION` (def OFF). Best-effort.
        try:
            paso_fusion_semantica(recientes=clusters_ventana)
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

    El hilo arranca SIEMPRE y comprueba `KENI_PIPELINE_SELECCION` en cada ciclo: encender/apagar en
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
    estado = "ACTIVO" if config.ingesta_activa() else "EN ESPERA (KENI_PIPELINE_SELECCION off)"
    _log.info(
        "Ingesta daemon %s, tick %.0fs (batch=%d, workers=%d, max_items=%d).",
        estado, _TICK_SEG, config.ingesta_batch(), config.ingesta_workers(),
        config.ingesta_max_items(),
    )
    return hilo
