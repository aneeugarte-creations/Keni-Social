"""Arranca SOLO los hilos demonio de fondo de la Consola (sin servidor web).

    python -m keni_consola.daemons

Pensado para el deploy HOSTED: ahi el `back` corre `uvicorn keni_consola.app:crear_app`
(que a proposito NO arranca daemons, para no levantarlos en los tests) y el `worker`
solo procesa la cola de jobs. Sin un proceso como este, los hilos demonio de fondo
NO correrian en produccion. Este proceso aparte los mantiene vivos:

  - refresco de metricas por cuenta y POR PIEZA (cache caliente desde Metricool),
  - alertas de rendimiento (solo leen + emiten eventos internos),
  - MÁQUINA DE CONTENIDO (Flujo C): el pipeline (`KENI_PIPELINE_REDACTAR`/`KENI_PIPELINE_RECOLECTAR`/
    `KENI_PIPELINE_ILUSTRAR`, bajo el maestro `KENI_MAQUINA`) ingiere del news-pool y lleva los
    temas a borrador (copy + arte) en la cola de revision; el resultado para en el gate
    humano (nada se publica solo),
  - recolector de generaciones colgadas (cierra como `error` las `ejecutando` sueltas).

SAFE BY DEFAULT: este proceso NO publica nada ni crea/aprueba contenido por su
cuenta. Los unicos caminos que lo harian estan gated por env y vienen AUSENTES por
defecto (`KENI_MAQUINA`, `KENI_PIPELINE_REDACTAR`, `KENI_PIPELINE_ILUSTRAR`).
La máquina de contenido PRODUCE hasta el borrador, pero NUNCA publica: la salida a
redes la dispara una persona desde el feed. Es el mismo conjunto de daemons que
`python -m keni_consola` arranca junto al servidor; aqui van sin uvicorn.
"""

from __future__ import annotations

import sys
import time

from .app import crear_app

# Cadencia del latido de liveness del proceso (fichero que sondea el healthcheck del
# contenedor `daemons` en deploy). El healthcheck tolera varios multiplos de esto.
_LATIDO_SEG = 30.0


def main() -> int:
    # Logging del paquete, igual que el servidor real (KENI_CONSOLA_LOG_LEVEL).
    from .observabilidad import configurar_logging

    configurar_logging()

    # Inicializa la persistencia (Postgres) igual que el servidor, PERO sin uvicorn.
    # `bootstrap=False`: el admin inicial y la migracion al tablero ya los hace el
    # contenedor `back`; aqui solo necesitamos la conexion/esquema (que `crear_app`
    # arranca SIEMPRE via `db.arrancar_persistencia`, fuera del bloque bootstrap).
    crear_app(bootstrap=False)

    # Backfill del histórico por pieza ANTES de arrancar el refresco de métricas (que en su
    # primer barrido PURGA las caches del listado de esquema viejo). El backfill vive en el
    # bloque bootstrap de `crear_app` (lo corre el `back`), pero aquí `bootstrap=False`: sin
    # esto, una subida de `_VERSION_ESQUEMA` purgaría las caches antiguas antes de volcarlas a
    # snapshots y se perdería el histórico retroactivo. Idempotente y best-effort.
    try:
        from . import metricas_pieza

        metricas_pieza.backfill_historico_desde_cache()
    except Exception:  # noqa: BLE001 -- el arranque de los daemons no debe romper por el backfill
        import logging

        logging.getLogger("keni_consola.daemons").warning(
            "No se pudo reconstruir el histórico por pieza al arrancar los daemons.", exc_info=True
        )

    from .alertas_rendimiento import iniciar_alertas_rendimiento
    from .produccion.refresco_algoritmos import iniciar_refresco_algoritmos
    from .cuenta_uso_daemon import iniciar_muestreo_uso
    from .produccion.recolectar_daemon import iniciar_ingesta
    from .media_gc_daemon import iniciar_media_gc
    from .metricas.refresco_piezas import iniciar_refresco_piezas
    from .metricas.refresco_cuentas import iniciar_refresco_metricas
    from .produccion.noticias_gc_daemon import iniciar_noticias_gc
    from .produccion.refresco_patrones import iniciar_refresco_patrones
    from .pipeline_contenido import iniciar_pipeline
    from .programador import iniciar_programador
    from .limpiador_generaciones import iniciar_limpiador
    from .produccion.trends_daemon import iniciar_trends

    # PUBLICADOR ("reloj del servidor"): publica las piezas `programado` cuando vence su
    # `fecha_programada`. Gateado por marca (`KENI_PUBLICAR_REAL`/`publicar_real_para`); en
    # las marcas sin el flag opera en dry-run (prepara, no postea).
    iniciar_programador()
    iniciar_refresco_metricas()
    iniciar_refresco_piezas()
    iniciar_alertas_rendimiento()  # solo lee + emite eventos; KENI_ALERTAS_RENDIMIENTO=0 lo apaga.
    # MÁQUINA DE CONTENIDO (Flujo C): el pipeline es el espinazo de la auto-producción. Sus
    # etapas —Recolectar (crear noticias, KENI_PIPELINE_RECOLECTAR), Redactar (generar copy, KENI_PIPELINE_REDACTAR) y Ilustrar
    # (generar arte, KENI_PIPELINE_ILUSTRAR)— corren bajo el maestro KENI_MAQUINA. El pipeline ingiere
    # del news-pool, genera copy+arte y valida, registrando cada etapa en "Actividad IA"; deja
    # borradores en revisión. SAFE BY DEFAULT: no barre salvo su toggle ON; nunca publica.
    iniciar_pipeline()
    iniciar_refresco_algoritmos()  # ingesta de feeds de algoritmo; solo lee si KENI_ALGORITMOS_AUTO=1.
    iniciar_media_gc()  # GC de media sin referencia; no borra salvo KENI_MEDIA_GC=1 (def OFF).
    # Re-derivación de PATRONES editoriales por marca (Metricool -> perfil + doc 'patrones'):
    # solo lee métricas y reescribe los artefactos de patrones cada N días. GATEADO: no corre
    # salvo KENI_PATRONES_AUTO=1 (def OFF); Voz/Reglas (criterio humano) jamás se tocan.
    iniciar_refresco_patrones()
    iniciar_noticias_gc()  # GC del pool de noticias por relevancia; no borra salvo KENI_NOTICIAS_GC=1 (def OFF).
    # MOTOR DE INGESTA PERSISTENTE (Ola A): sondea en background los feeds RSS vencidos y
    # PERSISTE cada artículo en `noticias_items` (archivo a nivel de artículo). SOLO LEE feeds
    # públicos y persiste; no genera ni publica. GATEADO: no sondea salvo KENI_PIPELINE_RECOLECTAR=1 (def
    # OFF para CI/tests; ACTIVO en producción vía deploy). Escalable: batch + workers acotados,
    # cadencia por feed/categoría y backoff exponencial por feed con error.
    iniciar_ingesta()
    # Google Trends como fuente externa: ingiere las tendencias (con sus noticias) al pool.
    # GATEADO: no ingiere salvo KENI_TRENDS=1 (def OFF).
    iniciar_trends()
    # Recolector de generaciones colgadas (SIEMPRE activo): cierra como `error`/`interrumpido` las
    # `ejecutando` cuyo proceso murio (reinicio/deploy/OOM/cuelgue), para que la UI no las
    # muestre "Generando..." indefinidamente. Barre al arrancar (limpia los sueltos del
    # deploy anterior) y cada N min. Se cablea aqui porque con el split de servicios NINGUN
    # proceso hosted corre `__main__`; sin esto el recolector no correria en produccion y los
    # sueltos quedarian "ejecutando" para siempre.
    iniciar_limpiador()
    # MUESTREO DE USO de la cuenta de Claude (SIEMPRE activo): corre `claude -p /usage` cada N
    # min y persiste el snapshot en `cuenta_uso`, para que el indicador de la barra lateral y el
    # gate diario lean de la BD sin ejecutar `claude`. Vive aqui (no en el back) porque solo el
    # `daemons` tiene `claude`. Mantenimiento: NO gateado por KENI_MAQUINA.
    iniciar_muestreo_uso()

    # LISTENER DE CONTROL (gestion de la cuenta de Claude desde el panel admin): solo se
    # monta si hay `KENI_CONTROL_BEARER`. Vive aqui (no en el back) porque cambiar la cuenta
    # ejecuta `claude` (auth/login/logout, /usage) y el back no lo tiene; el `daemons` es de
    # instancia unica, ideal para el login interactivo que mantiene un proceso vivo.
    from .control import iniciar_control

    iniciar_control()

    # Los daemons son hilos; el proceso principal queda en un bucle de LATIDO: toca el
    # fichero de liveness cada _LATIDO_SEG para que el healthcheck del contenedor (deploy)
    # distinga "proceso vivo" de "proceso colgado/atascado" sin depender de la BD. Un
    # Event().wait() mudo solo reiniciaria el contenedor si el proceso MURIERA, nunca si
    # quedara colgado.
    from . import latidos

    while True:
        latidos.tocar_fichero()
        time.sleep(_LATIDO_SEG)
    return 0  # inalcanzable; conserva la firma


if __name__ == "__main__":
    sys.exit(main())
