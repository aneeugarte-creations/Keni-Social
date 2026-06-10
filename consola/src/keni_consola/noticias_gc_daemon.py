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
    devuelve los conteos. Pasa ADEMÁS la caducidad por edad (`repos.caducar_pool`: TTL +
    retención) para que el pool envejezca aunque el daemon de ingesta esté apagado (en
    instalaciones con la ingesta viva, su propio paso de caducidad ya lo hace; repetirla es
    idempotente). Devuelve `{clusters, items, dry_run, caducidad}`.
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
    try:
        caducidad = repos.caducar_pool(
            ttl_horas=config.noticias_ttl_horas(),
            retencion_horas=config.noticias_retencion_horas(),
        )
    except Exception:  # noqa: BLE001 -- la caducidad es aditiva; no invalida la purga
        _log.exception("noticias_gc: fallo la caducidad por edad del pool.")
        caducidad = {"caducadas": 0, "purgadas": 0, "items_purgados": 0}
    if caducidad.get("caducadas") or caducidad.get("purgadas"):
        _log.info(
            "noticias_gc: caducidad: %d historia(s) caducada(s), %d purgada(s), %d item(s).",
            caducidad.get("caducadas", 0), caducidad.get("purgadas", 0),
            caducidad.get("items_purgados", 0),
        )
    return {**resumen, "caducidad": caducidad}


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
