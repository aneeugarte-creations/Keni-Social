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

    from .alertas_rendimiento import iniciar_alertas_rendimiento
    from .algoritmos_refresco import iniciar_refresco_algoritmos
    from .recolectar_daemon import iniciar_ingesta
    from .media_gc_daemon import iniciar_media_gc
    from .metricas_piezas_refresco import iniciar_refresco_piezas
    from .metricas_refresco import iniciar_refresco_metricas
    from .noticias_gc_daemon import iniciar_noticias_gc
    from .patrones_refresco import iniciar_refresco_patrones
    from .pipeline_contenido import iniciar_pipeline
    from .limpiador_generaciones import iniciar_limpiador
    from .trends_daemon import iniciar_trends

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
    # deploy anterior) y cada N min. Antes solo se cableaba en `__main__` (servidor monolitico);
    # con el split de servicios (Fase 3) NINGUN proceso hosted corre `__main__`, asi que sin
    # esto el recolector no corria en produccion y los sueltos quedaban "ejecutando" para siempre.
    iniciar_limpiador()

    # LISTENER DE CONTROL (gestion de la cuenta de Claude desde el panel admin): solo se
    # monta si hay `KENI_CONTROL_BEARER`. Vive aqui (no en el back) porque cambiar la cuenta
    # ejecuta `claude` (auth/login/logout, /usage) y el back no lo tiene; el `daemons` es de
    # instancia unica, ideal para el login interactivo que mantiene un proceso vivo.
    from .control import iniciar_control

    iniciar_control()

    # Los daemons son hilos; el proceso principal queda en un bucle de LATIDO: toca el
    # fichero de liveness cada _LATIDO_SEG para que el healthcheck del contenedor (deploy)
    # distinga "proceso vivo" de "proceso colgado/atascado" sin depender de la BD. Antes era
    # un Event().wait() mudo: el contenedor solo se reiniciaba si el proceso MORIA, nunca
    # si quedaba colgado.
    from . import latidos

    while True:
        latidos.tocar_fichero()
        time.sleep(_LATIDO_SEG)
    return 0  # inalcanzable; conserva la firma


if __name__ == "__main__":
    sys.exit(main())
