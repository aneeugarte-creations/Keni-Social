"""Fuente `metricool`: consume la **API REST de Metricool** como una `FuenteMetricas` más.

B (app Métricas) es **consumidor** de Metricool, no motor de ingesta propia
(ADR 0005). En vez de construir un adaptador contra cada API oficial (Meta/
TikTok/X/YouTube), leemos lo que Metricool YA consolidó vía su API REST
(el cliente está en plan **Advanced**, que habilita el API token). Esta clase implementa
el MISMO contrato `FuenteMetricas` que `FuenteMuestra` y `FuenteCompuesta`, de
modo que el dashboard, el MCP y los reportes funcionan igual con cualquiera.

Autenticación (doc oficial de la API de Metricool, swagger en
https://app.metricool.com/api/swagger.json y la guía
https://help.metricool.com/en/article/basic-guide-for-api-integration-abukgf/):

- Base URL: ``https://app.metricool.com/api``.
- Todas las llamadas requieren 3 parámetros de identidad:
  - ``userToken`` → va en la cabecera ``X-Mc-Auth`` (NO es un Bearer).
  - ``userId``    → query param (id de usuario de la cuenta Metricool).
  - ``blogId``    → query param (id de la "marca"/blog en Metricool).
- El API solo está disponible en plan Advanced o superior.

Degradación honesta: si NO hay ``userToken``, ``userId`` o ``blogId`` configurados,
la fuente activa NO inventa datos: `construir_fuente` (en `config.py`) cae a la
fuente `muestra`. Si la API falla en una llamada concreta, esa plataforma queda
OMITIDA en la cobertura (igual que `FuenteCompuesta`), nunca con ceros falsos.

Endpoints usados (documentados arriba):
- ``GET /admin/simpleProfiles``  → lista de marcas (id ↔ label) del usuario.
- ``GET /v2/analytics/timelines`` → serie temporal de UNA métrica para una red en
  un periodo; trae además un ``aggregate`` (SUM/AVG) que usamos como total del
  periodo. Params: ``network``, ``metric``, ``from``, ``to`` (ISO 8601), más la
  identidad (``userId``/``blogId``/``X-Mc-Auth``).
- ``GET /v2/analytics/posts/{network}`` → piezas del periodo por red, para
  las "mejores piezas". Params: ``from``, ``to`` (ISO 8601) + identidad.

SUPUESTOS SIN CONFIRMAR (no hay token real para validar contra la API en vivo;
documentados también en el reporte de la tarea):
- Los **nombres exactos de métrica** por red (`_METRICAS_RED`) salen del enum del
  swagger, pero el swagger no fija qué métrica es "la" de visualizaciones/
  interacciones/alcance para cada red de forma inequívoca. Se eligen los nombres
  más plausibles del enum y se AÍSLAN en un único mapa editable.
- La **forma del campo ``data``** de `/v2/analytics/posts/{network}` (qué claves
  trae cada post: id, fecha, vistas, interacciones, url) NO está detallada en el
  swagger (el item es genérico). El parseo es defensivo (varios alias por campo) y
  cualquier post sin vistas se descarta; si la forma real difiere, se ajusta el
  método `_pieza_desde_post` SIN tocar el resto.
- El **mapeo blogId ↔ marca**: una marca de keni (`claro_sports`, …) corresponde a
  un ``blogId`` de Metricool. Ese mapeo se configura por marca (ver `config.py`).
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import UTC, date, datetime, timedelta

import httpx

from ..schema import (
    CampaniaAds,
    Cobertura,
    Cuenta,
    MetricaPieza,
    MetricaPlataforma,
    MotivoOmision,
    Periodo,
    Pieza,
    Plataforma,
    PuntoSerie,
    ResumenMetricas,
    agregar_alcance,
    agregar_engagement,
    engagement_pct,
    resolver_rango,
)
from ._http import cliente_http, get_json

log = logging.getLogger("keni_metricas")

BASE = "https://app.metricool.com/api"
NOMBRE = "metricool"

# Zona horaria con la que se acotan TODAS las ventanas de fecha (from/to) contra la API.
# Sin `timezone`, Metricool asume su propio default y las fronteras de día quedan corridas
# para México (un "lunes" nuestro puede cortar a media tarde del domingo allí). Fijarla a
# `America/Mexico_City` alinea los días del piloto con los del medio. Configurable por env
# para otros husos sin tocar código.
_TZ = os.environ.get("KENI_METRICAS_TZ", "America/Mexico_City")

# Timeout del cliente HTTP de Metricool. El agregado mensual de posts de cuentas
# muy activas (p.ej. YouTube de Claro Sports: ~10k posts/mes) tarda 25-30s en
# responder; el default de 15s lo cortaba siempre (los reintentos repetían el
# mismo timeout, así que nunca cuajaban). `connect` se mantiene corto para fallar
# rápido si la API no responde; `read` es amplio para tolerar esos agregados.
_TIMEOUT = httpx.Timeout(connect=10.0, read=90.0, write=15.0, pool=15.0)

# Mapeo Plataforma (keni) -> network (Metricool). Metricool usa "twitter" para X.
_RED_METRICOOL: dict[Plataforma, str] = {
    Plataforma.facebook: "facebook",
    Plataforma.instagram: "instagram",
    Plataforma.x: "twitter",
    Plataforma.tiktok: "tiktok",
    Plataforma.youtube: "youtube",
}

# Campo de `/admin/simpleProfiles` -> Plataforma de keni. Un valor "truthy" en ese
# campo del perfil (id de la página/usuario de la red) significa que la marca TIENE esa
# red CONECTADA en Metricool. Permite distinguir "no conectada" (la marca no la tiene
# dada de alta) de "conectada pero sin datos en el rango", que de otro modo caerían en el
# mismo "error" engañoso. La conexión de cada red varía por marca y se detecta aquí (p.ej.
# YouTube solo en Claro Sports).
_PERFIL_RED: dict[str, Plataforma] = {
    "facebook": Plataforma.facebook,
    "instagram": Plataforma.instagram,
    "twitter": Plataforma.x,
    "tiktok": Plataforma.tiktok,
    "youtube": Plataforma.youtube,
}

# Validez (segundos) de la lectura cacheada de redes conectadas (`/admin/simpleProfiles`).
# La instancia de la fuente se reusa mientras el config.toml no cambie, así que una caché
# sin caducidad ocultaría para siempre los cambios hechos EN Metricool (un alta o una
# desconexión de red no toca nuestro config). Con esta ventana corta, la siguiente pasada
# del daemon —o cualquier lectura tras expirar— vuelve a consultar perfiles y refleja
# altas y desconexiones sin reiniciar el proceso.
_TTL_CONECTADAS_S = 300.0

# Validez (segundos) del payload CRUDO de posts/reels memoizado por (cuenta, red, desde,
# hasta). Una sola pasada del daemon —o un refresco de la UI— arma `resumen`, `mejores_piezas`,
# desglose, crosstab, tendencia y correlación sobre el MISMO (marca, rango): sin esto cada uno
# re-descarga los mismos `/v2/analytics/posts/{red}`, 6-8 veces por red. La ventana es corta a
# propósito: comparte el fetch dentro de una pasada (que dura segundos) sin servir datos rancios
# entre pasadas (que van minutos aparte y vuelven a consultar al expirar).
_TTL_FETCH_S = 120.0

# Métricas de Metricool por red para (visualizaciones, interacciones, alcance).
#
# SUPUESTO (ver docstring del módulo): los nombres salen del enum de
# `/v2/analytics/timelines` (swagger). El swagger NO declara de forma inequívoca
# cuál es "la" métrica de cada concepto por red; se eligen los más plausibles y se
# aíslan aquí para poder corregirlos contra la API real sin tocar la lógica.
#   - visualizaciones: impresiones/reproducciones agregadas del periodo.
#   - interacciones:   engagement total (likes+comentarios+compartidos+…).
#   - alcance:         solo Meta lo mide (PLATAFORMAS_CON_ALCANCE); el resto None.
_METRICA_VIS = "vis"
_METRICA_INT = "int"
_METRICA_ALC = "alc"
# Métrica de SEGUIDORES por red (tamaño de comunidad, un STOCK acumulado). Nombres
# CONFIRMADOS contra la API real (cuenta del piloto): la serie de community vive en
# `/v2/analytics/timelines` con `subject=account` (¡imprescindible!) y un nombre de métrica
# distinto por red:
#   - facebook:  pageFollows        - instagram: followers
#   - tiktok:    followers_count    - youtube:   totalSubscribers
# El neto del periodo = último - primer punto. Si la red no expone followers (o no está
# conectada) la serie viene vacía -> 0 (honesto).
_METRICA_SEG = "seg"
# Valor de `subject` para las métricas de cuenta/community en timelines (followers).
_SUBJECT_CUENTA = "account"
_METRICAS_RED: dict[Plataforma, dict[str, str]] = {
    Plataforma.facebook: {
        _METRICA_VIS: "impressions",
        _METRICA_INT: "interactions",
        _METRICA_ALC: "impressionsunique",
        _METRICA_SEG: "pageFollows",
    },
    Plataforma.instagram: {
        _METRICA_VIS: "impressions",
        _METRICA_INT: "interactions",
        _METRICA_ALC: "reach",
        _METRICA_SEG: "followers",
    },
    Plataforma.x: {
        _METRICA_VIS: "impressions",
        _METRICA_INT: "interactions",
        _METRICA_SEG: "communitySize",
    },
    Plataforma.tiktok: {
        _METRICA_VIS: "views",
        _METRICA_INT: "interactions",
        _METRICA_SEG: "followers_count",
    },
    Plataforma.youtube: {
        _METRICA_VIS: "views",
        _METRICA_INT: "interactions",
        _METRICA_SEG: "totalSubscribers",
    },
}

# Alias de campos al parsear un post de `/v2/analytics/posts/{network}`. La forma del
# post DIFIERE por red (confirmado contra la API real de Metricool del piloto):
#   - Instagram: publishedAt, views, interactions, reach, likes/comments/shares/saved.
#   - Facebook:  created (objeto) / timestamp (epoch ms), impressions, reactions,
#                comments, shares, linkclicks, videoViews.
#   - TikTok:    createTime (ISO), viewCount, likeCount/commentCount/shareCount,
#                averageTimeWatched, videoId, shareUrl, title/videoDescription.
#   - YouTube:   publishedAt, views, likes/comments/shares, videoId, watchUrl, title.
# Se prueban TODOS los alias en orden para parsear todas las redes de forma consistente.
_ALIAS_ID = ("id", "postId", "providerId", "videoId")
_ALIAS_FECHA = (
    "publishedAt", "publicationDate", "dateTime", "date", "createdAt",
    "createTime", "created", "timestamp",
)
# viewCount = TikTok; impressions = Facebook; views = Instagram/YouTube; reach = fallback.
_ALIAS_VIS = ("impressions", "views", "viewCount", "reach", "visualizations")
_ALIAS_INT = ("interactions", "engagement", "engagements")
_ALIAS_TEXTO = ("text", "title", "message", "caption", "content", "videoDescription")
_ALIAS_URL = ("url", "permalink", "permalinkUrl", "link", "shareUrl", "watchUrl", "embedLink")
# Alias granulares por pieza. Nombres reales de Metricool/redes; si ninguno viene, el
# campo queda en None (degradación honesta), nunca 0 inventado.
_ALIAS_LIKES = ("likes", "favorites", "reactions", "likeCount")
_ALIAS_COMENTARIOS = ("comments", "replies", "commentsCount", "commentCount")
_ALIAS_COMPARTIDOS = ("shares", "retweets", "reposts", "sharesCount", "shareCount")
_ALIAS_GUARDADOS = ("saves", "saved", "bookmarks", "savedCount")
# OJO: sin el alias genérico "views" a propósito. En posts de imagen/carrusel Metricool
# usa "views"/"impressions" para las visualizaciones GENERALES; si lo tomáramos aquí,
# `video_views` duplicaría `visualizaciones` en piezas que no son vídeo. Solo campos
# específicos de vídeo -> None en imágenes (honesto), valor real en reels/vídeos.
_ALIAS_VIDEO_VIEWS = ("videoViews", "plays", "videoViewCount", "reelPlays", "videoPlayCount")
_ALIAS_TIEMPO_VIS = (
    "avgWatchTime", "averageWatchTime", "avgTimeWatched", "averageViewDuration",
    "averageTimeWatched",
)
_ALIAS_CLICS = ("linkClicks", "clicks", "urlClicks", "websiteClicks", "linkClicksCount", "linkclicks")
# Alcance (usuarios ÚNICOS) a nivel post: solo Meta lo expone. IG lo trae como `reach`;
# FB como `impressionsUnique`/`postImpressionsUnique` (los reels FB usan este último). El
# resto de redes no lo miden -> None (degradación honesta, no un 0 inventado).
_ALIAS_ALCANCE = ("reach", "impressionsUnique", "postImpressionsUnique", "impressionsunique")
# Impresiones (veces MOSTRADA la pieza) por red, aditivas: IG `impressionsTotal`/`impressions`;
# FB `impressions`; TikTok `viewCount`; Twitter `impressions`; YouTube `views`. Es la cifra de
# VOLUMEN; distinta del alcance (usuarios únicos). None si ninguna viene (degradación honesta).
_ALIAS_IMPRESIONES = ("impressionsTotal", "impressions", "viewCount", "views")
_ALIAS_FORMATO = ("type", "mediaType", "postType", "contentType", "format", "videoType")
# Seguidores ganados/atribuidos a UN post: casi seguro Metricool no lo expone a
# nivel post; se captura si algún alias lo trae, si no queda None.
_ALIAS_SEG_POST = ("followsFromPost", "newFollowers", "followersGained")

# --- PUENTE scheduler -> analítica ---------------------------------------------
# El `id_post` que la Consola guarda (`pieza.id_post_metricool`) es el id del SCHEDULER
# de Metricool (`POST /v2/scheduler/posts` -> `id`), un espacio de ids DISTINTO al de la
# analítica: `/v2/analytics/posts/{network}` indexa cada post por su id NATIVO de la red
# (FB: `pageId_storyId`; IG: media id, con la URL `/p/{shortcode}/`), nunca por el id del
# scheduler. Por eso un match directo del id del scheduler contra la analítica nunca casa.
# El puente es `GET /v2/scheduler/posts/{id}`: su `providers[].id`/`publicUrl` dan el id
# nativo (o la URL pública) con el que SÍ se casa la analítica.
ENDPOINT_SCHEDULER_POST = "/v2/scheduler/posts"

# Shortcode de Instagram dentro de una URL `/p/{shortcode}/` o `/reel/{shortcode}/`
# (publicUrl del scheduler o `url`/`reelUrl` del registro de analítica): es la clave de
# enlace estable para IG (su id nativo de media no aparece tal cual en la analítica, pero la
# URL sí lleva el shortcode).
_RE_SHORTCODE_IG = re.compile(r"/(?:p|reel)/([^/?#]+)")
# storyId de Facebook dentro de `.../posts/{storyId}` (publicUrl del scheduler) o como
# sufijo `pageId_storyId` del `postId` de analítica.
_RE_STORY_FB = re.compile(r"/posts/(\d+)")
# Metricool sirve los Reels de Facebook/Instagram en un endpoint APARTE de `/posts`;
# `/posts/{network}` NO los incluye. Sin este endpoint aparte, todo el contenido en VÍDEO
# vertical (lo que más cross-postea un medio) quedaría invisible: solo se vería en TikTok. La
# FORMA del reel difiere de un post y entre redes (confirmado contra la API real):
#   - Instagram: reelId, content (caption), publishedAt, views, impressionsTotal,
#                interactions, likes/comments/shares/saved, url, averageWatchTime.
#   - Facebook:  reelId, description (caption), created, blueReelsPlayCount,
#                postImpressionsUnique, engagement, postVideoReactions, reelUrl/videoUrl.
# Redes con endpoint de reels (las demás no lo tienen):
_RED_CON_REELS: frozenset[Plataforma] = frozenset({Plataforma.facebook, Plataforma.instagram})
# Redes que exponen una SERIE DIARIA de alcance de cuenta (timelines subject=account
# metric=reach). Confirmado contra la API real: solo Instagram; Facebook no tiene reach en
# ningún sitio. Es un flujo diario (no un stock), distinto del alcance único de periodo —que
# Metricool no da de forma fiable—, así que se expone como serie, no como total de cabecera.
_RED_CON_ALCANCE_CUENTA: frozenset[Plataforma] = frozenset({Plataforma.instagram})
# Redes con endpoint de stories (`/v2/analytics/stories/{network}`). Solo se usa para CONTAR
# stories del periodo (volumen): Metricool casi no expone su rendimiento (FB ninguna métrica;
# IG con impresiones/alcance deprecados por Meta), así que no entran en vis/interacciones.
_RED_CON_STORIES: frozenset[Plataforma] = frozenset({Plataforma.facebook, Plataforma.instagram})
_ALIAS_REEL_ID = ("reelId", "id", "videoId", "postId")
# El caption del reel: `content` (IG) / `description` (FB) van PRIMERO (son el cuerpo
# real con los hashtags); el resto son defensivos.
_ALIAS_REEL_TEXTO = ("content", "description", "text", "caption", "title")
_ALIAS_REEL_VIS = (
    "views", "blueReelsPlayCount", "videoViews", "impressionsTotal",
    "postImpressionsUnique", "reach", "impressions", "plays",
)
# OJO: en Reels `engagement` es una TASA (%), NO un conteo de interacciones: no se usa como
# tal. El conteo se arma en `_interacciones_reel` (IG: `interactions`; FB: reacciones +
# acciones sociales; más el desglose granular).
_ALIAS_REEL_URL = ("url", "reelUrl", "permalink", "videoUrl", "shareUrl")
_ALIAS_REEL_TIEMPO = ("averageWatchTime", "postVideoAvgTimeWatchedSeconds", "avgWatchTime")
_ALIAS_REEL_LIKES = ("likes", "postVideoReactions", "reactions", "likeCount")

# Normalización del formato crudo (mediaType/type de Metricool/redes) a los
# literales del contrato. Claves comparadas en MAYÚSCULAS.
_FORMATO_NORMAL: dict[str, str] = {
    "IMAGE": "foto",
    "PHOTO": "foto",
    "VIDEO": "video",
    "IGTV": "video",
    "SHORT": "video",
    "SHORTS": "video",
    "REEL": "reel",
    "REELS": "reel",
    "CAROUSEL": "carrusel",
    "CAROUSEL_ALBUM": "carrusel",
    "ALBUM": "carrusel",
    "LINK": "link",
    "TEXT": "texto",
    "STATUS": "texto",
    "TWEET": "texto",
}


def _primero(d: dict, claves: tuple[str, ...], defecto=None):
    """Primer valor no nulo encontrado entre `claves` (parseo defensivo)."""
    for k in claves:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return defecto


def _entero(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


# --- Publicidad (Meta/TikTok Ads): el INORGÁNICO ------------------------------
# Las campañas de pago viven en `/v2/advertising/campaigns?providers[]=...`, APARTE del
# feed orgánico (`/v2/analytics/posts`), que NO trae lo pagado. Las métricas van en un
# objeto `metrics` con claves en MAYÚSCULAS (IMPRESSIONS/SPENT/CLICKS), acotadas por
# from/to. Confirmado contra la API real del piloto (act_… de Claro Sports/UnoTV).
# Providers por DEFECTO; una marca puede acotarlos con `ads_proveedores` en su config
# (p.ej. sin licencia de TikTok Ads: ["facebookads"] evita un 403 esperado cada barrido).
_PROVIDERS_ADS: tuple[str, ...] = ("facebookads", "tiktokads")
# Provider de Ads -> red destino normalizada (la de keni). 'facebookads' cubre FB e IG;
# se queda en 'facebook' (la cuenta de Ads es de la página). 'tiktokads' -> 'tiktok'.
_RED_DE_PROVIDER_ADS: dict[str, str] = {"facebookads": "facebook", "tiktokads": "tiktok"}
# Un nombre de campaña de un POST IMPULSADO: "Publicación: «caption»" o
# "Publicación de Instagram: caption". El grupo 1 es el caption (para atribuir a la pieza).
_PAT_AD_PUBLICACION = re.compile(
    r'^\s*publicaci[oó]n(?:\s+de\s+\w+)?\s*:\s*["“]?(.+?)["”]?\s*$', re.IGNORECASE | re.UNICODE
)


def _caption_de_anuncio(nombre: str) -> str:
    """Caption de un post impulsado a partir del nombre de la campaña de Ads; "" si el
    nombre no es de un post impulsado (campaña con nombre propio)."""
    m = _PAT_AD_PUBLICACION.match(nombre or "")
    return m.group(1).strip() if m else ""


def _fecha_ads(v) -> str:
    """Fecha ISO (YYYY-MM-DD) de un campo de Ads, que puede ser `{dateTime, timezone}` o
    una cadena; "" si no se puede determinar."""
    if isinstance(v, dict):
        v = v.get("dateTime") or v.get("date")
    return str(v)[:10] if v else ""


def _a_int_opt(v) -> int | None:
    """Convierte a int de forma segura, o None si el valor es ausente/no numérico.

    A diferencia de `_entero` (que cae a 0), aquí la ausencia es None: degradación
    honesta para los campos granulares opcionales (un 0 sería un dato falso).
    """
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


_GRANULAR_INTERACCION = ("likes", "comentarios", "compartidos", "guardados")


def _interacciones_efectivas(inter: int, gran: dict) -> int:
    """Interacciones del post: el MÁXIMO entre el agregado de Metricool y la suma del
    desglose por tipo (likes+comentarios+compartidos+guardados).

    El campo `interactions` agregado de Metricool no es fiable en muchos posts: a veces
    viene 0 y a veces un número diminuto (p.ej. 12) cuando el desglose es enorme (likes en
    decenas de miles, típico en TikTok/Facebook). Tomar ese agregado daría un engagement
    falsamente bajo. El desglose tampoco es siempre completo (Metricool no separa todos los
    tipos en toda red), así que el agregado puede legítimamente superarlo. `max(...)` toma
    lo MEJOR de ambos: nunca por debajo del agregado ni del desglose conocido. Si no hay ni
    agregado ni desglose, queda 0 (degradación honesta).
    """
    return max(inter, sum(gran[k] for k in _GRANULAR_INTERACCION if gran.get(k) is not None))


def _interacciones_reel(reel: dict, gran: dict) -> int:
    """Interacciones (CONTEO) de un Reel: el MÁXIMO entre el agregado, las acciones de FB y
    el desglose granular.

    Por red (confirmado contra la API real): Instagram trae `interactions` (conteo).
    Facebook NO lo trae: su conteo es reacciones (`postVideoReactions`) + acciones sociales
    (`postVideoSocialActions`); su campo `engagement` es una TASA (%), NO un conteo, así que
    NUNCA se usa como interacciones (era el bug: `engagement`=0.83 → 0). `max(...)` toma lo
    mejor disponible; 0 si la red no expone ninguno (degradación honesta).
    """
    agg = _entero(_primero(reel, ("interactions",), 0))
    fb = _entero(_primero(reel, ("postVideoReactions",), 0)) + _entero(
        _primero(reel, ("postVideoSocialActions",), 0)
    )
    desglose = sum(gran[k] for k in _GRANULAR_INTERACCION if gran.get(k) is not None)
    return max(agg, fb, desglose)


def _formato_opt(v) -> str | None:
    """Normaliza el formato crudo a un literal del contrato, o None si no viene.

    Metricool/redes usan vocabularios como 'feed_image', 'feed_carousel_album',
    'feed_video', 'feed_reel', 'reel', 'video', 'photo'... Se quita el prefijo 'FEED_'
    (Metricool antepone 'feed_' a los formatos de Instagram/Facebook) antes de mapear a
    los buckets del contrato (foto/carrusel/video/reel/link/texto). Si no se reconoce,
    devuelve el valor crudo en minúsculas (mejor algo que None cuando sí vino un dato);
    None solo si el campo está ausente.
    """
    if v is None or v == "":
        return None
    crudo = str(v).strip()
    clave = crudo.upper()
    if clave.startswith("FEED_"):
        clave = clave[len("FEED_"):]
    return _FORMATO_NORMAL.get(clave, crudo.lower() or None)


def _shortcode_ig(url: str | None) -> str | None:
    """Shortcode de una URL de Instagram `/p/{shortcode}/`, o None si no lo lleva."""
    if not url:
        return None
    m = _RE_SHORTCODE_IG.search(str(url))
    return m.group(1) if m else None


def _story_fb(valor: str | None) -> str | None:
    """storyId de Facebook: el `{storyId}` de `.../posts/{storyId}` o el sufijo de `pageId_storyId`.

    Acepta tanto una publicUrl (`facebook.com/<page>/posts/<storyId>`) como un id nativo
    crudo (`pageId_storyId` o `storyId` pelado). Devuelve el storyId comparable con el
    sufijo del `postId` de la analítica de Facebook, o None si no se reconoce.
    """
    if not valor:
        return None
    s = str(valor)
    m = _RE_STORY_FB.search(s)
    if m:
        return m.group(1)
    cola = s.rsplit("_", 1)[-1]
    return cola if cola.isdigit() else None


def _claves_enlace_post(post: dict, plat: Plataforma) -> set[str]:
    """Claves de enlace de un post de analítica para casarlo con un id del scheduler.

    Devuelve el conjunto de identificadores con los que un post PUEDE casarse: sus alias de
    id directos, y —según la red— el shortcode de IG (de su `url`) o el storyId de FB (sufijo
    de su `postId`). Así el matcher cubre los tres caminos de enlace sin recorrer la lista más
    de una vez.
    """
    claves = {
        str(v) for alias in (*_ALIAS_ID, *_ALIAS_REEL_ID)
        if (v := post.get(alias)) not in (None, "")
    }
    url = _primero(post, _ALIAS_URL) or _primero(post, _ALIAS_REEL_URL)
    if plat is Plataforma.instagram:
        sc = _shortcode_ig(url)
        if sc:
            claves.add(sc)
    elif plat is Plataforma.facebook:
        sid = _story_fb(str(post.get("postId") or "")) or _story_fb(url)
        if sid:
            claves.add(sid)
    return claves


def _objetivos_de_enlace(id_post: str, nativo: str | None, url_publica: str | None,
                         plat: Plataforma) -> set[str]:
    """Conjunto de ids que identifican al post buscado (para casarlo con la analítica).

    Incluye SIEMPRE el `id_post` crudo (cubre ids ya nativos / Postproxy, y el camino sin
    puente). Si el scheduler resolvió el id nativo/URL pública, añade el id nativo, el
    storyId de FB y el shortcode de IG, que son las claves con las que la analítica indexa.
    """
    objetivos = {str(id_post)}
    if nativo:
        objetivos.add(str(nativo))
        if plat is Plataforma.facebook and (sid := _story_fb(nativo)):
            objetivos.add(sid)
        if plat is Plataforma.instagram and (sc := _shortcode_ig(nativo)):
            objetivos.add(sc)
    if url_publica:
        if plat is Plataforma.facebook and (sid := _story_fb(url_publica)):
            objetivos.add(sid)
        if plat is Plataforma.instagram and (sc := _shortcode_ig(url_publica)):
            objetivos.add(sc)
    return objetivos


def _fecha(v) -> date | None:
    """Fecha de publicación del post -> `date`, o None si no se puede determinar.

    Metricool devuelve `publishedAt` como OBJETO `{'dateTime': 'AAAA-MM-DDTHH:MM:SS',
    'timezone': '...'}`, no como string plano. Se extrae el `dateTime` del objeto, y se
    acepta también string ISO (con o sin hora) o epoch (segundos/milisegundos). Devuelve
    None si no hay fecha reconocible: el llamante NO debe fabricar una fecha (ver
    `_pieza_desde_post`)."""
    if isinstance(v, dict):
        v = v.get("dateTime") or v.get("date") or v.get("value") or v.get("iso")
    if isinstance(v, bool):  # bool es subclase de int: no es una fecha
        return None
    if isinstance(v, (int, float)):
        try:
            ts = float(v)
            if ts > 1e11:  # epoch en milisegundos
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=UTC).date()
        except (ValueError, OSError, OverflowError):
            return None
    if isinstance(v, str):
        s = v.strip()
        if s.isdigit():
            return _fecha(int(s))
        if len(s) >= 10:
            try:
                return date.fromisoformat(s[:10])
            except ValueError:
                return None
    return None


# Tope de seguridad de posts a procesar de `/v2/analytics/posts/{network}`. La API ignora
# `from`/`to` en YouTube y devuelve el CANAL ENTERO (Claro Sports: ~10k ítems desde 2013
# por cada lectura mensual), sin paginación ni `limit` en su swagger. El acotado por rango
# (`_acotar_posts_por_rango`) ya recorta la inmensa mayoría; este tope es la última red por
# si los datos no vinieran ordenados y no se pudiera cortar.
_MAX_POSTS = 2000


def _acotar_posts_por_rango(posts: list[dict], desde: date) -> list[dict]:
    """Recorta una lista de posts ordenada por fecha DESC a los del rango, sin descargar
    más allá de lo necesario.

    Metricool devuelve los posts más nuevos primero (confirmado en todas las redes del
    piloto). Cuando se acumulan posts CONSECUTIVOS anteriores a `desde` se asume que el
    resto también lo es y se corta: evita arrastrar miles de ítems históricos que el filtro
    defensivo de `_parsear_posts` descartaría igual. El corte es DEFENSIVO: solo actúa si los
    posts vienen realmente en orden DESC; ante una fecha que rompe ese orden (sube tras haber
    bajado) NO recorta y devuelve la lista entera, para no perder nunca piezas en rango. El
    margen evita cortar por un puñado de posts sin fecha o desordenados intercalados."""
    margen = 0
    for i, post in enumerate(posts):
        f = _fecha(_primero(post, _ALIAS_FECHA))
        if f is None:
            continue
        if f >= desde:
            # Una pieza dentro/encima del rango tras haber visto anteriores: el orden DESC no
            # se cumple, abortar el recorte (devuelve todo; el filtro defensivo se encarga).
            if margen:
                return posts
            continue
        margen += 1
        if margen > 16:
            return posts[: i + 1]
    return posts


class FuenteMetricool:
    """Implementa `FuenteMetricas` leyendo de la API REST de Metricool.

    Credenciales POR MARCA: en el cliente cada marca es una cuenta Metricool distinta,
    así que cada una trae su PROPIO ``user_token`` (cabecera ``X-Mc-Auth``),
    ``user_id`` y ``blog_id`` (query params). NO hay identidad global.

    Parámetros:
      - ``marcas``: mapeo ``id_marca_keni -> {"user_token": ..., "user_id": ...,
        "blog_id": ..., "nombre": ..., "plataformas": [Plataforma...]}``. Solo
        deben pasarse marcas con credenciales completas (``config.py`` ya filtra
        y resuelve los defaults antes de construir la fuente); las demás se omiten
        antes (en el flujo).
      - ``cliente``: ``httpx.Client`` inyectable (tests con respx).
    """

    nombre = NOMBRE

    def __init__(
        self,
        marcas: dict[str, dict],
        cliente: httpx.Client | None = None,
    ):
        self._marcas = marcas
        self._cli = cliente or cliente_http(timeout=_TIMEOUT)
        # cache cuenta_id -> (instante_monotónico, set[Plataforma] conectadas) de
        # simpleProfiles; valor None si la consulta de perfiles falló (entonces no se filtra
        # por conexión: se intenta todo). Caduca a los `_TTL_CONECTADAS_S` para detectar
        # altas/desconexiones hechas en Metricool sin reiniciar el proceso.
        self._conectadas_cache: dict[str, tuple[float, set[Plataforma] | None]] = {}
        # Memo del payload CRUDO de posts/reels por (kind, cuenta, red, desde, hasta) con
        # caducidad (`_TTL_FETCH_S`): comparte UN solo fetch entre `resumen`/`mejores_piezas`/
        # desglose/… de un mismo (marca, rango) en una pasada. Solo cachea ÉXITOS (un fallo de
        # fetch se propaga y no se memoiza, para que la cobertura siga omitiendo la red).
        self._fetch_cache: dict[tuple[str, str, str, str, str], tuple[float, list[dict]]] = {}
        # Cobertura de la ÚLTIMA llamada a `mejores_piezas` (igual que en FuenteCompuesta):
        # qué plataformas aportaron piezas vs. fallaron. Las tools la leen vía
        # `cobertura_piezas()` para exponer la degradación parcial en vez de callarla.
        self._cobertura_piezas: Cobertura | None = None

    # --- identidad / HTTP (resuelta POR MARCA) ------------------------------
    def _headers(self, cuenta_id: str) -> dict:
        return {"X-Mc-Auth": str(self._marca(cuenta_id).get("user_token", ""))}

    def _params_base(self, cuenta_id: str) -> dict:
        marca = self._marca(cuenta_id)
        return {
            "userId": str(marca.get("user_id", "")),
            "blogId": str(marca.get("blog_id", "")),
        }

    def _rango_params(self, desde: date, hasta: date) -> dict:
        """`from`/`to` ISO de la ventana + `timezone` MX (frontera de día consistente).

        Centraliza el acotado de TODAS las peticiones con ventana de fecha (posts, reels,
        stories, timelines, campañas) para que la zona horaria viaje siempre y los días no
        se corran (ver `_TZ`)."""
        return {
            "from": desde.isoformat() + "T00:00:00",
            "to": hasta.isoformat() + "T23:59:59",
            "timezone": _TZ,
        }

    def _fetch_cacheado(self, clave: tuple, hacer) -> list[dict]:
        """Devuelve `hacer()` memoizado por `clave` durante `_TTL_FETCH_S` segundos.

        Solo memoiza el ÉXITO: si `hacer` lanza, la excepción se propaga sin tocar la cache
        (el llamante degrada como hasta ahora). El valor cacheado NO se muta aguas abajo
        (los parseos solo iteran), así que se comparte la misma lista sin copiarla.
        """
        ahora = time.monotonic()
        hit = self._fetch_cache.get(clave)
        if hit is not None and (ahora - hit[0]) < _TTL_FETCH_S:
            return hit[1]
        datos = hacer()
        self._fetch_cache[clave] = (ahora, datos)
        return datos

    def _marca(self, cuenta_id: str) -> dict:
        if cuenta_id not in self._marcas:
            from .base import CuentaNoEncontrada

            disponibles = ", ".join(self._marcas) or "(ninguna configurada)"
            raise CuentaNoEncontrada(
                f"Cuenta {cuenta_id!r} no encontrada o sin credenciales de Metricool. "
                f"Disponibles: {disponibles}."
            )
        return self._marcas[cuenta_id]

    def _plataformas(self, marca: dict) -> list[Plataforma]:
        plats = marca.get("plataformas") or list(_RED_METRICOOL)
        return [p if isinstance(p, Plataforma) else Plataforma(p) for p in plats]

    def _universo_plataformas(
        self, cuenta_id: str, conectadas: set[Plataforma] | None
    ) -> list[Plataforma]:
        """Redes a auditar: las configuradas de la marca UNIDAS con las conectadas AHORA.

        La lista `plataformas` del config es un mínimo curado, no un tope: una red dada de
        alta EN Metricool (la fuente de verdad de "conectada", vía simpleProfiles) que el
        config no liste DEBE auditarse igual, o un alta jamás se detectaría. Conserva el
        orden de las configuradas y añade al final, en orden canónico, las conectadas que
        falten. Si la detección falló (`conectadas` None) se queda con las configuradas.
        """
        universo = self._plataformas(self._marca(cuenta_id))
        if conectadas:
            universo += [p for p in _RED_METRICOOL if p in conectadas and p not in universo]
        return universo

    # --- contrato FuenteMetricas -------------------------------------------
    def cuentas(self) -> list[Cuenta]:
        return [
            Cuenta(
                id=cid,
                nombre=m.get("nombre", cid),
                plataformas=self._plataformas(m),
            )
            for cid, m in self._marcas.items()
        ]

    def resumen(self, cuenta_id: str, rango: str) -> ResumenMetricas:
        self._marca(cuenta_id)
        desde, hasta, _ = resolver_rango(rango)
        conectadas = self._redes_conectadas(cuenta_id)
        plats = self._universo_plataformas(cuenta_id, conectadas)

        por_plataforma: list[MetricaPlataforma] = []
        cobertura = Cobertura()
        for plat in plats:
            # 1) Red que la marca NO tiene conectada en Metricool (lo dice simpleProfiles):
            #    se omite con un motivo claro, no como "error" engañoso. Si la consulta de
            #    perfiles falló (conectadas=None) no se filtra: se intenta leer igualmente.
            if conectadas is not None and plat not in conectadas:
                cobertura.omitidas.append(plat)
                cobertura.motivo[plat.value] = MotivoOmision.no_conectada
                continue
            # 2) Agregado por red SUMANDO los posts del periodo. Es la fuente UNIFORME que
            #    funciona en todas las redes; `/v2/analytics/timelines` tiene un vocabulario
            #    de métrica distinto por red (y en Instagram ni encaja), así que solo daba
            #    datos de TikTok. Sumar posts da vistas+interacciones reales y consistentes
            #    con las piezas que ve el usuario.
            m = self._metrica_plataforma_desde_posts(cuenta_id, plat, desde, hasta)
            if m is None:
                cobertura.omitidas.append(plat)
                cobertura.motivo[plat.value] = MotivoOmision.error_api
                continue
            # 3) Stories (FB/IG): solo CONTAR las publicadas en el periodo (volumen). No se
            #    suman a vis/interacciones (Metricool casi no da su rendimiento; ver schema).
            if plat in _RED_CON_STORIES:
                m.stories = self._contar_stories(cuenta_id, plat, desde, hasta)
            por_plataforma.append(m)
            cobertura.ok.append(plat)

        if cobertura.omitidas:
            log.warning(
                "metricool: cobertura parcial en %s/%s: %d/%d plataformas omitidas",
                cuenta_id,
                rango,
                len(cobertura.omitidas),
                len(plats),
            )

        vis = sum(m.visualizaciones for m in por_plataforma)
        inter = sum(m.interacciones for m in por_plataforma)
        impresiones = sum(m.impresiones for m in por_plataforma)
        # Seguidores NETOS del periodo: suma, sobre las plataformas que respondieron,
        # de (último punto - primer punto) de su serie de followers. Defensivo: una
        # plataforma sin métrica de seguidores o con serie vacía aporta 0 (no inventa).
        seguidores_netos = sum(
            self._seguidores_netos_plataforma(cuenta_id, m.plataforma, desde, hasta)
            for m in por_plataforma
        )
        return ResumenMetricas(
            cuenta=cuenta_id,
            rango=rango,
            periodo=Periodo(desde=desde, hasta=hasta),
            visualizaciones=vis,
            impresiones=impresiones,
            alcance=agregar_alcance(por_plataforma),
            interacciones=inter,
            engagement_pct=agregar_engagement(por_plataforma, inter),
            seguidores_netos=seguidores_netos,
            variacion_vs_anterior={},
            por_plataforma=por_plataforma,
            fuente=self.nombre,
            cobertura=cobertura,
        )

    def _seguidores_netos_plataforma(
        self, cuenta_id: str, plat: Plataforma, desde: date, hasta: date
    ) -> int:
        """Seguidores netos ganados en el periodo por UNA red: último - primer punto.

        La serie de followers de `/v2/analytics/timelines` es un STOCK (tamaño de la
        comunidad cada día), no un flujo: el neto del periodo es el valor del último
        punto menos el del primero. Defensivo: si la red no declara métrica de
        seguidores, la API falla o la serie viene vacía, devuelve 0 (no inventa).
        """
        metricas = _METRICAS_RED.get(plat, {})
        metrica = metricas.get(_METRICA_SEG)
        if not metrica:
            return 0
        try:
            datos = get_json(
                self._cli,
                f"{BASE}/v2/analytics/timelines",
                params={
                    **self._params_base(cuenta_id),
                    "network": _RED_METRICOOL[plat],
                    "metric": metrica,
                    # subject=account: imprescindible para las métricas de community/followers.
                    "subject": _SUBJECT_CUENTA,
                    **self._rango_params(desde, hasta),
                },
                headers=self._headers(cuenta_id),
            )
        except Exception as e:  # noqa: BLE001 — degrada a 0, como el resto
            log.warning("metricool: seguidores %s/%s fallaron: %s", plat.value, cuenta_id, e)
            return 0
        # Reúne todos los puntos (fecha, valor) de las series, ordenados por fecha,
        # y toma último - primero. Combina por si la red devuelve varias series.
        puntos: list[tuple[str, float]] = []
        for serie in datos.get("data") or []:
            for v in serie.get("values", []):
                crudo = v.get("dateTime") or v.get("date")
                valor = v.get("value")
                if crudo is None or valor is None:
                    continue
                puntos.append((str(crudo), float(valor)))
        if len(puntos) < 2:
            # 0 o 1 puntos: no hay variación medible del periodo.
            return 0
        puntos.sort(key=lambda p: p[0])
        return int(puntos[-1][1] - puntos[0][1])

    def serie_seguidores(self, cuenta_id: str, rango: str) -> list[dict]:
        """Stock DIARIO de followers por red sobre el periodo (no flujo).

        Reutiliza la misma serie de `/v2/analytics/timelines` que
        `_seguidores_netos_plataforma`, pero CONSERVA los valores por día en vez de
        quedarse solo con (último − primero). Devuelve una lista de puntos
        ordenados por fecha:

            [{"fecha": "AAAA-MM-DD", "por_red": {"instagram": 1050, ...}}, ...]

        Una red que NO expone followers (sin métrica de seguidores, API caída o
        serie vacía) simplemente NO aparece en `por_red` (degradación honesta: se
        omite, nunca aporta 0 falso). Si NINGUNA red expone followers, la lista
        sale vacía. El total y el neto los calcula el llamante (`servicio`).
        """
        marca = self._marca(cuenta_id)
        desde, hasta, _ = resolver_rango(rango)
        por_dia: dict[date, dict[str, int]] = {}
        for plat in self._plataformas(marca):
            for f, valor in self._stock_seguidores_plataforma(cuenta_id, plat, desde, hasta):
                por_dia.setdefault(f, {})[plat.value] = valor
        return [
            {"fecha": f.isoformat(), "por_red": por_dia[f]} for f in sorted(por_dia)
        ]

    def _serie_cuenta_metrica(
        self, cuenta_id: str, plat: Plataforma, metrica: str, desde: date, hasta: date
    ) -> list[tuple[date, int]]:
        """Puntos (fecha, valor) de UNA métrica de CUENTA (timelines subject=account).

        Fuente única de las series de cuenta (followers, alcance diario): pide
        `/v2/analytics/timelines` con `subject=account` y la `metrica` dada. Degrada a []
        si la API falla o la serie viene vacía (degradación honesta).
        """
        try:
            datos = get_json(
                self._cli,
                f"{BASE}/v2/analytics/timelines",
                params={
                    **self._params_base(cuenta_id),
                    "network": _RED_METRICOOL[plat],
                    "metric": metrica,
                    # subject=account: imprescindible para las métricas de cuenta.
                    "subject": _SUBJECT_CUENTA,
                    **self._rango_params(desde, hasta),
                },
                headers=self._headers(cuenta_id),
            )
        except Exception as e:  # noqa: BLE001 — degrada a [], como el resto
            log.warning("metricool: serie %s %s/%s fallo: %s", metrica, plat.value, cuenta_id, e)
            return []
        # Un valor por día: si una fecha aparece en varias series, gana el último.
        por_fecha: dict[date, int] = {}
        for serie in datos.get("data") or []:
            for v in serie.get("values", []):
                crudo = v.get("dateTime") or v.get("date")
                valor = v.get("value")
                if crudo is None or valor is None:
                    continue
                try:
                    f = date.fromisoformat(str(crudo)[:10])
                except ValueError:
                    continue
                por_fecha[f] = _entero(valor)
        return sorted(por_fecha.items())

    def _stock_seguidores_plataforma(
        self, cuenta_id: str, plat: Plataforma, desde: date, hasta: date
    ) -> list[tuple[date, int]]:
        """Puntos (fecha, stock de followers) de UNA red, ordenados por fecha.

        Degrada a [] si la red no declara métrica de seguidores, la API falla o la
        serie viene vacía (mismo criterio honesto que `_seguidores_netos_plataforma`).
        """
        metrica = _METRICAS_RED.get(plat, {}).get(_METRICA_SEG)
        if not metrica:
            return []
        return self._serie_cuenta_metrica(cuenta_id, plat, metrica, desde, hasta)

    def serie_alcance(self, cuenta_id: str, rango: str) -> list[dict]:
        """Serie DIARIA de alcance de cuenta por red sobre el periodo (flujo, no stock).

        Solo Instagram expone alcance de cuenta (`reach`) como serie diaria vía
        `/v2/analytics/timelines` subject=account; el resto de redes no lo miden y se
        OMITEN (degradación honesta, nunca 0 falso). Devuelve puntos ordenados por fecha:

            [{"fecha": "AAAA-MM-DD", "por_red": {"instagram": 12000, ...}}, ...]

        Una red sin alcance de cuenta (o con serie vacía) no aparece en `por_red`. Si
        NINGUNA red lo expone, la lista sale vacía. El total lo calcula el llamante.
        """
        marca = self._marca(cuenta_id)
        desde, hasta, _ = resolver_rango(rango)
        por_dia: dict[date, dict[str, int]] = {}
        for plat in self._plataformas(marca):
            if plat not in _RED_CON_ALCANCE_CUENTA:
                continue
            metrica = _METRICAS_RED.get(plat, {}).get(_METRICA_ALC)
            if not metrica:
                continue
            for f, valor in self._serie_cuenta_metrica(cuenta_id, plat, metrica, desde, hasta):
                por_dia.setdefault(f, {})[plat.value] = valor
        return [
            {"fecha": f.isoformat(), "por_red": por_dia[f]} for f in sorted(por_dia)
        ]

    def _redes_conectadas(self, cuenta_id: str) -> set[Plataforma] | None:
        """Redes que la marca tiene CONECTADAS en Metricool, vía `/admin/simpleProfiles`.

        El perfil de la marca (su `blogId`) trae un campo por red (`facebook`,
        `instagram`, `twitter`, `tiktok`, `youtube`) con el id de la cuenta enlazada o
        `null`; un valor truthy = conectada. Permite marcar "no conectada" con honestidad
        en vez de "error" (la conexión de cada red varía por marca). Se cachea por instancia
        con caducidad (`_TTL_CONECTADAS_S`) para que un alta o una desconexión hecha EN
        Metricool se refleje sin reiniciar el proceso. Devuelve None si la consulta falla: el
        llamante NO filtra por conexión (intenta leer todas, comportamiento previo) en vez de
        ocultar redes.
        """
        cacheada = self._conectadas_cache.get(cuenta_id)
        if cacheada is not None and (time.monotonic() - cacheada[0]) < _TTL_CONECTADAS_S:
            return cacheada[1]
        try:
            datos = get_json(
                self._cli,
                f"{BASE}/admin/simpleProfiles",
                params={"userId": self._params_base(cuenta_id)["userId"]},
                headers=self._headers(cuenta_id),
            )
        except Exception as e:  # noqa: BLE001 — sin perfiles no filtramos (None)
            log.warning("metricool: simpleProfiles %s falló: %s", cuenta_id, e)
            self._conectadas_cache[cuenta_id] = (time.monotonic(), None)
            return None
        blog_id = str(self._marca(cuenta_id).get("blog_id", ""))
        perfil = None
        for p in datos if isinstance(datos, list) else []:
            if isinstance(p, dict) and str(p.get("id")) == blog_id:
                perfil = p
                break
        if perfil is None:
            self._conectadas_cache[cuenta_id] = (time.monotonic(), None)
            return None
        conectadas = {plat for clave, plat in _PERFIL_RED.items() if perfil.get(clave)}
        self._conectadas_cache[cuenta_id] = (time.monotonic(), conectadas)
        return conectadas

    def _metrica_plataforma_desde_posts(
        self, cuenta_id: str, plat: Plataforma, desde: date, hasta: date
    ) -> MetricaPlataforma | None:
        """Agregado por red SUMANDO los posts del periodo (None si la API de posts falla).

        Reúsa el MISMO parseo que las piezas (`/v2/analytics/posts/{network}` + los reels de
        FB/IG, que viven en `/v2/analytics/reels/{network}`), en vez de
        `/v2/analytics/timelines` (vocabulario de métrica distinto por red; solo daba TikTok).
        Así el agregado por red es consistente con las piezas/desglose que ve el usuario: una
        red que solo publica reels (FB/IG) aporta sus vistas+interacciones, no 0/0. `impresiones`
        (veces mostrada, aditiva) se SUMA por post; es la cifra de VOLUMEN. `alcance` (usuarios
        únicos) queda None: Metricool no da un alcance único de cuenta/periodo fiable, y el reach
        por post no es aditivo (vive en `Pieza.alcance` como detalle). Una red conectada sin
        actividad en el rango devuelve 0/0 (la UI lo muestra como "sin métricas", no como error).
        """
        try:
            posts = self._fetch_posts(cuenta_id, plat, desde, hasta)
        except Exception as e:  # noqa: BLE001 — error real de API → None → cobertura lo omite
            log.warning("metricool: agregado posts %s/%s falló: %s", plat.value, cuenta_id, e)
            return None
        piezas = self._parsear_posts(posts, plat, cuenta_id, desde, hasta)
        # Reels (FB/IG) viven en un endpoint aparte que `/posts` no cubre; inclúyelos —igual
        # que `mejores_piezas`— para que el agregado por red cuadre con el desglose. Sin esto,
        # una red que SOLO publica reels saldría 0/0 = "sin métricas" pese a tener actividad.
        if plat in _RED_CON_REELS:
            piezas.extend(self._reels_plataforma(cuenta_id, plat, desde, hasta))
        vis = sum(p.visualizaciones for p in piezas)
        inter = sum(p.interacciones for p in piezas)
        impresiones = sum(p.impresiones or 0 for p in piezas)
        return MetricaPlataforma(
            plataforma=plat,
            visualizaciones=vis,
            impresiones=impresiones,
            alcance=None,
            interacciones=inter,
            engagement_pct=engagement_pct(inter, vis),
        )

    def mejores_piezas(self, cuenta_id: str, rango: str, n: int) -> list[Pieza]:
        n = max(n, 0)
        if n == 0:
            return []
        self._marca(cuenta_id)
        desde, hasta, _ = resolver_rango(rango)
        piezas: list[Pieza] = []
        cobertura = Cobertura()
        for plat in self._universo_plataformas(cuenta_id, self._redes_conectadas(cuenta_id)):
            # A diferencia de `_piezas_plataforma` (que degrada a [] en silencio para
            # otros agregados), aquí el fallo del fetch se REGISTRA en la cobertura:
            # un top sin una plataforma configurada no debe pasar por completo.
            try:
                posts = self._fetch_posts(cuenta_id, plat, desde, hasta)
            except Exception as e:  # noqa: BLE001
                log.warning("metricool: piezas %s/%s fallaron: %s", plat.value, cuenta_id, e)
                cobertura.omitidas.append(plat)
                cobertura.motivo[plat.value] = MotivoOmision.error_api
                continue
            piezas.extend(self._parsear_posts(posts, plat, cuenta_id, desde, hasta))
            cobertura.ok.append(plat)
            # Reels (FB/IG) viven en un endpoint aparte que `/posts` no cubre: añádelos.
            # Si SOLO fallan los reels (los posts respondieron), degrada a [] con log;
            # la plataforma sigue contando como ok (cobertura de grano por red).
            if plat in _RED_CON_REELS:
                piezas.extend(self._reels_plataforma(cuenta_id, plat, desde, hasta))
        self._cobertura_piezas = cobertura
        piezas.sort(key=lambda p: p.engagement_pct, reverse=True)
        return piezas[:n]

    def cobertura_piezas(self) -> Cobertura | None:
        """Cobertura de la última llamada a `mejores_piezas` (None si aún no se llamó)."""
        return self._cobertura_piezas

    def campanias_ads(self, cuenta_id: str, rango: str) -> list[CampaniaAds]:
        """Campañas de publicidad PAGADA del periodo (Meta/TikTok Ads): el inorgánico.

        Lee `/v2/advertising/campaigns` por provider. Solo devuelve las campañas con ENTREGA
        en la ventana (impresiones > 0): la API lista TODO el histórico de campañas (activas
        o no), pero su `metrics` viene acotado a from/to, así que 0 impresiones = sin entrega
        en el periodo. Los providers consultados se acotan por marca (`ads_proveedores`; sin
        la clave, todos los conocidos). Degrada por provider: un 403/500 (red de Ads no
        conectada) se OMITE, no rompe el resto."""
        desde, hasta, _ = resolver_rango(rango)
        params_rango = self._rango_params(desde, hasta)
        out: list[CampaniaAds] = []
        provs = self._marca(cuenta_id).get("ads_proveedores") or _PROVIDERS_ADS
        for prov in provs:
            try:
                datos = get_json(
                    self._cli,
                    f"{BASE}/v2/advertising/campaigns",
                    params={**self._params_base(cuenta_id), **params_rango, "providers[]": prov},
                    headers=self._headers(cuenta_id),
                )
            except Exception as e:  # noqa: BLE001 -- provider no conectado/caído: se omite.
                log.warning("metricool: ads %s/%s fallaron: %s", prov, cuenta_id, e)
                continue
            for c in datos.get("data") or []:
                if not isinstance(c, dict):
                    continue
                m = c.get("metrics") or {}
                impresiones = _entero(m.get("IMPRESSIONS") or 0)
                if impresiones <= 0:
                    continue  # sin entrega en la ventana: no es del periodo
                nombre = str(c.get("name") or "")
                caption = _caption_de_anuncio(nombre)
                out.append(
                    CampaniaAds(
                        nombre=nombre,
                        red=_RED_DE_PROVIDER_ADS.get(prov, prov),
                        impresiones=impresiones,
                        gasto=round(float(m.get("SPENT") or 0.0), 2),
                        clics=_entero(m.get("CLICKS") or 0),
                        moneda=str(c.get("currency") or ""),
                        inicio=_fecha_ads(c.get("start")),
                        fin=_fecha_ads(c.get("stop")),
                        es_post_impulsado=bool(caption),
                        caption=caption,
                        cuenta=cuenta_id,
                    )
                )
        return out

    def _fetch_posts(
        self, cuenta_id: str, plat: Plataforma, desde: date, hasta: date
    ) -> list[dict]:
        """Posts crudos de `/v2/analytics/posts/{network}`, memoizados (RAISES si la API falla).

        Aislado para compartirlo entre las piezas y el agregado por red, y para que el
        llamante decida cómo degradar (las piezas → []; el agregado → None/omitida). El
        resultado se memoiza por (cuenta, red, rango) durante `_TTL_FETCH_S` para que los
        múltiples consumidores de un mismo (marca, rango) no re-peguen a la API."""
        clave = ("posts", cuenta_id, plat.value, desde.isoformat(), hasta.isoformat())
        return self._fetch_cacheado(
            clave, lambda: self._fetch_posts_remoto(cuenta_id, plat, desde, hasta)
        )

    def _fetch_posts_remoto(
        self, cuenta_id: str, plat: Plataforma, desde: date, hasta: date
    ) -> list[dict]:
        """GET crudo a `/v2/analytics/posts/{network}` + acotado por rango (sin cache)."""
        datos = get_json(
            self._cli,
            f"{BASE}/v2/analytics/posts/{_RED_METRICOOL[plat]}",
            params={
                **self._params_base(cuenta_id),
                **self._rango_params(desde, hasta),
            },
            headers=self._headers(cuenta_id),
        )
        crudos = [p for p in (datos.get("data") or []) if isinstance(p, dict)]
        # La API ignora `from`/`to` en YouTube y devuelve el canal entero (~10k ítems);
        # acota a los del rango aprovechando el orden DESC antes de seguir.
        posts = _acotar_posts_por_rango(crudos, desde)
        if len(posts) > _MAX_POSTS:
            log.warning(
                "metricool: posts %s/%s devolvió %d ítems (rango %s..%s); se truncan a %d "
                "(la API no acota por fecha ni pagina; ver _MAX_POSTS)",
                plat.value, cuenta_id, len(posts), desde, hasta, _MAX_POSTS,
            )
            posts = posts[:_MAX_POSTS]
        return posts

    def _parsear_posts(
        self, posts: list[dict], plat: Plataforma, cuenta_id: str, desde: date, hasta: date
    ) -> list[Pieza]:
        """Posts crudos -> list[Pieza], filtrando por rango REAL de la pieza.

        Filtro DEFENSIVO por rango: aunque se envíen `from`/`to` a la API, se exige que la
        fecha REAL de la pieza caiga en [desde, hasta] (Metricool ha devuelto posts fuera de
        ventana; sin esto se colaban en top/peores/stats/agregados)."""
        piezas: list[Pieza] = []
        for post in posts:
            try:
                pieza = self._pieza_desde_post(post, plat, cuenta_id)
            except Exception as e:  # noqa: BLE001 — un post malformado no tumba al resto del lote
                log.warning("metricool: post %s/%s no parseable: %s", plat.value, cuenta_id, e)
                continue
            if pieza is not None and desde <= pieza.publicado <= hasta:
                piezas.append(pieza)
        return piezas

    def _piezas_plataforma(
        self, cuenta_id: str, plat: Plataforma, desde: date, hasta: date, n: int
    ) -> list[Pieza]:
        """Posts de una plataforma (degrada a [] si la API falla)."""
        try:
            posts = self._fetch_posts(cuenta_id, plat, desde, hasta)
        except Exception as e:  # noqa: BLE001
            log.warning("metricool: piezas %s/%s fallaron: %s", plat.value, cuenta_id, e)
            return []
        return self._parsear_posts(posts, plat, cuenta_id, desde, hasta)

    def _fetch_reels(
        self, cuenta_id: str, plat: Plataforma, desde: date, hasta: date
    ) -> list[dict]:
        """Reels crudos de `/v2/analytics/reels/{network}`, memoizados (RAISES si la API falla).

        Igual que `_fetch_posts`: se memoiza por (cuenta, red, rango) durante `_TTL_FETCH_S`
        para compartir el fetch entre los consumidores de un mismo (marca, rango)."""
        clave = ("reels", cuenta_id, plat.value, desde.isoformat(), hasta.isoformat())
        return self._fetch_cacheado(
            clave, lambda: self._fetch_reels_remoto(cuenta_id, plat, desde, hasta)
        )

    def _fetch_reels_remoto(
        self, cuenta_id: str, plat: Plataforma, desde: date, hasta: date
    ) -> list[dict]:
        """GET crudo a `/v2/analytics/reels/{network}` (sin cache)."""
        datos = get_json(
            self._cli,
            f"{BASE}/v2/analytics/reels/{_RED_METRICOOL[plat]}",
            params={
                **self._params_base(cuenta_id),
                **self._rango_params(desde, hasta),
            },
            headers=self._headers(cuenta_id),
        )
        return [r for r in (datos.get("data") or []) if isinstance(r, dict)]

    def _contar_stories(
        self, cuenta_id: str, plat: Plataforma, desde: date, hasta: date
    ) -> int | None:
        """Nº de stories publicadas en el periodo (None si la API de stories falla).

        Solo VOLUMEN de actividad: cuenta las stories de `/v2/analytics/stories/{network}`
        cuya fecha real cae en [desde, hasta] (filtro defensivo, como los posts). NO lee su
        rendimiento: Metricool casi no lo expone (FB ninguna métrica; IG con impresiones/
        alcance deprecados por Meta). None = no se pudo leer; 0 = leído, sin stories.
        """
        try:
            datos = get_json(
                self._cli,
                f"{BASE}/v2/analytics/stories/{_RED_METRICOOL[plat]}",
                params={
                    **self._params_base(cuenta_id),
                    **self._rango_params(desde, hasta),
                },
                headers=self._headers(cuenta_id),
            )
        except Exception as e:  # noqa: BLE001 — sin stories no rompemos el resumen (None)
            log.warning("metricool: stories %s/%s falló: %s", plat.value, cuenta_id, e)
            return None
        n = 0
        for s in datos.get("data") or []:
            if not isinstance(s, dict):
                continue
            fecha = _fecha(_primero(s, _ALIAS_FECHA))
            # Sin fecha legible: se confía en el filtro from/to de la API (no se descarta).
            if fecha is None or desde <= fecha <= hasta:
                n += 1
        return n

    def _reels_plataforma(
        self, cuenta_id: str, plat: Plataforma, desde: date, hasta: date
    ) -> list[Pieza]:
        """Reels de una plataforma como `Pieza` (degrada a [] si la API falla)."""
        try:
            reels = self._fetch_reels(cuenta_id, plat, desde, hasta)
        except Exception as e:  # noqa: BLE001 -- sin reels (red sin endpoint / API caída): [].
            log.warning("metricool: reels %s/%s fallaron: %s", plat.value, cuenta_id, e)
            return []
        piezas: list[Pieza] = []
        for reel in reels:
            pieza = self._pieza_desde_reel(reel, plat, cuenta_id)
            if pieza is not None and desde <= pieza.publicado <= hasta:
                piezas.append(pieza)
        return piezas

    def _pieza_desde_reel(
        self, reel: dict, plat: Plataforma, cuenta_id: str | None = None
    ) -> Pieza | None:
        """Mapea un Reel de Metricool a `Pieza` (mismo contrato que un post; formato='reel').

        Descarta el reel sin reproducciones o sin fecha determinable (mismo criterio que
        `_pieza_desde_post`: sin fecha real no se ubica en el rango, no se fabrica)."""
        vis = _entero(_primero(reel, _ALIAS_REEL_VIS, 0))
        if not vis:
            return None
        fecha = _fecha(_primero(reel, _ALIAS_FECHA))
        if fecha is None:
            return None
        texto = str(_primero(reel, _ALIAS_REEL_TEXTO, ""))
        gran = {
            "likes": _a_int_opt(_primero(reel, _ALIAS_REEL_LIKES)),
            "comentarios": _a_int_opt(_primero(reel, _ALIAS_COMENTARIOS)),
            "compartidos": _a_int_opt(_primero(reel, _ALIAS_COMPARTIDOS)),
            "guardados": _a_int_opt(_primero(reel, _ALIAS_GUARDADOS)),
            "video_views": _a_int_opt(_primero(reel, _ALIAS_REEL_VIS)),
            "tiempo_medio_vis_s": _a_int_opt(_primero(reel, _ALIAS_REEL_TIEMPO)),
            "formato": "reel",
        }
        inter = _interacciones_reel(reel, gran)
        return Pieza(
            id=str(_primero(reel, _ALIAS_REEL_ID, "")),
            plataforma=plat,
            titulo=(texto or "(sin texto)")[:120],
            texto=texto,
            publicado=fecha,
            visualizaciones=vis,
            interacciones=inter,
            engagement_pct=engagement_pct(inter, vis),
            url=_primero(reel, _ALIAS_REEL_URL),
            cuenta=cuenta_id,
            alcance=_a_int_opt(_primero(reel, _ALIAS_ALCANCE)),
            # Impresiones del reel: sus reproducciones (la métrica de volumen del vídeo).
            impresiones=vis,
            **gran,
        )

    @staticmethod
    def _granulares(post: dict) -> dict:
        """Extrae los campos granulares opcionales de un post (parseo defensivo).

        Cada campo es None si su alias no viene (degradación honesta). Devuelve un
        dict listo para desempaquetar al construir `Pieza`/`MetricaPieza`, con las
        claves snake_case del contrato compartido.
        """
        return {
            "likes": _a_int_opt(_primero(post, _ALIAS_LIKES)),
            "comentarios": _a_int_opt(_primero(post, _ALIAS_COMENTARIOS)),
            "compartidos": _a_int_opt(_primero(post, _ALIAS_COMPARTIDOS)),
            "guardados": _a_int_opt(_primero(post, _ALIAS_GUARDADOS)),
            "video_views": _a_int_opt(_primero(post, _ALIAS_VIDEO_VIEWS)),
            "tiempo_medio_vis_s": _a_int_opt(_primero(post, _ALIAS_TIEMPO_VIS)),
            "clics_enlace": _a_int_opt(_primero(post, _ALIAS_CLICS)),
            "formato": _formato_opt(_primero(post, _ALIAS_FORMATO)),
        }

    def _pieza_desde_post(
        self, post: dict, plat: Plataforma, cuenta_id: str | None = None
    ) -> Pieza | None:
        """Mapea un post de Metricool a `Pieza` (parseo defensivo; ver SUPUESTOS).

        `cuenta_id` (id_metricas de la marca) se sella en la pieza para poder
        ESTRATIFICAR top/peores por marca y normalizar el rendimiento por grupo
        (ver `estadisticas.top_y_peores`). Descarta el post si no tiene visualizaciones
        o si no se puede determinar su fecha (sin fecha real no se puede ubicar en el
        rango; NO se fabrica una fecha de hoy).
        """
        vis = _entero(_primero(post, _ALIAS_VIS, 0))
        if not vis:
            return None  # sin visualizaciones no es una "mejor pieza" útil
        fecha = _fecha(_primero(post, _ALIAS_FECHA))
        if fecha is None:
            return None  # sin fecha real no se ubica en el rango (no se fabrica)
        inter = _entero(_primero(post, _ALIAS_INT, 0))
        gran = self._granulares(post)
        inter = _interacciones_efectivas(inter, gran)
        return Pieza(
            id=str(_primero(post, _ALIAS_ID, "")),
            plataforma=plat,
            titulo=(str(_primero(post, _ALIAS_TEXTO, "(sin texto)")))[:120],
            texto=str(_primero(post, _ALIAS_TEXTO, "")),
            publicado=fecha,
            visualizaciones=vis,
            interacciones=inter,
            engagement_pct=engagement_pct(inter, vis),
            url=str(u) if (u := _primero(post, _ALIAS_URL)) is not None else None,
            cuenta=cuenta_id,
            alcance=_a_int_opt(_primero(post, _ALIAS_ALCANCE)),
            impresiones=_a_int_opt(_primero(post, _ALIAS_IMPRESIONES)),
            **gran,
        )

    def _resolver_post_scheduler(
        self, cuenta_id: str, id_post: str
    ) -> tuple[str | None, str | None]:
        """Resuelve un id del SCHEDULER -> `(id_nativo, url_publica)` del post publicado.

        `GET /v2/scheduler/posts/{id}` devuelve `providers[].id`/`publicUrl` con el id nativo
        de la red (FB) o la URL pública (`/p/{shortcode}/` en IG), que SÍ casan con la
        analítica. Best-effort: si la API falla o el post aún no tiene provider publicado,
        devuelve `(None, None)` y el llamante cae al match directo por id.
        """
        try:
            datos = get_json(
                self._cli,
                f"{BASE}{ENDPOINT_SCHEDULER_POST}/{id_post}",
                params=self._params_base(cuenta_id),
                headers=self._headers(cuenta_id),
            )
        except Exception as e:  # noqa: BLE001 -- el puente es best-effort; degrada al match directo
            log.warning("metricool: scheduler %s/%s no resolvió: %s", cuenta_id, id_post, e)
            return None, None
        cuerpo = datos.get("data") if isinstance(datos.get("data"), dict) else datos
        for prov in (cuerpo.get("providers") or []) if isinstance(cuerpo, dict) else []:
            if not isinstance(prov, dict):
                continue
            nativo = prov.get("id")
            url = prov.get("publicUrl") or prov.get("url")
            if nativo or url:
                return (str(nativo) if nativo else None), (str(url) if url else None)
        return None, None

    def _metrica_de_record(
        self, post: dict, plat: Plataforma, id_post: str, *, es_reel: bool
    ) -> MetricaPieza:
        """Construye `MetricaPieza` (encontrado=True) desde un post/reel de analítica.

        Conserva el `id_post` con el que la Consola sigue la pieza (el del scheduler), no el
        id nativo: así la cache/histórico siguen indexados por la clave que guarda la Consola.
        Reúsa el mismo parseo de vis/interacciones/granulares que las piezas del periodo.
        """
        if es_reel:
            vis = _entero(_primero(post, _ALIAS_REEL_VIS, 0))
            gran = {
                "likes": _a_int_opt(_primero(post, _ALIAS_REEL_LIKES)),
                "comentarios": _a_int_opt(_primero(post, _ALIAS_COMENTARIOS)),
                "compartidos": _a_int_opt(_primero(post, _ALIAS_COMPARTIDOS)),
                "guardados": _a_int_opt(_primero(post, _ALIAS_GUARDADOS)),
                "video_views": _a_int_opt(_primero(post, _ALIAS_REEL_VIS)),
                "tiempo_medio_vis_s": _a_int_opt(_primero(post, _ALIAS_REEL_TIEMPO)),
                "clics_enlace": None,
                "formato": "reel",
            }
            inter = _interacciones_reel(post, gran)
            url = _primero(post, _ALIAS_REEL_URL)
        else:
            vis = _entero(_primero(post, _ALIAS_VIS, 0))
            gran = self._granulares(post)
            inter = _interacciones_efectivas(_entero(_primero(post, _ALIAS_INT, 0)), gran)
            url = _primero(post, _ALIAS_URL)
        return MetricaPieza(
            id_post=str(id_post),
            plataforma=plat,
            encontrado=True,
            visualizaciones=vis,
            interacciones=inter,
            engagement_pct=engagement_pct(inter, vis),
            url=url,
            publicado=_fecha(_primero(post, _ALIAS_FECHA)),
            fuente=self.nombre,
            **gran,
            # Seguidores atribuidos al post: casi seguro Metricool no lo da a
            # nivel post; None salvo que algún alias lo traiga.
            seguidores_netos_atribuidos=_a_int_opt(_primero(post, _ALIAS_SEG_POST)),
        )

    def metricas_de_post(
        self, cuenta_id: str, plat: Plataforma, id_post: str, *, dias: int = 90
    ) -> MetricaPieza | None:
        """Rendimiento de UN post concreto (por `id_post` de Metricool) o None si no aparece.

        El `id_post` que guarda la Consola es el id del SCHEDULER de Metricool, un espacio de
        ids DISTINTO al de la analítica (que indexa por id nativo de la red). Por eso se enlaza
        en dos pasos: (1) se buscan los posts —y los reels FB/IG, en su endpoint aparte— de la
        ventana de los últimos `dias`; (2) se casan contra el conjunto de OBJETIVOS de enlace:
        el id crudo (cubre ids ya nativos/Postproxy) y, resolviendo el id del scheduler vía
        `/v2/scheduler/posts/{id}`, el id nativo de FB (storyId) y el shortcode de IG. Degrada
        a None si la API falla o el post no aparece todavía (Metricool tarda en consolidar): el
        llamante marca `encontrado=False` en vez de inventar ceros.
        """
        if not id_post or plat not in _RED_METRICOOL:
            return None
        hasta = date.today()
        desde = hasta - timedelta(days=max(dias, 1))
        try:
            posts = self._fetch_posts(cuenta_id, plat, desde, hasta)
        except Exception as e:  # noqa: BLE001 -- degrada sin romper, como el resto
            log.warning("metricool: post %s/%s/%s fallo: %s", plat.value, cuenta_id, id_post, e)
            return None

        # Paso 1: match DIRECTO por id crudo (cubre ids ya nativos / Postproxy y evita el
        # golpe al scheduler cuando el id ya casa). Camino barato y el que prueban los tests.
        objetivos = {str(id_post)}
        encontrado = self._casar_post(posts, plat, objetivos, id_post, es_reel=False)
        if encontrado is not None:
            return encontrado

        # Paso 2: PUENTE scheduler -> nativo. Amplía los objetivos con el id nativo/URL del
        # post publicado y reintenta el match (posts + reels FB/IG, su endpoint aparte).
        nativo, url_publica = self._resolver_post_scheduler(cuenta_id, id_post)
        if nativo or url_publica:
            objetivos = _objetivos_de_enlace(id_post, nativo, url_publica, plat)
            encontrado = self._casar_post(posts, plat, objetivos, id_post, es_reel=False)
            if encontrado is not None:
                return encontrado
        if plat in _RED_CON_REELS:
            try:
                reels = self._fetch_reels(cuenta_id, plat, desde, hasta)
            except Exception as e:  # noqa: BLE001 -- sin reels: degrada al None final
                log.warning("metricool: reels %s/%s/%s fallo: %s", plat.value, cuenta_id, id_post, e)
                reels = []
            encontrado = self._casar_post(reels, plat, objetivos, id_post, es_reel=True)
            if encontrado is not None:
                return encontrado
        return None

    def _casar_post(
        self, registros: list[dict], plat: Plataforma, objetivos: set[str],
        id_post: str, *, es_reel: bool,
    ) -> MetricaPieza | None:
        """Devuelve la `MetricaPieza` del primer registro cuyas claves cruzan con `objetivos`."""
        for post in registros:
            if not isinstance(post, dict):
                continue
            if _claves_enlace_post(post, plat) & objetivos:
                return self._metrica_de_record(post, plat, id_post, es_reel=es_reel)
        return None

    def serie_diaria(self, cuenta_id: str, rango: str) -> list[PuntoSerie]:
        """Serie diaria del periodo: vistas + interacciones de las piezas, por día de publicación.

        Suma los POSTS de cada red (vía `_piezas_plataforma`) agrupados por su fecha de
        publicación. Antes usaba `/v2/analytics/timelines` con métricas de vis/int por red,
        que solo respondía TikTok (vocabulario distinto por red); la serie salía solo-TikTok,
        incoherente con el `resumen` (basado en posts). Ahora ambos comparten la MISMA fuente.

        Semántica: cada punto es la suma de vistas/interacciones de las piezas PUBLICADAS ese
        día (no impresiones acumuladas ese día) — consistente con las piezas que ve el usuario.
        Una red no conectada o cuya API de posts falla se omite (la serie se arma con el resto).
        """
        marca = self._marca(cuenta_id)
        desde, hasta, _ = resolver_rango(rango)
        conectadas = self._redes_conectadas(cuenta_id)
        vis_por_dia: dict[date, int] = {}
        int_por_dia: dict[date, int] = {}
        for plat in self._plataformas(marca):
            if conectadas is not None and plat not in conectadas:
                continue
            for p in self._piezas_plataforma(cuenta_id, plat, desde, hasta, 100_000):
                vis_por_dia[p.publicado] = vis_por_dia.get(p.publicado, 0) + p.visualizaciones
                int_por_dia[p.publicado] = int_por_dia.get(p.publicado, 0) + p.interacciones
        fechas = sorted(set(vis_por_dia) | set(int_por_dia))
        return [
            PuntoSerie(
                fecha=f,
                visualizaciones=vis_por_dia.get(f, 0),
                interacciones=int_por_dia.get(f, 0),
            )
            for f in fechas
        ]
