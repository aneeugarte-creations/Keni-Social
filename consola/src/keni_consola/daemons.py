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
  - MÁQUINA DE CONTENIDO (Flujo C): el pipeline (`KENI_PIPELINE`/`KENI_INGESTA`/
    `KENI_AUTOGEN_ARTE`, bajo el maestro `KENI_MAQUINA`) ingiere del news-pool y lleva los
    temas a borrador (copy + arte) en la cola de revision; el resultado para en el gate
    humano (nada se publica solo),
  - reaper de generaciones zombi (cierra como `error` las `ejecutando` huerfanas).

SAFE BY DEFAULT: este proceso NO publica nada ni crea/aprueba contenido por su
cuenta. Los unicos caminos que lo harian estan gated por env y vienen AUSENTES por
defecto (`KENI_PUBLICAR_REAL`, `KENI_MAQUINA`, `KENI_PIPELINE`, `KENI_AUTOGEN_ARTE`).
La máquina de contenido PRODUCE hasta el borrador, pero NUNCA publica: el posteo
real sigue gated por `KENI_PUBLICAR_REAL` (OFF). Es el mismo conjunto de daemons que
`python -m keni_consola` arranca junto al servidor; aqui van sin uvicorn.
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
    from .algoritmos_refresco import iniciar_refresco_algoritmos
    from .comercial import iniciar_captura_programada
    from .eventos_scanner import iniciar_scanner_vencimientos
    from .ingesta_daemon import iniciar_ingesta
    from .media_gc_daemon import iniciar_media_gc
    from .metricas_piezas_refresco import iniciar_refresco_piezas
    from .metricas_refresco import iniciar_refresco_metricas
    from .pipeline_contenido import iniciar_pipeline
    from .programador import iniciar_programador
    from .reaper_generaciones import iniciar_reaper
    from .sugerencias_editoriales import iniciar_sugerencias_editoriales
    from .trends_daemon import iniciar_trends

    iniciar_captura_programada()
    iniciar_programador()  # DRY-RUN salvo KENI_PUBLICAR_REAL=1: nunca publica solo.
    iniciar_scanner_vencimientos()
    iniciar_refresco_metricas()
    iniciar_refresco_piezas()
    iniciar_alertas_rendimiento()  # solo lee + emite eventos; KENI_ALERTAS_RENDIMIENTO=0 lo apaga.
    # MÁQUINA DE CONTENIDO (Flujo C): el pipeline es el espinazo de la auto-producción. Sus
    # etapas —ingesta (crear noticias, KENI_INGESTA), copy (generar copy, KENI_PIPELINE) y arte
    # (generar arte, KENI_AUTOGEN_ARTE)— corren bajo el maestro KENI_MAQUINA. El pipeline ingiere
    # del news-pool, genera copy+arte y valida, registrando cada etapa en "Actividad IA"; deja
    # borradores en revisión. SAFE BY DEFAULT: no barre salvo su toggle ON; nunca publica.
    iniciar_pipeline()
    iniciar_refresco_algoritmos()  # ingesta de feeds de algoritmo; solo lee si KENI_ALGORITMOS_AUTO=1.
    iniciar_sugerencias_editoriales()  # digest diario de sugerencias; encola solo si KENI_SUGERENCIAS_EDITORIALES=1.
    iniciar_media_gc()  # GC de media huerfana; no borra salvo KENI_MEDIA_GC=1 (def OFF).
    # MOTOR DE INGESTA PERSISTENTE (Ola A): sondea en background los feeds RSS vencidos y
    # PERSISTE cada artículo en `noticias_items` (archivo a nivel de artículo). SOLO LEE feeds
    # públicos y persiste; no genera ni publica. GATEADO: no sondea salvo KENI_INGESTA=1 (def
    # OFF para CI/tests; ACTIVO en producción vía deploy). Escalable: batch + workers acotados,
    # cadencia por feed/categoría y backoff exponencial por feed con error.
    iniciar_ingesta()
    # Google Trends como fuente externa: ingiere las tendencias (con sus noticias) al pool.
    # GATEADO: no ingiere salvo KENI_TRENDS=1 (def OFF).
    iniciar_trends()
    # Reaper de generaciones zombi (SIEMPRE activo): cierra como `error`/`interrumpido` las
    # `ejecutando` cuyo proceso murio (reinicio/deploy/OOM/cuelgue), para que la UI no las
    # muestre "Generando..." indefinidamente. Barre al arrancar (limpia los huerfanos del
    # deploy anterior) y cada N min. Antes solo se cableaba en `__main__` (servidor monolitico);
    # con el split de servicios (Fase 3) NINGUN proceso hosted corre `__main__`, asi que sin
    # esto el reaper no corria en produccion y los huerfanos quedaban "ejecutando" para siempre.
    iniciar_reaper()

    # Los daemons son hilos; mantenemos vivo el proceso principal indefinidamente.
    threading.Event().wait()
    return 0


if __name__ == "__main__":
    sys.exit(main())
