"""Hilo demonio que ejecuta la GC del POOL DE NOTICIAS por relevancia (GATEADO EN VIVO).

Espejo de `media_gc_daemon`: un hilo que arranca SIEMPRE y, gateado por `KENI_NOTICIAS_GC`
(def OFF), barre cada N horas SOLO cuando el flag está activo. Así encender/apagar en runtime
(desde la API de ajustes) aplica sin reiniciar.

SEGURO POR DEFECTO (CONSERVADOR): sin `KENI_NOTICIAS_GC` no se borra ninguna noticia. El barrido
purga el RUIDO de baja relevancia (historias `nuevo` no llevadas al tablero, de una sola fuente,
score bajo e inactivas + items huérfanos viejos), conservando lo usado/ligado/corroborado/score
alto/reciente. La lógica del borrado vive en `db_noticias.purgar_pool_irrelevante`. NO es un TTL.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from . import config, daemon_util, repos

_log = logging.getLogger("keni_consola.noticias_gc_daemon")


def ejecutar_barrido() -> dict[str, Any]:
    """Un barrido de GC del pool: purga el ruido de baja relevancia con los umbrales vivos.

    Best-effort: `repos.purgar_pool_irrelevante` es una operación atómica (commit único) y
    devuelve los conteos. Devuelve `{clusters, items, dry_run}`.

    UN SOLO DUEÑO DE LA CADUCIDAD POR TTL: la caducidad por edad (`repos.caducar_pool`: TTL +
    retención) la ejecuta SOLO `recolectar_daemon.paso_caducidad` (el reloj del feed: donde se
    construye, se limpia; corre SIEMPRE, mientras que este GC va gateado OFF por defecto). Aquí
    NO se duplica — este daemon hace EXCLUSIVAMENTE la purga por relevancia (score+inactividad),
    que es única suya.
    """
    resumen = repos.purgar_pool_irrelevante(
        score_umbral=config.noticias_gc_score_umbral(),
        inactividad_horas=config.noticias_gc_inactividad_horas(),
    )
    if resumen.get("clusters") or resumen.get("items"):
        _log.info(
            "noticias_gc: purgadas %d historia(s) y %d item(s) de baja relevancia.",
            resumen.get("clusters", 0), resumen.get("items", 0),
        )
    return resumen


def _resumen_barrido(res: dict[str, Any]) -> str:
    """Resumen corto del barrido de GC del pool de noticias para el historial."""
    clusters = (res or {}).get("clusters", 0)
    items = (res or {}).get("items", 0)
    if not (clusters or items):
        return "sin novedad"
    return f"{clusters} historia(s) · {items} item(s) purgado(s) por baja relevancia"


def _intervalo_segundos() -> float:
    """Intervalo del barrido en segundos (a partir de `KENI_NOTICIAS_GC_INTERVALO_HORAS`)."""
    return config.noticias_gc_intervalo_horas() * 3600.0


def iniciar_noticias_gc(intervalo_segundos: float | None = None) -> threading.Thread:
    """Arranca el hilo demonio de GC del pool de noticias (GATEADO EN VIVO).

    Pensado para el servidor real (`__main__`/`daemons`), NO para `crear_app` (los tests no lo
    arrancan, igual que el resto de daemons). El hilo arranca SIEMPRE y comprueba `KENI_NOTICIAS_GC`
    en cada ciclo: apagar/encender en runtime aplica sin reiniciar. El hilo es daemon; un fallo de
    barrido se loguea y NO lo mata.
    """
    intervalo = intervalo_segundos if intervalo_segundos is not None else _intervalo_segundos()

    def bucle() -> None:
        daemon_util.bucle_gateado(
            activo_fn=config.noticias_gc_activo,
            intervalo_seg_fn=lambda: intervalo,
            sweep_fn=ejecutar_barrido,
            log=_log,
            resumen_fn=_resumen_barrido,
        )

    hilo = threading.Thread(target=bucle, name="noticias-gc-daemon", daemon=True)
    hilo.start()
    estado = "ACTIVA" if config.noticias_gc_activo() else "EN ESPERA (KENI_NOTICIAS_GC off)"
    _log.info(
        "GC del pool de noticias %s, cada %.0f h (score<%.2f, inactividad>%dh).",
        estado, intervalo / 3600.0, config.noticias_gc_score_umbral(),
        config.noticias_gc_inactividad_horas(),
    )
    return hilo
