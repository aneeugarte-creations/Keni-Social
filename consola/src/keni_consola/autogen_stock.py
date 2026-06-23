"""Etapa de ARTE de STOCK: propone una foto externa como AYUDA VISUAL (nunca publicable).

Paralela a la etapa de Ilustrar (IA): para los temas con copy pero SIN imagen, baja una foto
—primero la ORIGINAL del artículo (RSS), si la trae; si no, una de las APIs gratuitas— y la
adjunta a la pieza como `imagen_origen='stock'`, `imagen_autorizada=0`, `falta_imagen=1`. Así el
feed no sale en blanco, pero la foto se ve atenuada y con watermark "SIN LICENCIA" (front) y el
bloqueo infranqueable impide publicarla hasta que un humano REVISE derechos y la autorice.

La etapa va GATEADA por `KENI_PIPELINE_STOCK` (def ON) + el maestro `KENI_MAQUINA`, y acota
cuántos temas por barrido con `KENI_STOCK_MAX_BARRIDO`. La SELECCIÓN (`topics_sin_stock`) es PURA.

PROPAGACIÓN ROBUSTA Y RETROACTIVA (no depende del frágil toggle `espejo`): la foto de stock es
ayuda del TEMA, así que `propagar_stock` la reparte a TODA red del tema que esté en gris (sin
pisar imágenes propias ni publicadas). El barrido REPARA temas a medias copiando, gratis, la foto
que ya tenga una red a las que aún no la tienen; solo BUSCA en APIs (con coste) cuando ninguna red
del tema tiene foto, y marca `autogen-stock` tras intentarlo para no re-buscar lo no encontrable.

`adjuntar_candidata` es la ÚNICA puerta para fijar una foto de stock (la usan esta etapa y el
endpoint manual `api/artes` de "Buscar foto") y SIEMPRE reparte a las hermanas vacías.
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


def _es_stock(plataforma: dict[str, Any]) -> bool:
    """True si la plataforma YA tiene una foto de stock adjunta (para repartirla a sus hermanas)."""
    return (plataforma.get("imagen_origen") or "") == licencia_imagen.ORIGEN_STOCK and bool(
        (plataforma.get("foto") or "").strip()
    )


def _campos_desde(plataforma: dict[str, Any]) -> dict[str, Any]:
    """Campos de stock a ESPEJAR desde una pieza que ya tiene la foto (la copia a las vacías).

    Conserva proveedor/autor/licencia/crédito de la foto original; `imagen_autorizada` SIEMPRE
    nace False en la copia (la autorización es una decisión humana por pieza, no se hereda sola).
    """
    return {
        "foto": plataforma.get("foto") or "",
        "imagen": "",
        "falta_imagen": True,
        "imagen_origen": licencia_imagen.ORIGEN_STOCK,
        "imagen_proveedor": (plataforma.get("imagen_proveedor") or "stock")[:60],
        "imagen_autor": (plataforma.get("imagen_autor") or "")[:200],
        "imagen_licencia": (plataforma.get("imagen_licencia") or "")[:200],
        "imagen_credito_url": (plataforma.get("imagen_credito_url") or "")[:500],
        "imagen_autorizada": False,
    }


def propagar_stock(publicacion_id: str, campos: dict[str, Any]) -> int:
    """Aplica `campos` (foto de stock) a TODA red del tema que aún NO tiene imagen. Robusto.

    Independiente del toggle `espejo` (la foto de stock es ayuda del TEMA, no edición por red):
    rellena solo las redes SIN imagen propia ni foto (no pisa una imagen real ya elegida) y salta
    las publicadas. Idempotente: una red ya con foto no se vuelve a tocar. Devuelve cuántas rellenó.
    Es el núcleo de "propaga en las que todavía no la tienen", usado por el adjuntado manual y el
    barrido (incluida la reparación retroactiva de temas que quedaron a medias).
    """
    if not publicacion_id:
        return 0
    rellenadas = 0
    for hermana in repos.listar_piezas_fila(publicacion_id):
        if (hermana.get("estado") or "") == "publicado":
            continue
        if not _sin_imagen(hermana):
            continue
        try:
            repos.actualizar_pieza_fila(hermana["id"], campos)
            rellenadas += 1
        except Exception:  # noqa: BLE001 -- una hermana borrada/en carrera no rompe el resto
            _log.debug("auto-stock: no se pudo espejar el stock a una hermana.", exc_info=True)
    return rellenadas


def topics_sin_stock(
    items: list[dict[str, Any]],
    *,
    plataformas_por_item: dict[str, list[dict[str, Any]]],
    ya_procesados: set[str],
    maximo: int,
) -> list[dict[str, Any]]:
    """Subconjunto de `items` que deben recibir/repartir una foto de stock (PURA, testeable).

    Reglas: clase 'contenido', estado != 'hecha', con título, marca no apagada, y con ALGUNA red
    con copy y SIN imagen. Sobre eso, RETROACTIVO y robusto:
      - si el tema YA tiene una foto de stock en alguna red, se elige SIEMPRE (para repartirla a
        las redes que aún están en gris), aunque ya estuviera procesado;
      - si NO la tiene, se elige solo si aún no se intentó (`autogen-stock`), para no re-buscar en
        las APIs un tema sin foto encontrable en cada barrido.
    Recortado a `maximo`.
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
        plataformas = plataformas_por_item.get(item.get("id"), [])
        hay_vacia = any(_tiene_copy(p) and _sin_imagen(p) for p in plataformas)
        if not hay_vacia:
            continue
        hay_stock = any(_es_stock(p) for p in plataformas)
        ya = item.get("id") in ya_procesados
        # Repartir una foto ya existente (reparación) no gasta APIs: se permite aunque esté
        # procesado. Buscar una nueva sí cuesta: solo si no se intentó antes.
        if hay_stock or not ya:
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
    objetivo actualizada o None si la pieza no existe. Propaga `extraccion_url.ExtraccionError`
    si la descarga falla o el contenido no es una imagen.

    ESPEJO: la misma foto + sus flags de stock se aplican a TODAS las redes hermanas (cuando el
    `espejo` del tema esta activo, el caso normal), no solo a la pieza tocada. Si no, una red
    saldria con la foto SIN LICENCIA pero sin el aviso, que es justo lo peligroso a evitar.
    """
    nombre = extraccion_url.descargar_imagen_a_media(url, categoria="copyright")
    campos = {
        "foto": nombre,
        "imagen": "",
        "falta_imagen": True,
        "imagen_origen": licencia_imagen.ORIGEN_STOCK,
        "imagen_proveedor": (proveedor or "stock")[:60],
        "imagen_autor": (autor or "")[:200],
        "imagen_licencia": (licencia or "")[:200],
        "imagen_credito_url": (credito_url or "")[:500],
        "imagen_autorizada": False,
    }
    objetivo = repos.actualizar_pieza_fila(pieza_id, campos)
    if objetivo is None:
        return None
    # Reparte la MISMA foto a las redes del tema que aún están en gris (robusto, no depende del
    # toggle `espejo`): así nunca queda una red con la foto SIN LICENCIA sin su aviso, ni en gris.
    propagar_stock(str(objetivo.get("publicacion_id") or ""), campos)
    return objetivo


def _marcar_procesado(item_id: str) -> None:
    """Etiqueta el tema `autogen-stock` (dedup al éxito). Best-effort, nunca rompe el barrido."""
    try:
        et_id = _id_etiqueta_autogen_stock(crear=True)
        if et_id:
            repos.asignar_etiqueta(item_id, et_id)
    except Exception:  # noqa: BLE001 -- el dedup es una optimización, no una garantía
        _log.debug("auto-stock: no se pudo etiquetar el tema %s.", item_id, exc_info=True)


def lanzar_para_topic(item: dict[str, Any]) -> dict[str, Any] | None:
    """Da a un tema su foto de stock y la reparte a todas sus redes en gris.

    Dos caminos, REPARACIÓN antes que búsqueda:
      1. Si alguna red del tema YA tiene una foto de stock, se REPARTE a las redes vacías (sin
         tocar APIs ni descargar): repara retroactivamente los temas que quedaron a medias.
      2. Si NINGUNA la tiene, se BUSCA (1º la original del RSS, luego APIs gratuitas), se adjunta
         y `adjuntar_candidata` ya la reparte a todas. Se marca `autogen-stock` tras intentarlo,
         para no re-buscar en cada barrido un tema sin foto encontrable.
    Devuelve la fila rellenada (o None si no había nada que repartir ni candidata).
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

    # Camino 1 — REPARACIÓN: ya hay foto de stock en el tema; repártela a las vacías (gratis).
    ya_con_stock = next((p for p in plataformas if _es_stock(p)), None)
    if ya_con_stock is not None:
        if propagar_stock(str(item_id), _campos_desde(ya_con_stock)):
            return repos.obtener_pieza_fila(str(objetivo.get("id") or ""))
        return None

    # Camino 2 — BÚSQUEDA. CANDIDATAS: original del artículo (RSS) y luego APIs gratuitas.
    candidatas: list[dict[str, str]] = []
    fuente = (objetivo.get("imagen_fuente") or "").strip()
    if fuente:
        candidatas.append({"url": fuente, "proveedor": "rss", "autor": "", "licencia": "", "credito_url": fuente})
    # Consulta de las APIs: la KEYWORD de la etapa Sugerir hashtags (`imagen_clave`); si aún no la
    # hay, el TEMA (`titulo`). NUNCA el copy/titular largo (no encuentra nada en los bancos).
    consulta = (objetivo.get("imagen_clave") or "").strip() or (item.get("titulo") or "").strip()
    if consulta:
        try:
            candidatas.extend(stock_fotos.buscar_todos(consulta, limite_por=2))
        except Exception:  # noqa: BLE001 -- una API caída no rompe el barrido
            _log.debug("auto-stock: fallo buscando en APIs para %r.", consulta, exc_info=True)

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
    # Se intentó buscar y no sirvió ninguna candidata: marca el tema para no re-buscar en cada
    # barrido (la selección igual lo retomará si algún día aparece una foto de stock que repartir).
    _marcar_procesado(str(item_id))
    return None


def ejecutar_stock() -> list[dict[str, Any]]:
    """Etapa de Stock del pipeline: adjunta fotos de ayuda a temas con copy sin imagen.

    Gateada por el maestro `KENI_MAQUINA` + su toggle `KENI_PIPELINE_STOCK` (def ON), igual que
    Ilustrar. Sin proveedores gratuitos disponibles degrada a no hacer nada. Devuelve la lista de
    piezas a las que adjuntó una foto (para el log del tick).
    """
    if not config.gate_maquina(config.stock_busca_activo)():
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
