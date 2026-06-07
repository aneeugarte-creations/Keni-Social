"""Google Trends como FUENTE EXTERNA del pool de Noticias.

El RSS de Google Trends (`trends.google.com/trending/rss?geo=MX`) trae, por término en
tendencia, su `ht:approx_traffic` (la señal HONESTA de viralidad) y sus `ht:news_item`
(noticias reales que lo explican). Este módulo APLANA esas noticias a items del pool
(`noticias_items`): una fila por `ht:news_item`, con la categoría 'tendencias' y la señal
del término. Determinista y PURO (sin red): el parseo no toca la red; la descarga —con guard
SSRF— la hace el daemon (`trends_daemon`) vía `dominio.http_feed`.

El RSS genérico de `http_feed.parsear_feed` descarta el namespace `ht:` (que es justo lo que
necesitamos), por eso Trends tiene su propio lector tolerante (misma stdlib `xml.etree`).
"""

from __future__ import annotations

import re
from typing import Any
from xml.etree import ElementTree as ET

from . import http_feed
from . import ingesta as dom_ingesta

# Geografías soportadas (id Google Trends -> nombre legible para el resumen).
GEOS: dict[str, str] = {
    "MX": "México",
    "US": "Estados Unidos",
    "ES": "España",
    "AR": "Argentina",
    "CO": "Colombia",
}

# Tope de términos en tendencia que se procesan por barrido (cada uno trae varias noticias).
MAX_TERMINOS = 40
_MAX_TITULO = 300


def url_trends(geo: str = "MX") -> str:
    """URL del feed RSS público de "trending now" de Google Trends para `geo`."""
    return f"https://trends.google.com/trending/rss?geo={geo}"


# "100+", "2K+", "50 mil+", "1M+", "1,000+". `mil`/`millones` van ANTES de `k`/`m` en la
# alternancia para que "mil" no case como "m".
_RE_TRAFICO = re.compile(r"([\d.,]+)\s*(millones|millón|million|mil|[kmKM])?", re.IGNORECASE)
_MULTIPLICADOR = {
    "k": 1_000,
    "m": 1_000_000,
    "mil": 1_000,
    "millones": 1_000_000,
    "millón": 1_000_000,
    "million": 1_000_000,
}


def traduce_trafico(crudo: str) -> int:
    """Convierte un `approx_traffic` ("2K+", "50 mil+") a un entero comparable, o 0.

    No fabrica nada: sin número parseable devuelve 0. Solo se usa para ORDENAR por señal.
    """
    if not isinstance(crudo, str) or not crudo.strip():
        return 0
    m = _RE_TRAFICO.search(crudo)
    if not m:
        return 0
    numero = m.group(1).replace(",", "").replace(".", "")
    if not numero.isdigit():
        return 0
    return int(numero) * _MULTIPLICADOR.get((m.group(2) or "").lower(), 1)


def _texto_hijo(elemento: ET.Element, *nombres: str) -> str:
    """Texto del primer hijo cuyo nombre local esté en `nombres` (ignora namespace)."""
    return http_feed._texto_local(http_feed._buscar_hijo(elemento, *nombres))


def parsear_trends_items(xml: str, *, geo: str = "MX") -> list[dict[str, Any]]:
    """Parsea el RSS de Google Trends a items de `noticias_items` (uno por `ht:news_item`).

    Cada `<item>` es un término en tendencia (titulo + `ht:approx_traffic` + sus `ht:news_item`).
    Se aplana a una fila de pool por noticia, con `senal` = el tráfico del término y `categoria`
    'tendencias'. Dedup por `clave` (URL canónica o hash del título). Tolerante: campos ausentes
    se omiten. Lanza `RSSError` si el XML no parsea.
    """
    try:
        raiz = ET.fromstring(xml)
    except ET.ParseError as e:
        raise http_feed.RSSError("El feed de tendencias no es un XML válido.") from e

    canal = http_feed._buscar_hijo(raiz, "channel")
    contenedor = canal if canal is not None else raiz
    items = [h for h in contenedor if http_feed._quitar_ns(h.tag) == "item"]

    resultado: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for item in items[:MAX_TERMINOS]:
        termino = _texto_hijo(item, "title").strip()
        trafico = _texto_hijo(item, "approx_traffic").strip()
        senal = traduce_trafico(trafico)
        for hijo in item:
            if http_feed._quitar_ns(hijo.tag) != "news_item":
                continue
            titulo = _texto_hijo(hijo, "news_item_title").strip()[:_MAX_TITULO]
            if not titulo:
                continue
            url = _texto_hijo(hijo, "news_item_url").strip()
            fuente = _texto_hijo(hijo, "news_item_source").strip()
            url_can = dom_ingesta.url_canonica(url)
            clave = dom_ingesta._clave_dedup(url_can, titulo)
            if not clave or clave in vistos:
                continue
            vistos.add(clave)
            resumen = f"En tendencia en {GEOS.get(geo, geo)}: {termino}" if termino else ""
            if trafico:
                resumen = f"{resumen} (~{trafico} búsquedas)" if resumen else f"~{trafico} búsquedas"
            resultado.append(
                {
                    "fuente_id": "google-trends",
                    "fuente_nombre": fuente or "Google Trends",
                    "categoria": "tendencias",
                    "marca": "",
                    "titulo": titulo,
                    "resumen": resumen,
                    "url": url,
                    "url_canonica": url_can,
                    "idioma": "es",
                    "publicado_en": "",
                    "clave": clave,
                    "senal": senal,
                    "geo": geo,
                    "estado": "nuevo",
                }
            )
    return resultado
