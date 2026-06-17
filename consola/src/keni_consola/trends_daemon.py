"""Daemon de Google Trends: vuelca las tendencias (con sus noticias) al pool de Noticias.

Google Trends es una FUENTE EXTERNA (como los feeds RSS): cada N min, si está encendido
(`KENI_TRENDS=1`, def OFF), descarga el RSS de "trending now" por geo, lo parsea con
`dominio.trends` (que aplana los `ht:news_item` a noticias reales) e inserta en
`noticias_items` (el pool). De ahí siguen el camino normal: clustering -> Historias.

- GATEADO + SAFE BY DEFAULT: el hilo arranca SIEMPRE pero solo ingiere con el flag ON.
- Best-effort: un geo que falla se omite con su error; no mata el hilo.
- Dedup: `noticias_items` tiene UNIQUE(fuente_id, clave); re-ingerir no duplica.
- NUNCA publica: solo alimenta el pool, que el equipo cura como cualquier otra noticia.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from . import config, daemon_util, repos
from .dominio import http_feed
from .dominio import trends as dom_trends
from .tiempo import iso_utc

_log = logging.getLogger("keni_consola.trends_daemon")

# Descargador INYECTABLE (los tests lo parchean para NUNCA tocar la red). Por defecto, el
# descargador real con guard SSRF de `http_feed`.
_DESCARGADOR: Callable[[str], str] = http_feed._descargar_real


def _ingerir_geo(geo: str) -> int:
    """Descarga + parsea + inserta las tendencias de un `geo`. Devuelve nº de items nuevos.

    Best-effort: cualquier fallo (URL inválida, red, XML) se loguea y devuelve 0 sin propagar.
    """
    url = dom_trends.url_trends(geo)
    url_ok, error = http_feed.validar_url(url)
    if url_ok is None:
        _log.warning("trends: URL no válida para geo=%s: %s", geo, error)
        return 0
    try:
        xml = _DESCARGADOR(url_ok)
        items = dom_trends.parsear_trends_items(xml, geo=geo)
    except http_feed.RSSError as e:
        _log.warning("trends: no se pudo leer el feed (geo=%s): %s", geo, e)
        return 0
    except Exception:  # noqa: BLE001 -- un geo no debe matar el barrido
        _log.exception("trends: fallo inesperado leyendo geo=%s", geo)
        return 0
    if not items:
        return 0
    # DEDUP Trends ↔ RSS directo: una nota que YA entró por el feed de su medio (misma url
    # canónica) no se vuelca de nuevo desde Trends —su `fuente_id` distinto burla el UNIQUE
    # (fuente_id, clave) y duplicaría la fila inflando `n_fuentes`—. Trends sigue aportando los
    # medios que NO ingerimos directamente (Milenio, TUDN…), que es su valor real como descubridor.
    try:
        desde = iso_utc(datetime.now(UTC) - timedelta(hours=config.cluster_ventana_h()))
        ya_directas = repos.claves_existentes_directas(
            [it["clave"] for it in items], desde=desde, excluir_fuente=dom_trends.FUENTE_ID
        )
        if ya_directas:
            items = [it for it in items if it.get("clave") not in ya_directas]
    except Exception:  # noqa: BLE001 -- si el dedup falla, se inserta igual (el ON CONFLICT evita el dup del propio Trends)
        _log.warning("trends: no se pudo deduplicar contra el pool (geo=%s); se inserta sin dedup extra.", geo, exc_info=True)
    if not items:
        return 0
    try:
        return repos.crear_noticias_items(items)
    except Exception:  # noqa: BLE001 -- best-effort: si la inserción falla, lo intenta el próximo barrido
        _log.exception("trends: no se pudieron insertar items (geo=%s)", geo)
        return 0


def ejecutar_barrido() -> int:
    """Ingiere todas las geografías configuradas. Devuelve el total de items nuevos."""
    total = 0
    for geo in config.trends_geos():
        total += _ingerir_geo(geo)
    if total:
        _log.info("trends: %d items nuevos en el pool.", total)
    return total


def _resumen_barrido(total: int) -> str:
    """Resumen corto del barrido de trends para el historial."""
    return f"{total} tendencia(s) ingerida(s)" if total else "sin novedad"


def _intervalo_segundos() -> float:
    return config.trends_intervalo_min() * 60.0


def iniciar_trends(intervalo_segundos: float | None = None) -> threading.Thread:
    """Arranca el hilo demonio de Google Trends (GATEADO EN VIVO por `KENI_TRENDS`).

    El hilo arranca SIEMPRE y comprueba el flag en cada ciclo (encender/apagar en runtime
    aplica sin reiniciar). Daemon; un fallo de barrido se loguea y NO lo mata. Vive en el
    servidor real (`daemons.py`), no en `crear_app` (los tests no lo arrancan).
    """
    intervalo = intervalo_segundos if intervalo_segundos is not None else _intervalo_segundos()

    def bucle() -> None:
        daemon_util.bucle_gateado(
            activo_fn=config.gate_maquina(config.trends_activo),
            intervalo_seg_fn=lambda: intervalo,
            sweep_fn=ejecutar_barrido,
            log=_log,
            resumen_fn=_resumen_barrido,
        )

    hilo = threading.Thread(target=bucle, name="trends-daemon", daemon=True)
    hilo.start()
    estado = "ACTIVO" if config.trends_activo() else "EN ESPERA (KENI_TRENDS off)"
    _log.info(
        "Trends daemon %s, cada %.0f min (geos=%s).",
        estado, intervalo / 60.0, ",".join(config.trends_geos()),
    )
    return hilo
