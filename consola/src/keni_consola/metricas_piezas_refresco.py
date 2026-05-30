"""Daemon de refresco PROACTIVO de la cache de metricas POR PIEZA (Fase 3 auto-operativa).

Hermano de `metricas_refresco.py` (mismo patron de hilo demonio), pero para la cache POR
PIEZA del tablero (`metricas_pieza.py`, tipo `pieza_contenido`), no para los combos
agregados (rango × marca). El daemon `metricas_refresco` refresca los REPORTES; este
refresca el RENDIMIENTO de cada PIEZA publicada reciente.

Que resuelve: hoy el rendimiento por pieza es LAZY (se recalcula al abrir el tablero si la
cache esta vieja). Esto adelanta ese trabajo: cada N horas (def 4h;
`KENI_METRICAS_PIEZAS_REFRESCO_HORAS`) recalcula la cache de las piezas publicadas
RECIENTES con `id_post_metricool` desde Metricool, para que el tablero y la heuristica de
reciclaje vean datos FRESCOS sin pagar el lazy-fill en la apertura.

Vive en el servidor real (`__main__`), NO en `crear_app`: los tests no lo arrancan (igual
que el programador y la captura comercial). Un fallo de barrido se loguea y NO mata el
hilo. Cada operacion abre/cierra su propia conexion (via `repos`), seguro entre hilos.
"""

from __future__ import annotations

import logging
import threading
import time

from . import config, metricas_pieza

_log = logging.getLogger("keni_consola.metricas_piezas_refresco")


def _intervalo_segundos() -> float:
    """Intervalo del barrido en segundos (a partir de `KENI_METRICAS_PIEZAS_REFRESCO_HORAS`)."""
    return config.metricas_piezas_refresco_horas() * 3600.0


def iniciar_refresco_piezas(intervalo_segundos: float | None = None) -> threading.Thread:
    """Arranca un hilo demonio que refresca la cache POR PIEZA del tablero en bucle.

    Pensado para el servidor real (`__main__`), NO para `crear_app`: los tests crean la
    app sin arrancar esto. El hilo es daemon: muere al cerrar el proceso. Refresca una vez
    al arrancar y luego cada `intervalo`. Un fallo de barrido se loguea y NO mata el hilo.
    """
    intervalo = intervalo_segundos if intervalo_segundos is not None else _intervalo_segundos()

    def bucle() -> None:
        while True:
            try:
                n = metricas_pieza.refrescar_piezas_recientes()
                if n:
                    _log.info("Refresco proactivo por pieza: %d pieza(s) actualizada(s).", n)
            except Exception:  # noqa: BLE001 -- un fallo de barrido no debe matar el hilo
                _log.exception("Fallo en el barrido de refresco de metricas por pieza.")
            time.sleep(intervalo)

    hilo = threading.Thread(target=bucle, name="refresco-metricas-piezas-daemon", daemon=True)
    hilo.start()
    _log.info("Refresco de metricas por pieza activo cada %.0f h.", intervalo / 3600.0)
    return hilo
