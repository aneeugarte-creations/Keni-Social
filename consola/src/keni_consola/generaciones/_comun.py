"""GENERACIONES · piezas COMUNES: constantes, helpers de id/tiempo y registro en memoria.

Submódulo interno del paquete `generaciones` (ver `__init__.py`, que re-exporta la
superficie pública estable). Aquí viven las CONSTANTES de estado/fase/motivo/tipos, los
helpers triviales (`nuevo_id`, `ahora_iso`, `_timeout`), el logger del dominio, el registro
EN MEMORIA de trabajos en vuelo (`_HANDLES`/`_HANDLES_LOCK`) y el alias de tipo `Procesar`.
Sin estado de negocio: solo cimientos compartidos por `_almacen` y `_lanzadores`.

`ColaLlenaError` se RE-EXPORTA aquí (tope de cola, #137): los endpoints capturan
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
)
from ..tiempo import ahora_iso

__all__ = [
    "ColaLlenaError",
    "GeneracionPausadaError",
    "PresupuestoAgotadoError",
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
# Migracion suave: registros viejos sin `fase` la traen como "" (la UI cae al comportamiento
# previo); por eso NO sube la version de esquema YAML (anadir un campo opcional vacio es compat).
FASE_RAZONANDO = stream.FASE_RAZONANDO
FASE_GENERANDO = stream.FASE_GENERANDO
FASE_COMPLETADO = stream.FASE_COMPLETADO
# Motivos terminales (campo `motivo`): para que el llamante/UI distingan el porque.
MOTIVO_TIMEOUT = "timeout"
MOTIVO_COLA_LLENA = "cola_llena"
MOTIVO_CANCELADO = "cancelado"
# Una generacion quedo `ejecutando` pero su proceso murio (reinicio/deploy, OOM, worker
# matado, o `generar()` colgado): el finalizador nunca corrio. El reaper la marca asi.
MOTIVO_INTERRUMPIDO = "interrumpido"

# Tipos de trabajo (para que el frontend sepa como renderizar el resultado).
TIPOS = (
    "copy", "rss", "hashtags", "imagen", "verificacion", "qa-editorial", "prompt",
    "parrilla-import", "insumos", "import-calendario",
    # Taller EVERGREEN / brainstorming: `evergreen-ideas` = la PROPUESTA de ideas evergreen (IA);
    # `evergreen` = el copy de una idea APROBADA (pieza `flujo='evergreen'` del tablero).
    "evergreen-ideas", "evergreen",
    # Jobs de PROCESO (no-claude) del motor de video (Ola VIDEO): render con ffmpeg y
    # transcripcion ASR. Se cuelgan de Actividad IA igual que el resto de generaciones.
    "render-video", "transcribir",
)

# Wall-timeout (segundos) de un trabajo de claude en background. Override por
# `KENI_CLAUDE_TIMEOUT` (centralizado en `config.claude_timeout`). Sustituye al viejo
# timeout de 180 s de la peticion sincrona.

# Registro EN MEMORIA de trabajos en vuelo (id -> handle). El YAML es la fuente de
# verdad para el sondeo; esto solo permite inspeccionar/cancelar localmente.
_HANDLES: dict[str, dict[str, object]] = {}
_HANDLES_LOCK = threading.Lock()

# Numero de generaciones recientes que devuelve el listado.
_LISTADO_MAX = 50

# Estados TERMINALES de una generacion (ya no esta en vuelo). Una idempotencia solo retiene a
# DOS lanzamientos del MISMO trabajo mientras hay uno EN VUELO; al terminar, un re-lanzamiento
# legitimo (el usuario quiere regenerar) vuelve a correr.
_ESTADOS_TERMINALES = frozenset({ESTADO_COMPLETADO, ESTADO_ERROR})

# Patron del NOMBRE base de un registro de generacion (`<id>.yaml`): exactamente 12 hex,
# tal como los acuna `nuevo_id`. La poda solo borra ficheros cuyo stem case con esto (nunca
# temporales `.tmp-*` ni nombres ajenos en el dir).
_ES_ID = re.compile(r"[0-9a-f]{12}")

# `procesar(salida, metricas) -> dict`: parsea la salida final de claude y crea los
# artefactos (historial, publicaciones, hashtags…), devolviendo el `resultado` que se
# guarda en el registro. Corre en el hilo del trabajo al COMPLETARSE con exito.
Procesar = Callable[[str, Any], dict[str, Any]]


def _timeout() -> int:
    """Wall-timeout (s) de un trabajo de claude; `KENI_CLAUDE_TIMEOUT` lo sobreescribe."""
    return config.claude_timeout()


def nuevo_id() -> str:
    """Nuevo id de generacion (12 hex)."""
    return uuid.uuid4().hex[:12]

