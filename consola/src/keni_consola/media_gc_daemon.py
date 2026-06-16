"""Hilo demonio que ejecuta la GC de media sin dueño periodicamente (GATEADO EN VIVO).

La LOGICA del barrido (deteccion + borrado de objetos sin dueño) vive en `dominio.media_gc`; aqui
solo esta el envoltorio de DAEMON, espejo de `radar_auto`/`autogen_ilustrar`: un hilo que arranca
SIEMPRE y, gateado por `KENI_MEDIA_GC` (def OFF), barre cada N horas SOLO cuando el flag esta
activo. Asi encender/apagar en runtime (desde la API de ajustes) aplica sin reiniciar.

SEGURO POR DEFECTO (CONSERVADOR): sin `KENI_MEDIA_GC` el hilo no borra nada. El barrido solo
elimina objetos SIN DUEÑO (no referenciados por ninguna pieza) y mas viejos que el
umbral (`dominio.media_gc.limpiar`).
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from . import config, daemon_util
from .dominio import media_gc

_log = logging.getLogger("keni_consola.media_gc_daemon")


def ejecutar_barrido() -> dict[str, Any]:
    """Un barrido de GC: borra los objetos sin dueño viejos con el umbral de antiguedad vivo.

    Lo llama el daemon. Best-effort: `media_gc.limpiar` es robusto ante errores por objeto y
    loguea el resumen. Devuelve el dict de resumen (`{borrados, conservados, dry_run, ...}`).
    """
    return media_gc.limpiar(antiguedad_horas=config.media_gc_antiguedad_horas())


def _resumen_barrido(res: dict[str, Any]) -> str:
    """Resumen corto del barrido de GC de media para el historial."""
    borrados = (res or {}).get("borrados", 0)
    if not borrados:
        return "sin novedad"
    seco = " (dry-run)" if (res or {}).get("dry_run") else ""
    return f"{borrados} media sin dueño borrada(s){seco}"


def _intervalo_segundos() -> float:
    """Intervalo del barrido en segundos (a partir de `KENI_MEDIA_GC_INTERVALO_HORAS`)."""
    return config.media_gc_intervalo_horas() * 3600.0


def iniciar_media_gc(intervalo_segundos: float | None = None) -> threading.Thread:
    """Arranca el hilo demonio de GC de media sin dueño (GATEADO EN VIVO).

    Pensado para el servidor real (`__main__`/`daemons`), NO para `crear_app` (los tests no
    lo arrancan, igual que el resto de daemons). El hilo arranca SIEMPRE y comprueba
    `KENI_MEDIA_GC` en cada ciclo: apagar/encender en runtime aplica sin reiniciar (apagar en
    <= ~1 min; encender tras estar apagado dispara un barrido de inmediato). El hilo es
    daemon; un fallo de barrido se loguea y NO lo mata.
    """
    intervalo = intervalo_segundos if intervalo_segundos is not None else _intervalo_segundos()

    def bucle() -> None:
        daemon_util.bucle_gateado(
            activo_fn=config.media_gc_activo,
            intervalo_seg_fn=lambda: intervalo,
            sweep_fn=ejecutar_barrido,
            log=_log,
            resumen_fn=_resumen_barrido,
        )

    hilo = threading.Thread(target=bucle, name="media-gc-daemon", daemon=True)
    hilo.start()
    estado = "ACTIVA" if config.media_gc_activo() else "EN ESPERA (KENI_MEDIA_GC off)"
    _log.info(
        "GC de media sin dueño %s, cada %.0f h (umbral antiguedad=%dh).",
        estado, intervalo / 3600.0, config.media_gc_antiguedad_horas(),
    )
    return hilo
