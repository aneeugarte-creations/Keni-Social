"""GENERACIONES · piezas COMUNES: constantes, helpers de id/tiempo y registro en memoria.

Submódulo interno del paquete `generaciones` (ver `__init__.py`, que re-exporta la
superficie pública estable). Aquí viven las CONSTANTES de estado/fase/motivo/tipos, los
helpers triviales (`nuevo_id`, `ahora_iso`, `_timeout`), el logger del dominio, el registro
EN MEMORIA de trabajos en curso (`_HANDLES`/`_HANDLES_LOCK`) y el alias de tipo `Procesar`.
Sin estado de negocio: solo cimientos compartidos por `_almacen` y `_lanzadores`.

`ColaLlenaError` se RE-EXPORTA aquí (clase BASE del backpressure de admisión —
presupuesto/pausa/prompt; la cola ya no tiene tope, R-NO-LIMIT): los endpoints capturan
`generaciones.ColaLlenaError` sin acoplarse al módulo `dominio.runner`. Lo usan otros
módulos, no este, de ahí el `noqa: F401` en el import.
"""

from __future__ import annotations

import logging
import re
import threading
import uuid
from collections.abc import Callable
from typing import Any

from .. import config
from ..dominio import stream
from ..dominio.runner import (  # noqa: F401  (re-export; ver nota arriba)
    ColaLlenaError,
    GeneracionPausadaError,
    PresupuestoAgotadoError,
    PromptExcesivoError,
)
from ..tiempo import ahora_iso

__all__ = [
    "ColaLlenaError",
    "GeneracionPausadaError",
    "PresupuestoAgotadoError",
    "PromptExcesivoError",
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
    "TIPOS",
    "Procesar",
    "_ESTADOS_TERMINALES",
    "_ES_ID",
    "_HANDLES",
    "_HANDLES_LOCK",
    "_LISTADO_MAX",
    "_log",
    "_timeout",
    "ahora_iso",
    "nuevo_id",
    "evento_terminal",
    "notificar_terminal",
    "descartar_evento_terminal",
]

# Logger del lanzador de generaciones: cuelga del logger raiz del paquete (#123), asi
# `configurar_logging()` fija nivel/handler para todo. Aqui logueamos los fallos del hilo
# de generacion CON el job-id en vez de tragarlos (antes `except Exception: pass`).
_log = logging.getLogger("keni_consola.generaciones")

# Estados terminales e intermedio de un trabajo.
ESTADO_EJECUTANDO = "ejecutando"
ESTADO_COMPLETADO = "completado"
ESTADO_ERROR = "error"
# Fases de PROGRESO (en que etapa va el run, no cuanto falta). Re-exportadas del dominio
# (`stream`), unica fuente. La UI las pinta ("Razonando…" → "Escribiendo…" → "Terminando…").
FASE_RAZONANDO = stream.FASE_RAZONANDO
FASE_GENERANDO = stream.FASE_GENERANDO
FASE_COMPLETADO = stream.FASE_COMPLETADO
# Motivos terminales (campo `motivo`): para que el llamante/UI distingan el porque.
MOTIVO_TIMEOUT = "timeout"
MOTIVO_COLA_LLENA = "cola_llena"
MOTIVO_CANCELADO = "cancelado"
# Una generacion quedo `ejecutando` pero su proceso murio (reinicio/deploy, OOM, worker
# matado, o `generar()` colgado): el finalizador nunca corrio. El recolector la marca asi.
MOTIVO_INTERRUMPIDO = "interrumpido"

# Tipos de trabajo (para que el frontend sepa como renderizar el resultado).
TIPOS = (
    "copy", "rss", "hashtags", "imagen", "verificacion", "revision", "prompt",
    "parrilla-import", "insumos", "import-calendario",
    # Taller EVERGREEN / brainstorming: `evergreen-ideas` = la PROPUESTA de ideas evergreen (IA);
    # `evergreen` = el copy de una idea APROBADA (pieza `flujo='evergreen'` del tablero).
    "evergreen-ideas", "evergreen",
    # Jobs de PROCESO (no-claude) del motor de video (Ola VIDEO): render con ffmpeg y
    # transcripcion ASR. Se cuelgan de Actividad IA igual que el resto de generaciones.
    "render-video", "transcribir",
)

# PROCESO de la maquina (ADR 0011): la frontera entre los DOS loops. INVESTIGACION es el motor
# de noticias —Admitir + verificación/Verificar de la fuente + Fusionar/Clasificar/Traducir (Haiku del
# pool)—; PRODUCCION es la maquina de contenido —Redactar + Ilustrar + avance—. Comparten la
# MISMA cola y el MISMO pool (no hay dos colas): el `proceso` solo CLASIFICA el trabajo para
# poder medir cada lado por separado en el Monitor. Se SELLA en el registro al lanzar (campo
# `proceso`); para registros previos a este campo, `proceso_de` lo DEDUCE de tipo/etiqueta.
PROCESO_INVESTIGACION = "investigacion"
PROCESO_PRODUCCION = "produccion"
PROCESOS = frozenset({PROCESO_INVESTIGACION, PROCESO_PRODUCCION})


def proceso_de(reg: dict[str, Any]) -> str:
    """Proceso (investigacion|produccion) de una generacion. Prefiere el campo SELLADO.

    Si el registro trae `proceso` valido (sellado al lanzar tras ADR 0011), lo usa. Para
    registros PREVIOS al sello, lo deduce: la verificación de la fuente (Verificar) y los marcadores
    CI/verificación son Investigacion; el copy del pipeline y los marcadores CD/ARTE son Produccion; el
    resto (copy manual, imagen, hashtags, video, prompt, evergreen...) es Produccion (la maquina
    de contenido). Defensivo: nunca lanza; default Produccion ante lo desconocido.
    """
    if not isinstance(reg, dict):
        return PROCESO_PRODUCCION
    sellado = (reg.get("proceso") or "").strip()
    if sellado in PROCESOS:
        return sellado
    tipo = (reg.get("tipo") or "").strip()
    etiqueta = reg.get("etiqueta") or ""
    if tipo == "pipeline_etapa":
        # La etapa viaja en la etiqueta ("ADMITIR · ..."/"VERIFICAR · ..."/"REDACTAR · ..."/"ILUSTRAR · ...").
        return PROCESO_INVESTIGACION if etiqueta.startswith(("ADMITIR", "VERIFICAR")) else PROCESO_PRODUCCION
    if tipo == "pipeline":
        # La verificación de la fuente (Verificar) lleva etiqueta "Verificar · ..."; el resto es copy/arte.
        return (
            PROCESO_INVESTIGACION
            if etiqueta.startswith("Verificar ·")
            else PROCESO_PRODUCCION
        )
    return PROCESO_PRODUCCION

# Wall-timeout (segundos) de un trabajo de claude en background. Override por
# `KENI_CLAUDE_TIMEOUT` (centralizado en `config.claude_timeout`).

# Registro EN MEMORIA de trabajos en curso (id -> handle). El YAML es la fuente de
# verdad para el sondeo; esto solo permite inspeccionar/cancelar localmente.
_HANDLES: dict[str, dict[str, object]] = {}
_HANDLES_LOCK = threading.Lock()

# SEÑALIZACION IN-PROCESO del fin de un trabajo (gen_id -> Event). El worker corre el job en
# el MISMO proceso que lo espera (`worker._esperar_terminal`); el hilo que fija el estado
# terminal (`_almacen.actualizar`) DESPIERTA al que espera con este Event, en vez de obligarlo
# a re-stat/re-parsear el YAML cada 200 ms. El Event se crea perezosamente (get-or-create) y se
# DESCARTA cuando el que espera termina, asi no se acumulan eventos sueltos. Si el job lo
# fijara OTRO proceso (no deberia: quien reclama ejecuta), el que espera cae a un sondeo de
# disco acotado como red de seguridad (ver `worker._esperar_terminal`).
_TERMINALES: dict[str, threading.Event] = {}
_TERMINALES_LOCK = threading.Lock()


def evento_terminal(gen_id: str) -> threading.Event:
    """Event (get-or-create) que se señaliza cuando `gen_id` alcanza un estado terminal.

    El que ESPERA lo obtiene ANTES de leer el estado: asi una señal que llegue entre la
    lectura y el `wait` no se pierde (el Event ya quedo `set`). Debe pareársele un
    `descartar_evento_terminal(gen_id)` al terminar para no fugar entradas del registro.
    """
    with _TERMINALES_LOCK:
        ev = _TERMINALES.get(gen_id)
        if ev is None:
            ev = threading.Event()
            _TERMINALES[gen_id] = ev
        return ev


def notificar_terminal(gen_id: str) -> None:
    """Despierta al que espera el fin de `gen_id` (no-op si nadie espera). La llama `actualizar`."""
    with _TERMINALES_LOCK:
        ev = _TERMINALES.get(gen_id)
    if ev is not None:
        ev.set()


def descartar_evento_terminal(gen_id: str) -> None:
    """Olvida el Event de `gen_id` (lo llama el que esperaba, al terminar). Idempotente."""
    with _TERMINALES_LOCK:
        _TERMINALES.pop(gen_id, None)

# Numero de generaciones recientes que devuelve el listado.
_LISTADO_MAX = 50

# Estados TERMINALES de una generacion (ya no esta en curso). Una idempotencia solo retiene a
# DOS lanzamientos del MISMO trabajo mientras hay uno EN CURSO; al terminar, un re-lanzamiento
# legitimo (el usuario quiere regenerar) vuelve a correr.
_ESTADOS_TERMINALES = frozenset({ESTADO_COMPLETADO, ESTADO_ERROR})

# Patron del NOMBRE base de un registro de generacion (`<id>.yaml`): exactamente 12 hex,
# tal como los acuna `nuevo_id`. La limpieza solo borra ficheros cuyo stem case con esto (nunca
# temporales `.tmp-*` ni nombres ajenos en el dir).
_ES_ID = re.compile(r"[0-9a-f]{12}")

# `procesar(salida, metricas) -> dict`: parsea la salida final de claude y crea los
# artefactos (historial, piezas, hashtags…), devolviendo el `resultado` que se
# guarda en el registro. Corre en el hilo del trabajo al COMPLETARSE con exito.
Procesar = Callable[[str, Any], dict[str, Any]]


def _timeout() -> int:
    """Wall-timeout (s) de un trabajo de claude; `KENI_CLAUDE_TIMEOUT` lo sobreescribe."""
    return config.claude_timeout()


def nuevo_id() -> str:
    """Nuevo id de generacion (12 hex)."""
    return uuid.uuid4().hex[:12]

