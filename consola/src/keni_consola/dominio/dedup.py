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
from difflib import SequenceMatcher
from urllib.parse import urlsplit


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


# Prefijos de parametros de tracking que NO identifican el recurso (se quitan al canonizar):
# las `utm_*` (campaña), `fbclid`/`gclid` (click ids de Facebook/Google). Asi dos enlaces a
# la MISMA nota con distinto tracking cruzan como la misma URL canonica.
_PARAMS_TRACKING = ("utm_",)
_PARAMS_TRACKING_EXACTOS = frozenset({"fbclid", "gclid"})


def url_canonica(url: str) -> str:
    """Normaliza una URL para CRUCE EXACTO entre enlaces equivalentes.

    Minusculas en el host, quita el esquema y el `www.`, quita el fragmento (`#...`), quita
    los parametros de tracking (`utm_*`, `fbclid`, `gclid`) y la `/` final. Devuelve "" si no
    es http(s) o si no parsea. Pura (solo `urllib.parse`).
    """
    if not url or not isinstance(url, str):
        return ""
    partes = urlsplit(url.strip())
    if partes.scheme.lower() not in ("http", "https"):
        return ""
    host = partes.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    # Conserva solo los parametros que NO son de tracking (preservando orden y formato).
    consulta = "&".join(
        seg
        for seg in partes.query.split("&")
        if seg
        and not seg.split("=", 1)[0].lower().startswith(_PARAMS_TRACKING)
        and seg.split("=", 1)[0].lower() not in _PARAMS_TRACKING_EXACTOS
    )
    camino = partes.path.rstrip("/")
    # Reensamblamos a mano (sin esquema/`//`/fragmento): `host[/camino][?consulta]`.
    canonica = host + camino
    if consulta:
        canonica += "?" + consulta
    return canonica


def es_similar(titulo: str, titulos_norm: set[str], *, umbral: float = 0.85) -> bool:
    """True si `titulo` casa (exacto o fuzzy) con algun titulo del set ya NORMALIZADO.

    `titulos_norm` son claves `clave(...)` ya calculadas. Casa si `clave(titulo)` esta exacto
    en el set, o si `SequenceMatcher(...).ratio() >= umbral` contra alguna. Titulo vacio o
    set vacio -> False. Pura.
    """
    k = clave(titulo)
    if not k or not titulos_norm:
        return False
    if k in titulos_norm:
        return True
    return any(
        SequenceMatcher(None, k, t).ratio() >= umbral for t in titulos_norm if t
    )
