"""API Metricas: opciones, reporte consolidado, comparativa de rangos y export.

Consume la fachada estable `keni_metricas.servicio` (SOLO LECTURA); ya no importa
internals (`config`/`reporte`/`schema`). El SPA dibuja el dashboard a partir de
`/api/metricas/reporte` (ya no hay endpoint HTML de dashboard).

  - `/api/metricas/opciones`: marcas + rangos para poblar los selectores.
  - `/api/metricas/reporte`: total consolidado + por cuenta (nombres resueltos).
  - `/api/metricas/comparar`: comparativa A vs B (total + por marca).
  - `/api/metricas/analisis`: análisis diario con narrativa "qué cambió y por qué"
    + siguiente paso; ensambla reporte + picos en una lectura accionable.
  - `/api/metricas/piezas-export`: descarga del Top 5 / Peores 5 de piezas (csv|md|json).
  - `/api/metricas/piezas-por-etiqueta`: rendimiento del periodo por serie/tipo (cruce
    piezas↔contenido para resolver tipo_contenido + etiquetas; Item C).
  - `/api/metricas/lineas`: rendimiento del periodo por LÍNEA (etiqueta clase `vertical`)
    y por ORIGEN (clase `origen`); "qué línea funciona" + dual editorial-vs-impuesto.
  - `/api/metricas/export.{csv,md,json}`: descargas (misma serializacion que el CLI).

DEFERIDO / BLOQUEADO — "procedencia de la audiencia" (de dónde viene quién ve el
contenido): NO implementado a propósito. Requiere la Meta Graph API por cliente
(insights de audiencia/demografía con token y permisos de cada página), que el
proveedor primario (Metricool) no expone de forma uniforme. Queda fuera del v1 de
solo-lectura multi-fuente hasta cablear Meta por cliente.

================================================================================
ESTRUCTURA DEL PAQUETE (refactor sin cambio de comportamiento)

Este módulo era un único `metricas.py` (~1400 líneas); se partió en submódulos por
área funcional. El descubridor de `api/__init__.py` (`pkgutil.iter_modules`) NO
desciende dentro de subpaquetes, así que la ÚNICA superficie pública sigue siendo la
variable `RUTAS` que este `__init__` exporta (mismo orden/paths/métodos que antes).

  - `_comun.py`  : imports + helpers compartidos (rango, marca, nombres, logger…).
  - `reporte.py` : opciones, reporte, comparar.
  - `analisis.py`: analisis.
  - `piezas.py`  : piezas, piezas_rendimiento, piezas_listado, pieza_historico,
                   piezas_por_etiqueta, lineas.
  - `series.py`  : tendencia, seguidores, desglose, crosstab, correlacion.
  - `estado.py`  : estado, refrescar.
  - `export.py`  : export_csv, export_md, export_json, piezas_export.
================================================================================
"""

from __future__ import annotations

from starlette.routing import Route

from .analisis import analisis
from .estado import estado, refrescar
from .export import export_csv, export_json, export_md, piezas_export
from .piezas import (
    lineas,
    pieza_historico,
    piezas,
    piezas_listado,
    piezas_por_etiqueta,
    piezas_rendimiento,
)
from .reporte import (
    _cobertura_por_marca,
    _comparar_totales,
    _suma_clics,
    comparar,
    opciones,
    reporte,
)
from .series import ads, correlacion, crosstab, desglose, ingesta, seguidores, tendencia

# `_comparar_totales`, `_suma_clics` y `_cobertura_por_marca` se re-exportan porque la
# suite (`test_api_metricas.py`) los importa de `keni_consola.api.metricas`; no son
# superficie de la API HTTP, solo helpers verificados por unidad. El resto de helpers
# privados viven en sus submódulos.
__all__ = [
    "RUTAS",
    "opciones",
    "reporte",
    "comparar",
    "analisis",
    "piezas",
    "piezas_export",
    "piezas_rendimiento",
    "piezas_listado",
    "pieza_historico",
    "piezas_por_etiqueta",
    "lineas",
    "tendencia",
    "seguidores",
    "desglose",
    "crosstab",
    "correlacion",
    "ads",
    "ingesta",
    "estado",
    "refrescar",
    "export_csv",
    "export_md",
    "export_json",
    "_comparar_totales",
    "_suma_clics",
    "_cobertura_por_marca",
]


RUTAS = [
    Route("/api/metricas/opciones", opciones, methods=["GET"]),
    Route("/api/metricas/reporte", reporte, methods=["GET"]),
    Route("/api/metricas/comparar", comparar, methods=["GET"]),
    Route("/api/metricas/analisis", analisis, methods=["GET"]),
    Route("/api/metricas/piezas", piezas, methods=["GET"]),
    Route("/api/metricas/piezas-export", piezas_export, methods=["GET"]),
    Route("/api/metricas/piezas-rendimiento", piezas_rendimiento, methods=["GET"]),
    Route("/api/metricas/piezas-listado", piezas_listado, methods=["GET"]),
    Route("/api/metricas/pieza-historico", pieza_historico, methods=["GET"]),
    Route("/api/metricas/piezas-por-etiqueta", piezas_por_etiqueta, methods=["GET"]),
    Route("/api/metricas/lineas", lineas, methods=["GET"]),
    Route("/api/metricas/tendencia", tendencia, methods=["GET"]),
    Route("/api/metricas/seguidores", seguidores, methods=["GET"]),
    Route("/api/metricas/desglose", desglose, methods=["GET"]),
    Route("/api/metricas/crosstab", crosstab, methods=["GET"]),
    Route("/api/metricas/correlacion", correlacion, methods=["GET"]),
    Route("/api/metricas/ads", ads, methods=["GET"]),
    Route("/api/metricas/ingesta", ingesta, methods=["GET"]),
    Route("/api/metricas/estado", estado, methods=["GET"]),
    Route("/api/metricas/refrescar", refrescar, methods=["POST"]),
    Route("/api/metricas/export.csv", export_csv, methods=["GET"]),
    Route("/api/metricas/export.md", export_md, methods=["GET"]),
    Route("/api/metricas/export.json", export_json, methods=["GET"]),
]
