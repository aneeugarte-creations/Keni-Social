"""Fuente `metricool`: consume la **API REST de Metricool** como una `FuenteMetricas` más.

B (app Métricas) es **consumidor** de Metricool, no motor de ingesta propia
(ADR 0005 §B). En vez de construir un adaptador contra cada API oficial (Meta/
TikTok/X/YouTube), leemos lo que Metricool YA consolidó vía su API REST
(AMX está en plan **Advanced**, que habilita el API token). Esta clase implementa
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
- ``GET /v2/analytics/posts/{network}`` → publicaciones del periodo por red, para
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
from datetime import date, datetime, timedelta

import httpx

from ..schema import (
    PLATAFORMAS_CON_ALCANCE,
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

# Mapeo Plataforma (keni) -> network (Metricool). Metricool usa "twitter" para X.
_RED_METRICOOL: dict[Plataforma, str] = {
    Plataforma.facebook: "facebook",
    Plataforma.instagram: "instagram",
    Plataforma.x: "twitter",
    Plataforma.tiktok: "tiktok",
    Plataforma.youtube: "youtube",
}

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
# Métrica de SEGUIDORES por red (tamaño de comunidad). SUPUESTO sin confirmar:
# los nombres salen del enum de `/v2/analytics/timelines`; el swagger no fija de
# forma inequívoca cuál es "la" de followers por red. Se usa para calcular el NETO
# del periodo (último punto - primer punto de la serie), no como agregado SUM.
# YouTube llama "subscribers" a sus seguidores. Si la métrica no está disponible
# para una red, simplemente no se incluye y `seguidores_netos` queda en 0.
_METRICA_SEG = "seg"
_METRICAS_RED: dict[Plataforma, dict[str, str]] = {
    Plataforma.facebook: {
        _METRICA_VIS: "impressions",
        _METRICA_INT: "interactions",
        _METRICA_ALC: "impressionsunique",
        _METRICA_SEG: "followers",
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
        _METRICA_SEG: "followers",
    },
    Plataforma.youtube: {
        _METRICA_VIS: "views",
        _METRICA_INT: "interactions",
        _METRICA_SEG: "subscribers",
    },
}

# Alias de campos al parsear un post de `/v2/analytics/posts/{network}` (forma no
# fijada por el swagger; ver SUPUESTOS). Se prueba cada alias en orden.
_ALIAS_ID = ("id", "postId", "providerId")
_ALIAS_FECHA = ("publishedAt", "publicationDate", "dateTime", "date", "createdAt")
_ALIAS_VIS = ("impressions", "views", "reach", "visualizations")
_ALIAS_INT = ("interactions", "engagement", "engagements")
_ALIAS_TEXTO = ("text", "title", "message", "caption", "content")
_ALIAS_URL = ("url", "permalink", "permalinkUrl", "link")
# Alias granulares por pieza (forma del post NO fijada por el swagger; ver
# SUPUESTOS del módulo). Nombres plausibles de Metricool/redes; si ninguno viene,
# el campo queda en None (degradación honesta), nunca 0 inventado.
_ALIAS_LIKES = ("likes", "favorites", "reactions", "likeCount")
_ALIAS_COMENTARIOS = ("comments", "replies", "commentsCount")
_ALIAS_COMPARTIDOS = ("shares", "retweets", "reposts", "sharesCount")
_ALIAS_GUARDADOS = ("saves", "saved", "bookmarks", "savedCount")
# OJO: sin el alias genérico "views" a propósito. En posts de imagen/carrusel Metricool
# usa "views"/"impressions" para las visualizaciones GENERALES; si lo tomáramos aquí,
# `video_views` duplicaría `visualizaciones` en piezas que no son vídeo. Solo campos
# específicos de vídeo -> None en imágenes (honesto), valor real en reels/vídeos.
_ALIAS_VIDEO_VIEWS = ("videoViews", "plays", "videoViewCount", "reelPlays", "videoPlayCount")
_ALIAS_TIEMPO_VIS = ("avgWatchTime", "averageWatchTime", "avgTimeWatched", "averageViewDuration")
_ALIAS_CLICS = ("linkClicks", "clicks", "urlClicks", "websiteClicks", "linkClicksCount")
_ALIAS_FORMATO = ("type", "mediaType", "postType", "contentType", "format")
# Seguidores ganados/atribuidos a UN post: casi seguro Metricool no lo expone a
# nivel post; se captura si algún alias lo trae, si no queda None.
_ALIAS_SEG_POST = ("followsFromPost", "newFollowers", "followersGained")

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


def _fecha(v) -> date | None:
    """Fecha de publicación del post -> `date`, o None si no se puede determinar.

    Metricool devuelve `publishedAt` como OBJETO `{'dateTime': 'AAAA-MM-DDTHH:MM:SS',
    'timezone': '...'}`, NO como string plano; antes esto no se parseaba y CADA pieza
    quedaba sellada con la fecha de hoy (colando posts viejos/sin-fecha como "en rango").
    Aquí se extrae el `dateTime` del objeto, y se acepta también string ISO (con o sin
    hora) o epoch (segundos/milisegundos). Devuelve None si no hay fecha reconocible: el
    llamante NO debe fabricar una fecha (ver `_pieza_desde_post`)."""
    if isinstance(v, dict):
        v = v.get("dateTime") or v.get("date") or v.get("value") or v.get("iso")
    if isinstance(v, bool):  # bool es subclase de int: no es una fecha
        return None
    if isinstance(v, (int, float)):
        try:
            ts = float(v)
            if ts > 1e11:  # epoch en milisegundos
                ts /= 1000.0
            return datetime.fromtimestamp(ts).date()
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


class FuenteMetricol:
    """Implementa `FuenteMetricas` leyendo de la API REST de Metricool.

    Credenciales POR MARCA: en AMX cada marca es una cuenta Metricool distinta,
    así que cada una trae su PROPIO ``user_token`` (cabecera ``X-Mc-Auth``),
    ``user_id`` y ``blog_id`` (query params). NO hay identidad global.

    Parámetros:
      - ``marcas``: mapeo ``id_marca_keni -> {"user_token": ..., "user_id": ...,
        "blog_id": ..., "nombre": ..., "plataformas": [Plataforma...]}``. Solo
        deben pasarse marcas con credenciales completas (``config.py`` ya filtra
        y resuelve los defaults antes de construir la fuente); las demás se omiten
        aguas arriba.
      - ``cliente``: ``httpx.Client`` inyectable (tests con respx).
    """

    nombre = NOMBRE

    def __init__(
        self,
        marcas: dict[str, dict],
        cliente: httpx.Client | None = None,
    ):
        self._marcas = marcas
        self._cli = cliente or cliente_http()

    # --- identidad / HTTP (resuelta POR MARCA) ------------------------------
    def _headers(self, cuenta_id: str) -> dict:
        return {"X-Mc-Auth": str(self._marca(cuenta_id).get("user_token", ""))}

    def _params_base(self, cuenta_id: str) -> dict:
        marca = self._marca(cuenta_id)
        return {
            "userId": str(marca.get("user_id", "")),
            "blogId": str(marca.get("blog_id", "")),
        }

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
        marca = self._marca(cuenta_id)
        desde, hasta, _ = resolver_rango(rango)
        plats = self._plataformas(marca)

        por_plataforma: list[MetricaPlataforma] = []
        cobertura = Cobertura()
        for plat in plats:
            m = self._metrica_plataforma(cuenta_id, plat, desde, hasta)
            if m is None:
                cobertura.omitidas.append(plat)
                cobertura.motivo[plat.value] = MotivoOmision.error_api
                continue
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
                    "from": desde.isoformat() + "T00:00:00",
                    "to": hasta.isoformat() + "T23:59:59",
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
        try:
            datos = get_json(
                self._cli,
                f"{BASE}/v2/analytics/timelines",
                params={
                    **self._params_base(cuenta_id),
                    "network": _RED_METRICOOL[plat],
                    "metric": metrica,
                    "from": desde.isoformat() + "T00:00:00",
                    "to": hasta.isoformat() + "T23:59:59",
                },
                headers=self._headers(cuenta_id),
            )
        except Exception as e:  # noqa: BLE001 — degrada a [], como el resto
            log.warning("metricool: serie seguidores %s/%s fallo: %s", plat.value, cuenta_id, e)
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

    def _metrica_plataforma(
        self, cuenta_id: str, plat: Plataforma, desde: date, hasta: date
    ) -> MetricaPlataforma | None:
        """Métricas de UNA plataforma (None si la API falla → cobertura la omite)."""
        try:
            metricas = _METRICAS_RED[plat]
            vis = self._agregado(cuenta_id, plat, metricas[_METRICA_VIS], desde, hasta)
            inter = self._agregado(cuenta_id, plat, metricas[_METRICA_INT], desde, hasta)
            alcance = None
            if plat in PLATAFORMAS_CON_ALCANCE and _METRICA_ALC in metricas:
                alcance = self._agregado(cuenta_id, plat, metricas[_METRICA_ALC], desde, hasta)
            return MetricaPlataforma(
                plataforma=plat,
                visualizaciones=vis,
                alcance=alcance,
                interacciones=inter,
                engagement_pct=engagement_pct(inter, vis),
            )
        except Exception as e:  # noqa: BLE001 — degrada sin romper (como AdaptadorBase)
            log.warning("metricool: métricas %s/%s fallaron: %s", plat.value, cuenta_id, e)
            return None

    def _agregado(
        self, cuenta_id: str, plat: Plataforma, metrica: str, desde: date, hasta: date
    ) -> int:
        """Valor agregado del periodo para (red, métrica) vía /v2/analytics/timelines.

        Aislado a propósito (encapsula la llamada HTTP): si la forma exacta del
        endpoint difiere, se corrige SOLO aquí. Suma los `values` de la serie y, si
        Metricool trae un `aggregate`, prefiere ese total.
        """
        datos = get_json(
            self._cli,
            f"{BASE}/v2/analytics/timelines",
            params={
                **self._params_base(cuenta_id),
                "network": _RED_METRICOOL[plat],
                "metric": metrica,
                "from": desde.isoformat() + "T00:00:00",
                "to": hasta.isoformat() + "T23:59:59",
            },
            headers=self._headers(cuenta_id),
        )
        series = datos.get("data") or []
        total = 0.0
        for serie in series:
            agg = serie.get("aggregate")
            if isinstance(agg, dict) and agg.get("value") is not None:
                total += float(agg["value"])
            else:
                total += sum(float(v.get("value", 0) or 0) for v in serie.get("values", []))
        return int(total)

    def mejores_piezas(self, cuenta_id: str, rango: str, n: int) -> list[Pieza]:
        n = max(n, 0)
        if n == 0:
            return []
        marca = self._marca(cuenta_id)
        desde, hasta, _ = resolver_rango(rango)
        piezas: list[Pieza] = []
        for plat in self._plataformas(marca):
            piezas.extend(self._piezas_plataforma(cuenta_id, plat, desde, hasta, n))
        piezas.sort(key=lambda p: p.engagement_pct, reverse=True)
        return piezas[:n]

    def _piezas_plataforma(
        self, cuenta_id: str, plat: Plataforma, desde: date, hasta: date, n: int
    ) -> list[Pieza]:
        """Posts de una plataforma (degrada a [] si la API falla)."""
        try:
            datos = get_json(
                self._cli,
                f"{BASE}/v2/analytics/posts/{_RED_METRICOOL[plat]}",
                params={
                    **self._params_base(cuenta_id),
                    "from": desde.isoformat() + "T00:00:00",
                    "to": hasta.isoformat() + "T23:59:59",
                },
                headers=self._headers(cuenta_id),
            )
        except Exception as e:  # noqa: BLE001
            log.warning("metricool: piezas %s/%s fallaron: %s", plat.value, cuenta_id, e)
            return []
        piezas: list[Pieza] = []
        for post in datos.get("data") or []:
            if not isinstance(post, dict):
                continue
            pieza = self._pieza_desde_post(post, plat, cuenta_id)
            # Filtro DEFENSIVO por rango: aunque se envíen `from`/`to` a la API, se
            # exige que la fecha REAL de la pieza caiga en [desde, hasta] (Metricool ha
            # devuelto posts fuera de ventana; sin esto se colaban en top/peores/stats).
            if pieza is not None and desde <= pieza.publicado <= hasta:
                piezas.append(pieza)
        return piezas

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
            publicado=fecha,
            visualizaciones=vis,
            interacciones=inter,
            engagement_pct=engagement_pct(inter, vis),
            url=_primero(post, _ALIAS_URL),
            cuenta=cuenta_id,
            **gran,
        )

    def metricas_de_post(
        self, cuenta_id: str, plat: Plataforma, id_post: str, *, dias: int = 90
    ) -> MetricaPieza | None:
        """Rendimiento de UN post concreto (por `id_post` de Metricool) o None si no aparece.

        Busca el post en `/v2/analytics/posts/{network}` dentro de una ventana de los
        ultimos `dias` (un post programado desde la Consola es reciente) y casa por id
        contra cualquiera de los alias de id (`_ALIAS_ID`). Degrada a None si la API
        falla o el id no aparece todavia (Metricool tarda en consolidar): el llamante
        marca `encontrado=False` en vez de inventar ceros (misma honestidad que el resto).
        """
        if not id_post or plat not in _RED_METRICOOL:
            return None
        hasta = date.today()
        desde = hasta - timedelta(days=max(dias, 1))
        try:
            datos = get_json(
                self._cli,
                f"{BASE}/v2/analytics/posts/{_RED_METRICOOL[plat]}",
                params={
                    **self._params_base(cuenta_id),
                    "from": desde.isoformat() + "T00:00:00",
                    "to": hasta.isoformat() + "T23:59:59",
                },
                headers=self._headers(cuenta_id),
            )
        except Exception as e:  # noqa: BLE001 -- degrada sin romper, como el resto
            log.warning("metricool: post %s/%s/%s fallo: %s", plat.value, cuenta_id, id_post, e)
            return None
        objetivo = str(id_post)
        for post in datos.get("data") or []:
            if not isinstance(post, dict):
                continue
            ids = {str(_primero(post, (alias,), "")) for alias in _ALIAS_ID}
            if objetivo not in ids:
                continue
            vis = _entero(_primero(post, _ALIAS_VIS, 0))
            inter = _entero(_primero(post, _ALIAS_INT, 0))
            gran = self._granulares(post)
            inter = _interacciones_efectivas(inter, gran)
            return MetricaPieza(
                id_post=objetivo,
                plataforma=plat,
                encontrado=True,
                visualizaciones=vis,
                interacciones=inter,
                engagement_pct=engagement_pct(inter, vis),
                url=_primero(post, _ALIAS_URL),
                publicado=_fecha(_primero(post, _ALIAS_FECHA)),
                fuente=self.nombre,
                **gran,
                # Seguidores atribuidos al post: casi seguro Metricool no lo da a
                # nivel post; None salvo que algún alias lo traiga.
                seguidores_netos_atribuidos=_a_int_opt(_primero(post, _ALIAS_SEG_POST)),
            )
        return None

    def serie_diaria(self, cuenta_id: str, rango: str) -> list[PuntoSerie]:
        """Serie diaria del periodo (visualizaciones + interacciones) sumada entre plataformas.

        Reutiliza /v2/analytics/timelines (la misma llamada del agregado) pero CONSERVA
        los valores por dia en vez de sumarlos al total. Degrada por plataforma: si una
        falla, se omite y la serie se arma con el resto (honestidad, como `resumen`).
        """
        marca = self._marca(cuenta_id)
        desde, hasta, _ = resolver_rango(rango)
        vis_por_dia: dict[date, int] = {}
        int_por_dia: dict[date, int] = {}
        for plat in self._plataformas(marca):
            metricas = _METRICAS_RED[plat]
            self._acumular_serie(cuenta_id, plat, metricas[_METRICA_VIS], desde, hasta, vis_por_dia)
            self._acumular_serie(cuenta_id, plat, metricas[_METRICA_INT], desde, hasta, int_por_dia)
        fechas = sorted(set(vis_por_dia) | set(int_por_dia))
        return [
            PuntoSerie(
                fecha=f,
                visualizaciones=vis_por_dia.get(f, 0),
                interacciones=int_por_dia.get(f, 0),
            )
            for f in fechas
        ]

    def _acumular_serie(
        self,
        cuenta_id: str,
        plat: Plataforma,
        metrica: str,
        desde: date,
        hasta: date,
        acc: dict[date, int],
    ) -> None:
        """Suma en `acc` (fecha->valor) los puntos diarios de (red, metrica). No-op si la API falla."""
        try:
            datos = get_json(
                self._cli,
                f"{BASE}/v2/analytics/timelines",
                params={
                    **self._params_base(cuenta_id),
                    "network": _RED_METRICOOL[plat],
                    "metric": metrica,
                    "from": desde.isoformat() + "T00:00:00",
                    "to": hasta.isoformat() + "T23:59:59",
                },
                headers=self._headers(cuenta_id),
            )
        except Exception as e:  # noqa: BLE001 — degrada sin romper, como _metrica_plataforma
            log.warning("metricool: serie %s/%s %s fallo: %s", plat.value, metrica, cuenta_id, e)
            return
        for serie in datos.get("data") or []:
            for punto in serie.get("values", []):
                crudo = punto.get("dateTime") or punto.get("date")
                if not crudo:
                    continue
                try:
                    f = date.fromisoformat(str(crudo)[:10])
                except ValueError:
                    continue
                acc[f] = acc.get(f, 0) + _entero(punto.get("value", 0))
