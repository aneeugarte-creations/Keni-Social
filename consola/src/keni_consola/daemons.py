"""Arranca SOLO los hilos demonio de fondo de la Consola (sin servidor web).

    python -m keni_consola.daemons

Pensado para el deploy HOSTED: ahi el `back` corre `uvicorn keni_consola.app:crear_app`
(que a proposito NO arranca daemons, para no levantarlos en los tests) y el `worker`
solo procesa la cola de jobs. Sin un proceso como este, los hilos demonio de fondo
NO correrian en produccion. Este proceso aparte los mantiene vivos:

  - captura comercial (snapshots de interacciones),
  - programador de publicaciones (DRY-RUN salvo `KENI_PUBLICAR_REAL=1`),
  - scanner de vencimientos (emite `contenido.vencido` a los webhooks),
  - refresco de metricas por cuenta y POR PIEZA (cache caliente desde Metricool),
  - alertas de rendimiento / reciclaje (solo leen + emiten eventos internos),
  - auto-promocion del Radar (solo arranca con `KENI_RADAR_AUTO=1`).

SAFE BY DEFAULT: este proceso NO publica nada ni crea/aprueba contenido por su
cuenta. Los unicos caminos que lo harian estan gated por env y vienen AUSENTES por
defecto (`KENI_PUBLICAR_REAL`, `KENI_RADAR_AUTO`). Es el mismo conjunto de daemons
que `python -m keni_consola` arranca junto al servidor; aqui van sin uvicorn.
"""

from __future__ import annotations

import sys
import threading

from .app import crear_app


def main() -> int:
    # Logging del paquete, igual que el servidor real (KENI_CONSOLA_LOG_LEVEL).
    from .observabilidad import configurar_logging

    configurar_logging()

    # Inicializa la persistencia (Postgres) igual que el servidor, PERO sin uvicorn.
    # `bootstrap=False`: el admin inicial y la migracion al tablero ya los hace el
    # contenedor `back`; aqui solo necesitamos la conexion/esquema (que `crear_app`
    # arranca SIEMPRE via `db.arrancar_persistencia`, fuera del bloque bootstrap).
    crear_app(bootstrap=False)

    from .alertas_rendimiento import iniciar_alertas_rendimiento
    from .comercial import iniciar_captura_programada
    from .eventos_scanner import iniciar_scanner_vencimientos
    from .media_gc_daemon import iniciar_media_gc
    from .metricas_piezas_refresco import iniciar_refresco_piezas
    from .metricas_refresco import iniciar_refresco_metricas
    from .programador import iniciar_programador
    from .radar_auto import iniciar_radar_auto

    iniciar_captura_programada()
    iniciar_programador()  # DRY-RUN salvo KENI_PUBLICAR_REAL=1: nunca publica solo.
    iniciar_scanner_vencimientos()
    iniciar_refresco_metricas()
    iniciar_refresco_piezas()
    iniciar_alertas_rendimiento()  # solo lee + emite eventos; KENI_ALERTAS_RENDIMIENTO=0 lo apaga.
    iniciar_radar_auto()  # no arranca salvo KENI_RADAR_AUTO=1 (def OFF).
    iniciar_media_gc()  # GC de media huerfana; no borra salvo KENI_MEDIA_GC=1 (def OFF).

    # Los daemons son hilos; mantenemos vivo el proceso principal indefinidamente.
    threading.Event().wait()
    return 0


if __name__ == "__main__":
    sys.exit(main())
