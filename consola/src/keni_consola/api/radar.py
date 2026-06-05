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

import threading
import time
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import agencias, config, investigador, marcas, parrilla, radar, relevancia_marca
from ..dominio import fuentes_presets
from . import rss

# --------------------------------------------------------------------------- #
# Cache con TTL del radar consolidado (F0 rendimiento)                          #
# --------------------------------------------------------------------------- #
#
# El radar descarga Trends + TODOS los feeds del equipo + agencias en el path de carga.
# Abrir Plan, luego Descubrimiento y la bandeja Auto lo recalculaba TODO cada vez (varias
# descargas de red repetidas en segundos). Aqui cacheamos el resultado CONSOLIDADO (los
# grupos de temas por fuente + el estado por fuente) keyed por `(geo, incluir_feeds, marca)`,
# con un TTL corto, compartido entre `api/radar.py` y `api/parrilla.py`.
#
# Honestidad intacta: el TTL es corto (los datos siguen siendo "de ahora"); pasado el TTL
# se vuelve a descargar de fuentes reales. Thread-safe con un Lock (los handlers async corren
# las descargas en hilos). `limpiar_cache()` invalida (lo usan los tests entre casos, ver la
# fixture autouse del conftest, para que la cache de un test no contamine al siguiente).

_TTL_CACHE = 180.0  # segundos: ventana corta; refresca de fuentes reales pasado el TTL.
_cache_lock = threading.Lock()

# TTL del SNAPSHOT del Investigador (Fase 1): distinto de `_TTL_CACHE` (la cache en vivo de
# Trends/feeds). El snapshot lo materializa el daemon cada `KENI_INVESTIGADOR_INTERVALO_HORAS`;
# lo damos por valido durante ~2 intervalos (margen ante un barrido perdido) antes de caer al
# camino en vivo. Lazy (no usa config a nivel de modulo): se calcula en cada lectura.


def _ttl_snapshot() -> float:
    """TTL del snapshot del Investigador en segundos (~2 intervalos del daemon, min 1h)."""
    return max(config.investigador_intervalo_horas() * 2, 1) * 3600.0

# clave -> (instante_monotonic, (grupos, fuentes))
_cache: dict[tuple[str, bool, str | None], tuple[float, tuple[list[list[radar.Tema]], list[dict[str, Any]]]]] = {}


def limpiar_cache() -> None:
    """Vacia la cache del radar consolidado (invalidacion manual / aislamiento de tests)."""
    with _cache_lock:
        _cache.clear()


def _radar_consolidado(
    geo: str, *, incluir_feeds: bool, marca: str | None, refrescar: bool = False
) -> tuple[list[list[radar.Tema]], list[dict[str, Any]]]:
    """Trae los grupos de temas (Trends + feeds + agencias) y el estado por fuente, CACHEADO.

    Devuelve `(grupos, fuentes)` listo para consolidar. Cacheado por `(geo, incluir_feeds,
    marca)` con TTL corto; `refrescar=True` fuerza el recalculo (boton "Actualizar"). Nunca
    lanza: cada `_radar_*` degrada honesto por fuente.

    NOTA sobre la cache y los `Tema`: los `Tema` se reutilizan entre llamadas dentro del TTL.
    `consolidar` FUNDE temas mutando el representante (`fusionar`), asi que NO debe correr dos
    veces sobre los MISMOS objetos. Por eso la cache guarda los grupos CRUDOS (sin consolidar)
    y cada llamante hace su propio `consolidar` sobre COPIAS (ver `_grupos_para_consolidar`).
    """
    clave = (geo, incluir_feeds, marca)
    if not refrescar:
        with _cache_lock:
            entrada = _cache.get(clave)
            if entrada is not None and (time.monotonic() - entrada[0]) < _TTL_CACHE:
                return entrada[1]

    grupos: list[list[radar.Tema]] = []
    fuentes: list[dict[str, Any]] = []

    temas_trends, estado_trends = _radar_trends(geo)
    grupos.append(temas_trends)
    fuentes.append(estado_trends)

    if incluir_feeds:
        temas_feeds, estados_feeds = _radar_feeds(marca)
        grupos.append(temas_feeds)
        fuentes.extend(estados_feeds)
        # Agencias (Reuters/AFP): gateadas por credencial; sin ella salen como NO disponibles.
        temas_agencias, estados_agencias = _radar_agencias()
        grupos.append(temas_agencias)
        fuentes.extend(estados_agencias)

    resultado = (grupos, fuentes)
    with _cache_lock:
        _cache[clave] = (time.monotonic(), resultado)
    return resultado


def _grupos_para_consolidar(grupos: list[list[radar.Tema]]) -> list[list[radar.Tema]]:
    """Clona los `Tema` de los grupos cacheados para que `consolidar` no mute el original.

    `consolidar`/`fusionar` mutan el representante de cada cluster; correrlo sobre los objetos
    cacheados los corromperia para la siguiente lectura. Devolvemos COPIAS superficiales con
    sus colecciones duplicadas (lo que `fusionar` toca), baratas frente a una descarga de red.
    """
    import copy

    return [[copy.deepcopy(t) for t in grupo] for grupo in grupos]


def _temas_desde_snapshot(
    marca: str | None, geo: str, *, refrescar: bool = False
) -> list[radar.Tema] | None:
    """Temas del SNAPSHOT del Investigador (Fase 1), o None para caer al camino en vivo.

    Contrato de CERO REGRESION: la PRIMERA linea devuelve None si el flag esta OFF o si se pide
    `?refresh=1`, asi que con `KENI_INVESTIGADOR` ausente el comportamiento es IDENTICO a hoy y
    `?refresh=1` SIEMPRE golpea fuentes reales (nunca sirve el snapshot). Si el flag esta ON y no
    se refresca, lee del snapshot fresco (`repos.listar_radar_items` con `frescas_seg`); devuelve
    None si esta vacio (sin snapshot aun) o ante cualquier excepcion (degradacion al camino en
    vivo). Reconstruye los `Tema` con `api.parrilla._tema_desde_dict` (misma reconstruccion que
    los temas pasados por body).
    """
    if not config.investigador_activo() or refrescar:
        return None
    try:
        from .. import repos
        from . import parrilla as api_parrilla

        filas = repos.listar_radar_items(
            marca=marca or "", geo=geo, frescas_seg=_ttl_snapshot()
        )
        if not filas:
            return None
        temas = [t for t in (api_parrilla._tema_desde_dict(f) for f in filas) if t is not None]
        return temas or None
    except Exception:  # noqa: BLE001 -- ante cualquier fallo, caer al camino en vivo (sin regresion)
        return None


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


def _radar_agencias() -> tuple[list[radar.Tema], list[dict[str, Any]]]:
    """Trae temas de las AGENCIAS (Reuters/AFP) GATEADAS por credencial. `(temas, estados)`.

    Cada agencia sale con su estado HONESTO: si no hay credencial, `disponible=False` con el
    motivo y NO aporta items (degradacion honesta, no se inventa nada). Con credencial,
    descarga y normaliza a items (misma forma que el RSS del equipo) y los convierte a temas
    via `radar.temas_de_feeds` (señal cualitativa, igual que un feed). Un fallo de descarga se
    OMITE con su motivo sin romper los demas.
    """
    from ..dominio import http_feed

    def _trabajo(agencia: str) -> tuple[list[radar.Tema], dict[str, Any]]:
        estado = agencias.estado_fuente(agencia)
        estado_salida: dict[str, Any] = {
            "id": f"agencia-{agencia}",
            "nombre": estado["nombre"],
            "red": estado["red"],
            "disponible": estado["disponible"],
            "motivo": estado["motivo"],
            "conteo": 0,
        }
        if estado["disponible"]:
            try:
                items = agencias.traer_items(agencia)
                propios = radar.temas_de_feeds(items)
                estado_salida["conteo"] = len(propios)
                return propios, estado_salida
            except rss.RSSError as e:
                estado_salida.update(disponible=False, motivo=str(e))
            except Exception:  # noqa: BLE001 -- nunca traceback crudo; se omite la agencia
                estado_salida.update(disponible=False, motivo="No se pudo leer la agencia.")
        return [], estado_salida

    # Descarga EN PARALELO (F0 rendimiento); recompone el orden original (reuters, afp).
    resultados = http_feed.mapear_en_paralelo(_trabajo, ("reuters", "afp"))
    temas: list[radar.Tema] = []
    estados: list[dict[str, Any]] = []
    for propios, estado in resultados:
        temas.extend(propios)
        estados.append(estado)
    return temas, estados


def _radar_feeds(marca: str | None = None) -> tuple[list[radar.Tema], list[dict[str, Any]]]:
    """Trae temas de los feeds RSS ACTIVOS del equipo. Devuelve `(temas, estados)`.

    Reutiliza `api.rss._items_de_fuente` (mismos filtros del feed). Cada feed sale con
    su estado; uno que falla se OMITE con su motivo sin romper los demas. No marca items
    como usados (esto es descubrimiento, no la pagina Fuentes).

    POR MARCA: si se pasa `marca`, se leen SOLO los feeds de esa marca + los compartidos
    (sin marca). Los feeds propios de la marca producen temas CURADOS (entran a su foco
    sin pasar por el filtro de keywords). Sin `marca`, se leen todos los feeds activos.
    """
    from .. import repos
    from ..dominio import http_feed

    # Filtra ANTES las fuentes a leer (activas + de la marca/compartidas) para abanicar solo
    # las que tocan; conserva el orden de `listar_fuentes_rss` (determinista).
    fuentes = [
        fuente
        for fuente in repos.listar_fuentes_rss()
        if fuente.get("activo", True)
        # Feed de OTRA marca: fuera del radar de la marca activa. Sin marca = compartido.
        and not (marca and (fuente.get("marca") or "").strip()
                 and (fuente.get("marca") or "").strip() != marca)
    ]

    # Índice URL->idioma del catálogo de presets (Ola 4): O(1) para feeds conocidos.
    # Los feeds no presentes en el catálogo quedan con idioma "es" (defecto conservador).
    _url_a_idioma: dict[str, str] = {
        p["url"]: p.get("idioma", "es")
        for p in fuentes_presets.listar_presets()
    }

    def _trabajo(fuente: dict[str, Any]) -> tuple[list[radar.Tema], dict[str, Any]]:
        es_de_marca = bool(marca and (fuente.get("marca") or "").strip() == marca)
        # Idioma del feed: del catálogo de presets si se conoce; "es" si no.
        idioma_feed = _url_a_idioma.get(str(fuente.get("url", "")).strip(), "es")
        estado: dict[str, Any] = {
            "id": f"rss-{fuente['id']}",
            "nombre": fuente["nombre"],
            "red": "rss",
            "disponible": True,
            "motivo": "",
            "conteo": 0,
        }
        try:
            # `vistas=set()`: el Radar NO usa la marca `usado` (sus consumidores no la leen),
            # asi evitamos el N+1 a Postgres (`repos.claves_vistas` por feed) en el path de carga.
            items = rss._items_de_fuente(fuente, ocultar_usados=False, vistas=set())
            propios = radar.temas_de_feeds(items, curado=es_de_marca, idioma=idioma_feed)
            estado["conteo"] = len(propios)
            return propios, estado
        except rss.RSSError as e:
            estado.update(disponible=False, motivo=str(e))
        except Exception:  # noqa: BLE001 -- nunca traceback crudo; se omite el feed
            estado.update(disponible=False, motivo="No se pudo leer el feed.")
        return [], estado

    # Descarga EN PARALELO (F0 rendimiento); recompone el orden original de `fuentes`.
    resultados = http_feed.mapear_en_paralelo(_trabajo, fuentes)
    temas: list[radar.Tema] = []
    estados: list[dict[str, Any]] = []
    for propios, estado in resultados:
        temas.extend(propios)
        estados.append(estado)
    return temas, estados


def _aplicar_traduccion(temas: list[radar.Tema]) -> None:
    """Traduce+tropicaliza los temas extranjeros del TOP al español MX. MUTA en sitio.

    - Toma hasta `config.traduccion_max()` temas con `idioma != 'es'` del top del listado.
    - Llama UNA sola vez a `traduccion.traducir_items` (Haiku, best-effort).
    - Sustituye `titulo`/`por_que` por la versión ES y marca `traducido=True`.
    - `titulo_original` preserva el original para trazabilidad.
    - Si la traduccion falla o devuelve el original inalterado, `traducido` queda False.
    - NUNCA lanza: el llamante ya envuelve en try/except.
    """
    from ..dominio import traduccion as dom_traduccion

    max_trad = config.traduccion_max()
    # Índice {tema: posicion_en_lista} para hacer la sustitución por referencia.
    a_traducir: list[tuple[int, radar.Tema]] = [
        (i, t) for i, t in enumerate(temas) if t.idioma != "es"
    ][:max_trad]

    if not a_traducir:
        return

    # Prepara el payload: un id serial por ítem (no usamos el titulo como id porque puede
    # tener caracteres extraños y el modelo a veces trunca).
    items_payload: list[dict[str, Any]] = [
        {
            "id": str(i),
            "titulo": t.titulo,
            "resumen": t.por_que,
        }
        for i, (_, t) in enumerate(a_traducir)
    ]

    resultado = dom_traduccion.traducir_items(items_payload)

    # Aplica las traducciones por índice serial.
    por_id: dict[str, dict[str, Any]] = {str(r.get("id", "")): r for r in resultado}
    for serial, (_, tema) in enumerate(a_traducir):
        trad = por_id.get(str(serial))
        if not trad:
            continue
        titulo_es = (trad.get("titulo_es") or "").strip()
        resumen_es = (trad.get("resumen_es") or "").strip()
        # Solo se marca como traducido si la versión ES es distinta del original.
        if titulo_es and titulo_es != tema.titulo:
            tema.titulo_original = tema.titulo
            tema.titulo = titulo_es
            tema.por_que = resumen_es or tema.por_que
            tema.traducido = True


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
    # Marca activa: si se pide, las tendencias se FILTRAN al foco de la marca.
    marca_crudo = (request.query_params.get("marca") or "").strip()
    marca = marca_crudo if marca_crudo and marcas.es_marca(marca_crudo) else None
    palabras = relevancia_marca.palabras_de_marca(marca)
    # "Actualizar": `?refresh=1` fuerza el recalculo saltando la cache (contrato OPCIONAL; sin
    # el parametro basta el TTL, asi no se rompe a quien ya llama sin el).
    refrescar = _flag(request, "refresh", defecto=False)

    # Snapshot del Investigador (Fase 1): si el flag esta ON y hay snapshot fresco (y no se
    # pidio `?refresh=1`), se sirve del snapshot (sin re-descargar). None => camino en vivo
    # INTACTO de Fase 0. Con el flag OFF, `_temas_desde_snapshot` devuelve None en su primera
    # linea: cero regresion.
    temas = _temas_desde_snapshot(marca, geo, refrescar=refrescar)
    if temas is None:
        # Cacheado (TTL) y compartido con la Parrilla: abrir Plan + Descubrimiento no re-descarga.
        grupos, fuentes = _radar_consolidado(
            geo, incluir_feeds=incluir_feeds, marca=marca, refrescar=refrescar
        )
        temas = radar.consolidar(*_grupos_para_consolidar(grupos))
    else:
        # Del snapshot: las fuentes en vivo no se consultaron (la frescura la garantiza el TTL).
        fuentes = []

    # Filtro por marca: solo las tendencias en el foco de la marca (las demas se
    # reportan como `total_fuera_foco`, no se inventan ni se ocultan en silencio).
    fuera_foco = 0
    if palabras:
        en_foco = [t for t in temas if parrilla.tema_en_foco(t, palabras)]
        fuera_foco = len(temas) - len(en_foco)
        temas = en_foco

    # Traduccion + tropicalizacion MX (Ola 4) — ADITIVA y BEST-EFFORT.
    # Si el flag esta ON, toma los temas extranjeros del TOP (cap `traduccion_max()`),
    # llama UNA vez a Haiku y sustituye titulo/por_que por la version ES, guardando
    # `titulo_original` y marcando `traducido=True`. Wrap en try/except: si falla, el
    # Radar sigue funcionando sin traduccion (no se lanza excepcion al cliente).
    if config.traduccion_activa() and temas:
        try:
            _aplicar_traduccion(temas)
        except Exception:  # noqa: BLE001 -- best-effort; nunca rompe el Radar
            pass

    # Badges por tema (Investigador F2b): `estado` (cruzando el tablero de la marca AL LEER,
    # asi funciona aunque el daemon este OFF) y `prioritario` (señal >= umbral muy-viral).
    # Campos ADITIVOS; una sola query al tablero por request (best-effort, ver investigador).
    temas_dict = [t.a_dict() for t in temas]
    investigador.anotar_estado_prioritario(temas_dict, marca)

    return JSONResponse(
        {
            "geo": geo,
            "marca": marca,
            "geos_disponibles": [{"id": gid, "nombre": nombre} for gid, nombre in radar.GEOS.items()],
            "temas": temas_dict,
            "fuentes": fuentes,
            "fuentes_pendientes": radar.fuentes_pendientes(),
            "total": len(temas),
            "total_fuera_foco": fuera_foco,
        }
    )


RUTAS = [
    Route("/api/radar", obtener, methods=["GET"]),
]
