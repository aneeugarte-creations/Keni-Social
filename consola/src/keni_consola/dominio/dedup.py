"""Dedup de CONTENIDO por título — lógica PURA (sin I/O).

La ingesta automática (pipeline) no debe crear DOS veces la misma noticia: ni dos temas con el
mismo título en la cola AHORA (la misma noticia llegada por dos fuentes), ni un tema cuya noticia
ya se publicó hace poco (republicar lo ya salido). Ambas se reducen a comparar el TÍTULO de la
pieza nueva contra los títulos del contenido reciente de la MISMA marca, de forma robusta a
acentos/mayúsculas/puntuación. Esta capa solo calcula la CLAVE de comparación y decide si hay
duplicado; el llamante (`pipeline_contenido`) le pasa el conjunto de claves existentes (que arma
`repos` desde el contenido de la marca en una ventana reciente).
"""

from __future__ import annotations

import re
import unicodedata


def clave(titulo: str) -> str:
    """Clave de comparación de un título: minúsculas, sin acentos, solo tokens alfanuméricos.

    "¡Increíble  remontada!" y "increible remontada" -> "increible remontada". Título vacío o
    sin tokens útiles -> "" (no casa con nada: nunca se trata como duplicado).
    """
    descompuesto = unicodedata.normalize("NFKD", (titulo or "").lower())
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", sin_acentos))


def es_duplicado(titulo: str, claves_existentes: set[str]) -> bool:
    """True si el título (normalizado) coincide con alguna clave ya existente.

    `claves_existentes` son las claves (`clave(...)`) del contenido reciente de la marca. Una
    clave vacía nunca es duplicado (no hay con qué comparar de forma fiable).
    """
    k = clave(titulo)
    return bool(k) and k in claves_existentes
