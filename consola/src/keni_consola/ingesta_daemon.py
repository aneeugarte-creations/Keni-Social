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

from . import config, daemon_util, db, relevancia_marca, repos
from .dominio import clustering, http_feed, ingesta, traduccion

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
            palabras = relevancia_marca.palabras_de_marca(recalc.get("marca") or None)
            score, _razon = clustering.puntuar(recalc, palabras_marca=palabras, ahora=ahora)
            recalc["score"] = score
            repos.upsert_noticia_cluster(recalc)
        except Exception:  # noqa: BLE001 -- recalcular un cluster no aborta el paso
            _log.exception("ingesta_daemon: fallo al recalcular el cluster %s.", cid)

    return {"items": len(pendientes), "clusters_nuevos": nuevos, "clusters_tocados": len(tocados)}


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

        # Paso de CLUSTERING (Ola B): agrupa en historias los items recién insertados (y
        # cualquier reciente sin cluster), recalcula y puntúa. Best-effort: un fallo del paso
        # se loguea y NO invalida el barrido de ingesta (que ya persistió los artículos).
        cluster_resumen: dict[str, Any] = {"items": 0, "clusters_nuevos": 0, "clusters_tocados": 0}
        try:
            cluster_resumen = paso_clustering()
        except Exception:  # noqa: BLE001 -- el clustering es aditivo; nunca tumba la ingesta
            _log.exception("ingesta_daemon: fallo en el paso de clustering.")

        # Paso de TRADUCCIÓN (Ola D): traduce a ES, por lotes, los clusters EXTRANJEROS recientes
        # aún sin traducir. Best-effort: un fallo (subproceso, JSON, etc.) se loguea y NO invalida
        # el barrido. Sin tope artificial: cada barrido procesa un lote del backlog.
        trad_resumen: dict[str, Any] = {"traducidos": 0, "candidatos": 0}
        try:
            trad_resumen = paso_traduccion()
        except Exception:  # noqa: BLE001 -- la traducción es aditiva; nunca tumba la ingesta
            _log.exception("ingesta_daemon: fallo en el paso de traducción.")

        _log.info(
            "ingesta_daemon: barrido de %d feed(s) -> %d artículo(s) nuevo(s), %d error(es), "
            "%d auto-desactivado(s); clustering: %d item(s), %d historia(s) nueva(s); "
            "traducción: %d historia(s).",
            len(feeds), items_nuevos, errores, auto_desactivados,
            cluster_resumen["items"], cluster_resumen["clusters_nuevos"],
            trad_resumen["traducidos"],
        )
        return {
            "feeds": len(feeds),
            "items_nuevos": items_nuevos,
            "errores": errores,
            "auto_desactivados": auto_desactivados,
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
