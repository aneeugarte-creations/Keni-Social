"""Fachada estable de keni-metricas para consumidores en proceso (la Consola).

`docs/arquitectura.md` declara la frontera "MCP / stdio", pero la Consola corre en
el mismo proceso y necesita los datos de metricas sin levantar el servidor MCP.
Este modulo es el CONTRATO ESTABLE que la Consola consume: un refactor interno de
`config`/`reporte`/`fuentes` no debe romper a la Consola mientras esta fachada
mantenga su firma.

REGLA DE ORO — la sección «Lectura de métricas» es de SOLO LECTURA: nunca escribe a
disco ni muta el config. La sección «Gestión de configuración» es la unica que
toca el config.toml (cambiar la fuente activa y el alcance de marcas); es frontera
de gestion, no de datos. La escritura de CREDENCIALES (tokens de redes, claves de
imagen) NO vive aqui: la gestiona `keni_metricas.asistente` directamente desde
`api/conexiones.py`.

Esta fachada evita que la Consola importe internals profundos
(`config.construir_fuente`, `config.FuenteScoped`, `reporte.construir_reporte`,
`schema.RANGOS_DIAS`, ...).
"""

from __future__ import annotations

import dataclasses
import json
import logging
import statistics
import threading
from pathlib import Path

from . import analisis_diario as _analisis
from . import asistente
from . import config as _config
from . import estadisticas as _estadisticas
from . import reporte as _reporte
from .config import FUENTES_VALIDAS, ConfigInvalida
from .fuentes.base import CuentaNoEncontrada
from .schema import (
    RANGOS_DIAS,
    RANGOS_PRECALENTAR,
    RANGOS_PRESET_UI,
    AnaliticaPiezas,
    CeldaCrosstab,
    CeldaDesglose,
    CorrelacionSeguidores,
    Crosstab,
    DesgloseInteracciones,
    ItemCorrelacion,
    MetricaPieza,
    Periodo,
    Plataforma,
    PostEstrella,
    PuntoSeguidores,
    PuntoSerie,
    SerieDiaria,
    SerieSeguidores,
    etiqueta_rango,
    resolver_rango,
)

# --------------------------------------------------------------------------- #
# Constantes re-exportadas (única fuente de verdad para la Consola)            #
# --------------------------------------------------------------------------- #

# Rangos validos para las metricas generales (rodantes: terminan hoy). La Consola
# no debe importar el schema: este es el contrato.
RANGOS_VALIDOS: tuple[str, ...] = tuple(RANGOS_DIAS.keys())

# Fuentes validas ("muestra" | "real"). Re-export para la pantalla de configuracion.
FUENTES_DISPONIBLES: tuple[str, ...] = tuple(sorted(FUENTES_VALIDAS))

# --------------------------------------------------------------------------- #
# Formato de pieza — contrato CANÓNICO (única fuente de verdad del backend)    #
# --------------------------------------------------------------------------- #
#
# El formato crudo de una pieza varía por red/fuente (Metricool antepone `feed_` en
# Meta, YouTube llama `short` al vertical, X distingue `status`…). El dashboard filtra
# por un id CANÓNICO estable; este es el mapa que la Consola (`api/metricas/_comun`)
# reusa para no duplicar la verdad. Un crudo desconocido cae a su propio bucket (su
# string en minúsculas), así el filtro nunca rompe.

# Ids canónicos que el dashboard puede filtrar.
FORMATOS_VALIDOS: frozenset[str] = frozenset(
    {"reel", "carrusel", "foto", "video", "enlace", "texto"}
)

# Crudo (minúsculas) -> id canónico. Lo no listado conserva su propio string.
_FORMATO_CANONICO_RAW: dict[str, str] = {
    "reel": "reel", "feed_reel": "reel", "reels": "reel",
    "carrusel": "carrusel", "carousel": "carrusel",
    "feed_carousel_album": "carrusel", "album": "carrusel",
    "foto": "foto", "photo": "foto", "feed_image": "foto",
    "image": "foto", "imagen": "foto",
    "video": "video", "feed_video": "video", "short": "video", "shorts": "video",
    "link": "enlace", "enlace": "enlace",
    "texto": "texto", "text": "texto", "status": "texto",
}


def formato_canonico(raw: str) -> str:
    """Normaliza el formato crudo de una pieza a su id canónico (minúsculas).

    Un crudo desconocido se devuelve tal cual (en minúsculas): su propio bucket, sin
    romper nunca. Es la fuente ÚNICA de verdad del canónico de formato del backend.
    """
    s = (raw or "").strip().lower()
    return _FORMATO_CANONICO_RAW.get(s, s)


def _filtrar_formato(piezas: list, formato: tuple[str, ...]) -> list:
    """Filtra las piezas cuyo formato CANÓNICO está entre `formato`. Vacío = todas."""
    fmts = set(formato)
    if not fmts:
        return piezas
    return [p for p in piezas if formato_canonico(p.formato or "") in fmts]

# Excepciones de dominio que la Consola captura (re-export para no importar internals).
__all__ = [
    "RANGOS_VALIDOS",
    "RANGOS_PRESET_UI",
    "RANGOS_PRECALENTAR",
    "FUENTES_DISPONIBLES",
    "FORMATOS_VALIDOS",
    "formato_canonico",
    "ConfigInvalida",
    "CuentaNoEncontrada",
    "nombre_fuente",
    "cuentas_disponibles",
    "construir_reporte",
    "reporte_csv",
    "reporte_markdown",
    "reporte_json",
    "construir_analisis_diario",
    "analisis_diario_markdown",
    "construir_analitica_piezas",
    "construir_listado_piezas",
    "construir_tendencia_diaria",
    "construir_ads_desglose",
    "construir_flujo_audiencia",
    "construir_serie_seguidores",
    "construir_serie_alcance",
    "construir_desglose_interacciones",
    "construir_crosstab",
    "construir_correlacion_seguidores",
    "construir_metricas_pieza",
    "mejor_hora",
    "etiqueta_rango",
    "instantanea_config",
    "guardar_fuente_y_alcance",
]


# --------------------------------------------------------------------------- #
# Lectura de métricas — SOLO LECTURA                                          #
# --------------------------------------------------------------------------- #


# Cache de la fuente BASE (sin acotar a marca) y su `httpx.Client` subyacente. La
# fuente Metricool mantiene UN solo `httpx.Client` durante su vida (keep-alive + pool de
# conexiones), así que reusarla entre llamadas por-pieza evita abrir docenas de
# conexiones nuevas y re-construir la fuente en cada tarjeta del tablero (N+1).
#
# Invalidación: la cache se keyea con la MISMA huella que `cargar_config`
# (`_config._clave_cache_config()` = ruta + mtime del fichero + env relevantes). Un token
# nuevo en disco cambia el mtime -> la clave cambia -> se reconstruye la fuente (y su
# cliente) sin reiniciar el proceso. El acotado por marca (`FuenteScoped`) es un wrapper
# barato sobre la base: NO crea cliente ni relee config, así que no se cachea por marca.
#
# Thread-safety: un lock protege el llenado para que dos hilos no construyan dos fuentes/
# clientes a la vez. La lectura del puntero es atómica en CPython; el lock solo se toma
# en el camino de (re)construcción.
_fuente_lock = threading.Lock()
_cache_fuente: tuple[object, object] | None = None


def _fuente_base():
    """Fuente activa SIN acotar (cacheada), reconstruida solo si cambia la config.

    Reusa el mismo objeto fuente —y por tanto el mismo `httpx.Client` con keep-alive—
    mientras la huella de config (`_config._clave_cache_config`) no cambie.
    """
    global _cache_fuente
    clave = _config._clave_cache_config()
    cacheada = _cache_fuente
    if cacheada is not None and cacheada[0] == clave:
        return cacheada[1]
    with _fuente_lock:
        cacheada = _cache_fuente
        if cacheada is not None and cacheada[0] == clave:
            return cacheada[1]
        # `cargar_config` ya está memoizada con la misma clave: aquí solo reconstruimos
        # la fuente/cliente cuando la config cambió de verdad.
        fuente = _config.construir_fuente(_config.cargar_config())
        _cache_fuente = (clave, fuente)
        return fuente


def reset_cache_fuente() -> None:
    """Vacía la cache de la fuente base (la próxima llamada la reconstruye).

    Se invoca tras escribir el config (ver `asistente.escribir_config_atomico`) para que
    un cambio de credenciales/fuente se refleje de inmediato. No cierra el cliente viejo
    explícitamente: httpx lo libera al recolectarse; cerrarlo aquí arriesgaría usar un
    cliente cerrado si otro hilo lo tomó justo antes del reset.
    """
    global _cache_fuente
    with _fuente_lock:
        _cache_fuente = None


def _fuente(marca: str | None = None):
    """Fuente activa segun el config, opcionalmente acotada a UNA marca.

    El acotado por marca se delega en la propia fuente (FuenteScoped es interno):
    la Consola pasa el id en forma `id_metricas` (guion_bajo) y la fuente filtra. La
    fuente BASE se reusa entre llamadas (cache + cliente httpx con keep-alive); el
    wrapper `FuenteScoped` por marca es barato y no abre conexiones nuevas.
    """
    fuente = _fuente_base()
    if marca:
        return _config.FuenteScoped(fuente, [marca])
    return fuente


def nombre_fuente() -> str:
    """Nombre de la fuente de datos activa: "muestra" o "real".

    Para que la UI distinga datos ficticios de reales (riesgo operativo del piloto).
    """
    return _fuente_base().nombre


def cuentas_disponibles(marca: str | None = None) -> list[tuple[str, str]]:
    """Pares (id_metricas, nombre) de las cuentas en la fuente activa.

    Devuelve `[]` si la fuente no puede listar cuentas (config incompleto).
    """
    try:
        return [(c.id, c.nombre) for c in _fuente(marca).cuentas()]
    except Exception:  # noqa: BLE001 -- sin fuente valida: la UI usa lo que ya tiene
        return []


def construir_reporte(rango: str = "mes", marca: str | None = None) -> dict:
    """Reporte consolidado (total + por cuenta) como dict JSON-serializable.

    Incluye el campo `fuente` ("muestra"|"real"). Propaga `ValueError` (rango
    invalido) y `CuentaNoEncontrada` (marca fuera de alcance).
    """
    return _reporte.construir_reporte(_fuente(marca), rango)


def reporte_csv(rango: str = "mes", marca: str | None = None) -> str:
    """Reporte consolidado renderizado a CSV (misma serializacion que el CLI)."""
    return _reporte.render_csv(construir_reporte(rango, marca))


def reporte_markdown(rango: str = "mes", marca: str | None = None) -> str:
    """Reporte consolidado renderizado a Markdown (misma serializacion que el CLI)."""
    return _reporte.render_markdown(construir_reporte(rango, marca))


def reporte_json(rango: str = "mes", marca: str | None = None) -> str:
    """Reporte consolidado serializado a JSON indentado (crudo, sin reformatear)."""
    return json.dumps(construir_reporte(rango, marca), ensure_ascii=False, indent=2)


def _historico_lectura():
    """Histórico SOLO LECTURA si está activado, o None.

    El análisis diario usa el histórico para leer la variación REAL vs. el periodo
    anterior cuando hay datos previos. Es best-effort: si no se puede abrir (disco,
    permisos), seguimos sin él en vez de romper la lectura.
    """
    from .historico import Historico, historico_activo

    if not historico_activo():
        return None
    try:
        return Historico()
    except Exception:  # noqa: BLE001 -- el histórico es complementario, nunca obligatorio
        return None


def construir_analisis_diario(rango: str = "semana", marca: str | None = None) -> dict:
    """Análisis diario con narrativa como dict JSON-serializable.

    Lectura accionable del periodo: qué se movió, la(s) pieza(s) que lo explican y
    el siguiente paso. Incluye `fuente`/`es_muestra` para que la UI marque cuando
    los datos son de muestra. Propaga `ValueError` (rango inválido) y
    `CuentaNoEncontrada` (marca fuera de alcance).
    """
    return _analisis.construir_analisis(_fuente(marca), rango, marca, _historico_lectura())


def analisis_diario_markdown(rango: str = "semana", marca: str | None = None) -> str:
    """Análisis diario renderizado a Markdown (misma narrativa que el MCP/CLI)."""
    return _analisis.render_markdown(construir_analisis_diario(rango, marca))


# Tope de piezas por cuenta para las ESTADÍSTICAS del periodo. Debe cubrir TODAS las
# piezas del rango: si se trunca, la mediana/percentiles/distribución/`total` se calculan
# sobre un subconjunto SESGADO (mejores_piezas ordena por engagement antes de recortar) y
# no reflejan el periodo real (una marca puede tener cientos de posts/mes). El coste extra
# es nulo en API (la llamada a /posts ya devuelve todo el periodo; esto solo evita el
# recorte en memoria).
_TOPE_PIEZAS = 100_000


def construir_analitica_piezas(
    rango: str = "mes",
    marca: str | None = None,
    red: "str | tuple[str, ...] | list[str] | None" = None,
    formato: tuple[str, ...] = (),
) -> dict:
    """Analítica de piezas del periodo: estadísticas + top 10 + peores 10 + distribución.

    Coste 0 de API: reúsa las piezas que `mejores_piezas` ya descarga del periodo.
    `marca=None` agrega todas las cuentas en alcance (tab "Todas"); con marca, esa
    cuenta. `red` (id de plataforma, p.ej. "tiktok") acota a UNA red: el top/peores y las
    estadísticas se calculan SOLO sobre las piezas de esa red (None = todas las redes).
    `formato` (ids canónicos, p.ej. ("reel",)) acota a esos formatos por su canónico de
    pieza (vacío = todos). Propaga `ValueError` (rango inválido) y `CuentaNoEncontrada`
    (marca fuera de alcance). Devuelve un dict JSON-serializable (`AnaliticaPiezas`).
    """
    fuente = _fuente(marca)
    desde, hasta, _ = resolver_rango(rango)
    piezas = []
    for c in fuente.cuentas():
        piezas.extend(fuente.mejores_piezas(c.id, rango, _TOPE_PIEZAS))
    # Filtro por red(es): el top/peores y las estadísticas se calculan SOLO sobre las redes
    # elegidas (una o varias; `red` admite un id o una colección). Vacío = todas.
    reds = {red} if isinstance(red, str) else set(red or ())
    if reds:
        piezas = [p for p in piezas if p.plataforma.value in reds]
    # Filtro por formato(s) canónico(s): igual semántica que la red. Vacío = todos.
    piezas = _filtrar_formato(piezas, formato)

    top, peores = _estadisticas.top_y_peores(piezas, n=10)
    analitica = AnaliticaPiezas(
        cuenta=marca,
        rango=rango,
        periodo=Periodo(desde=desde, hasta=hasta),
        total=len(piezas),
        fuente=nombre_fuente(),
        engagement=_estadisticas.resumen_numerico(p.engagement_pct for p in piezas),
        visualizaciones=_estadisticas.resumen_numerico(p.visualizaciones for p in piezas),
        top=top,
        peores=peores,
        distribucion=_estadisticas.buckets_engagement(piezas),
    )
    return analitica.model_dump(mode="json")


def construir_listado_piezas(
    rango: str = "mes", marca: str | None = None, formato: tuple[str, ...] = ()
) -> list[dict]:
    """Lista los posts YA PUBLICADOS del periodo, para SELECCIONARLOS (no para rankear).

    A diferencia de `construir_analitica_piezas` (top/peores + distribucion), esto
    devuelve el listado COMPLETO de piezas de la(s) cuenta(s) en alcance, ordenado por
    fecha de pieza descendente (lo mas reciente primero), pensado para un selector:
    el apartado Comercial lo usa para elegir QUE pieza monitorizar por su `id` de
    Metricool, sin que nadie pegue enlaces a mano.

    Cada elemento trae lo necesario para identificar y previsualizar el post: `id`
    (id de Metricool), `red`, `titulo`, `publicado` (ISO), `visualizaciones`,
    `interacciones`, `engagement_pct` y `url`. Reusa `mejores_piezas` (coste de API ya
    pagado por el dashboard). `marca=None` agrega todas las cuentas en alcance.
    Propaga `ValueError` (rango invalido) y `CuentaNoEncontrada` (marca fuera de alcance).
    """
    fuente = _fuente(marca)
    piezas = []
    for c in fuente.cuentas():
        piezas.extend(fuente.mejores_piezas(c.id, rango, _TOPE_PIEZAS))
    # Filtro por formato(s) canónico(s) antes de ordenar/serializar (vacío = todos).
    piezas = _filtrar_formato(piezas, formato)
    # Orden estable: mas recientes primero; a igualdad de fecha, mayor engagement antes.
    piezas.sort(key=lambda p: (p.publicado.isoformat(), p.engagement_pct), reverse=True)
    return [
        {
            "id": p.id,
            "red": p.plataforma.value,
            "titulo": p.titulo,
            "texto": p.texto,
            "publicado": p.publicado.isoformat(),
            "visualizaciones": p.visualizaciones,
            "interacciones": p.interacciones,
            "engagement_pct": p.engagement_pct,
            "url": p.url,
            # alcance (usuarios únicos): None salvo Meta (FB/IG); ver schema.
            "alcance": p.alcance,
            # Métricas granulares (None cuando la fuente no las trae; ver schema).
            "likes": p.likes,
            "comentarios": p.comentarios,
            "compartidos": p.compartidos,
            "guardados": p.guardados,
            "video_views": p.video_views,
            "tiempo_medio_vis_s": p.tiempo_medio_vis_s,
            "clics_enlace": p.clics_enlace,
            "formato": p.formato,
            # cuenta (id_metricas) y rendimiento_relativo (vs la mediana del grupo):
            # None cuando la fuente no los aporta. Mismos campos que `Pieza`/`PiezaMetrica`.
            "cuenta": p.cuenta,
            "rendimiento_relativo": p.rendimiento_relativo,
        }
        for p in piezas
    ]


_log = logging.getLogger("keni_metricas")


def construir_ads(rango: str = "mes", marca: str | None = None) -> list[dict]:
    """Campañas de publicidad PAGADA del periodo (Meta/TikTok Ads): el INORGÁNICO.

    Dispatch por capacidad (mismo idioma que `construir_tendencia_diaria`): usa
    `fuente.campanias_ads` si la fuente activa la expone (Metricool, también a través de
    `FuenteScoped` por-marca). Si no (muestra/compuesta), degrada a [] — el inorgánico solo
    existe contra la API real. OJO: el `FuenteScoped` por-marca SÍ debe exponer el método
    (lo delega); sin eso, campañas y dashboard por-marca salían SIEMPRE vacíos.
    `marca=None` agrega todas las cuentas en alcance. Propaga `ValueError` (rango inválido)
    y `CuentaNoEncontrada` (marca fuera de alcance)."""
    fuente = _fuente(marca)
    ads_fn = getattr(fuente, "campanias_ads", None)
    if ads_fn is None:
        return []
    salida: list[dict] = []
    for c in fuente.cuentas():
        try:
            campanias = ads_fn(c.id, rango)
        except AttributeError:
            # La fuente envuelta no la implementa (FuenteScoped lo propaga): inorgánico vacío.
            return []
        except Exception:  # noqa: BLE001 -- una cuenta que falla no aborta el resto
            _log.exception("construir_ads: cuenta %s falló (rango=%s).", c.id, rango)
            continue
        for ad in campanias:
            d = ad.model_dump()
            d["cuenta"] = c.id
            salida.append(d)
    return salida


def construir_flujo_audiencia(rango: str = "mes", marca: str | None = None) -> dict:
    """Altas y bajas de seguidores del periodo por red (suma de las cuentas en alcance).

    Dispatch por capacidad (como `construir_ads`): usa `fuente.flujo_audiencia` si la fuente la
    expone (Metricool, también vía `FuenteScoped`); si no, degrada a `{"por_red": []}`. Agrega
    por red sobre las cuentas: `altas`/`bajas` suman donde la red las da (None si NINGUNA cuenta
    de esa red las separa — TikTok/IG), `neto` siempre suma. Propaga `ValueError` (rango
    inválido) y `CuentaNoEncontrada` (marca fuera de alcance).
    """
    fuente = _fuente(marca)
    fn = getattr(fuente, "flujo_audiencia", None)
    acc: dict[str, dict] = {}
    if fn is not None:
        for c in fuente.cuentas():
            try:
                filas = fn(c.id, rango)
            except AttributeError:
                # La fuente envuelta no la implementa (FuenteScoped lo propaga): flujo vacío.
                return {"por_red": []}
            except Exception:  # noqa: BLE001 -- una cuenta que falla no aborta el resto
                _log.exception("construir_flujo_audiencia: cuenta %s falló (rango=%s).", c.id, rango)
                continue
            for fila in filas:
                red = fila["red"]
                a = acc.setdefault(red, {"red": red, "altas": None, "bajas": None, "neto": 0})
                if fila.get("altas") is not None:
                    a["altas"] = (a["altas"] or 0) + fila["altas"]
                if fila.get("bajas") is not None:
                    a["bajas"] = (a["bajas"] or 0) + fila["bajas"]
                a["neto"] += fila.get("neto") or 0
    return {"por_red": [acc[r] for r in sorted(acc)]}


def construir_ads_desglose(
    rango: str = "mes", marca: str | None = None, provider_campaign_id: str = ""
) -> dict:
    """Drill-down de UNA campaña de Ads: sus adgroups y ads (Meta/TikTok Ads).

    Dispatch por capacidad (como `construir_ads`): usa `fuente.campanias_ads_desglose` si la
    fuente la expone (Metricool, también vía `FuenteScoped`). Si no, degrada a vacío. Sella el
    `cuenta` (id_metricas) en cada item. Propaga `ValueError` (rango inválido) y
    `CuentaNoEncontrada` (marca fuera de alcance).
    """
    fuente = _fuente(marca)
    fn = getattr(fuente, "campanias_ads_desglose", None)
    adgroups: list[dict] = []
    ads: list[dict] = []
    if fn is not None and provider_campaign_id:
        for c in fuente.cuentas():
            try:
                d = fn(c.id, provider_campaign_id, rango)
            except AttributeError:
                # La fuente envuelta no lo implementa (FuenteScoped lo propaga): desglose vacío.
                return {"adgroups": [], "ads": [], "provider_campaign_id": provider_campaign_id}
            except Exception:  # noqa: BLE001 -- una cuenta que falla no aborta el resto
                _log.exception(
                    "construir_ads_desglose: cuenta %s falló (rango=%s).", c.id, rango
                )
                continue
            for g in d.get("adgroups") or []:
                adgroups.append({**g, "cuenta": c.id})
            for a in d.get("ads") or []:
                ads.append({**a, "cuenta": c.id})
    return {"adgroups": adgroups, "ads": ads, "provider_campaign_id": provider_campaign_id}


def construir_tendencia_diaria(
    rango: str = "mes",
    marca: str | None = None,
    red: "str | tuple[str, ...] | list[str] | None" = None,
    formato: tuple[str, ...] = (),
) -> dict:
    """Serie diaria del periodo (visualizaciones + interacciones) sumada por cuenta.

    Dispatch por capacidad: usa `fuente.serie_diaria` si la fuente activa la expone
    (muestra/Metricool); si no (fuentes 'real' compuestas), degrada a serie vacía sin
    romper. Devuelve un dict JSON-serializable (`SerieDiaria`).

    `red` (id de plataforma) acota la serie a UNA red y `formato` (ids canónicos) a esos
    formatos. Como `serie_diaria` agrega las redes (no las desglosa), CON red o formato la
    serie se DERIVA de las piezas filtradas del periodo, sumando visualizaciones/
    interacciones por fecha de publicación (mismas piezas que ya descarga el dashboard,
    coste 0 de API). Sin red ni formato = todas (camino y semántica de siempre, vía
    `serie_diaria`).
    """
    fuente = _fuente(marca)
    desde, hasta, _ = resolver_rango(rango)
    vis: dict = {}
    inter: dict = {}
    reds = {red} if isinstance(red, str) else set(red or ())
    fmts = set(formato)
    if reds or fmts:
        for p in _piezas_periodo(fuente, rango):
            if reds and p.plataforma.value not in reds:
                continue
            if fmts and formato_canonico(p.formato or "") not in fmts:
                continue
            vis[p.publicado] = vis.get(p.publicado, 0) + (p.visualizaciones or 0)
            inter[p.publicado] = inter.get(p.publicado, 0) + (p.interacciones or 0)
    else:
        serie_fn = getattr(fuente, "serie_diaria", None)
        if serie_fn is not None:
            for c in fuente.cuentas():
                try:
                    puntos = serie_fn(c.id, rango)
                except AttributeError:
                    # La fuente envuelta no la implementa (FuenteScoped lo propaga): degrada.
                    puntos = []
                for p in puntos:
                    vis[p.fecha] = vis.get(p.fecha, 0) + p.visualizaciones
                    inter[p.fecha] = inter.get(p.fecha, 0) + p.interacciones

    fechas = sorted(set(vis) | set(inter))
    puntos = [
        PuntoSerie(fecha=f, visualizaciones=vis.get(f, 0), interacciones=inter.get(f, 0))
        for f in fechas
    ]
    serie = SerieDiaria(
        cuenta=marca,
        rango=rango,
        periodo=Periodo(desde=desde, hasta=hasta),
        fuente=nombre_fuente(),
        puntos=puntos,
    )
    return serie.model_dump(mode="json")


# --------------------------------------------------------------------------- #
# Análisis de estrategia digital — REUSAN serie de followers + piezas          #
# --------------------------------------------------------------------------- #
#
# Cuatro lecturas ricas de la estrategia digital, todas a COSTE 0 de API extra:
# reúsan la serie de followers que ya consulta `seguidores_netos` (vía la nueva
# `fuente.serie_seguidores`) y las piezas granulares que ya descarga el dashboard
# (`mejores_piezas`). Filosofía: degradación honesta — si un dato no está, None/0/
# vacío, nunca inventado.


def _piezas_periodo(fuente, rango: str) -> list:
    """Reúne las piezas del periodo de TODAS las cuentas en alcance de `fuente`.

    Mismo camino que `construir_analitica_piezas`/`construir_listado_piezas`: itera
    las cuentas y acumula `mejores_piezas` con un tope alto para cubrir el periodo.
    Coste 0 de API extra (las piezas ya las descarga el dashboard).
    """
    piezas = []
    for c in fuente.cuentas():
        piezas.extend(fuente.mejores_piezas(c.id, rango, _TOPE_PIEZAS))
    return piezas


def _serie_seguidores_cuentas(fuente, rango: str) -> dict[str, list[dict]]:
    """Serie de followers por cuenta: `{cuenta_id: [{"fecha", "por_red"}, ...]}`.

    Dispatch por capacidad: usa `fuente.serie_seguidores` si la fuente la expone
    (muestra/Metricool); si no (fuentes 'real' compuestas) o si la cuenta no trae
    serie, esa cuenta se omite. Devuelve `{}` cuando NINGUNA cuenta aporta serie
    (la fuente no soporta followers) — degradación honesta.
    """
    serie_fn = getattr(fuente, "serie_seguidores", None)
    if serie_fn is None:
        return {}
    out: dict[str, list[dict]] = {}
    for c in fuente.cuentas():
        try:
            puntos = serie_fn(c.id, rango)
        except AttributeError:
            # La fuente envuelta no la implementa (FuenteScoped lo propaga): degrada.
            return {}
        if puntos:
            out[c.id] = puntos
    return out


def _serie_seguidores_saneada(
    fuente, rango: str
) -> tuple[list[str], dict[tuple[str, str], dict[str, int]]]:
    """Serie de followers SANEADA por (cuenta, red): validez + carry-forward + backfill.

    Devuelve `(fechas, stock)` con `fechas` ordenadas y `stock[(cuenta, red)][fecha]` = el
    stock YA arrastrado de esa cuenta×red ese día. Fuente ÚNICA de saneamiento de followers:
    la consumen la serie agregada (`serie_seguidores_desde_fuente`) y la correlación
    (`correlacion_seguidores_desde_fuente`), que necesitan el stock saneado, no el crudo
    (los snapshots parciales daban deltas absurdos sobre la serie sin sanear).
    """
    series = _serie_seguidores_cuentas(fuente, rango)

    # Stock REPORTADO por (cuenta, red) y fecha (lo que trajo la fuente ese día, si lo trajo).
    reportado: dict[tuple[str, str], dict[str, int]] = {}
    for cuenta, puntos in series.items():
        for punto in puntos:
            fecha = punto["fecha"]
            for red, valor in (punto.get("por_red") or {}).items():
                reportado.setdefault((cuenta, red), {})[fecha] = int(valor)

    fechas = sorted({f for fv in reportado.values() for f in fv})

    # VALIDEZ de un punto: la serie de followers es un STOCK enorme y estable; un valor 0 o
    # ANÓMALAMENTE BAJO (< la mitad de la mediana de SU serie) es un día INCOMPLETO de la
    # fuente —típicamente HOY, aún sin consolidar—, no una pérdida real de seguidores.
    # El umbral es POR CUENTA×RED, no por red agregada: cuando a una cuenta grande le faltan
    # snapshots (p.ej. el TikTok de una marca deja de reportar 2 semanas) la suma de la red
    # baja un 30-40% —por encima de cualquier umbral agregado— y el total pintaba precipicios
    # falsos de millones; mirando cada cuenta por separado el hueco es inconfundible (ausente).
    umbral: dict[tuple[str, str], float] = {
        clave: (0.5 * statistics.median(list(fv.values())) if fv else 0.0)
        for clave, fv in reportado.items()
    }

    def _valido(clave: tuple[str, str], v: int) -> bool:
        return v > 0 and v >= umbral.get(clave, 0.0)

    # CARRY-FORWARD por cuenta×red: los followers PERSISTEN día a día; si una cuenta no
    # reporta (o reporta un valor inválido) se arrastra su último valor válido en vez de
    # hundir el total. BACKFILL del borde inicial: cada cuenta aporta su PRIMER valor válido
    # también en los días ANTERIORES a su primera aparición. Sin esto, conectar una cuenta a
    # mitad de ventana mete su stock entero de golpe el día del alta y la curva pinta un
    # escalón que parece crecimiento sin serlo; con el baseline constante el neto no cambia.
    primer_valido: dict[tuple[str, str], int] = {}
    claves_orden = sorted(reportado)
    for clave in claves_orden:
        for f in fechas:
            v = reportado[clave].get(f)
            if v is not None and _valido(clave, v):
                primer_valido[clave] = v
                break

    stock: dict[tuple[str, str], dict[str, int]] = {}
    ultimo: dict[tuple[str, str], int] = dict(primer_valido)  # baseline desde el primer día
    for f in fechas:
        for clave in claves_orden:
            v = reportado[clave].get(f)
            if v is not None and _valido(clave, v):
                ultimo[clave] = v
            if clave in ultimo:
                stock.setdefault(clave, {})[f] = ultimo[clave]
    return fechas, stock


def construir_serie_seguidores(rango: str = "mes", marca: str | None = None) -> dict:
    """Crecimiento de seguidores POR DÍA y por red (suma de las cuentas en alcance).

    REÚSA la serie de followers que ya consulta `seguidores_netos` (la misma de
    `/v2/analytics/timelines`), expuesta ahora como `fuente.serie_seguidores`. Por
    cada día: `total` = suma del stock de followers de cada red ese día; `neto` =
    último − primer total. Una red que no expone followers se OMITE (no 0 falso).
    Si la fuente no soporta followers, `puntos=[]` y `neto=0` (degradación honesta).
    Devuelve un dict JSON-serializable (`SerieSeguidores`).
    """
    return serie_seguidores_desde_fuente(_fuente(marca), rango, marca)


def serie_seguidores_desde_fuente(fuente, rango: str, marca: str | None = None) -> dict:
    """Worker de `construir_serie_seguidores` sobre una `fuente` explícita (lo usa el MCP)."""
    desde, hasta, _ = resolver_rango(rango)
    fechas, stock = _serie_seguidores_saneada(fuente, rango)

    # Suma por RED y día sobre la serie YA saneada (cada fecha presente, aun si vacía).
    arrastrado: dict[str, dict[str, int]] = {f: {} for f in fechas}
    for (_cuenta, red), por_fecha in stock.items():
        for f, valor in por_fecha.items():
            arrastrado[f][red] = arrastrado[f].get(red, 0) + valor

    puntos_out: list[PuntoSeguidores] = [
        PuntoSeguidores(
            fecha=f,
            total=sum(arrastrado[f].values()),
            por_red=dict(sorted(arrastrado[f].items())),
        )
        for f in fechas
    ]

    # Neto del periodo POR RED sobre la serie YA arrastrada: último − primer día en que la
    # red tiene valor (los huecos quedaron rellenos, así que una cuenta que deja de reportar
    # ya no resta su stock al total). El neto global = suma de los netos por red. Una red con
    # un solo día -> 0 (sin variación medible), pero SE CONSERVA para el desglose del gráfico.
    neto_por_red: dict[str, int] = {}
    for red in sorted({red for _cuenta, red in stock}):
        valores = [arrastrado[f][red] for f in fechas if red in arrastrado[f]]
        neto_por_red[red] = (valores[-1] - valores[0]) if len(valores) >= 2 else 0
    neto = sum(neto_por_red.values())

    serie = SerieSeguidores(
        cuenta=marca,
        rango=rango,
        etiqueta_rango=etiqueta_rango(rango),
        periodo=Periodo(desde=desde, hasta=hasta),
        fuente=fuente.nombre,
        puntos=puntos_out,
        neto=neto,
        neto_por_red=neto_por_red,
    )
    return serie.model_dump(mode="json")


def mejor_hora(marca: str, red: str) -> str | None:
    """Mejor hora de publicación (CDMX, "HH:mm") para una marca×red, o None si no hay datos.

    Reúsa `fuente.mejores_horas` (matriz 7x24 normalizada de besttimes): la mejor franja es la
    celda de mayor score; se devuelve solo su HORA (la franja, sin día). None si la fuente no
    expone besttimes (muestra/compuesta), la red no es válida o no hay datos para esa red.
    """
    fuente = _fuente(marca)
    fn = getattr(fuente, "mejores_horas", None)
    if fn is None:
        return None
    try:
        plat = Plataforma(red)
    except ValueError:
        return None
    mejor_val = 0.0
    mejor_hora_int: int | None = None
    for c in fuente.cuentas():
        try:
            matriz = fn(c.id, plat)
        except AttributeError:
            # La fuente envuelta no la implementa (FuenteScoped lo propaga): sin besttimes.
            return None
        for fila in matriz:
            for hora, val in enumerate(fila):
                if val > mejor_val:
                    mejor_val = val
                    mejor_hora_int = hora
    if mejor_hora_int is None:
        return None
    return f"{mejor_hora_int:02d}:00"


def construir_serie_alcance(rango: str = "mes", marca: str | None = None) -> dict:
    """Alcance de cuenta POR DÍA y por red (suma de las cuentas en alcance).

    Solo Instagram expone alcance de cuenta (reach diario vía `/v2/analytics/timelines`),
    así que `por_red` solo trae `instagram`. El alcance es un FLUJO diario (no un stock como
    los followers): por eso no hay `neto`, solo la serie. `puntos=[]` si la fuente no lo
    soporta (degradación honesta). Devuelve un dict JSON-serializable.
    """
    return serie_alcance_desde_fuente(_fuente(marca), rango, marca)


def serie_alcance_desde_fuente(fuente, rango: str, marca: str | None = None) -> dict:
    """Worker de `construir_serie_alcance` sobre una `fuente` explícita (lo usa el MCP)."""
    desde, hasta, _ = resolver_rango(rango)
    serie_fn = getattr(fuente, "serie_alcance", None)
    por_dia: dict[str, dict[str, int]] = {}
    if serie_fn is not None:
        for c in fuente.cuentas():
            try:
                puntos = serie_fn(c.id, rango)
            except AttributeError:
                # La fuente envuelta no la implementa (FuenteScoped lo propaga): degrada.
                puntos = []
            for punto in puntos:
                f = punto["fecha"]
                for red, valor in (punto.get("por_red") or {}).items():
                    dia = por_dia.setdefault(f, {})
                    dia[red] = dia.get(red, 0) + int(valor)
    puntos_out = [
        {
            "fecha": f,
            "total": sum(por_dia[f].values()),
            "por_red": dict(sorted(por_dia[f].items())),
        }
        for f in sorted(por_dia)
    ]
    return {
        "cuenta": marca,
        "rango": rango,
        "etiqueta_rango": etiqueta_rango(rango),
        "periodo": {"desde": desde.isoformat(), "hasta": hasta.isoformat()},
        "fuente": fuente.nombre,
        "puntos": puntos_out,
    }


def construir_desglose_interacciones(
    rango: str = "mes", marca: str | None = None, formato: tuple[str, ...] = ()
) -> dict:
    """Desglose de engagement (likes/comentarios/compartidos/guardados/video_views)
    agregado por MARCA×RED.

    AGREGA desde las piezas del periodo (que ya traen los campos granulares). Los
    campos granulares ausentes (None) cuentan como 0 SOLO en la suma; `n_piezas`
    cuenta TODAS las piezas del grupo. `engagement_pct` de la celda =
    interacciones/visualizaciones*100 (0 si no hay visualizaciones). `formato` (ids
    canónicos) acota a esos formatos antes de agregar (vacío = todos). Devuelve un
    dict JSON-serializable (`DesgloseInteracciones`).
    """
    return desglose_interacciones_desde_fuente(_fuente(marca), rango, formato)


def desglose_interacciones_desde_fuente(
    fuente, rango: str, formato: tuple[str, ...] = ()
) -> dict:
    """Worker de `construir_desglose_interacciones` sobre una `fuente` explícita (MCP)."""
    desde, hasta, _ = resolver_rango(rango)
    piezas = _filtrar_formato(_piezas_periodo(fuente, rango), formato)

    _campos = ("likes", "comentarios", "compartidos", "guardados", "video_views")
    # Acumula por (marca, red). marca None -> "" (sin marca) para que la clave sea str.
    acc: dict[tuple[str, str], dict] = {}
    for p in piezas:
        clave = (p.cuenta or "", p.plataforma.value)
        celda = acc.setdefault(
            clave,
            {
                "likes": 0, "comentarios": 0, "compartidos": 0, "guardados": 0,
                "video_views": 0, "interacciones": 0, "visualizaciones": 0, "n_piezas": 0,
            },
        )
        for campo in _campos:
            celda[campo] += getattr(p, campo) or 0  # None -> 0 solo en la suma
        celda["interacciones"] += p.interacciones or 0
        celda["visualizaciones"] += p.visualizaciones or 0
        celda["n_piezas"] += 1

    celdas: list[CeldaDesglose] = []
    totales = {c: 0 for c in (*_campos, "interacciones", "visualizaciones")}
    for (marca_k, red), c in sorted(acc.items()):
        vis = c["visualizaciones"]
        celdas.append(
            CeldaDesglose(
                marca=marca_k,
                red=red,
                likes=c["likes"],
                comentarios=c["comentarios"],
                compartidos=c["compartidos"],
                guardados=c["guardados"],
                video_views=c["video_views"],
                interacciones=c["interacciones"],
                visualizaciones=vis,
                engagement_pct=round(c["interacciones"] / vis * 100, 2) if vis else 0.0,
                n_piezas=c["n_piezas"],
            )
        )
        for campo in totales:
            totales[campo] += c[campo]

    desglose = DesgloseInteracciones(
        rango=rango,
        etiqueta_rango=etiqueta_rango(rango),
        periodo=Periodo(desde=desde, hasta=hasta),
        fuente=fuente.nombre,
        celdas=celdas,
        totales=totales,
    )
    return desglose.model_dump(mode="json")


def construir_crosstab(
    rango: str = "mes", marca: str | None = None, formato: tuple[str, ...] = ()
) -> dict:
    """Cruce MARCA×RED×FORMATO de las piezas del periodo.

    Agrupa las piezas por (marca, red, formato). `rendimiento_relativo_medio` = media
    del `rendimiento_relativo` (no-None) del grupo, computado con
    `estadisticas.anotar_rendimiento_relativo` sobre TODAS las piezas antes de agrupar
    (normaliza contra el baseline marca×red). None si ninguna pieza del grupo lo tiene.
    `formato` (ids canónicos) acota a esos formatos antes de agrupar (vacío = todos).
    Devuelve un dict JSON-serializable (`Crosstab`).
    """
    return crosstab_desde_fuente(_fuente(marca), rango, formato)


def crosstab_desde_fuente(fuente, rango: str, formato: tuple[str, ...] = ()) -> dict:
    """Worker de `construir_crosstab` sobre una `fuente` explícita (lo usa el MCP)."""
    desde, hasta, _ = resolver_rango(rango)
    piezas = _filtrar_formato(_piezas_periodo(fuente, rango), formato)
    # Anota el rendimiento relativo (vs. la mediana del grupo marca×red) ANTES de
    # agrupar por formato: así el score por pieza ya está disponible al promediar.
    _estadisticas.anotar_rendimiento_relativo(piezas)

    acc: dict[tuple[str, str, str | None], dict] = {}
    for p in piezas:
        clave = (p.cuenta or "", p.plataforma.value, p.formato)
        grupo = acc.setdefault(
            clave, {"n_piezas": 0, "visualizaciones": 0, "interacciones": 0, "rr": []}
        )
        grupo["n_piezas"] += 1
        grupo["visualizaciones"] += p.visualizaciones or 0
        grupo["interacciones"] += p.interacciones or 0
        if p.rendimiento_relativo is not None:
            grupo["rr"].append(p.rendimiento_relativo)

    celdas: list[CeldaCrosstab] = []
    # Orden estable: marca, red, formato (None al final).
    for (marca_k, red, formato) in sorted(acc, key=lambda k: (k[0], k[1], k[2] is None, k[2] or "")):
        g = acc[(marca_k, red, formato)]
        vis = g["visualizaciones"]
        rr = g["rr"]
        celdas.append(
            CeldaCrosstab(
                marca=marca_k,
                red=red,
                formato=formato,
                n_piezas=g["n_piezas"],
                visualizaciones=vis,
                interacciones=g["interacciones"],
                engagement_pct=round(g["interacciones"] / vis * 100, 2) if vis else 0.0,
                rendimiento_relativo_medio=round(sum(rr) / len(rr), 3) if rr else None,
            )
        )

    crosstab = Crosstab(
        rango=rango,
        etiqueta_rango=etiqueta_rango(rango),
        periodo=Periodo(desde=desde, hasta=hasta),
        fuente=fuente.nombre,
        celdas=celdas,
    )
    return crosstab.model_dump(mode="json")


# Caveat de atribución para la correlación seguidores↔posts. Honesto a propósito:
# el delta diario de followers NO es atribuible 1:1 a un post.
_NOTA_CORRELACION = (
    "Correlación, no causalidad: el crecimiento diario de seguidores no es atribuible "
    "1:1 a las piezas de ese día (influyen campañas, tendencias, recomendación "
    "del algoritmo y arrastre de días previos). 'seguidores_por_post' es un reparto "
    "indicativo, no una métrica de atribución."
)
_NOTA_SIN_SERIE = (
    "La fuente activa no expone serie de seguidores, así que no se puede correlacionar "
    "crecimiento de comunidad con piezas."
)


def construir_correlacion_seguidores(
    rango: str = "mes", marca: str | None = None, formato: tuple[str, ...] = ()
) -> dict:
    """Correlación (NO causalidad) crecimiento de seguidores ↔ piezas.

    Por (marca, red, día): `seguidores_ganados` = delta diario de la serie de
    followers (punto N − N-1); `n_posts` = piezas publicadas ese día;
    `seguidores_por_post` = ganados/n_posts si n_posts>0 (None si 0); `post_estrella`
    = la pieza de mayor engagement ese día. `formato` (ids canónicos) acota las piezas
    que cuentan (n_posts/estrella) a esos formatos; el stock de followers no tiene
    dimensión de formato, así que `seguidores_ganados` no varía. Si no hay serie de
    followers, `items=[]` y `nota` lo explica. Devuelve un dict JSON-serializable
    (`CorrelacionSeguidores`).
    """
    return correlacion_seguidores_desde_fuente(_fuente(marca), rango, formato)


def correlacion_seguidores_desde_fuente(
    fuente, rango: str, formato: tuple[str, ...] = ()
) -> dict:
    """Worker de `construir_correlacion_seguidores` sobre una `fuente` explícita (MCP)."""
    desde, hasta, _ = resolver_rango(rango)
    fechas, stock = _serie_seguidores_saneada(fuente, rango)
    base = dict(
        rango=rango,
        etiqueta_rango=etiqueta_rango(rango),
        periodo=Periodo(desde=desde, hasta=hasta),
        fuente=fuente.nombre,
    )
    if not stock:
        return CorrelacionSeguidores(**base, items=[], nota=_NOTA_SIN_SERIE).model_dump(mode="json")

    # Piezas indexadas por (marca, red, fecha) para contar posts y hallar la estrella.
    # El filtro de formato afecta SOLO al recuento de piezas, no al stock de seguidores.
    piezas = _filtrar_formato(_piezas_periodo(fuente, rango), formato)
    por_dia: dict[tuple[str, str, str], list] = {}
    for p in piezas:
        clave = (p.cuenta or "", p.plataforma.value, p.publicado.isoformat())
        por_dia.setdefault(clave, []).append(p)

    items: list[ItemCorrelacion] = []
    for (cuenta_id, red), por_fecha in stock.items():
        # delta diario de followers sobre el stock SANEADO: punto N − N-1 (no el crudo).
        anterior: int | None = None
        for fecha in fechas:
            stock_dia = por_fecha.get(fecha)
            if stock_dia is None:
                continue
            if anterior is None:
                anterior = stock_dia  # primer día con valor: no hay delta previo.
                continue
            ganados = stock_dia - anterior
            anterior = stock_dia
            piezas_dia = por_dia.get((cuenta_id, red, fecha), [])
            n_posts = len(piezas_dia)
            estrella = None
            if piezas_dia:
                mejor = max(piezas_dia, key=lambda x: x.engagement_pct)
                estrella = PostEstrella(
                    id=mejor.id,
                    titulo=mejor.titulo,
                    engagement_pct=mejor.engagement_pct,
                    url=mejor.url,
                )
            items.append(
                ItemCorrelacion(
                    marca=cuenta_id,
                    red=red,
                    fecha=fecha,
                    seguidores_ganados=ganados,
                    n_posts=n_posts,
                    seguidores_por_post=(
                        round(ganados / n_posts, 2) if n_posts > 0 else None
                    ),
                    post_estrella=estrella,
                )
            )

    items.sort(key=lambda it: (it.fecha.isoformat(), it.marca, it.red))
    return CorrelacionSeguidores(**base, items=items, nota=_NOTA_CORRELACION).model_dump(
        mode="json"
    )


def construir_metricas_pieza(marca: str, red: str, id_post: str) -> dict:
    """Rendimiento REAL de UNA pieza ya publicada (por su `id_post` de Metricool).

    `marca` es el id_metricas (guion_bajo) de la cuenta; `red` la plataforma keni
    ('facebook'|'instagram'|'x'|'tiktok'|'youtube'); `id_post` el id que devolvio el
    scheduler de Metricool al programar (lo guarda la Consola en
    `pieza.id_post_metricool`). Lo consume el tablero para pintar el
    rendimiento en cada tarjeta SIN adaptadores por red: una sola lectura sobre la
    fuente activa (Metricool de pago en prod; muestra en demo).

    Devuelve un dict JSON-serializable (`MetricaPieza`). Si la red no es valida, la
    fuente no expone la lectura por post (fuentes 'real' compuestas), o Metricool aun
    no tiene datos del post, devuelve `encontrado=False` (la UI muestra "sin datos
    todavia", nunca ceros falsos). Propaga `CuentaNoEncontrada` (marca fuera de alcance).
    """
    try:
        plat = Plataforma(red)
    except ValueError:
        return _pieza_sin_datos(id_post, red).model_dump(mode="json")

    fuente = _fuente(marca)
    leer = getattr(fuente, "metricas_de_post", None)
    if leer is None:
        return _pieza_sin_datos(id_post, plat.value).model_dump(mode="json")
    try:
        metrica = leer(marca, plat, id_post)
    except AttributeError:
        # La fuente envuelta no lo implementa (FuenteScoped lo propaga): degrada.
        metrica = None
    if metrica is None:
        metrica = _pieza_sin_datos(id_post, plat.value)
    return metrica.model_dump(mode="json")


def _pieza_sin_datos(id_post: str, red: str) -> MetricaPieza:
    """`MetricaPieza` vacia (encontrado=False) para 'sin datos todavia' sin romper.

    Usa una plataforma valida si `red` lo es; si no, cae a facebook como placeholder
    (el campo `encontrado=False` ya le dice a la UI que no hay rendimiento real).
    """
    try:
        plat = Plataforma(red)
    except ValueError:
        plat = Plataforma.facebook
    return MetricaPieza(
        id_post=str(id_post), plataforma=plat, encontrado=False, fuente=nombre_fuente()
    )


# --------------------------------------------------------------------------- #
# Gestión de configuración — lee y cambia fuente/alcance (NO credenciales)     #
# --------------------------------------------------------------------------- #


def instantanea_config() -> dict:
    """Estado del config para la pantalla de configuracion (SIN credenciales).

    Devuelve `{fuente, marcas, marcas_disponibles, credenciales_presentes}`:
      - `marcas_disponibles`: pares (id, nombre) elegibles para el alcance (las del
        config + las de la fuente sin acotar), orden estable y sin duplicados.
      - `credenciales_presentes`: por bloque conocido (meta/youtube/x/tiktok), True
        si trae un token real (nunca el valor, solo presencia).

    Lanza `ConfigInvalida` si el config.toml existe pero no se puede leer.
    """
    cfg = _config.cargar_config()
    return {
        "fuente": cfg.fuente,
        "marcas": list(cfg.marcas),
        "marcas_disponibles": _marcas_disponibles(cfg),
        "credenciales_presentes": _presencia_credenciales(cfg),
    }


def _marcas_disponibles(cfg: _config.Config) -> list[tuple[str, str]]:
    """Marcas elegibles para el alcance: las del config + las de la fuente sin acotar."""
    pares: list[tuple[str, str]] = []
    vistos: set[str] = set()

    for c in cfg.cuentas:
        if c.id not in vistos:
            vistos.add(c.id)
            pares.append((c.id, c.nombre))

    # Sin alcance (marcas=[]) listamos TODAS las marcas de la fuente, asi el usuario
    # puede ampliar su alcance aunque ya lo tenga acotado.
    try:
        cfg_sin_alcance = dataclasses.replace(cfg, marcas=[])
        for c in _config.construir_fuente(cfg_sin_alcance).cuentas():
            if c.id not in vistos:
                vistos.add(c.id)
                pares.append((c.id, c.nombre))
    except Exception:  # noqa: BLE001 -- sin fuente valida seguimos con lo del config
        pass

    return pares


# Bloques de credenciales reconocidos, en orden estable (derivado del asistente).
_BLOQUES_CREDENCIALES: tuple[str, ...] = ("meta", "youtube", "x", "tiktok")


def _presencia_credenciales(cfg: _config.Config) -> dict[str, bool]:
    """Por cada bloque conocido: True si trae un token real (no vacio ni placeholder)."""
    creds = cfg.credenciales if isinstance(cfg.credenciales, dict) else {}
    salida: dict[str, bool] = {}
    for bloque in _BLOQUES_CREDENCIALES:
        valores = creds.get(bloque) if isinstance(creds.get(bloque), dict) else {}
        campo = asistente.CAMPO_TOKEN.get(bloque)
        token = valores.get(campo) if campo else None
        salida[bloque] = bool(token) and token != asistente.PLACEHOLDER_TOKEN
    return salida


def normalizar_alcance(marcas: list[str], ids_validos: list[str]) -> list[str]:
    """Normaliza la lista de marcas del alcance contra los ids validos (re-export)."""
    return asistente.normalizar_alcance(marcas, ids_validos=ids_validos)


def guardar_fuente_y_alcance(fuente: str, marcas: list[str]) -> None:
    """Escribe SOLO `fuente` y `marcas` en el config.toml preservando el resto.

    Merge no destructivo + escritura atomica (delega en `asistente`). NO toca
    credenciales. Frontera de GESTION (no de datos de metricas); por eso vive en
    esta fachada y no obliga a los consumidores a importar internals.

    Lanza `ValueError` si la fuente no es valida; `OSError` si falla la escritura.
    """
    if fuente not in FUENTES_VALIDAS:
        validas = ", ".join(FUENTES_DISPONIBLES)
        raise ValueError(f"Fuente invalida {fuente!r}. Usa una de: {validas}.")
    # `real` es un fallback histórico desactivado por defecto (ver config): no se
    # persiste desde la fachada sin el flag opt-in, para no dejar el config apuntando a
    # una fuente que rompería la lectura del tablero. La fuente única es `metricool`.
    if fuente == "real" and not _config._real_permitida():
        raise ValueError(
            "La fuente 'real' está desactivada (dejaría el rendimiento por pieza sin "
            f"datos). Usa 'metricool' o 'muestra', o exporta {_config.ENV_PERMITIR_REAL}=1."
        )
    ruta = _config.ruta_config()
    existente = asistente.leer_config_existente(ruta)
    nuevo: dict = {"fuente": fuente}
    if marcas:
        nuevo["marcas"] = list(marcas)
    fusionado = asistente.fusionar_config(existente, nuevo)
    if not marcas:
        fusionado.pop("marcas", None)
    asistente.escribir_config_atomico(ruta, fusionado)
