"""Clustering de HISTORIAS sobre el archivo de artículos (Ola B) — capa PURA/testeable.

El motor de ingesta (Ola A) archiva miles de artículos crudos en `noticias_items`. Esta
capa los agrupa en HISTORIAS: la misma noticia contada por varias fuentes y a lo largo del
tiempo. Una historia (cluster) es la unidad newsroom — deduplicada, corroborada por N
fuentes distintas, puntuada y rankeable.

PURA: no toca BD ni red. El daemon de ingesta le pasa el item recién insertado y los
clusters de la ventana reciente (que cargó de `db`), decide a cuál unir (o crear uno
nuevo), y persiste el resultado. Determinista y testeable sin I/O.

Reutiliza la lógica de cruce de títulos del Radar (`radar._clave_fuzzy` + sinónimos +
`SequenceMatcher`) y la normalización/hash de `dominio.dedup`, para no reinventar el
fuzzy-matching ni divergir de cómo el Radar consolida temas.

Reglas de agrupación (`asignar`):
  - (a) MISMA `url_canonica_clustering` (host+path, SIN query): es literalmente el mismo
    recurso → mismo cluster, sin ambigüedad.
  - (b) si no, FUZZY del título normalizado del item contra el `titulo`/`clave` del cluster
    con ratio `SequenceMatcher` ≥ `umbral` (def `KENI_CLUSTER_UMBRAL` = 0.82). Conservador:
    títulos muy cortos no entran al fuzzy (ratios espurios).
  - si nada casa → cluster nuevo.

Scoring (`puntuar`): ver la fórmula documentada en su docstring.

ESTRUCTURA: este módulo era un solo fichero (1125 LOC); se troceó en un paquete por áreas
(`asignacion`, `corroboracion`, `scoring`, `relevancia`, `promocion`, con helpers comunes en
`_comun`). Este `__init__` es un FACADE: re-exporta VERBATIM la misma superficie pública (y los
helpers privados que usan los tests), sin cambiar comportamiento.
"""

from __future__ import annotations

# Submódulos hermanos de `dominio` reexportados para compatibilidad (p.ej. tests usan
# `clustering.similitud`): antes el módulo hacía `from . import dedup, similitud`.
from .. import dedup, similitud
from ._comun import BREAKING_PESO_DEF, BREAKING_VENTANA_H_DEF
from ._comun import _numeros_incompatibles as _numeros_incompatibles  # re-export para tests
from .asignacion import (
    Asignador,
    asignar,
    clave_cluster,
    grupos_lexicos,
    url_canonica_clustering,
)
from .corroboracion import (
    clasificar_verificacion,
    fuentes_detalle,
    peso_corroboracion,
    peso_ventana_actual,
    recalcular,
)
from .promocion import (
    LISTON_MIN_MARCA_DEF,
    LISTON_MIN_SCORE_DEF,
    evaluar_liston,
)
from .relevancia import UMBRAL_MARCA_VOCABULARIO, marca_por_vocabulario, relevancia_marca_detalle
from .relevancia import _relevancia_marca as _relevancia_marca  # re-export para tests
from .scoring import (
    PesosScore,
    puntuar,
    puntuar_detalle,
    seleccionar_diversos,
)

__all__ = [
    "BREAKING_PESO_DEF",
    "BREAKING_VENTANA_H_DEF",
    "LISTON_MIN_MARCA_DEF",
    "LISTON_MIN_SCORE_DEF",
    "UMBRAL_MARCA_VOCABULARIO",
    "Asignador",
    "PesosScore",
    "asignar",
    "clasificar_verificacion",
    "clave_cluster",
    "dedup",
    "evaluar_liston",
    "fuentes_detalle",
    "grupos_lexicos",
    "marca_por_vocabulario",
    "peso_corroboracion",
    "peso_ventana_actual",
    "puntuar",
    "puntuar_detalle",
    "recalcular",
    "relevancia_marca_detalle",
    "seleccionar_diversos",
    "similitud",
    "url_canonica_clustering",
]
