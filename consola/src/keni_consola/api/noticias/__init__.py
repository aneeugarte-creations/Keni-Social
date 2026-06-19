"""API del MOTOR DE INGESTA PERSISTENTE (Ola A): archivo de artículos + cobertura.

Superficie de LECTURA del archivo (`noticias_items`) + curación ligera. El motor ingiere en
background (`recolectar_daemon`); aquí el equipo VE el flujo continuo, filtra, y decide qué USA
(lleva al tablero) o DESCARTA. Nada se publica desde aquí.

  - GET  /api/noticias            -> {items:[...], total} filtrable + paginado, recientes 1º.
  - POST /api/noticias/{id}/usar  -> lleva el item al tablero (borrador) + estado=usado.
  - POST /api/noticias/{id}/descartar -> estado=descartado.
  - GET  /api/noticias/cobertura  -> resumen de salud del motor (feeds, items 24h, frescura).

MARCA-AWARE: `marca` filtra el archivo; '' o ausente = todas (vista admin). El alta del
borrador (`usar`) reusa el MISMO camino que la aportación manual (`crear_publicacion` +
`autogen_redactar.lanzar_para_topic`, `origen='noticia'`). Validación: `marca`/`estado` de
allowlist; SQL parametrizado en `db`. Errores en español, sin tracebacks.

================================================================================
ESTRUCTURA DEL PAQUETE (refactor sin cambio de comportamiento)

Este módulo era un único `noticias.py` (~982 líneas); se partió en submódulos por área
funcional. El descubridor de `api/__init__.py` (`pkgutil.iter_modules`) NO desciende dentro
de subpaquetes, así que la ÚNICA superficie pública sigue siendo la variable `RUTAS` que este
`__init__` exporta (mismo orden/paths/métodos que antes).

  - `_comun.py`   : imports + helpers compartidos (validación de marca, redes iniciales,
                    serialización de un item, constantes de paginación/límites).
  - `items.py`    : pool de ÍTEMS del archivo (`listar`/`usar`/`descartar`) + monitor de
                    salud/stats de fuentes (`cobertura`/`salud`/`stats_fuentes_handler`).
  - `historias.py`: HISTORIAS (clusters): `listar_historias`, `mesa`, `detalle_historia`,
                    `usar_historia`, `descartar_historia`, `restaurar_historia` y los lotes
                    (`descartar-lote`/`borrar-lote`/`borrar-todo`).
================================================================================
"""

from __future__ import annotations

from starlette.routing import Route

from ._comun import _item_a_dict, _redes_iniciales, _validar_marca
from .historias import (
    _evaluar_umbral,
    _fuentes_timeline,
    _historia_a_dict,
    _pesos_score_publicos,
    _pieza_estado,
    _pieza_estado_de,
    borrar_historias_lote,
    borrar_todas_historias,
    descartar_historia,
    descartar_historias_lote,
    detalle_historia,
    listar_historias,
    mesa,
    restaurar_historia,
    usar_historia,
)
from .items import (
    _frescura_min,
    cobertura,
    construir_salud,
    descartar,
    listar,
    salud,
    stats_fuentes_handler,
    usar,
)

__all__ = [
    "RUTAS",
    # Handlers a nivel de ITEM + salud de fuentes.
    "listar",
    "usar",
    "descartar",
    "cobertura",
    "salud",
    "stats_fuentes_handler",
    "construir_salud",
    "_frescura_min",
    # Handlers de HISTORIAS (clusters) + la Mesa.
    "listar_historias",
    "mesa",
    "detalle_historia",
    "usar_historia",
    "descartar_historia",
    "restaurar_historia",
    "descartar_historias_lote",
    "borrar_historias_lote",
    "borrar_todas_historias",
    # Helpers compartidos / de serialización (re-exportados para terceros y tests).
    "_validar_marca",
    "_redes_iniciales",
    "_item_a_dict",
    "_historia_a_dict",
    "_fuentes_timeline",
    "_pieza_estado",
    "_pieza_estado_de",
    "_evaluar_umbral",
    "_pesos_score_publicos",
]


RUTAS = [
    Route("/api/noticias", listar, methods=["GET"]),
    Route("/api/noticias/cobertura", cobertura, methods=["GET"]),
    Route("/api/noticias/salud", salud, methods=["GET"]),
    # Rendimiento editorial por fuente (tracking de fuentes). ANTES de `/{item_id}/...` para
    # que `fuentes` nunca se interprete como un item_id.
    Route("/api/noticias/fuentes/stats", stats_fuentes_handler, methods=["GET"]),
    Route("/api/noticias/historias", listar_historias, methods=["GET"]),
    # La Mesa de redacción: pool segmentado por las líneas del plan + progreso del día.
    Route("/api/noticias/mesa", mesa, methods=["GET"]),
    # Los lotes van ANTES de `/historias/{cluster_id}` para que `descartar-lote`/`borrar-lote`/
    # `borrar-todo` no se confundan con un cluster_id (difieren en método, pero el orden lo deja
    # explícito y a prueba de futuros GET).
    Route("/api/noticias/historias/descartar-lote", descartar_historias_lote, methods=["POST"]),
    Route("/api/noticias/historias/borrar-lote", borrar_historias_lote, methods=["POST"]),
    Route("/api/noticias/historias/borrar-todo", borrar_todas_historias, methods=["POST"]),
    Route("/api/noticias/historias/{cluster_id}", detalle_historia, methods=["GET"]),
    Route("/api/noticias/historias/{cluster_id}/usar", usar_historia, methods=["POST"]),
    Route("/api/noticias/historias/{cluster_id}/descartar", descartar_historia, methods=["POST"]),
    Route("/api/noticias/historias/{cluster_id}/restaurar", restaurar_historia, methods=["POST"]),
    Route("/api/noticias/{item_id}/usar", usar, methods=["POST"]),
    Route("/api/noticias/{item_id}/descartar", descartar, methods=["POST"]),
]
