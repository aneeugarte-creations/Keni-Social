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
from datetime import UTC, datetime, timedelta
from typing import Any

from . import config, daemon_util, db, repos
from .dominio import http_feed, ingesta

_log = logging.getLogger("keni_consola.ingesta_daemon")

# Tick corto: apagar aplica en <= esto y un feed vencido se recoge pronto.
_TICK_SEG = 30.0


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

        items_nuevos = 0
        errores = 0
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
            try:
                repos.registrar_sondeo_feed(
                    feed["id"],
                    conteo=int(salud.get("conteo") or 0),
                    error=str(salud.get("error") or ""),
                    proximo_sondeo=plan["proximo_sondeo"],
                    errores_seguidos=plan["errores_seguidos"],
                    pausado_hasta=plan["pausado_hasta"],
                )
            except Exception:  # noqa: BLE001 -- registrar salud es best-effort
                _log.exception(
                    "ingesta_daemon: fallo al registrar el sondeo de feed %s.", feed.get("id")
                )

        _log.info(
            "ingesta_daemon: barrido de %d feed(s) -> %d artículo(s) nuevo(s), %d error(es).",
            len(feeds), items_nuevos, errores,
        )
        return {"feeds": len(feeds), "items_nuevos": items_nuevos, "errores": errores}


def iniciar_ingesta() -> threading.Thread:
    """Arranca el hilo daemon del motor de ingesta (GATEADO EN VIVO).

    El hilo arranca SIEMPRE y comprueba `KENI_INGESTA` en cada ciclo: encender/apagar en
    runtime aplica sin reiniciar. Tick corto (30s) para recoger feeds vencidos pronto y ser
    responsivo al apagado. El hilo es daemon; un fallo de barrido se loguea y NO lo mata.
    """

    def bucle() -> None:
        daemon_util.bucle_gateado(
            activo_fn=config.ingesta_activa,
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
