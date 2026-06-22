"""Etapa de ARTE de STOCK: propone una foto externa como AYUDA VISUAL (nunca publicable).

Paralela a la etapa de Ilustrar (IA): para los temas con copy pero SIN imagen, baja una foto
—primero la ORIGINAL del artículo (RSS), si la trae; si no, una de las APIs gratuitas— y la
adjunta a la pieza como `imagen_origen='stock'`, `imagen_autorizada=0`, `falta_imagen=1`. Así el
feed no sale en blanco, pero la foto se ve atenuada y con watermark "SIN LICENCIA" (front) y el
bloqueo infranqueable impide publicarla hasta que un humano REVISE derechos y la autorice.

La etapa va GATEADA por `KENI_PIPELINE_STOCK` (def OFF, como Ilustrar) y acota cuántos temas por
barrido con `KENI_STOCK_MAX_BARRIDO`. La SELECCIÓN (`topics_sin_stock`) es PURA y testeable.
El dedup por etiqueta `autogen-stock` evita re-procesar un tema en cada barrido.

`adjuntar_candidata` es la ÚNICA puerta para fijar una foto de stock en una pieza (la usan tanto
esta etapa como el endpoint manual `api/artes` de "Buscar foto"), para que los campos de
procedencia/autorización se escriban siempre igual.
"""

from __future__ import annotations

import logging
from typing import Any

from . import config, repos, stock_fotos
from .dominio import extraccion_url, licencia_imagen

_log = logging.getLogger("keni_consola.autogen_stock")

ETIQUETA_AUTOGEN_STOCK = "autogen-stock"
_ESTADO_CERRADO = "hecha"
CLASE_CONTENIDO = "contenido"


def _normaliza(texto: object) -> str:
    return " ".join(("" if texto is None else str(texto)).strip().lower().split())


def _id_etiqueta_autogen_stock(*, crear: bool = True) -> str:
    """Id de la etiqueta `autogen-stock` (la crea si no existe y `crear`). "" si no se puede."""
    for et in repos.listar_etiquetas():
        if _normaliza(et.get("nombre", "")) == ETIQUETA_AUTOGEN_STOCK:
            return et.get("id", "")
    if not crear:
        return ""
    return repos.crear_etiqueta(nombre=ETIQUETA_AUTOGEN_STOCK).get("id", "")


def ids_ya_procesados() -> set[str]:
    """Ids de contenido ya procesados para auto-stock (etiqueta `autogen-stock`). Best-effort."""
    try:
        et_id = _id_etiqueta_autogen_stock(crear=False)
        if not et_id:
            return set()
        return repos.ids_contenido_con_etiqueta(et_id)
    except Exception:  # noqa: BLE001 -- un fallo de lectura no debe abortar el barrido
        return set()


def _tiene_copy(plataforma: dict[str, Any]) -> bool:
    return bool((plataforma.get("copy") or "").strip())


def _sin_imagen(plataforma: dict[str, Any]) -> bool:
    """True si a la plataforma no le hay imagen NI foto (ni compuesta IA ni cruda/stock previa)."""
    return not (plataforma.get("imagen") or "").strip() and not (plataforma.get("foto") or "").strip()


def topics_sin_stock(
    items: list[dict[str, Any]],
    *,
    plataformas_por_item: dict[str, list[dict[str, Any]]],
    ya_procesados: set[str],
    maximo: int,
) -> list[dict[str, Any]]:
    """Subconjunto de `items` que deben recibir una foto de stock de ayuda (PURA, testeable).

    Reglas: clase 'contenido', estado != 'hecha', con título, con ALGUNA plataforma con copy y
    SIN imagen ni foto, no ya procesados (dedup `autogen-stock`), recortado a `maximo`.
    """
    elegidos: list[dict[str, Any]] = []
    for item in items:
        if len(elegidos) >= maximo:
            break
        if (item.get("clase") or CLASE_CONTENIDO) != CLASE_CONTENIDO:
            continue
        if (item.get("estado") or "") == _ESTADO_CERRADO:
            continue
        if not (item.get("titulo") or "").strip():
            continue
        if config.marca_apagada(config.ENV_PIPELINE_STOCK, item.get("marca") or ""):
            continue
        if item.get("id") in ya_procesados:
            continue
        plataformas = plataformas_por_item.get(item.get("id"), [])
        if not any(_tiene_copy(p) and _sin_imagen(p) for p in plataformas):
            continue
        elegidos.append(item)
    return elegidos


def adjuntar_candidata(
    pieza_id: str,
    *,
    url: str,
    proveedor: str,
    autor: str = "",
    licencia: str = "",
    credito_url: str = "",
) -> dict[str, Any] | None:
    """Descarga `url` (SSRF guard) y la fija en la pieza como foto de STOCK (ayuda visual).

    ÚNICA puerta para marcar una foto de stock: deja `imagen_origen='stock'`,
    `imagen_autorizada=0` y `falta_imagen=1` (sigue faltando imagen real). Devuelve la fila
    actualizada o None si la pieza no existe. Propaga `extraccion_url.ExtraccionError` si la
    descarga falla o el contenido no es una imagen.
    """
    nombre = extraccion_url.descargar_imagen_a_media(url)
    return repos.actualizar_pieza_fila(
        pieza_id,
        {
            "foto": nombre,
            "imagen": "",
            "falta_imagen": True,
            "imagen_origen": licencia_imagen.ORIGEN_STOCK,
            "imagen_proveedor": (proveedor or "stock")[:60],
            "imagen_autor": (autor or "")[:200],
            "imagen_licencia": (licencia or "")[:200],
            "imagen_credito_url": (credito_url or "")[:500],
            "imagen_autorizada": False,
        },
    )


def _marcar_procesado(item_id: str) -> None:
    """Etiqueta el tema `autogen-stock` (dedup al éxito). Best-effort, nunca rompe el barrido."""
    try:
        et_id = _id_etiqueta_autogen_stock(crear=True)
        if et_id:
            repos.asignar_etiqueta(item_id, et_id)
    except Exception:  # noqa: BLE001 -- el dedup es una optimización, no una garantía
        _log.debug("auto-stock: no se pudo etiquetar el tema %s.", item_id, exc_info=True)


def lanzar_para_topic(item: dict[str, Any]) -> dict[str, Any] | None:
    """Adjunta a un tema una foto de stock: 1º la original del RSS, luego una API gratuita.

    Devuelve la fila actualizada, o None si no había candidata (sin foto de fuente y sin
    resultados de las APIs) o falló la descarga. Marca el tema `autogen-stock` al éxito.
    """
    item_id = item.get("id")
    if not item_id:
        return None
    try:
        plataformas = repos.listar_piezas_fila(item_id)
    except Exception:  # noqa: BLE001 -- sin plataformas legibles, no hay dónde adjuntar
        _log.exception("auto-stock: no se pudieron leer las plataformas de un tema.")
        return None
    objetivo = next((p for p in plataformas if _tiene_copy(p) and _sin_imagen(p)), None)
    if objetivo is None:
        return None

    # CANDIDATAS, en orden de preferencia: original del artículo (RSS) y luego APIs gratuitas.
    candidatas: list[dict[str, str]] = []
    fuente = (objetivo.get("imagen_fuente") or "").strip()
    if fuente:
        candidatas.append({"url": fuente, "proveedor": "rss", "autor": "", "licencia": "", "credito_url": fuente})
    titulo = (item.get("titulo") or "").strip()
    if titulo:
        try:
            candidatas.extend(stock_fotos.buscar_todos(titulo, limite_por=2))
        except Exception:  # noqa: BLE001 -- una API caída no rompe el barrido
            _log.debug("auto-stock: fallo buscando en APIs para %r.", titulo, exc_info=True)

    for cand in candidatas:
        try:
            actualizada = adjuntar_candidata(
                str(objetivo.get("id") or ""),
                url=cand.get("url", ""),
                proveedor=cand.get("proveedor", "stock"),
                autor=cand.get("autor", ""),
                licencia=cand.get("licencia", ""),
                credito_url=cand.get("credito_url", ""),
            )
        except extraccion_url.ExtraccionError:
            continue  # esa candidata no servía (no es imagen, URL muerta…): prueba la siguiente
        if actualizada is not None:
            _marcar_procesado(str(item_id))
            return actualizada
    return None


def ejecutar_stock() -> list[dict[str, Any]]:
    """Etapa de arte de stock del barrido: adjunta fotos de ayuda a temas con copy sin imagen.

    Gateada por `KENI_PIPELINE_STOCK` (def OFF). Sin proveedores gratuitos disponibles degrada a
    no hacer nada. Devuelve la lista de piezas a las que adjuntó una foto (para el log del tick).
    """
    if not config.stock_busca_activo():
        return []
    if not stock_fotos.proveedores_disponibles():
        return []
    from . import autogen_ilustrar

    try:
        # Solo la clase 'contenido' (las tareas nunca llevan foto de stock); el resto de reglas
        # las aplica `topics_sin_stock`. Misma fuente que la etapa de Ilustrar.
        items = repos.listar_publicacion(clase="contenido")
    except Exception:  # noqa: BLE001 -- sin tablero legible, no hay etapa este tick
        _log.exception("auto-stock: no se pudo leer el tablero.")
        return []
    plataformas_por_item = autogen_ilustrar._plataformas_por_item(items)
    elegidos = topics_sin_stock(
        items,
        plataformas_por_item=plataformas_por_item,
        ya_procesados=ids_ya_procesados(),
        maximo=config.stock_max_por_barrido(),
    )
    adjuntadas: list[dict[str, Any]] = []
    for item in elegidos:
        res = lanzar_para_topic(item)
        if res is not None:
            adjuntadas.append(res)
    return adjuntadas
