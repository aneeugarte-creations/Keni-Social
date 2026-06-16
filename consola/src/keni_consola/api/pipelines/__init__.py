"""API PIPELINES: el feed UNIFICADO de Producción (runs del pipeline + actividad suelta).

Cada `contenido` con `origen='pipeline'` (los que produce el daemon
`pipeline_contenido`) es una RUN: el recorrido de UNA pieza por las etapas
CI (Ingesta) → CD (Copy + placa) → QA (Validación) → Aprobación, con un estado por
etapa derivado del ESTADO REAL de la pieza y sus publicaciones por plataforma (no solo
de los logs: robusto y auto-curativo). El detalle por run añade el LOG de actividad de
las etapas (las generaciones-marcador `tipo='pipeline'` correlacionadas por `contenido_id`).

La LISTA ya no es solo de runs: es el feed de la página Producción, que MEZCLA en una
sola línea temporal las runs del pipeline (`clase: "run"`) y la ACTIVIDAD SUELTA
(`clase: "actividad"`): generaciones que no nacieron de una run (copy manual, imágenes,
investigación, importaciones…) y los runs de agente. Cada item suelto se presenta con la
MISMA forma que una run, con UNA etapa (su tipo de trabajo), para que la UI lo pinte con
la misma tarjeta y el mismo detalle entrada/salida. Antes esto vivía partido en dos
pestañas (Feed / Pipelines) con contenido medio duplicado y medio faltante en ambas.
Todos los items (runs incluidas) llevan `metricas` (items, tokens, coste, duración)
sumadas de sus generaciones correlacionadas.

Endpoints (solo lectura):
  - `GET /api/pipelines?marca=&etapa=&estado=&tipo=&clase=&limite=50`
      -> `{"pipelines": [item, ...], "paginacion": {...}}`        · `feed.listar`
  - `GET /api/pipelines/problemas?marca=&limite=50` -> `{"problemas": [...], "total": n}`
      · `problemas.problemas`
  - `GET /api/pipelines/{pipeline_id}` -> `{"pipeline": run, "actividad": [...]}`
      · `detalle.detalle`

Estructura del paquete (extraído del monolito `pipelines.py`, ~1080 líneas):
  - `_comun`    constantes compartidas + presentación (`_red_nombre`/`_marca_nombre`/`_verificacion_fuente_de`).
  - `_runs`     motor de derivación de runs y sus 7 etapas (núcleo compartido por lista y detalle).
  - `_metricas` agregación de métricas por run + evidencia de pool / arte IA.
  - `feed` · `problemas` · `detalle`  los tres endpoints.

Errores en español como `{"error": "..."}`; sin tracebacks crudos.
"""

from __future__ import annotations

from starlette.routing import Route

from ._runs import _estado_global  # re-exportado: lo importa test_api_pipelines  # noqa: F401
from .detalle import detalle
from .feed import listar
from .problemas import problemas

RUTAS = [
    Route("/api/pipelines", listar, methods=["GET"]),
    # ANTES del detalle: Starlette matchea en orden y `{pipeline_id}` capturaría "problemas".
    Route("/api/pipelines/problemas", problemas, methods=["GET"]),
    Route("/api/pipelines/{pipeline_id}", detalle, methods=["GET"]),
]
