"""Rendimiento REAL por PIEZA del tablero, leido de Metricool por `id_post_metricool`.

PROBLEMA QUE RESUELVE
=====================
El tablero (`api/publicaciones.py`) muestra el estado editorial de cada pieza (copy/imagen/
revision/publicar) pero NO su rendimiento una vez publicada. Cuando el programador
empuja una pieza a Metricool guarda su `id_post_metricool` por plataforma
(`pieza.id_post_metricool`). Aqui cerramos el bucle: con ese id se lee
el rendimiento REAL (visualizaciones, interacciones, engagement) desde la **API de
Metricool** —la fuente PAGADA— y se pinta en cada tarjeta, SIN adaptadores por red.

La lectura unifica sobre `keni_metricas.servicio.construir_metricas_pieza`, que va a la
fuente activa (Metricool). No hay un adaptador
por plataforma: una sola lectura por (marca, red, id_post).

CACHE
=====
Golpear Metricool por cada tarjeta en cada apertura del tablero seria lento y costoso.
Se cachea por pieza en la tabla generica `metricas_cache` (tipo `pieza_contenido`,
clave `pieza:{marca}:{red}:{id_post}`), igual que el resto de metricas. La lectura es:

  - LAZY FILL con TTL: si la entrada no esta o es vieja (> `TTL_SEGUNDOS`), se recalcula
    al vuelo, se guarda y se devuelve. Si esta fresca, se devuelve la cacheada
    (instantaneo). Asi el rendimiento se actualiza solo cada pocas horas sin recalcular
    en cada render.
  - Degradacion honesta: si la fuente no encuentra el post (recien publicado) o falla,
    se devuelve `encontrado=False` (la UI muestra "sin datos todavia", nunca ceros).

Solo LECTURA de metricas; no muta el tablero. Conexion por operacion (via `repos`),
segura entre hilos como el resto.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timedelta
from typing import Any

from keni_metricas import servicio

from . import config, marcas, repos

_log = logging.getLogger("keni_consola.metricas_pieza")

# Ventana (dias) para considerar una pieza publicada "reciente" y refrescarla de forma
# PROACTIVA (el daemon `metricas_piezas_refresco`). Pasada la ventana el rendimiento se
# estabiliza y el lazy-fill con TTL basta; refrescarla activamente solo gasta cuota.
VENTANA_REFRESCO_DIAS = 30

# Tipo de entrada en `metricas_cache` para las piezas del tablero.
TIPO_PIEZA = "pieza_contenido"

# Frescura del rendimiento por pieza: pasado esto, la siguiente lectura recalcula.
# 4 h casa con la cadencia del daemon de metricas ("1 vez al dia importa"): el
# rendimiento de un post no cambia minuto a minuto.
TTL_SEGUNDOS = 4 * 60 * 60


def _ahora() -> datetime:
    return datetime.now()


def _clave(marca: str, red: str, id_post: str) -> str:
    return f"pieza:{marca}:{red}:{id_post}"


def _es_fresca(generado_en: str, ahora: datetime) -> bool:
    """True si `generado_en` (ISO) esta dentro del TTL respecto a `ahora`."""
    if not generado_en:
        return False
    try:
        ts = datetime.fromisoformat(generado_en)
    except ValueError:
        return False
    return (ahora - ts).total_seconds() < TTL_SEGUNDOS


def _calcular(marca: str, red: str, id_post: str) -> dict[str, Any]:
    """Lee el rendimiento crudo de una pieza desde la fachada de metricas.

    `marca` es el id de marca de la Consola (slug-guion): se traduce a `id_metricas`
    (guion_bajo) en la frontera, igual que el programador. Devuelve el dict de
    `MetricaPieza` (con `encontrado`/`fuente`). Best-effort: cualquier error de la
    fuente se degrada a `encontrado=False` sin romper el tablero.
    """
    id_metricas = marcas.id_metricas_de(marca)
    try:
        return servicio.construir_metricas_pieza(id_metricas, red, id_post)
    except Exception:  # noqa: BLE001 -- nunca rompe el tablero por una pieza
        _log.exception(
            "metricas_pieza: fallo al leer rendimiento de marca=%s red=%s id_post=%s.",
            marca, red, id_post,
        )
        return {
            "id_post": id_post,
            "plataforma": red,
            "encontrado": False,
            "visualizaciones": 0,
            "interacciones": 0,
            "engagement_pct": 0.0,
            # Granulares ausentes en el camino de error: None (sin dato), no 0 falso.
            "likes": None,
            "comentarios": None,
            "compartidos": None,
            "guardados": None,
            "video_views": None,
            "tiempo_medio_vis_s": None,
            "clics_enlace": None,
            "seguidores_netos_atribuidos": None,
            "formato": None,
            "url": None,
            "publicado": None,
            "fuente": "desconocida",
        }


def rendimiento(marca: str, red: str, id_post: str) -> dict[str, Any]:
    """Rendimiento de UNA pieza desde cache (lazy fill + TTL). `{payload..., generado_en}`.

    Si la cache esta fresca devuelve la entrada cacheada; si falta o es vieja, recalcula,
    guarda y devuelve. El payload es el dict de `MetricaPieza` mas `generado_en` (cuando
    se leyo de Metricool, para que la UI muestre "actualizado hace X").
    """
    if not (marca and red and id_post):
        return {**_calcular(marca, red, id_post), "generado_en": ""}

    ahora = _ahora()
    clave = _clave(marca, red, id_post)
    entrada = repos.leer_metricas_cache(clave)
    if entrada is not None and _es_fresca(entrada["generado_en"], ahora):
        return {**entrada["payload"], "generado_en": entrada["generado_en"]}

    payload = _calcular(marca, red, id_post)
    generado_en = ahora.isoformat(timespec="seconds")
    # Solo cacheamos lo ENCONTRADO: un post recien publicado (encontrado=False) no debe
    # quedar pegado en cache; la proxima apertura reintenta hasta que Metricool lo tenga.
    if payload.get("encontrado"):
        repos.guardar_metricas_cache(
            clave,
            TIPO_PIEZA,
            "-",
            marca,
            payload,
            payload.get("fuente") or "",
            generado_en,
        )
    return {**payload, "generado_en": generado_en if payload.get("encontrado") else ""}


def rendimiento_de_tablero(
    contenidos: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Mapa `pieza.id -> rendimiento` para las filas con `id_post_metricool`.

    Recibe los items del tablero (ya con sus `plataformas`) y devuelve solo las filas
    publicadas que tienen `id_post_metricool`: cada una con su rendimiento (cacheado).
    Las filas sin id (no publicadas via Metricool) se omiten: la UI no pinta nada.
    Best-effort por pieza: un fallo de una no afecta a las demas.
    """
    salida: dict[str, dict[str, Any]] = {}
    for contenido in contenidos:
        marca = contenido.get("marca") or ""
        for plat in contenido.get("plataformas", []):
            id_post = plat.get("id_post_metricool") or ""
            red = plat.get("red") or ""
            if not id_post or not marca:
                continue
            salida[plat["id"]] = rendimiento(marca, red, id_post)
    return salida


def listado_piezas_publicadas(
    contenidos: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Lista de piezas publicadas (con `id_post_metricool`) y su rendimiento, para el drill-down.

    Es la vista "marca -> pieza" de Analíticas: aplana las filas por plataforma con
    `id_post_metricool` a una lista de piezas enlazables al tablero, cada una con su
    rendimiento REAL leído de Metricool (la MISMA fuente que el dashboard y que las
    tarjetas del tablero; sin desfase) vía `rendimiento` (cacheado, degradación honesta).

    Recibe los items del tablero ya enriquecidos con `id`/`titulo`/`marca`/`marca_nombre`
    y sus `plataformas`. Cada elemento de la salida lleva la metadata para enlazar a la
    pieza en `/operacion/feed/lista` (`publicacion_id`) y su rendimiento aplanado. Ordena de
    mayor a menor engagement (las encontradas primero; las "sin datos" al final).
    Best-effort por pieza: un fallo de una no afecta a las demás.
    """
    filas: list[dict[str, Any]] = []
    for contenido in contenidos:
        marca = contenido.get("marca") or ""
        publicacion_id = contenido.get("id") or ""
        titulo = contenido.get("titulo") or ""
        marca_nombre = contenido.get("marca_nombre") or marca
        for plat in contenido.get("plataformas", []):
            id_post = plat.get("id_post_metricool") or ""
            red = plat.get("red") or ""
            if not id_post or not marca:
                continue
            rend = rendimiento(marca, red, id_post)
            filas.append(
                {
                    "publicacion_id": publicacion_id,
                    "pieza_id": plat.get("id", ""),
                    "titulo": titulo,
                    "marca": marca,
                    "marca_nombre": marca_nombre,
                    "red": red,
                    "id_post_metricool": id_post,
                    "encontrado": bool(rend.get("encontrado")),
                    "visualizaciones": rend.get("visualizaciones", 0),
                    "interacciones": rend.get("interacciones", 0),
                    "engagement_pct": rend.get("engagement_pct", 0.0),
                    # Desglose granular por pieza (None cuando la fuente no lo da): se
                    # propaga tal cual para el drill-down. El payload base (cache) ya lo
                    # lleva por ser el dict completo de `construir_metricas_pieza`; aqui
                    # solo lo aplanamos campo a campo para esta vista.
                    "likes": rend.get("likes"),
                    "comentarios": rend.get("comentarios"),
                    "compartidos": rend.get("compartidos"),
                    "guardados": rend.get("guardados"),
                    "video_views": rend.get("video_views"),
                    "tiempo_medio_vis_s": rend.get("tiempo_medio_vis_s"),
                    "clics_enlace": rend.get("clics_enlace"),
                    "seguidores_netos_atribuidos": rend.get("seguidores_netos_atribuidos"),
                    "formato": rend.get("formato"),
                    "url": rend.get("url"),
                    "publicado": rend.get("publicado"),
                    "fuente": rend.get("fuente") or "desconocida",
                    "generado_en": rend.get("generado_en", ""),
                }
            )
    # Encontradas primero, ordenadas por engagement desc; las "sin datos" al final.
    filas.sort(key=lambda f: (f["encontrado"], f["engagement_pct"]), reverse=True)
    return filas


# --------------------------------------------------------------------------- #
# Refresco PROACTIVO (daemon): mantiene caliente la cache por pieza             #
# --------------------------------------------------------------------------- #
#
# `rendimiento` (arriba) es LAZY: recalcula al abrir el tablero si la cache esta vieja.
# El daemon `metricas_piezas_refresco` usa lo de abajo para adelantarse: recalcula la
# cache de las piezas publicadas RECIENTES (con `id_post_metricool`) en segundo plano,
# para que el tablero vea datos FRESCOS sin pagar el
# lazy-fill en la apertura. Es solo lectura; no muta el tablero.


def _es_reciente(fecha_iso: str, ahora: datetime, ventana_dias: int) -> bool:
    """True si `fecha_iso` (ISO) cae dentro de la ventana `[ahora - ventana, ahora]`.

    Tolerante: fecha vacia/invalida -> True (no excluimos por no saber la fecha; mejor
    refrescar de mas que dejar fuera una pieza viva por un dato ausente).
    """
    if not fecha_iso:
        return True
    try:
        ts = datetime.fromisoformat(fecha_iso)
    except ValueError:
        return True
    return ts >= ahora - timedelta(days=ventana_dias)


def _registrar_historico(
    marca: str, red: str, id_post: str, payload: dict[str, Any], ts: str
) -> None:
    """Escribe un punto en el HISTÓRICO por pieza (`metricas_pieza_snapshots`). Best-effort.

    Además de cachear el valor ACTUAL, el daemon acumula la SERIE histórica: una fila por
    pieza por refresco, para análisis temporales por marca×red×formato (ADR 0007). El `ts`
    (ISO, del reloj del llamante) da la idempotencia por `(pieza_id, ts)`. Si la escritura
    falla, se loguea y NO se rompe el refresco (el cache ya quedó actualizado).
    """
    try:
        repos.registrar_snapshot_pieza(
            id_post, marca, red, payload.get("formato") or "", ts, payload
        )
    except Exception:  # noqa: BLE001 -- el histórico es best-effort; nunca rompe el refresco
        _log.exception(
            "metricas_pieza: fallo al registrar histórico de marca=%s red=%s id_post=%s.",
            marca, red, id_post,
        )


def registrar_snapshots_de_listado(piezas: list[dict[str, Any]], ts: str) -> int:
    """Acumula un punto del histórico por cada pieza del LISTADO del periodo. Devuelve nº escritos.

    El histórico por pieza (`metricas_pieza_snapshots`) se alimenta con CADA refresco del
    listado de piezas del periodo (`metricas_cache`, tipo `piezas_listado`), usando el `ts`
    del refresco como instante. Así la curva del detalle crece para CUALQUIER pieza del
    periodo —no solo las que la Consola sigue por `id_post_metricool`—. La clave de cada
    snapshot es el `id` de Metricool de la pieza, el MISMO con el que el detalle lee la serie
    (`serie_pieza`). Idempotente por `(pieza_id, ts)`; best-effort por pieza (un fallo de una
    no aborta el resto).
    """
    if not ts:
        return 0
    escritos = 0
    for p in piezas:
        pieza_id = str(p.get("id") or "")
        if not pieza_id:
            continue
        try:
            if repos.registrar_snapshot_pieza(
                pieza_id,
                p.get("cuenta") or "",
                p.get("red") or p.get("plataforma") or "",
                p.get("formato") or "",
                ts,
                p,
            ):
                escritos += 1
        except Exception:  # noqa: BLE001 -- el histórico es best-effort; nunca rompe el refresco
            _log.exception("metricas_pieza: fallo al registrar histórico de pieza id=%s.", pieza_id)
    return escritos


def backfill_historico_desde_cache() -> int:
    """Reconstruye el histórico por pieza replayando las caches del listado de piezas.

    Las entradas `metricas_cache` de tipo `piezas_listado` guardan, por refresco (cada una
    con un `generado_en` distinto), el listado de piezas del periodo con sus métricas en ESA
    fecha: puntos históricos reales ya capturados y dispersos. Esto los vuelca a
    `metricas_pieza_snapshots` (idempotente por `(pieza_id, ts)`), de modo que la curva del
    detalle se llena con el pasado sin esperar a que el daemon acumule puntos nuevos. Se
    invoca una vez al arrancar; reejecutarlo no duplica. Devuelve nº de snapshots escritos.
    """
    from . import metricas_cache

    try:
        filas = repos.listar_metricas_cache_por_tipo((metricas_cache.TIPO_PIEZAS_LISTADO,))
    except Exception:  # noqa: BLE001 -- el backfill es best-effort; no debe romper el arranque
        _log.exception("metricas_pieza: fallo al leer las caches del listado para el backfill.")
        return 0
    total = 0
    for fila in filas:
        payload = fila.get("payload") or {}
        piezas = payload.get("piezas") if isinstance(payload, dict) else None
        if not piezas:
            continue
        total += registrar_snapshots_de_listado(piezas, fila.get("generado_en") or "")
    if total:
        _log.info("Backfill del histórico por pieza: %d snapshot(s) reconstruidos desde la cache.", total)
    return total


def recalcular(marca: str, red: str, id_post: str) -> dict[str, Any]:
    """Recalcula el rendimiento de UNA pieza SALTANDO el TTL y refresca la cache.

    A diferencia de `rendimiento` (lazy: respeta el TTL), esta SIEMPRE va a la fuente.
    La usa el daemon de refresco proactivo. Best-effort: degrada a `encontrado=False`
    sin romper. Solo cachea lo encontrado (igual que `rendimiento`) y, ADEMÁS, si la pieza
    tiene datos, persiste un punto en el histórico por pieza (`metricas_pieza_snapshots`).
    """
    if not (marca and red and id_post):
        return {**_calcular(marca, red, id_post), "generado_en": ""}
    ahora = _ahora()
    payload = _calcular(marca, red, id_post)
    generado_en = ahora.isoformat(timespec="seconds")
    if payload.get("encontrado"):
        repos.guardar_metricas_cache(
            _clave(marca, red, id_post),
            TIPO_PIEZA,
            "-",
            marca,
            payload,
            payload.get("fuente") or "",
            generado_en,
        )
        # Acumula la serie histórica (best-effort, no rompe el refresco si falla).
        _registrar_historico(marca, red, id_post, payload, generado_en)
    return {**payload, "generado_en": generado_en if payload.get("encontrado") else ""}


def refrescar_piezas_recientes(
    *, ventana_dias: int = VENTANA_REFRESCO_DIAS, ahora: datetime | None = None
) -> int:
    """Recalcula la cache de las piezas publicadas RECIENTES con `id_post_metricool`.

    Recorre el tablero, toma las filas por plataforma con `id_post_metricool` cuya
    `fecha_actualizacion` cae dentro de `ventana_dias`, y fuerza un `recalcular` de cada
    una. Devuelve cuantas piezas refresco. Best-effort por pieza (un fallo de una no
    afecta a las demas). Lo invoca el daemon `metricas_piezas_refresco` cada N horas.
    """
    ahora = ahora or _ahora()
    try:
        items = repos.listar_publicacion()
        por_contenido: dict[str, list[dict[str, Any]]] = {}
        for plat in repos.listar_piezas_fila():
            por_contenido.setdefault(plat["publicacion_id"], []).append(plat)
    except Exception:  # noqa: BLE001 -- un fallo de lectura no debe matar el barrido
        _log.exception("metricas_pieza: fallo al leer el tablero para el refresco proactivo.")
        return 0

    refrescadas = 0
    for it in items:
        marca = it.get("marca") or ""
        if not marca:
            continue
        for plat in por_contenido.get(it["id"], []):
            id_post = plat.get("id_post_metricool") or ""
            red = plat.get("red") or ""
            if not id_post:
                continue
            if not _es_reciente(plat.get("fecha_actualizacion", "") or "", ahora, ventana_dias):
                continue
            datos = recalcular(marca, red, id_post)
            if datos.get("encontrado"):
                refrescadas += 1
    # Tras acumular puntos nuevos en el histórico, borra los antiguos para acotar el
    # crecimiento de `metricas_pieza_snapshots` (ADR 0007). El "ahora" lo pasa este
    # llamante (que ya tiene el reloj), no db.py. Best-effort: un fallo de borrado no
    # invalida el barrido (los puntos ya quedaron escritos).
    try:
        retencion = config.metricas_historico_retencion_dias()
        borrados = repos.purgar_snapshots_piezas(retencion, ahora.isoformat(timespec="seconds"))
        if borrados:
            _log.info(
                "Limpieza del histórico por pieza: %d snapshot(s) > %d días eliminados.",
                borrados, retencion,
            )
    except Exception:  # noqa: BLE001 -- el borrado es best-effort; no debe romper el barrido
        _log.exception("metricas_pieza: fallo al borrar el histórico por pieza.")
    return refrescadas


# --------------------------------------------------------------------------- #
# Analítica por SERIE / TIPO (Item C): metricas (Metricool) ↔ contenido (BD)    #
# --------------------------------------------------------------------------- #
#
# Metricool NO expone la "categoría" editorial de un post (serie, tipo, campaña): eso
# vive en la BD de la Consola (`contenido.tipo_contenido` + las `etiquetas` clase/nombre).
# Para graficar el rendimiento POR SERIE/TIPO hay que ENLAZAR cada pieza de Metricool del
# periodo con su `contenido` de la BD y leer ahí su clasificación. El enlace es:
#
#   1) PRIMARIO por id: `pieza.id_post_metricool` (y, como acceso directo a
#      nivel pieza, `contenido.id_post_metricool`) -> el id que Metricool devuelve al
#      programar. Es el enlace fuerte y sin ambigüedad.
#   2) FALLBACK por título: si una pieza de Metricool no tiene id enlazado en la BD (p. ej.
#      publicada fuera de la Consola, o antes de guardar el id), se intenta casar por título
#      NORMALIZADO (sin acentos/may/espacios extra). Es heurístico y puede fallar; se marca
#      como `enlace="titulo"` para ser honestos en la UI. Las piezas sin enlace alguno caen
#      en el grupo "Sin clasificar".
#
# TODO(captura del id al publicar): hoy el id de Metricool se guarda en
# `pieza.id_post_metricool` cuando el programador empuja la pieza (ver
# `metricas_pieza.rendimiento` / el flujo de publicación). La columna
# `contenido.id_post_metricool` (añadida en db.py) queda disponible como acceso directo a
# nivel pieza para cuando el flujo de publicación la rellene; mientras no se rellene, el
# enlace por `pieza` ya cubre las piezas publicadas desde la Consola y el
# fuzzy-match por título cubre el resto. No requiere cambios en el publicador para funcionar.

# Ejes de agrupación de la analítica por serie/tipo. El eje "tipo" sale de
# `contenido.tipo_contenido`; los EJES_ETIQUETA son CLASES de etiqueta (`etiquetas.clase`).
# OJO: la clase de etiqueta "tipo" se renombra a "etiqueta_tipo" como eje para no chocar con
# el eje "tipo" (tipo_contenido). El mapeo eje->clase vive en `_CLASE_DE_EJE`.
EJES_ETIQUETA: tuple[str, ...] = ("campania", "vertical", "etiqueta_tipo")
# Clase de etiqueta real de cada eje de etiqueta (el eje "etiqueta_tipo" mapea a clase "tipo").
_CLASE_DE_EJE: dict[str, str] = {"campania": "campania", "vertical": "vertical", "etiqueta_tipo": "tipo"}
SIN_CLASIFICAR = "Sin clasificar"


def _normalizar_titulo(titulo: str) -> str:
    """Título canónico para el fuzzy-match: sin acentos, minúsculas, espacios colapsados."""
    s = unicodedata.normalize("NFKD", titulo or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    return re.sub(r"\s+", " ", s)


def _red_canonica(pieza: dict[str, Any]) -> str:
    """Red canónica de una pieza del listado del periodo: minúsculas y `twitter` -> `x`.

    El listado (`servicio.construir_listado_piezas`) emite la red en `red`; misma
    normalización que el resto del dashboard para que el filtro hable el mismo idioma.
    """
    red = (pieza.get("red") or pieza.get("plataforma") or "").strip().lower()
    return "x" if red == "twitter" else red


def filtrar_piezas_periodo(
    piezas: list[dict[str, Any]],
    redes: tuple[str, ...] = (),
    formatos: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """Filtra el listado de piezas del periodo por red(es) y formato(s) canónicos.

    Espejo del filtrado del resto del dashboard: una pieza se conserva si su red canónica
    está entre `redes` (vacío = todas) Y su formato canónico (`servicio.formato_canonico`)
    está entre `formatos` (vacío = todos). Con ambos vacíos devuelve la MISMA lista sin
    tocar (comportamiento idéntico a no filtrar). No muta la lista de entrada.
    """
    salida = piezas
    if redes:
        focos = set(redes)
        salida = [p for p in salida if _red_canonica(p) in focos]
    if formatos:
        fmts = set(formatos)
        salida = [p for p in salida if servicio.formato_canonico(p.get("formato") or "") in fmts]
    return salida


# Prefijos de `id_post_metricool` que NO son un id real de post de Metricool, sino sellos de
# degradación: el timeout de publicación (`programador.ID_POST_INCIERTO = "incierto-timeout"`)
# y las reconciliaciones manuales que ops ha escrito sobre piezas inciertas ("reconc-timeout-…").
# Un id real de Metricool/Postproxy nunca empieza así. Hay que excluirlos del índice de enlace:
# al ser un valor COMPARTIDO entre todas las piezas que expiraron, varias piezas distintas
# colisionarían bajo la misma clave ficticia (gana la primera por `setdefault`) y se podrían
# atribuir métricas a la pieza equivocada. Excluirlos no pierde ningún enlace real —un sello
# nunca casa con el feed de Metricool— y la pieza sigue enlazando por el fallback de título.
_SELLOS_ID_POST = ("incierto-", "reconc-")


def _es_id_post_real(id_post: str) -> bool:
    """True si `id_post` es un id de post utilizable como clave de enlace (no un sello)."""
    return bool(id_post) and not id_post.startswith(_SELLOS_ID_POST)


def _indice_contenido_por_post(
    contenidos: list[dict[str, Any]],
    plataformas: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, str]]:
    """Construye los índices de enlace `id_post_metricool -> publicacion_id` y `titulo_norm -> publicacion_id`.

    El índice por id usa tanto `pieza.id_post_metricool` (enlace real por red)
    como `contenido.id_post_metricool` (acceso directo a nivel pieza, si está relleno); los
    sellos de timeout/reconciliación (`_es_id_post_real`) se descartan para que no colisionen
    bajo una clave ficticia compartida. El índice por título normalizado es el fallback
    heurístico. En empates de título (dos piezas con el mismo título) gana la primera vista:
    el fuzzy-match es best-effort, no autoritativo.
    """
    por_id: dict[str, str] = {}
    por_titulo: dict[str, str] = {}
    for c in contenidos:
        cid = c.get("id") or ""
        if not cid:
            continue
        id_directo = (c.get("id_post_metricool") or "").strip()
        if _es_id_post_real(id_directo):
            por_id.setdefault(id_directo, cid)
        titulo_norm = _normalizar_titulo(c.get("titulo", ""))
        if titulo_norm:
            por_titulo.setdefault(titulo_norm, cid)
    for plat in plataformas:
        id_post = (plat.get("id_post_metricool") or "").strip()
        cid = plat.get("publicacion_id") or ""
        if _es_id_post_real(id_post) and cid:
            por_id.setdefault(id_post, cid)
    return por_id, por_titulo


def _grupos_de_contenido(
    contenido: dict[str, Any] | None, etiquetas_por_cid: dict[str, dict[str, str]]
) -> dict[str, str]:
    """Devuelve, para una pieza enlazada, su valor en cada eje (`tipo` + clases de etiqueta).

    `etiquetas_por_cid` es `publicacion_id -> {clase: nombre_etiqueta}`. Si la pieza no está
    enlazada (`contenido is None`) o no tiene valor en un eje, ese eje queda "Sin clasificar".
    """
    grupos: dict[str, str] = {}
    cid = (contenido or {}).get("id") or ""
    etiquetas = etiquetas_por_cid.get(cid, {})
    grupos["tipo"] = (contenido or {}).get("tipo_contenido") or SIN_CLASIFICAR if contenido else SIN_CLASIFICAR
    for eje in EJES_ETIQUETA:
        grupos[eje] = etiquetas.get(_CLASE_DE_EJE[eje], SIN_CLASIFICAR)
    return grupos


def _acumular(serie: dict[str, dict[str, Any]], valor: str, pieza: dict[str, Any]) -> None:
    """Suma una pieza al grupo `valor` de una serie (n, visualizaciones, engagement acumulado)."""
    g = serie.setdefault(valor, {"valor": valor, "n": 0, "visualizaciones": 0, "_eng_sum": 0.0})
    g["n"] += 1
    g["visualizaciones"] += int(pieza.get("visualizaciones", 0) or 0)
    g["_eng_sum"] += float(pieza.get("engagement_pct", 0.0) or 0.0)


def _serie_final(serie: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Cierra una serie: calcula engagement medio por grupo y ordena por engagement desc."""
    salida = []
    for g in serie.values():
        n = g["n"] or 1
        salida.append(
            {
                "valor": g["valor"],
                "n": g["n"],
                "visualizaciones": g["visualizaciones"],
                "engagement_pct": round(g["_eng_sum"] / n, 2),
            }
        )
    salida.sort(key=lambda x: (x["engagement_pct"], x["visualizaciones"]), reverse=True)
    return salida


def analitica_por_etiqueta(
    rango: str,
    marca_consola: str | None,
    marca_metricas: str | None,
    redes: tuple[str, ...] = (),
    formatos: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Rendimiento de las piezas del periodo AGRUPADO por tipo de contenido y por etiqueta.

    Cruza las piezas de Metricool del periodo (`servicio.construir_listado_piezas`) con su
    `contenido` de la BD (enlace por `id_post_metricool`; fallback fuzzy por título) y agrega
    engagement medio + visualizaciones + nº de piezas por cada eje (`tipo` + clases de
    etiqueta `campania`/`vertical`/`tipo`). `redes` acota a esas redes y `formatos` a esos
    formatos canónicos ANTES de agregar (vacío = todas/todos), igual que el resto del
    dashboard. Devuelve una estructura lista para graficar:

        {"series": [{"eje": "tipo", "etiqueta": "Tipo de contenido",
                     "grupos": [{"valor": ..., "n": ..., "visualizaciones": ..., "engagement_pct": ...}]}, ...],
         "total": <piezas del periodo>, "enlazadas": <por id>, "enlazadas_titulo": <por fuzzy>,
         "sin_enlace": <sin casar>, "fuente": <metricool|...>}

    Best-effort y honesto: si nada enlaza, las series salen con todo en "Sin clasificar".
    """
    piezas = filtrar_piezas_periodo(
        servicio.construir_listado_piezas(rango, marca_metricas), redes, formatos
    )
    fuente = servicio.nombre_fuente()

    contenidos = repos.listar_publicacion(marca=marca_consola)
    plataformas = repos.listar_piezas_fila()
    por_id, por_titulo = _indice_contenido_por_post(contenidos, plataformas)
    contenido_por_id = {c["id"]: c for c in contenidos if c.get("id")}

    # Resuelve etiquetas: publicacion_id -> {clase: nombre}. Solo nos interesa el nombre por
    # clase (el primero asignado de cada clase; el modelo garantiza nombre único por clase).
    # SOLO etiquetas ACTIVAS: una línea/vertical retirada del plan (p. ej. "Ciencia/Tech" en
    # UnoTV) sigue en piezas antiguas, pero no debe reaparecer como serie; se ignora y la
    # pieza cae en "Sin clasificar" para ese eje.
    etiquetas = {e["id"]: e for e in repos.listar_etiquetas(solo_activas=True)}
    asignaciones = repos.etiquetas_por_contenido()
    etiquetas_por_cid: dict[str, dict[str, str]] = {}
    for cid, ids in asignaciones.items():
        for eid in ids:
            et = etiquetas.get(eid)
            if not et:
                continue
            etiquetas_por_cid.setdefault(cid, {}).setdefault(et.get("clase", ""), et.get("nombre", ""))

    series_acum: dict[str, dict[str, dict[str, Any]]] = {
        eje: {} for eje in ("tipo", *EJES_ETIQUETA)
    }
    enlazadas = enlazadas_titulo = sin_enlace = 0
    for p in piezas:
        cid = por_id.get(str(p.get("id") or ""))
        if cid:
            enlazadas += 1
        else:
            cid = por_titulo.get(_normalizar_titulo(p.get("titulo", "")))
            if cid:
                enlazadas_titulo += 1
            else:
                sin_enlace += 1
        contenido = contenido_por_id.get(cid) if cid else None
        grupos = _grupos_de_contenido(contenido, etiquetas_por_cid)
        for eje, serie in series_acum.items():
            _acumular(serie, grupos[eje], p)

    etiquetas_eje = {
        "tipo": "Tipo de contenido",
        "campania": "Campaña",
        "vertical": "Vertical",
        "etiqueta_tipo": "Tipo (etiqueta)",
    }
    series = [
        {"eje": eje, "etiqueta": etiquetas_eje.get(eje, eje.capitalize()), "grupos": _serie_final(serie)}
        for eje, serie in series_acum.items()
    ]
    return {
        "series": series,
        "total": len(piezas),
        "enlazadas": enlazadas,
        "enlazadas_titulo": enlazadas_titulo,
        "sin_enlace": sin_enlace,
        "fuente": fuente,
    }
