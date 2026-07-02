"""Google Trends como FUENTE EXTERNA del pool de Noticias.

El RSS de Google Trends (`trends.google.com/trending/rss?geo=MX`) trae, por término en
tendencia, su `ht:approx_traffic` (la señal HONESTA de viralidad) y sus `ht:news_item`
(noticias reales que lo explican). Este módulo APLANA esas noticias a items del pool
(`noticias_items`): hasta `MAX_NOTICIAS_POR_TERMINO` filas por término (los medios que cubren
un tema son casi-duplicados; basta una muestra), con su categoría editorial por geografía
(MX → 'mx', resto → 'internacional') y la señal del término. Determinista y PURO (sin red):
el parseo no toca la red; la descarga —con guard
SSRF— la hace el daemon (`trends_daemon`) vía `dominio.http_feed`.

El RSS genérico de `http_feed.parsear_feed` descarta el namespace `ht:` (que es justo lo que
necesitamos), por eso Trends tiene su propio lector tolerante (misma stdlib `xml.etree`).
"""

from __future__ import annotations

import re
from typing import Any
from xml.etree import ElementTree as ET

from ..dominio import http_feed
from ..dominio import ingesta as dom_ingesta

# Geografías soportadas (id Google Trends -> nombre legible para el resumen).
GEOS: dict[str, str] = {
    "MX": "México",
    "US": "Estados Unidos",
    "ES": "España",
    "AR": "Argentina",
    "CO": "Colombia",
}

# `fuente_id` FIJO de todas las noticias volcadas desde Google Trends (común a todos los geos).
# Es la clave que el dedup de ingesta usa para distinguir Trends de los feeds RSS directos.
FUENTE_ID = "google-trends"

# Tope de términos en tendencia que se procesan por barrido (cada uno trae varias noticias).
MAX_TERMINOS = 40
# Tope de noticias que se conservan POR término: un tema en tendencia trae muchos medios
# cubriendo lo mismo (casi-duplicados). La señal útil es el TEMA, no la cobertura; con una
# muestra basta. Para profundizar están las fuentes RSS directas.
MAX_NOTICIAS_POR_TERMINO = 3
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


# "1.5" / "1,5": separador DECIMAL (1-2 dígitos al final), no de millares. "1.000"/"1,000"
# (3 dígitos) sí es millar. Distinguirlos evita leer "1.5M" como 15M (10× la señal real).
_RE_DECIMAL = re.compile(r"^(\d+)[.,](\d{1,2})$")


def traduce_trafico(crudo: str) -> int:
    """Convierte un `approx_traffic` ("2K+", "50 mil+", "1.5M+") a un entero comparable, o 0.

    Trata `./,` seguidos de 1-2 dígitos al final como separador DECIMAL ("1.5M" -> 1 500 000);
    el resto, como separador de millares ("1,000" -> 1000). No fabrica nada: sin número
    parseable devuelve 0. Solo se usa para ORDENAR por señal.
    """
    if not isinstance(crudo, str) or not crudo.strip():
        return 0
    m = _RE_TRAFICO.search(crudo)
    if not m:
        return 0
    grupo = m.group(1)
    decimal = _RE_DECIMAL.match(grupo)
    if decimal:
        valor = float(f"{decimal.group(1)}.{decimal.group(2)}")
    else:
        numero = grupo.replace(",", "").replace(".", "")
        if not numero.isdigit():
            return 0
        valor = float(numero)
    return int(valor * _MULTIPLICADOR.get((m.group(2) or "").lower(), 1))


def _texto_hijo(elemento: ET.Element, *nombres: str) -> str:
    """Texto del primer hijo cuyo nombre local esté en `nombres` (ignora namespace)."""
    return http_feed._texto_local(http_feed._buscar_hijo(elemento, *nombres))


def parsear_trends_terminos(xml: str, *, geo: str = "MX") -> list[dict[str, Any]]:
    """Parsea el RSS de Google Trends a la lista de TÉRMINOS en tendencia (sin aplanar a noticias).

    Una fila por `<item>` (término): su texto, el tráfico aproximado (crudo `trafico` para mostrar
    y `senal` comparable para ordenar) y una muestra de las noticias que lo explican. Es para VER
    "qué está sonando", no para el pool. Orden: por señal (tráfico) desc. PURO (sin red). Lanza
    `RSSError` si el XML no parsea.
    """
    try:
        raiz = ET.fromstring(xml)
    except ET.ParseError as e:
        raise http_feed.RSSError("El feed de tendencias no es un XML válido.") from e

    canal = http_feed._buscar_hijo(raiz, "channel")
    contenedor = canal if canal is not None else raiz
    items = [h for h in contenedor if http_feed._quitar_ns(h.tag) == "item"]

    terminos: list[dict[str, Any]] = []
    for item in items[:MAX_TERMINOS]:
        termino = _texto_hijo(item, "title").strip()
        if not termino:
            continue
        trafico = _texto_hijo(item, "approx_traffic").strip()
        noticias: list[dict[str, str]] = []
        for hijo in item:
            if http_feed._quitar_ns(hijo.tag) != "news_item":
                continue
            titulo = _texto_hijo(hijo, "news_item_title").strip()[:_MAX_TITULO]
            if not titulo:
                continue
            noticias.append(
                {
                    "titulo": titulo,
                    "url": _texto_hijo(hijo, "news_item_url").strip(),
                    "fuente": _texto_hijo(hijo, "news_item_source").strip(),
                }
            )
            if len(noticias) >= MAX_NOTICIAS_POR_TERMINO:
                break
        terminos.append(
            {
                "termino": termino,
                "trafico": trafico,
                "senal": traduce_trafico(trafico),
                "geo": geo,
                "noticias": noticias,
            }
        )
    terminos.sort(key=lambda t: t["senal"], reverse=True)
    return terminos


def parsear_trends_items(xml: str, *, geo: str = "MX") -> list[dict[str, Any]]:
    """Parsea el RSS de Google Trends a items de `noticias_items`.

    Cada `<item>` es un término en tendencia (titulo + `ht:approx_traffic` + sus `ht:news_item`).
    Se aplana a hasta `MAX_NOTICIAS_POR_TERMINO` filas de pool por término (los medios que cubren
    un mismo tema son casi-duplicados), con `senal` = el tráfico del término y `categoria`
    por geo (MX → 'mx', resto → 'internacional'). Dedup por `clave` (URL canónica o hash del título). Tolerante: campos ausentes
    se omiten. Lanza `RSSError` si el XML no parsea.
    """
    try:
        raiz = ET.fromstring(xml)
    except ET.ParseError as e:
        raise http_feed.RSSError("El feed de tendencias no es un XML válido.") from e

    canal = http_feed._buscar_hijo(raiz, "channel")
    contenedor = canal if canal is not None else raiz
    items = [h for h in contenedor if http_feed._quitar_ns(h.tag) == "item"]

    # La tendencia entra al vocabulario editorial por su geografía: MX → nacional, resto →
    # internacional. Así una tendencia compite por una línea real del plan en vez de quedar fuera.
    categoria = "mx" if (geo or "").upper() == "MX" else "internacional"
    resultado: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for item in items[:MAX_TERMINOS]:
        termino = _texto_hijo(item, "title").strip()
        trafico = _texto_hijo(item, "approx_traffic").strip()
        senal = traduce_trafico(trafico)
        n_termino = 0
        for hijo in item:
            if n_termino >= MAX_NOTICIAS_POR_TERMINO:
                break
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
            n_termino += 1
            resumen = f"En tendencia en {GEOS.get(geo, geo)}: {termino}" if termino else ""
            if trafico:
                resumen = f"{resumen} (~{trafico} búsquedas)" if resumen else f"~{trafico} búsquedas"
            resultado.append(
                {
                    "fuente_id": FUENTE_ID,
                    "fuente_nombre": fuente or "Google Trends",
                    "categoria": categoria,
                    "marca": "",
                    "titulo": titulo,
                    "resumen": resumen,
                    "url": url,
                    "url_canonica": url_can,
                    # Google Trends da los temas que tienden EN México, pero los enlaza a la fuente
                    # que sea (a menudo extranjera): el idioma se DETECTA del titular real, no se
                    # asume "es" (si no, lo inglés nunca entraría a Traducir). El `resumen` es
                    # texto sintético en español, así que NO entra en la detección.
                    "idioma": dom_ingesta.detectar_idioma(titulo),
                    "publicado_en": "",
                    "clave": clave,
                    "senal": senal,
                    "geo": geo,
                    "estado": "nuevo",
                }
            )
    return resultado
