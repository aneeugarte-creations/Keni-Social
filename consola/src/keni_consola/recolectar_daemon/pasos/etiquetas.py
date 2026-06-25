"""Paso de ETIQUETAS (Fase 2): extrae las etiquetas del sitio de las notas web propias al pool."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from ... import repos
from ...dominio import http_feed
from .._comun import _log

# Tope de notas a etiquetar por barrido: acota la red (un fetch por nota) sin recorrer el archivo.
_LOTE_ETIQUETAS = 20


def _dominios_propios() -> list[str]:
    """Dominios (host sin `www.`) de las fuentes RSS marcadas `propia`. [] si no hay ninguna.

    La etiqueta del sitio (`/etiqueta/<slug>/`) solo existe en las notas web PROPIAS (UnoTV /
    Claro Sports): el flag `propia` de `fuentes_rss` es la fuente de verdad de qué hosts son
    nuestros. Deduplica preservando el orden de aparición.
    """
    dominios: list[str] = []
    for f in repos.listar_fuentes_rss():
        if not f.get("propia"):
            continue
        host = (urlsplit(f.get("url") or "").hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        if host and host not in dominios:
            dominios.append(host)
    return dominios


def paso_etiquetas() -> dict[str, Any]:
    """Extrae las etiquetas del sitio (`/etiqueta/<slug>/`) de las notas web propias. Best-effort.

    Toma un lote acotado de items propios aún sin etiquetas (`repos.items_sin_tags`), descarga el
    HTML de cada nota EN PARALELO (`http_feed.descargar_html`), extrae los slugs
    (`http_feed.extraer_etiquetas`) y los persiste (`repos.actualizar_tags_item`). Una nota que no
    descarga o que no trae chips de etiqueta se omite sin tocar la BD. Una nota que falla al
    persistir se loguea y NO aborta el resto. Devuelve `{notas}` con cuántas quedaron etiquetadas.
    """
    dominios = _dominios_propios()
    if not dominios:
        return {"notas": 0}
    items = repos.items_sin_tags(dominios, _LOTE_ETIQUETAS)
    if not items:
        return {"notas": 0}
    htmls = http_feed.mapear_en_paralelo(
        lambda it: http_feed.descargar_html(it["url"]), items
    )
    etiquetadas = 0
    for it, html in zip(items, htmls):
        try:
            tags = http_feed.extraer_etiquetas(html or "")
            if tags:
                repos.actualizar_tags_item(it["id"], tags)
                etiquetadas += 1
            else:
                # Sin chips (o no descargó): marca revisada para no volver a pedirla cada barrido
                # (si no, las notas sin etiqueta atascan la cola y bloquean a las que sí la tienen).
                repos.marcar_etiquetas_revisadas(it["id"])
        except Exception:  # noqa: BLE001 -- una nota no debe tumbar el paso ni el barrido
            _log.exception(
                "recolectar_daemon: fallo extrayendo etiquetas de la nota %s.", it.get("id")
            )
    return {"notas": etiquetadas}
