"""Etapa de ARTE de STOCK: propone una foto externa como AYUDA VISUAL (nunca publicable).

Paralela a la etapa de Ilustrar (IA): para los temas con copy pero SIN imagen, baja una foto
—primero la ORIGINAL del artículo (RSS), si la trae; si no, una de las APIs gratuitas— y la
adjunta a la pieza como `imagen_origen='stock'`, `imagen_autorizada=0`, `falta_imagen=1`. Así el
feed no sale en blanco, pero la foto se ve atenuada y con watermark "SIN LICENCIA" (front) y el
bloqueo infranqueable impide publicarla hasta que un humano REVISE derechos y la autorice.

La etapa va GATEADA por `KENI_PIPELINE_STOCK` (def ON) + el maestro `KENI_MAQUINA`, y acota
cuántos temas por barrido con `KENI_STOCK_MAX_BARRIDO`. La SELECCIÓN (`topics_sin_stock`) es PURA.

PROPAGACIÓN ROBUSTA Y RETROACTIVA (no depende del frágil toggle `espejo`): la foto de stock es
ayuda del TEMA, así que es UNA sola por tema, idéntica en todas las redes. `propagar_stock` reparte
la foto CANÓNICA a TODA red en gris Y UNIFICA las redes que tuvieran otra foto de stock distinta
(sin pisar imágenes propias, stock ya autorizada ni publicadas). El barrido REPARA/unifica temas a
medias o divergentes copiando, gratis, la foto que ya tenga una red; solo BUSCA en APIs (con coste)
cuando NINGUNA red del tema tiene foto, y marca `autogen-stock` tras intentarlo para no re-buscar lo
no encontrable. Así una búsqueda manual o un barrido nunca dejan IG con una foto y FB con otra.

`adjuntar_candidata` es la ÚNICA puerta para fijar una foto de stock (la usan esta etapa y el
endpoint manual `api/artes` de "Buscar foto") y SIEMPRE reparte a las hermanas vacías.
"""

from __future__ import annotations

import logging
from typing import Any

from . import config, repos, stock_fotos
from .dominio import extraccion_url, licencia_imagen
from .pipeline_contenido._comun import ORIGEN_PORTAL

_log = logging.getLogger("keni_consola.autogen_stock")

ETIQUETA_AUTOGEN_STOCK = "autogen-stock"
_ESTADO_CERRADO = "hecha"
CLASE_CONTENIDO = "contenido"
# Lado mínimo (px) de una foto de stock: descarta iconos/emojis/thumbnails que se cuelan como
# candidata (p. ej. la original RSS resulta ser el emoji 72×72 de WordPress). Una foto real de
# banco o de portada de artículo lo supera de sobra.
_MIN_LADO_FOTO = 320


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


# Identidad de una foto de stock (la foto + su crédito): dos redes con la MISMA tupla comparten la
# misma foto de stock; si difieren, el tema tiene stock DIVERGENTE que hay que unificar.
_CLAVES_CANONICAS = (
    "foto",
    "imagen_proveedor",
    "imagen_autor",
    "imagen_licencia",
    "imagen_credito_url",
)


def _firma_stock(plataforma: dict[str, Any]) -> tuple[str, ...]:
    """Tupla identidad de la foto de stock de una plataforma (foto + crédito)."""
    return tuple((plataforma.get(c) or "") for c in _CLAVES_CANONICAS)


def _difiere_de_canonica(plataforma: dict[str, Any], campos: dict[str, Any]) -> bool:
    """True si la foto de stock de la plataforma difiere de la canónica `campos` (foto o crédito)."""
    return any((plataforma.get(c) or "") != (campos.get(c) or "") for c in _CLAVES_CANONICAS)


def _hay_stock_divergente(plataformas: list[dict[str, Any]]) -> bool:
    """True si entre las redes del tema hay DOS o más fotos de stock DISTINTAS que se pueden unificar.

    Solo cuenta el stock NO publicado y NO autorizado (la unificación nunca pisa una foto que un
    humano autorizó ni una publicada): si todas las que se podrían tocar ya coinciden, no diverge.
    """
    firmas = {
        _firma_stock(p)
        for p in plataformas
        if (p.get("estado") or "") != "publicado"
        and _es_stock(p)
        and not p.get("imagen_autorizada")
    }
    return len(firmas) > 1


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
    """Aplica `campos` (foto de stock CANÓNICA) a TODA red del tema para que converja a UNA sola foto.

    Independiente del toggle `espejo` (la foto de stock es ayuda del TEMA, no edición por red).
    Escribe la canónica a una hermana cuando:
      - está en GRIS (sin imagen propia ni foto) -> rellena la que aún no la tiene; o
      - ya tiene OTRA foto de STOCK distinta (otro `foto`/crédito) -> UNIFICA, para que el tema no
        quede con metadata divergente entre redes (p. ej. IG autor A / FB autor B por el mismo tema,
        fruto de barridos o búsquedas manuales distintas).
    NUNCA pisa una imagen PROPIA del usuario (subida/galería/IA/licenciada: no es `_es_stock`), una
    foto de stock que un humano ya AUTORIZÓ, ni una pieza publicada. Idempotente: una red que ya
    tiene la canónica no se reescribe. Devuelve cuántas tocó. Lo usan el adjuntado manual y el
    barrido (reparación/unificación retroactiva de temas a medias o divergentes).
    """
    if not publicacion_id:
        return 0
    tocadas = 0
    for hermana in repos.listar_piezas_fila(publicacion_id):
        if (hermana.get("estado") or "") == "publicado":
            continue
        rellena_gris = _sin_imagen(hermana)
        unifica_stock = (
            _es_stock(hermana)
            and not hermana.get("imagen_autorizada")
            and _difiere_de_canonica(hermana, campos)
        )
        if not (rellena_gris or unifica_stock):
            continue
        try:
            repos.actualizar_pieza_fila(hermana["id"], campos)
            tocadas += 1
        except Exception:  # noqa: BLE001 -- una hermana borrada/en carrera no rompe el resto
            _log.debug("auto-stock: no se pudo espejar el stock a una hermana.", exc_info=True)
    return tocadas


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
        # PORTAL: usa SOLO su foto propia (la del artículo). Nunca foto de stock.
        if (item.get("origen") or "") == ORIGEN_PORTAL:
            continue
        if not (item.get("titulo") or "").strip():
            continue
        if config.marca_apagada(config.ENV_PIPELINE_STOCK, item.get("marca") or ""):
            continue
        plataformas = plataformas_por_item.get(item.get("id"), [])
        hay_vacia = any(_tiene_copy(p) and _sin_imagen(p) for p in plataformas)
        # UNIFICACIÓN: aunque NINGUNA red esté en gris, un tema con DOS fotos de stock distintas
        # debe converger a una sola; se elige para repartir la canónica (reparación, sin coste API).
        hay_divergente = _hay_stock_divergente(plataformas)
        if not (hay_vacia or hay_divergente):
            continue
        hay_stock = any(_es_stock(p) for p in plataformas)
        ya = item.get("id") in ya_procesados
        # Repartir/unificar una foto ya existente (reparación) no gasta APIs: se permite aunque esté
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
    origen: str = licencia_imagen.ORIGEN_STOCK,
    autorizada: bool = False,
    falta_imagen: bool = True,
) -> dict[str, Any] | None:
    """Descarga `url` (SSRF guard) y la fija en la pieza como foto externa, reparte a las hermanas.

    ÚNICA puerta para fijar una foto externa. Por defecto (`origen='stock'`) deja la pieza como
    AYUDA VISUAL bloqueada (`imagen_origen='stock'`, `imagen_autorizada=0`, `falta_imagen=1`). Para
    una foto LICENCIADA (AFP), el endpoint de agencias pasa `origen='licenciada'`, `autorizada=True`
    y `falta_imagen=False`: publicable directamente (la licencia cubre los derechos), conservando
    autor/crédito (obligatorio). Devuelve la fila objetivo actualizada o None si la pieza no existe.
    Propaga `extraccion_url.ExtraccionError` si la descarga falla o el contenido no es una imagen.

    ESPEJO: la misma foto + sus flags se aplican a TODAS las redes hermanas en gris (no solo a la
    pieza tocada): así nunca queda una red con la foto sin su crédito/aviso.
    """
    nombre = extraccion_url.descargar_imagen_a_media(
        url, min_lado=_MIN_LADO_FOTO, categoria="copyright"
    )
    return _fijar_foto(
        pieza_id,
        nombre,
        proveedor=proveedor,
        autor=autor,
        licencia=licencia,
        credito_url=credito_url,
        origen=origen,
        autorizada=autorizada,
        falta_imagen=falta_imagen,
    )


def adjuntar_bytes(
    pieza_id: str,
    datos: bytes,
    *,
    proveedor: str,
    autor: str = "",
    licencia: str = "",
    credito_url: str = "",
    origen: str = licencia_imagen.ORIGEN_GALERIA,
    autorizada: bool = True,
    falta_imagen: bool = False,
) -> dict[str, Any] | None:
    """Guarda una imagen ya en memoria (no una URL) en media y la fija en la pieza.

    Misma puerta que `adjuntar_candidata` para una foto que llega como BYTES (la galería local
    «Propio» por el túnel keni-fotos), no por descarga HTTP. Valida que el contenido es una imagen
    soportada, la sube a media (S3/Garage) y reparte a las hermanas en gris como cualquier otra
    foto adjunta. Por defecto publicable (foto PROPIA del equipo). Lanza `extraccion_url.ExtraccionError`
    si los bytes no son una imagen reconocible.
    """
    from . import media

    ext = extraccion_url._ext_imagen(datos)
    if ext is None:
        raise extraccion_url.ExtraccionError(
            "El contenido recibido no es una imagen (png/jpg/gif/webp)."
        )
    try:
        nombre = media.guardar_bytes(datos, ext=ext, categoria="fotos")
    except media.MediaError as e:
        raise extraccion_url.ExtraccionError(str(e)) from e
    return _fijar_foto(
        pieza_id,
        nombre,
        proveedor=proveedor,
        autor=autor,
        licencia=licencia,
        credito_url=credito_url,
        origen=origen,
        autorizada=autorizada,
        falta_imagen=falta_imagen,
    )


def _fijar_foto(
    pieza_id: str,
    nombre: str,
    *,
    proveedor: str,
    autor: str,
    licencia: str,
    credito_url: str,
    origen: str,
    autorizada: bool,
    falta_imagen: bool,
) -> dict[str, Any] | None:
    """Fija la foto `nombre` (ya en media) en la pieza con sus flags y la reparte a las hermanas.

    Núcleo común de `adjuntar_candidata` (descarga URL) y `adjuntar_bytes` (bytes del túnel):
    escribe los campos de imagen en la pieza y propaga la MISMA foto a las redes del tema en gris.
    """
    campos = {
        "foto": nombre,
        "imagen": "",
        "falta_imagen": falta_imagen,
        "imagen_origen": origen,
        "imagen_proveedor": (proveedor or "stock")[:60],
        "imagen_autor": (autor or "")[:200],
        "imagen_licencia": (licencia or "")[:200],
        "imagen_credito_url": (credito_url or "")[:500],
        "imagen_autorizada": autorizada,
    }
    objetivo = repos.actualizar_pieza_fila(pieza_id, campos)
    if objetivo is None:
        return None
    # Reparte la MISMA foto a las redes del tema que aún están en gris (robusto, no depende del
    # toggle `espejo`): así nunca queda una red con la foto sin su aviso, ni en gris.
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
      1. Si alguna red del tema YA tiene una foto de stock, se REPARTE a las redes vacías Y se
         UNIFICAN las que tuvieran OTRA foto de stock (sin tocar APIs ni descargar): repara y hace
         converger retroactivamente los temas a medias o divergentes, sin un objetivo en gris.
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

    # Camino 1 — REPARACIÓN/UNIFICACIÓN: si el tema YA tiene foto de stock en alguna red, repártela a
    # las vacías Y unifica las redes con OTRA foto de stock (gratis, sin tocar APIs). Va ANTES de
    # exigir un objetivo en gris: un tema sin huecos vacíos pero con stock DIVERGENTE igual converge.
    # Garantiza que la BÚSQUEDA (camino 2) nunca se repita una vez que el tema tiene stock.
    ya_con_stock = next((p for p in plataformas if _es_stock(p)), None)
    if ya_con_stock is not None:
        if not propagar_stock(str(item_id), _campos_desde(ya_con_stock)):
            return None
        fila_id = str((objetivo or ya_con_stock).get("id") or "")
        return repos.obtener_pieza_fila(fila_id)

    # Sin stock que repartir: la búsqueda necesita una red en gris donde adjuntar.
    if objetivo is None:
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
        marca = (item.get("marca") or "").strip()
        try:
            candidatas.extend(stock_fotos.buscar_todos(consulta, limite_por=2, marca=marca))
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
