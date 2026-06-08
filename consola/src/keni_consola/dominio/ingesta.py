"""Motor de ingesta persistente (Ola A) — capa PURA/inyectable de dominio.

Convierte un feed (fila de `fuentes_rss`) en una lista de dicts de `noticias_items` listos
para persistir, MÁS un dict de salud del sondeo. No toca BD ni red directamente: la descarga
pasa por `http_feed` (cuyo descargador es inyectable), así que los tests le pasan un FETCHER
falso y NUNCA tocan la red.

Responsabilidades:
  - `url_canonica(url)`: normaliza una URL para dedup (quita `utm_*`/`fbclid`/`gclid`,
    fragmento `#...`, esquema/`www.` y `/` final). Reusa `dedup.url_canonica`.
  - `items_de_feed(feed, *, max_items, fetcher=None)`: descarga+parsea (reusando
    `http_feed.leer_items_fuente` con `max_items`), construye los dicts de `noticias_items`
    con su `clave` de dedup (`url_canonica`; si no hay url, hash del título normalizado),
    `idioma` (del feed/preset si se conoce; heurística simple si no) y `publicado_en` (pubDate
    normalizado a ISO si parsea). Devuelve `(items, salud)`.

`salud` = `{conteo, error}`: `error` vacío en éxito, mensaje en español si el feed falló.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC
from typing import Any

from . import dedup, http_feed

# Tope por defecto de artículos por feed en la ingesta (el Radar/RSS usan 30; aquí más, para
# archivar cobertura newsroom-grade). El daemon pasa `config.ingesta_max_items()` (def 100).
MAX_ITEMS_DEF = 100

# Fetcher inyectable: `(url) -> str` (XML del feed). En tests se pasa uno falso. None = el
# descargador real de `http_feed` (que aplica timeout/tamaño/SSRF).
Fetcher = Callable[[str], str]


def url_canonica(url: str) -> str:
    """URL normalizada para dedup (delega en `dedup.url_canonica`). "" si no es http(s)."""
    return dedup.url_canonica(url)


def _hash_titulo(titulo: str) -> str:
    """Hash estable del título NORMALIZADO (fallback de `clave` cuando no hay url).

    Usa `dedup.clave` (minúsculas, sin acentos, solo tokens alfanuméricos) para que dos
    titulares equivalentes con distinta puntuación colisionen. "" si el título no tiene
    tokens útiles (no se puede deduplicar de forma fiable: el item se omite aguas arriba).
    """
    k = dedup.clave(titulo)
    if not k:
        return ""
    return "t:" + hashlib.blake2b(k.encode("utf-8"), digest_size=12).hexdigest()


def _clave_dedup(url_can: str, titulo: str) -> str:
    """Clave de dedup de un item: la url canónica si la hay, si no el hash del título."""
    if url_can:
        return url_can
    return _hash_titulo(titulo)


# Heurística MUY simple de idioma por palabras funcionales frecuentes. Solo se usa cuando el
# feed/preset no declara idioma; es un "mejor esfuerzo" honesto (no un detector real).
_PISTAS_ES = frozenset(
    {"el", "la", "los", "las", "de", "que", "en", "con", "por", "para", "del", "una", "un"}
)
_PISTAS_EN = frozenset(
    {"the", "of", "and", "to", "in", "for", "with", "on", "is", "are", "by", "as"}
)


def _idioma_heuristico(texto: str) -> str:
    """Adivina es/en por palabras funcionales; "" si no hay señal clara. Mejor esfuerzo."""
    palabras = dedup.clave(texto).split()
    if not palabras:
        return ""
    es = sum(1 for p in palabras if p in _PISTAS_ES)
    en = sum(1 for p in palabras if p in _PISTAS_EN)
    if es == en:
        return ""
    return "es" if es > en else "en"


def _publicado_en(fecha_cruda: str) -> str:
    """`pubDate` del feed normalizado a ISO 8601 UTC; "" si no parsea (mejor esfuerzo)."""
    dt = http_feed.fecha_a_orden(fecha_cruda)
    if dt == http_feed._FECHA_MINIMA:
        return ""
    return dt.astimezone(UTC).isoformat()


def items_de_feed(
    feed: dict[str, Any],
    *,
    max_items: int = MAX_ITEMS_DEF,
    fetcher: Fetcher | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Descarga+parsea un feed y construye dicts de `noticias_items` + salud del sondeo.

    PURA respecto a la red: `fetcher` (inyectable) es lo único que la tocaría; en tests se
    pasa uno falso. Degradación honesta: si el feed falla, devuelve `([], {conteo:0, error})`
    en vez de lanzar, para que el daemon registre el error sin abortar el barrido.

    Cada item resultante trae: identidad (`fuente_id`/`fuente_nombre`/`categoria`/`marca`/
    `geo`), contenido (`titulo`/`resumen`/`url`/`imagen`/`autor`), `url_canonica`, `clave` de
    dedup, `idioma` y `publicado_en`. Los items sin `clave` (sin url ni título útil) se omiten:
    no se pueden deduplicar de forma estable.
    """
    feed_id = str(feed.get("id") or "")
    feed_nombre = str(feed.get("nombre") or "")
    categoria = str(feed.get("categoria") or "")
    marca = str(feed.get("marca") or "")
    geo = str(feed.get("geo") or "")
    idioma_feed = str(feed.get("idioma") or "").strip().lower()

    descargador = (lambda url: fetcher(url)) if fetcher is not None else None
    try:
        crudos = http_feed.leer_items_fuente(feed, descargador, max_items=max_items)
    except http_feed.RSSError as e:
        return [], {"conteo": 0, "error": str(e)}
    except Exception as e:  # noqa: BLE001 -- un fallo inesperado del fetcher no debe abortar
        return [], {"conteo": 0, "error": str(e) or "Error al leer el feed."}

    items: list[dict[str, Any]] = []
    for crudo in crudos:
        url = (crudo.get("enlace") or "").strip()
        titulo = (crudo.get("titulo") or "").strip()
        url_can = url_canonica(url)
        clave = _clave_dedup(url_can, titulo)
        if not clave:
            continue  # sin identidad estable: no se archiva
        resumen = (crudo.get("resumen") or "").strip()
        idioma = idioma_feed or _idioma_heuristico(f"{titulo} {resumen}")
        items.append(
            {
                "fuente_id": feed_id,
                "fuente_nombre": feed_nombre,
                "categoria": categoria,
                "marca": marca,
                "geo": geo,
                "titulo": titulo,
                "resumen": resumen,
                "url": url,
                "url_canonica": url_can,
                "imagen": (crudo.get("imagen") or "").strip(),
                "autor": (crudo.get("autor") or "").strip(),
                "idioma": idioma,
                "publicado_en": _publicado_en(crudo.get("fecha") or ""),
                "clave": clave,
                "estado": "nuevo",
            }
        )
    return items, {"conteo": len(items), "error": ""}


# --------------------------------------------------------------------------- #
# Pool único (Ola E): unificar TODAS las notas en `noticias_items`             #
# --------------------------------------------------------------------------- #
#
# Las notas de CUALQUIER origen (cajones del equipo, investigación) deben entrar al MISMO pool
# (`noticias_items`) para que el clustering las deduplique y el auto-feed las pueda usar. Estos
# constructores son PUROS: arman el dict de `noticias_items` (con su `clave` de dedup, reusando
# `url_canonica`/`_clave_dedup`) a partir de la fila propia (insumo_item / inv_candidato). El
# `crear_noticias_items` es idempotente por UNIQUE(fuente_id, clave): re-insertar es inofensivo.

# Señal alta de las notas CURADAS por el equipo (cajones): material elegido a mano = alta
# prioridad, así su historia supera fácilmente el umbral del auto-feed. Por encima del log-norm
# de viralidad (`_SENAL_SATURA`=1e6 en clustering) NO tiene sentido; este valor satura el peso.
SENAL_CURADO = 1_000_000


def noticia_item_de_insumo(insumo: dict[str, Any]) -> dict[str, Any] | None:
    """Fila de `noticias_items` a partir de un `insumo_item` de cajón. None si no se puede.

    Los EVENTOS no entran al pool (son agenda de cobertura, no notas de copy): se omiten
    devolviendo None. La `clave` es el hash del título normalizado (los cajones no traen URL);
    sin título útil no hay identidad estable y se omite. `senal` alta (curado por el equipo).
    """
    if str(insumo.get("tipo") or "").strip().lower() == "evento":
        return None
    titulo = str(insumo.get("titulo") or "").strip()
    clave = _clave_dedup("", titulo)
    if not clave:
        return None
    cajon = str(insumo.get("cajon") or "").strip()
    return {
        "fuente_id": f"cajon-{cajon}" if cajon else "cajon",
        "fuente_nombre": cajon or "cajón",
        "categoria": str(insumo.get("linea") or "").strip(),
        "marca": str(insumo.get("marca") or "").strip(),
        "titulo": titulo,
        "resumen": str(insumo.get("resumen") or "").strip(),
        "url": "",
        "url_canonica": "",
        "idioma": str(insumo.get("idioma") or "es").strip(),
        "publicado_en": str(insumo.get("fecha") or "").strip(),
        "clave": clave,
        "senal": SENAL_CURADO,
        "estado": "nuevo",
    }


def noticia_item_de_agencia(item: dict[str, str], *, agencia: str) -> dict[str, Any] | None:
    """Fila de `noticias_items` a partir de un item de AGENCIA (Reuters/AFP). None sin identidad.

    El item de agencia tiene la forma `{titulo, resumen, enlace, fecha, fuente, clave}`
    (`agencias._item`). La `clave` de dedup es la url canónica del enlace o, si no hay url, el
    hash del título normalizado; sin ninguna de las dos no hay identidad estable y se omite.

    Idempotencia: `fuente_id="agencia-{agencia}"` (estable por agencia) + `clave` casan con el
    UNIQUE(fuente_id, clave) del pool, así re-ingerir el mismo barrido o entre barridos no
    duplica (igual que RSS/Trends). Señal NORMAL (no curado): las agencias no son material
    elegido a mano por el equipo, a diferencia de los cajones. `marca` vacía: las agencias no
    tienen marca asociada hoy (señal global, como Trends); el clustering la puntúa por
    vocabulario de marca igual que cualquier otro item.
    """
    titulo = (item.get("titulo") or "").strip()
    url = (item.get("enlace") or "").strip()
    url_can = url_canonica(url)
    clave = _clave_dedup(url_can, titulo)
    if not clave:
        return None
    return {
        "fuente_id": f"agencia-{agencia}",
        "fuente_nombre": (item.get("fuente") or "").strip() or agencia.upper(),
        "categoria": "agencias",
        "marca": "",
        "titulo": titulo,
        "resumen": (item.get("resumen") or "").strip(),
        "url": url,
        "url_canonica": url_can,
        "idioma": "",
        "publicado_en": _publicado_en((item.get("fecha") or "").strip()),
        "clave": clave,
        "estado": "nuevo",
    }
