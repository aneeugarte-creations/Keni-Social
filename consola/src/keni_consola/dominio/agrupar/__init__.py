"""Agrupación de HISTORIAS sobre el archivo de artículos (Ola B) — capa PURA/testeable.

El motor de ingesta (Ola A) archiva miles de artículos crudos en `noticias_items`. Esta
capa los agrupa en HISTORIAS: la misma noticia contada por varias fuentes y a lo largo del
tiempo. Una historia (cluster) es la unidad newsroom — deduplicada, corroborada por N
fuentes distintas, puntuada y rankeable.

PURA: no toca BD ni red. El daemon de ingesta le pasa el item recién insertado y los
clusters de la ventana reciente (que cargó de `db`), decide a cuál unir (o crear uno
nuevo), y persiste el resultado. Determinista y testeable sin I/O.

Reutiliza la normalización/hash de `dominio.dedup` para el cruce EXACTO de identidad.

Reglas de agrupación (`asignar`) — DEDUP EXACTO, sin léxico:
  - (a) MISMA `url_canonica_clustering` (host+path, SIN query): es literalmente el mismo
    recurso → mismo cluster, sin ambigüedad.
  - (b) si no hay url, título normalizado IDÉNTICO (`t:<hash>` de `dedup`).
  - si nada casa EXACTO → cluster nuevo.

La agrupación de historias del MISMO evento con titulares DISTINTOS la resuelve la fusión
semántica con Haiku (`paso_fusionar_semantica`, ON por defecto), no el léxico.

Scoring (`puntuar`): ver la fórmula documentada en su docstring.

ESTRUCTURA: este módulo era un solo fichero (1125 LOC); se troceó en un paquete por áreas
(`asignacion`, `corroboracion`, `scoring`, `relevancia`, `promocion`, con helpers comunes en
`_comun`). Este `__init__` es un FACADE: re-exporta VERBATIM la misma superficie pública (y los
helpers privados que usan los tests), sin cambiar comportamiento.
"""

from __future__ import annotations

from .. import dedup, similitud
from ._comun import BREAKING_PESO_DEF, BREAKING_VENTANA_H_DEF
from ._comun import _numeros_incompatibles as _numeros_incompatibles  # re-export para tests
from .asignacion import (
    Asignador,
    asignar,
    clave_cluster,
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
    UMBRAL_MIN_MARCA_DEF,
    UMBRAL_MIN_SCORE_DEF,
    evaluar_umbral,
)
from .relevancia import UMBRAL_MARCA_VOCABULARIO, marca_por_vocabulario, relevancia_marca_detalle
from .relevancia import _relevancia_marca as _relevancia_marca  # re-export para tests
from .scoring import (
    PesosScore,
    encaje_evento_detalle,
    evento_ancla,
    puntuar,
    puntuar_detalle,
    seleccionar_diversos,
)

__all__ = [
    "BREAKING_PESO_DEF",
    "BREAKING_VENTANA_H_DEF",
    "UMBRAL_MIN_MARCA_DEF",
    "UMBRAL_MIN_SCORE_DEF",
    "UMBRAL_MARCA_VOCABULARIO",
    "Asignador",
    "PesosScore",
    "asignar",
    "clasificar_verificacion",
    "clave_cluster",
    "dedup",
    "encaje_evento_detalle",
    "evaluar_umbral",
    "evento_ancla",
    "fuentes_detalle",
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
