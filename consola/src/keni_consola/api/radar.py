"""API Radar de tendencias: lo MAS VIRAL del momento, multi-red (F7 · #147).

Superficie de DESCUBRIMIENTO de SOLO LECTURA. Consolida lo que esta reventando ahora,
agrupado por tema, deduplicado y priorizado por SEÑAL, con "por que sube" y enlaces.
SOLO PROPONE: no publica nada (no hay endpoint de escritura aqui); la relevancia
editorial la decide el equipo.

  - `GET /api/radar?geo=MX&feeds=1`  -> radar consolidado + estado por fuente.
      `geo`   pais del feed de Google Trends (allowlist en `radar.GEOS`; def. MX).
      `feeds` `1` (def) incluye los feeds RSS del equipo como señal editorial; `0` los omite.

REGLA CRITICA — HONESTIDAD: no se inventan tendencias, conteos ni causas. Cada fuente
sale con su estado (`disponible`/`no_disponible`) y, si falla o no esta, su MOTIVO. Las
redes que aun no se pueden traer (TikTok, Instagram, X, YouTube) se listan en
`fuentes_pendientes` para que la UI muestre el hueco sin rellenarlo.

SEGURIDAD: la URL de Trends pasa por el guard SSRF de `api.rss.validar_url`; la descarga
por el `_DESCARGADOR` inyectable (limites de tamaño/timeout; en tests, sin red). `geo` se
valida contra la allowlist. Errores en español, sin tracebacks.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import radar
from . import rss


def _flag(request: Request, nombre: str, *, defecto: bool) -> bool:
    """Lee un query param booleano; si esta ausente devuelve `defecto`."""
    crudo = request.query_params.get(nombre)
    if crudo is None:
        return defecto
    return crudo.strip().lower() in ("1", "true", "si", "yes")


def _radar_trends(geo: str) -> tuple[list[radar.Tema], dict[str, Any]]:
    """Trae los temas de Google Trends para `geo`. Devuelve `(temas, estado_fuente)`.

    Nunca lanza: ante cualquier fallo de descarga/parseo devuelve `[]` y un estado
    `no_disponible` con el motivo en español (degradacion honesta).
    """
    estado: dict[str, Any] = {
        "id": f"google-trends-{geo.lower()}",
        "nombre": f"Google Trends · {radar.GEOS.get(geo, geo)}",
        "red": f"busquedas-{geo.lower()}",
        "disponible": True,
        "motivo": "",
        "conteo": 0,
    }
    url, error = rss.validar_url(radar._url_trends(geo))
    if error is not None:
        estado.update(disponible=False, motivo=error)
        return [], estado
    try:
        xml = rss._DESCARGADOR(url)
        temas = radar.parsear_trends(xml, geo=geo)
    except rss.RSSError as e:
        estado.update(disponible=False, motivo=str(e))
        return [], estado
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo; degradamos honesto
        estado.update(disponible=False, motivo="No se pudo leer Google Trends.")
        return [], estado
    estado["conteo"] = len(temas)
    return temas, estado


def _radar_feeds() -> tuple[list[radar.Tema], list[dict[str, Any]]]:
    """Trae temas de los feeds RSS ACTIVOS del equipo. Devuelve `(temas, estados)`.

    Reutiliza `api.rss._items_de_fuente` (mismos filtros del feed). Cada feed sale con
    su estado; uno que falla se OMITE con su motivo sin romper los demas. No marca items
    como usados (esto es descubrimiento, no la pagina Fuentes).
    """
    from .. import repos

    temas: list[radar.Tema] = []
    estados: list[dict[str, Any]] = []
    for fuente in repos.listar_fuentes_rss():
        if not fuente.get("activo", True):
            continue
        estado: dict[str, Any] = {
            "id": f"rss-{fuente['id']}",
            "nombre": fuente["nombre"],
            "red": "rss",
            "disponible": True,
            "motivo": "",
            "conteo": 0,
        }
        try:
            items = rss._items_de_fuente(fuente, ocultar_usados=False)
            propios = radar.temas_de_feeds(items)
            temas.extend(propios)
            estado["conteo"] = len(propios)
        except rss.RSSError as e:
            estado.update(disponible=False, motivo=str(e))
        except Exception:  # noqa: BLE001 -- nunca traceback crudo; se omite el feed
            estado.update(disponible=False, motivo="No se pudo leer el feed.")
        estados.append(estado)
    return temas, estados


async def obtener(request: Request) -> Response:
    """`GET /api/radar?geo=&feeds=` -> radar consolidado + estado HONESTO por fuente.

    Respuesta:
      `{geo, geos_disponibles, temas:[...], fuentes:[{id,nombre,red,disponible,motivo,
        conteo}], fuentes_pendientes:[{red,nombre,motivo}], total}`.
    `temas` ya viene deduplicado y ordenado por señal desc. Si TODAS las fuentes vivas
    fallan, `temas` queda vacio y cada fuente lo dice en su `motivo` (no se inventa nada).
    """
    geo_crudo = (request.query_params.get("geo") or radar.GEO_DEFECTO).strip().upper()
    geo = geo_crudo if radar.es_geo(geo_crudo) else radar.GEO_DEFECTO
    incluir_feeds = _flag(request, "feeds", defecto=True)

    grupos: list[list[radar.Tema]] = []
    fuentes: list[dict[str, Any]] = []

    temas_trends, estado_trends = _radar_trends(geo)
    grupos.append(temas_trends)
    fuentes.append(estado_trends)

    if incluir_feeds:
        temas_feeds, estados_feeds = _radar_feeds()
        grupos.append(temas_feeds)
        fuentes.extend(estados_feeds)

    temas = radar.consolidar(*grupos)
    return JSONResponse(
        {
            "geo": geo,
            "geos_disponibles": [{"id": gid, "nombre": nombre} for gid, nombre in radar.GEOS.items()],
            "temas": [t.a_dict() for t in temas],
            "fuentes": fuentes,
            "fuentes_pendientes": radar.fuentes_pendientes(),
            "total": len(temas),
        }
    )


RUTAS = [
    Route("/api/radar", obtener, methods=["GET"]),
]
