"""Daemon de refresco de la cache de metricas (espejo de `programador.py`).

Un hilo demonio que mantiene caliente la cache de metricas (`metricas_cache.py`):
refresca TODOS los combos (rango × marca, reporte+analisis) al arrancar (rellena la
cache fria) y luego cada N horas (def 6h; `KENI_METRICAS_REFRESCO_HORAS`). Asi la UI
lee siempre datos ya calculados (instantaneo) y nadie espera a las APIs externas en
una apertura. El boton "Actualizar" de la UI dispara un refresco extra a demanda
(via `metricas_cache.disparar_refresco`), que reusa el MISMO barrido.

Vive en el servidor real (`__main__`), NO en `crear_app`: los tests no lo arrancan
(igual que el programador y la captura comercial). Un fallo de barrido se loguea y
NO mata el hilo (el siguiente barrido reintenta). Cada operacion abre/cierra su
propia conexion (via `repos`), asi que correr en un hilo aparte es seguro.
"""

from __future__ import annotations

import logging
import threading
import time

from . import config, metricas_cache

_log = logging.getLogger("keni_consola.metricas_refresco")


def _intervalo_segundos() -> float:
    """Intervalo del barrido en segundos (a partir de `KENI_METRICAS_REFRESCO_HORAS`)."""
    return config.metricas_refresco_horas() * 3600.0


def iniciar_refresco_metricas(intervalo_segundos: float | None = None) -> threading.Thread:
    """Arranca un hilo demonio que refresca la cache de metricas en bucle.

    Pensado para el servidor real (`__main__`), NO para `crear_app`: los tests crean la
    app sin arrancar esto. El hilo es daemon: muere al cerrar el proceso. Refresca una
    vez al arrancar (cache fria) y luego cada `intervalo`. Un fallo de barrido se loguea
    y NO mata el hilo.
    """
    intervalo = intervalo_segundos if intervalo_segundos is not None else _intervalo_segundos()

    def bucle() -> None:
        from . import latidos  # import tardio: solo lo paga el hilo del servidor real

        while True:
            t0 = time.monotonic()
            try:
                n = metricas_cache.refrescar_todo()
                _log.info("Refresco periodico de metricas: %d combo(s) actualizado(s).", n)
                latidos.barrido(
                    "metricas", ok=True, intervalo_seg=intervalo, tick_seg=intervalo,
                    duracion_ms=int((time.monotonic() - t0) * 1000),
                    resumen=f"caché refrescada · {n} combo(s) actualizado(s)",
                )
            except Exception as e:  # noqa: BLE001 -- un fallo de barrido no debe matar el hilo
                _log.exception("Fallo en el barrido de refresco de metricas.")
                latidos.barrido(
                    "metricas", ok=False, intervalo_seg=intervalo, tick_seg=intervalo,
                    duracion_ms=int((time.monotonic() - t0) * 1000), error=repr(e),
                )
            time.sleep(intervalo)

    hilo = threading.Thread(target=bucle, name="refresco-metricas-daemon", daemon=True)
    hilo.start()
    _log.info("Refresco de metricas activo cada %.0f h.", intervalo / 3600.0)
    return hilo
