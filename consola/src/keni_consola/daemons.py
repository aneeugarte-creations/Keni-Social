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
  - auto-promocion del Radar (solo barre con `KENI_RADAR_AUTO=1`),
  - auto-produccion (Flujo C): auto-copy (`KENI_AUTOGEN=1`) y auto-arte
    (`KENI_AUTOGEN_ARTE=1`) que llevan los temas de entrada a borrador en la cola de
    revision; el resultado para en el gate humano (nada se publica solo),
  - Carril Rápido de Breaking (`KENI_BREAKING=1`): pre-genera borradores de copy para
    los temas breaking de Claro Sports sin draft aún; el equipo solo aprueba con un tap.
  - reaper de generaciones zombi (cierra como `error` las `ejecutando` huerfanas).

SAFE BY DEFAULT: este proceso NO publica nada ni crea/aprueba contenido por su
cuenta. Los unicos caminos que lo harian estan gated por env y vienen AUSENTES por
defecto (`KENI_PUBLICAR_REAL`, `KENI_RADAR_AUTO`, `KENI_AUTOGEN`, `KENI_AUTOGEN_ARTE`).
La auto-produccion (autogen) PRODUCE hasta el borrador, pero NUNCA publica: el posteo
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
    from .auto_avance import iniciar_auto_avance
    from .autogen_arte import iniciar_autogen_arte
    from .autogen_copy import iniciar_autogen
    from .breaking_daemon import iniciar_breaking
    from .comercial import iniciar_captura_programada
    from .eventos_scanner import iniciar_scanner_vencimientos
    from .investigador import iniciar_investigador
    from .media_gc_daemon import iniciar_media_gc
    from .metricas_piezas_refresco import iniciar_refresco_piezas
    from .metricas_refresco import iniciar_refresco_metricas
    from .pipeline_contenido import iniciar_pipeline
    from .programador import iniciar_programador
    from .radar_auto import iniciar_radar_auto
    from .reaper_generaciones import iniciar_reaper
    from .sugerencias_algoritmo import iniciar_sugerencias_editoriales

    iniciar_captura_programada()
    iniciar_programador()  # DRY-RUN salvo KENI_PUBLICAR_REAL=1: nunca publica solo.
    iniciar_scanner_vencimientos()
    iniciar_refresco_metricas()
    iniciar_refresco_piezas()
    iniciar_alertas_rendimiento()  # solo lee + emite eventos; KENI_ALERTAS_RENDIMIENTO=0 lo apaga.
    iniciar_radar_auto()  # no arranca salvo KENI_RADAR_AUTO=1 (def OFF).
    # Investigador (Fase 1): materializa el snapshot del Radar por marca para que Radar/Parrilla
    # lean del snapshot (rapido, sin red) en vez de golpear fuentes en cada request. GATEADO y
    # SAFE BY DEFAULT: el hilo arranca SIEMPRE pero solo materializa con KENI_INVESTIGADOR=1
    # (def OFF). Sin el flag, los endpoints siguen en vivo (comportamiento de Fase 0 intacto).
    iniciar_investigador()
    # TUBERIA automatica (Flujo C): los daemons de auto-produccion. Encadenan
    # entrada -> (radar_auto) -> copy -> arte -> cola de revision. GATEADOS y SAFE BY
    # DEFAULT: el hilo arranca SIEMPRE pero solo barre con su flag ON (KENI_AUTOGEN /
    # KENI_AUTOGEN_ARTE, def OFF). Sin ellos no se auto-genera nada. Antes solo `__main__`
    # los arrancaba; con el split de servicios (NINGUN proceso hosted corre `__main__`) sin
    # esto la auto-produccion NO correria en produccion aunque se encendieran los flags.
    iniciar_autogen()  # auto-copy; no barre salvo KENI_AUTOGEN=1 (def OFF).
    iniciar_breaking()  # Carril Rápido de Breaking (Claro Sports); no barre salvo KENI_BREAKING=1 (def OFF).
    iniciar_autogen_arte()  # auto-arte; no barre salvo KENI_AUTOGEN_ARTE=1 (def OFF) ni sin proveedor de imagen.
    # Pipeline de contenido CI→CD→QA por marca (ADITIVO, SAFE BY DEFAULT): ingiere RSS, genera
    # copy+arte y valida, registrando cada etapa en "Actividad IA"; deja borradores en revision.
    # No barre salvo KENI_PIPELINE=1 (def OFF); nunca publica.
    iniciar_pipeline()
    # Auto-avance "dale el OK" (Flujo D): lleva SOLO a en_revision las piezas listas (copy out +
    # copy in/exención + imagen con formato + QA 🟢/🟡) y lanza la QA de las que falte. GATEADO:
    # no barre salvo KENI_AUTO_AVANCE=1 (def OFF). Abre los OK del equipo; nunca aprueba ni publica.
    iniciar_auto_avance()
    iniciar_refresco_algoritmos()  # ingesta de feeds de algoritmo; solo lee si KENI_ALGORITMOS_AUTO=1.
    iniciar_sugerencias_editoriales()  # digest diario de sugerencias; encola solo si KENI_SUGERENCIAS_EDITORIALES=1.
    iniciar_media_gc()  # GC de media huerfana; no borra salvo KENI_MEDIA_GC=1 (def OFF).
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
