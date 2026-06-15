"""Dominio GENERACIONES: trabajos de IA en SEGUNDO PLANO, seguibles en vivo.

TODA generacion de IA de la consola (copy desde nota, copy desde RSS, hashtags,
imagen) corre como un TRABAJO en segundo plano en vez de bloquear la peticion HTTP:

  1. El endpoint valida, crea un registro `{estado: "ejecutando"}` y ENCOLA el trabajo
     (#130 Fase 2): persiste un `spec` serializable en la cola (`cola.py`/tabla `jobs`).
  2. El POST responde de INMEDIATO con el registro (no bloquea, no hay timeout de 180 s
     en la peticion). El trabajo sigue aunque el usuario cambie de pestana o de pagina.
  3. Un WORKER (in-proceso en local, servicio aparte en hosted; ver `worker.py`) CLAVA el
     job, reconstruye prompt+post-procesado desde el `spec` y corre `claude -p` con el
     runner de `lanzar_job_claude` (mismo #137: grupo de procesos, kill del arbol, tope de
     cola, cancelacion). El hilo avanza el registro de forma incremental y ATOMICA: persiste
     el TEXTO en vivo (stream token a token con `--include-partial-messages`) + metricas
     parciales. Al terminar fija el estado terminal (`completado` con el `resultado` ya
     procesado, o `error`).
  4. El frontend SONDEA `GET /api/generaciones/{id}` hasta el estado terminal.

DESACOPLO (#130 Fase 2 / ADR 0002 Fase B): el back ENCOLA (`encolar_job_claude`) y el
WORKER EJECUTA (`lanzar_job_claude`). `lanzar_job_claude` NO desaparece: es la primitiva de
ejecucion del worker (con todo el #137). En el perfil LOCAL el worker corre en un hilo del
propio back (UX de una sola maquina intacta, sin servicio aparte); en HOSTED corre en un
contenedor `worker` que SI tiene `claude` (la imagen del back ya no lleva Node).

El registro YAML es la FUENTE DE VERDAD del sondeo. Los ARTEFACTOS durables (historial
de skills, publicaciones, imagenes) se guardan en su sitio de siempre; el registro de
generacion es estado de ejecucion (efimero, inspeccionable), por eso vive aparte de los
datos editoriales:

    <KENI_CONSOLA_GENERACIONES>/<id>.yaml         (def local ~/.config/keni-social/
    generaciones; bajo KENI_DATA_DIR cuelga de <data_dir>/keni-social/generaciones)

LANZADORES INYECTABLES: `lanzar_job_claude` y `lanzar_job_imagen` son funciones a nivel
de modulo; `crear_app(...)` las reasigna y los tests pasan fakes que NO usan Popen ni
red (NUNCA se llama a `claude` ni a un proveedor de imagen real en tests). El
`procesar` (callback que parsea la salida y crea los artefactos) SI corre en los tests
(con una salida canned), asi se cubre el post-procesado real.

SEGURIDAD: escritura atomica (tmp + os.replace); el id de un registro se repara contra
traversal al leer; sin shell (argv como lista). Errores en espanol, sin tracebacks.

ENDURECIMIENTO PERMANENTE (#137): la generacion se hace —y se SEGUIRA haciendo— con el
subprocess `claude -p` (ahora en sandbox por usuario; ver ADR 0001), NO con la API de
Claude. Por eso este lanzador NO es transitorio: su robustez es deuda PERMANENTE:
  - GRUPO DE PROCESOS: el subprocess arranca con su propio grupo (`runner.lanzar_proc`)
    y al timeout/cancel se mata el ARBOL entero (`runner.matar_arbol`), no solo el padre.
  - ADMISION SIN TOPE DE COLA (R-NO-LIMIT): la cola SIEMPRE admite; el unico limite es la
    concurrencia (`max_jobs`), el exceso ESPERA. El límite VOLUNTARIO de presupuesto/pausa sí
    rechaza (subclases de `ColaLlenaError` -> 429), reflejado como `error`/`motivo="cola_llena"`.
  - CANCELACION: `cancelar(gen_id)` mata el arbol del job y lo marca cancelado; el usuario
    la dispara desde la SPA (`POST /api/generaciones/{id}/cancelar`).
  - SIN TRAGAR EXCEPCIONES: los fallos del hilo se LOGUEAN correlacionados por job-id (y
    por el request-id de la peticion que lo lanzo, #123), ya no se silencian en mudo.

"""

from __future__ import annotations

# Imports a nivel de módulo que el módulo original exponía (algunos consumidores y tests
# acceden p.ej. a `generaciones.runner`, `generaciones.preferencias`, etc.): se RE-EXPORTAN
# aquí para mantener IDÉNTICA la superficie del paquete barrel. Llevan supresión de F401
# (no se usan en este __init__, solo se re-exponen); su forma canónica vive en los submódulos.
import hashlib  # noqa: F401
import logging  # noqa: F401
import os  # noqa: F401
import re  # noqa: F401
import shutil  # noqa: F401
import subprocess  # noqa: F401
import threading  # noqa: F401
import uuid  # noqa: F401
from collections.abc import Callable  # noqa: F401
from datetime import datetime  # noqa: F401
from pathlib import Path  # noqa: F401
from typing import Any  # noqa: F401

import yaml  # noqa: F401
from keni_shared.esquema_yaml import migrar, sellar  # noqa: F401

from .. import config, preferencias, rutas  # noqa: F401
from ..dominio import runner, stream  # noqa: F401
from ..io_atomico import bloqueo_archivo, escribir_atomico  # noqa: F401
from ..observabilidad import request_id_actual  # noqa: F401
from ._almacen import (
    _RETENCION_DIAS_DEF,
    _RETENCION_MAX_DEF,
    _TIPO,
    _cuerpo,
    _entero_env,
    _escribir_yaml_atomico,
    _leer_idem,
    _leer_yaml,
    _publico,
    _ruta,
    _ruta_idem,
    _todas_ordenadas,
    actualizar,
    borrar_registro,
    clave_idempotencia,
    contar,
    crear,
    crear_idempotente,
    listar,
    obtener,
    purgar_generaciones,
    raiz,
    reclamar_atascadas,
)

# --- Re-exportación de la superficie del dominio (submódulos internos) --------------- #
from ._comun import (
    _ES_ID,
    _ESTADOS_TERMINALES,
    _HANDLES,
    _HANDLES_LOCK,
    _LISTADO_MAX,
    ESTADO_COMPLETADO,
    ESTADO_EJECUTANDO,
    ESTADO_ERROR,
    FASE_COMPLETADO,
    FASE_GENERANDO,
    FASE_RAZONANDO,
    MOTIVO_CANCELADO,
    MOTIVO_COLA_LLENA,
    MOTIVO_INTERRUMPIDO,
    MOTIVO_TIMEOUT,
    PROCESO_INVESTIGACION,
    PROCESO_PRODUCCION,
    PROCESOS,
    TIPOS,
    ColaLlenaError,
    GeneracionPausadaError,
    PresupuestoAgotadoError,
    Procesar,
    PromptExcesivoError,
    _log,
    _timeout,
    ahora_iso,
    descartar_evento_terminal,
    evento_terminal,
    notificar_terminal,
    nuevo_id,
    proceso_de,
)
from ._lanzadores import (
    _ENV_DENYLIST_EXACTOS,
    _ENV_DENYLIST_PREFIJOS,
    _argv_claude,
    _entorno_generacion,
    _es_secreto_infra,
    cancelar,
    encolar_job_claude,
    encolar_job_proceso,
    lanzar_job_claude,
    lanzar_job_imagen,
)

__all__ = [
    # Constantes de estado/fase/motivo + tipos de trabajo.
    "ESTADO_EJECUTANDO",
    "ESTADO_COMPLETADO",
    "ESTADO_ERROR",
    "FASE_RAZONANDO",
    "FASE_GENERANDO",
    "FASE_COMPLETADO",
    "MOTIVO_TIMEOUT",
    "MOTIVO_COLA_LLENA",
    "MOTIVO_CANCELADO",
    "MOTIVO_INTERRUMPIDO",
    "PROCESO_INVESTIGACION",
    "PROCESO_PRODUCCION",
    "PROCESOS",
    "proceso_de",
    "TIPOS",
    "ColaLlenaError",
    "GeneracionPausadaError",
    "PresupuestoAgotadoError",
    "PromptExcesivoError",
    "Procesar",
    # Almacén / CRUD / idempotencia / limpieza / recolector de colgadas.
    "raiz",
    "crear",
    "crear_idempotente",
    "borrar_registro",
    "clave_idempotencia",
    "actualizar",
    "obtener",
    "listar",
    "contar",
    "purgar_generaciones",
    "reclamar_atascadas",
    "nuevo_id",
    "ahora_iso",
    # Señalización in-proceso del fin de un job (la usa `worker._esperar_terminal`).
    "evento_terminal",
    "notificar_terminal",
    "descartar_evento_terminal",
    # Lanzadores (inyectables) + cancelación.
    "encolar_job_claude",
    "encolar_job_proceso",
    "lanzar_job_claude",
    "lanzar_job_imagen",
    "cancelar",
    # Símbolos INTERNOS (prefijo `_`) re-exportados a propósito: algún consumidor o test los
    # alcanza vía `generaciones._<símbolo>` (constantes, helpers de almacén, internos del
    # lanzador). Se listan para preservar la superficie EXACTA del módulo original y para que
    # el barrel los re-exponga explícitamente (no son API pública nueva).
    "_ES_ID",
    "_ESTADOS_TERMINALES",
    "_HANDLES",
    "_HANDLES_LOCK",
    "_LISTADO_MAX",
    "_log",
    "_timeout",
    "_RETENCION_DIAS_DEF",
    "_RETENCION_MAX_DEF",
    "_TIPO",
    "_cuerpo",
    "_entero_env",
    "_escribir_yaml_atomico",
    "_leer_idem",
    "_leer_yaml",
    "_publico",
    "_ruta",
    "_ruta_idem",
    "_todas_ordenadas",
    "_ENV_DENYLIST_EXACTOS",
    "_ENV_DENYLIST_PREFIJOS",
    "_argv_claude",
    "_entorno_generacion",
    "_es_secreto_infra",
]
