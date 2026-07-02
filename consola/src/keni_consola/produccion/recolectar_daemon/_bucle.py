"""Orquestador del barrido de recolección: planificación PURA, barrido y arranque del hilo daemon.

`ejecutar_barrido` invoca cada `paso_*` a través del facade (`_pkg.paso_*`) para que el
parcheo de los pasos en tests siga surtiendo efecto tras el troceado del módulo.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from typing import Any

import keni_consola.produccion.recolectar_daemon as _pkg

from ... import config, daemon_util, db, repos
from ...dominio import http_feed, ingesta
from ...tiempo import iso_utc
from ._comun import _log

# Tick corto: apagar aplica en <= esto y un feed vencido se recoge pronto.
_TICK_SEG = 30.0


def _intervalo_feed(feed: dict[str, Any]) -> int:
    """Intervalo (segundos) de un feed: su `intervalo_min` (>0), si no la cadencia de su LÍNEA,
    y como último recurso el legado por `categoria`.

    La línea dicta el ritmo (el feed la hereda); el fallback por `categoria` cubre feeds aún sin
    línea asociada (catch-all / pre-migración).
    """
    propio = int(feed.get("intervalo_min") or 0)
    if propio > 0:
        return propio
    linea_id = str(feed.get("linea_id") or "")
    if linea_id:
        et = db.obtener_etiqueta(linea_id)
        if et is not None:
            return config.intervalo_de_cadencia(str(et.get("cadencia") or "normal"))
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


def _particion_por_plan(
    feeds: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Separa los feeds en (dentro_del_plan, fuera_del_plan) según el plan de su marca. PURA-ish.

    Fuera de plan = la marca TIENE plan (`config.plan_dia`, claveado por LÍNEA) y la LÍNEA del
    feed (`linea_id`) no está en el plan. Sin marca, sin plan o sin línea → dentro (fail-open).
    Memoiza el plan por marca (una lectura de config por barrido y marca).
    """
    planes: dict[str, dict[str, int]] = {}
    dentro: list[dict[str, Any]] = []
    fuera: list[dict[str, Any]] = []
    for f in feeds:
        marca = str(f.get("marca") or "")
        linea = str(f.get("linea_id") or "").strip()
        if not marca or not linea:
            dentro.append(f)
            continue
        if marca not in planes:
            planes[marca] = config.plan_dia(marca)
        plan = planes[marca]
        (dentro if not plan or linea in plan else fuera).append(f)
    return dentro, fuera


def ejecutar_barrido() -> dict[str, Any]:
    """Un barrido: elige feeds vencidos, los sondea en paralelo, persiste y replanifica.

    Devuelve un resumen `{feeds, items_nuevos, errores}`. Best-effort de punta a punta: un
    feed que falla se anota y no aborta el resto; un fallo de persistencia de un feed se loguea
    y se sigue. Single-flight cross-proceso vía advisory lock (no duplica con un barrido
    solapado).
    """
    with db.lock_barrido("ingesta") as ok:
        if not ok:
            _log.debug("recolectar_daemon: otro barrido en curso; salgo (single-flight).")
            return {"feeds": 0, "items_nuevos": 0, "errores": 0}

        ahora = datetime.now(UTC)
        feeds = repos.feeds_vencidos(iso_utc(ahora), config.ingesta_batch())
        # Recolectar es POR MARCA (KENI_PIPELINE_RECOLECTAR::<marca>): salta los feeds de marcas con
        # Recolectar apagado. Los COMPARTIDOS (marca vacía) siempre corren si el daemon corre.
        # Best-effort: no toca agrupar/traducir (pasos globales).
        feeds = [
            f
            for f in feeds
            if not (m := str(f.get("marca") or ""))
            or config.etapa_activa(config.ENV_PIPELINE_RECOLECTAR, m)
        ]
        # PLAN EDITORIAL DIARIO: una marca con plan solo digiere los feeds de las categorías
        # de su plan — sondear lo que jamás competirá por una plaza es carga (red + archivo +
        # agrupar) sin salida. Los feeds fuera de plan se APLAZAN (proximo_sondeo += 6 h)
        # para no re-evaluarlos en cada barrido. FAIL-OPEN: un feed SIN categoría o sin marca
        # no se filtra (sin clasificar no hay criterio; mejor digerir de más que quedar ciego).
        feeds, fuera_de_plan = _particion_por_plan(feeds)
        for f in fuera_de_plan:
            try:
                repos.registrar_sondeo_feed(
                    f["id"], proximo_sondeo=iso_utc(ahora + timedelta(hours=6))
                )
            except Exception:  # noqa: BLE001 -- aplazar es best-effort; el feed solo re-aparece
                _log.debug("recolectar_daemon: no se pudo aplazar el feed fuera de plan %s.", f.get("id"))
        if fuera_de_plan:
            _log.info(
                "recolectar_daemon: %d feed(s) fuera del plan editorial de su marca, aplazados.",
                len(fuera_de_plan),
            )

        # OJO: sin feeds RSS vencidos el barrido NO termina aquí: los pasos post-RSS (agencias,
        # agrupar, fusionar, re-score, traducir) corren IGUAL.
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
        items_filtrados = 0
        errores = 0
        auto_desactivados = 0
        for feed, items, salud in resultados:
            hubo_error = bool(salud.get("error"))
            if hubo_error:
                errores += 1
            # SIN PÉRDIDAS EN LA PUERTA: se archiva TODO lo que entra por un feed (la selección
            # vive aguas abajo: umbral de promoción + aprobación humana). `filtrados` queda en 0.
            filtrados = 0
            insertadas = 0
            if items:
                try:
                    insertadas = repos.crear_noticias_items(items)
                except Exception:  # noqa: BLE001 -- persistir un feed no debe abortar el barrido
                    _log.exception(
                        "recolectar_daemon: fallo al persistir items de feed %s.", feed.get("id")
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
                    filtrados=filtrados,
                )
            except Exception:  # noqa: BLE001 -- registrar salud es best-effort
                _log.exception(
                    "recolectar_daemon: fallo al registrar el sondeo de feed %s.", feed.get("id")
                )

        # Paso de AGENCIAS (Fase 2): vuelca al MISMO pool las notas de Reuters/AFP CONFIGURADAS,
        # antes de agrupar para que se agrupen en el mismo barrido. Gateado por KENI_PIPELINE_RECOLECTAR
        # (este daemon) — sin toggle propio. Best-effort + no-op honesto sin credencial: nunca
        # rompe el barrido de RSS. Sus items entran al conteo de `items_nuevos`.
        agencias_resumen: dict[str, Any] = {"items": 0}
        try:
            agencias_resumen = _pkg.paso_agencias()
        except Exception:  # noqa: BLE001 -- las agencias son aditivas; nunca tumban la recolección
            _log.exception("recolectar_daemon: fallo en el paso de agencias.")
        items_nuevos += agencias_resumen["items"]

        # Paso de ETIQUETAS (Fase 2): extrae las etiquetas del sitio (`/etiqueta/<slug>/`) de las
        # notas web PROPIAS ya archivadas y las persiste en `noticias_items.tags` (vínculo
        # nota↔campaña). Best-effort: un fallo se loguea y NO invalida el barrido. No suma a
        # `items_nuevos` (no crea filas, solo enriquece las existentes).
        try:
            _pkg.paso_etiquetas()
        except Exception:  # noqa: BLE001 -- las etiquetas son aditivas; nunca tumban la recolección
            _log.exception("recolectar_daemon: fallo en el paso de etiquetas.")

        # Paso de AGRUPAR (Ola B): agrupa en historias los items recién insertados (y
        # cualquier reciente sin cluster), recalcula y puntúa. Best-effort: un fallo del paso
        # se loguea y NO invalida el barrido de recolección (que ya persistió los artículos).
        cluster_resumen: dict[str, Any] = {"items": 0, "clusters_nuevos": 0, "clusters_tocados": 0}
        try:
            cluster_resumen = _pkg.paso_agrupar()
        except Exception:  # noqa: BLE001 -- el agrupar es aditivo; nunca tumba la recolección
            _log.exception("recolectar_daemon: fallo en el paso de agrupar.")
        # Ventana ya cargada/actualizada por el agrupar (si la hay): se REUTILIZA en el
        # re-score y el fusionar del mismo barrido, sin re-leer la BD.
        clusters_ventana = cluster_resumen.pop("clusters_ventana", None)

        # Paso de RE-SCORE (score que envejece): repuntúa periódicamente la ventana para que
        # la frescura DECAIGA aunque no entren items nuevos (ver `paso_rescore`). Best-effort.
        try:
            _pkg.paso_rescore(clusters_ventana)
        except Exception:  # noqa: BLE001 -- el re-score es aditivo; nunca tumba la recolección
            _log.exception("recolectar_daemon: fallo en el paso de re-score.")

        # Pasos Haiku que ENCOLAN (gastan tokens vía worker): los corta la parada de emergencia /
        # presupuesto igual que a la cola (`ia_fondo_bloqueada`), porque el barrido decide ENCOLAR.
        # Los pasos de arriba (feeds, agencias, etiquetas, agrupar dedup, re-score, caducidad) son
        # I/O y NO gastan tokens: siguen corriendo.
        ia_bloqueada = _pkg.ia_fondo_bloqueada()

        # Paso de FUSIONAR SEMÁNTICAMENTE (Fase 2b): ENCOLA un job de fusión Haiku POR MARCA por las
        # historias del MISMO evento contadas con titulares distintos (la formación solo dedup-ea
        # EXACTO: url o hash de título); el worker funde/etiqueta, ruteado al carril de la cuenta de la
        # marca. Gateado `KENI_PIPELINE_FUSIONAR` (def ON; throttled internamente). Best-effort.
        if not ia_bloqueada:
            try:
                _pkg.paso_fusionar_semantica(recientes=clusters_ventana)
            except Exception:  # noqa: BLE001 -- el fusionar es aditivo; nunca tumba la recolección
                _log.exception("recolectar_daemon: fallo en el paso de fusionar semántico.")

        # Paso de TRADUCIR (Ola D): ENCOLA un job de traducción a ES POR MARCA por cada lote de
        # clusters EXTRANJEROS recientes sin traducir (la traducción la corre el worker, ruteada al
        # carril de la cuenta de la marca). Best-effort: un fallo se loguea y NO invalida el barrido.
        # Sin tope artificial: cada barrido encola un lote del backlog.
        trad_resumen: dict[str, Any] = {"encolados": 0, "marcas": 0, "candidatos": 0}
        if not ia_bloqueada and config.alguna_marca_con_etapa(config.ENV_PIPELINE_TRADUCIR):
            try:
                trad_resumen = _pkg.paso_traducir()
            except Exception:  # noqa: BLE001 -- el traducir es aditivo; nunca tumba la recolección
                _log.exception("recolectar_daemon: fallo en el paso de traducir.")

        # Paso de CADUCIDAD (TTL): lo viejo expira solo y lo caducado se purga tras la retención.
        # Throttled (1 pasada / 15 min) y best-effort: nunca tumba la recolección.
        try:
            _pkg.paso_caducidad()
        except Exception:  # noqa: BLE001 -- la caducidad es aditiva; nunca tumba la recolección
            _log.exception("recolectar_daemon: fallo en el paso de caducidad.")

        _log.info(
            "recolectar_daemon: barrido de %d feed(s) -> %d artículo(s) nuevo(s) (%d de agencias, "
            "%d filtrados en la entrada), %d error(es), %d auto-desactivado(s); agrupar: "
            "%d item(s), %d historia(s) nueva(s); traducir: %d historia(s) encolada(s) en %d job(s).",
            len(feeds), items_nuevos, agencias_resumen["items"], items_filtrados, errores,
            auto_desactivados, cluster_resumen["items"], cluster_resumen["clusters_nuevos"],
            trad_resumen["encolados"], trad_resumen["marcas"],
        )
        return {
            "feeds": len(feeds),
            "items_nuevos": items_nuevos,
            "items_filtrados": items_filtrados,
            "errores": errores,
            "auto_desactivados": auto_desactivados,
            "agencias": agencias_resumen,
            "agrupar": cluster_resumen,
            "traducir": trad_resumen,
        }


def _resumen_barrido(res: dict[str, Any]) -> str:
    """Resumen corto del barrido de recolección para el historial (feeds/items/historias)."""
    feeds = res.get("feeds", 0)
    nuevos = res.get("items_nuevos", 0)
    clusters = (res.get("agrupar") or {}).get("clusters_nuevos", 0)
    if not (feeds or nuevos or clusters):
        return "sin novedad"
    return f"{feeds} feed(s) sondeado(s) · {nuevos} item(s) nuevo(s) · {clusters} historia(s)"


def iniciar_ingesta() -> threading.Thread:
    """Arranca el hilo daemon del motor de recolección (GATEADO EN VIVO).

    El hilo arranca SIEMPRE y comprueba `KENI_PIPELINE_RECOLECTAR` en cada ciclo: encender/apagar en
    runtime aplica sin reiniciar. Tick corto (30s) para recoger feeds vencidos pronto y ser
    responsivo al apagado. El hilo es daemon; un fallo de barrido se loguea y NO lo mata.
    """

    def bucle() -> None:
        daemon_util.bucle_gateado(
            activo_fn=config.gate_maquina(
                lambda: config.alguna_marca_con_etapa(config.ENV_PIPELINE_RECOLECTAR)
            ),
            intervalo_seg_fn=lambda: _TICK_SEG,
            sweep_fn=ejecutar_barrido,
            tick_seg=_TICK_SEG,
            log=_log,
            resumen_fn=_resumen_barrido,
        )

    hilo = threading.Thread(target=bucle, name="ingesta-daemon", daemon=True)
    hilo.start()
    estado = (
        "ACTIVO"
        if config.alguna_marca_con_etapa(config.ENV_PIPELINE_RECOLECTAR)
        else "EN ESPERA (Recolectar apagado en todas las marcas)"
    )
    _log.info(
        "Daemon de recolección %s, tick %.0fs (batch=%d, workers=%d, max_items=%d).",
        estado, _TICK_SEG, config.ingesta_batch(), config.ingesta_workers(),
        config.ingesta_max_items(),
    )
    return hilo
