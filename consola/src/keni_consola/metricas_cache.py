"""Cache de metricas: lectura instantanea + refresco en segundo plano.

PROBLEMA QUE RESUELVE
=====================
La pantalla de Metricas y el Panel recalculaban los reportes EN CADA apertura y en
cada cambio de filtro, golpeando las APIs externas (Metricool/Meta/YouTube/X/TikTok)
en serie por cuenta y plataforma: un consolidado podia tardar 30-120 s. Aqui se
persiste el resultado en Postgres (`metricas_cache`, ver `db.py`) y la UI lo lee
instantaneamente. El dato se refresca por dos vias:

  - Un DAEMON cada N horas (def 6h; `metricas_refresco.py`) — "1 vez al dia importa".
  - El boton "Actualizar" de la UI -> `POST /api/metricas/refrescar`, que dispara un
    refresco EN SEGUNDO PLANO priorizando el combo (rango, marca) que se esta viendo;
    la UI POLLea `GET /api/metricas/estado` hasta que el dato del combo cambia.

QUE SE GUARDA
=============
El dict CRUDO de `keni_metricas.servicio` (`construir_reporte` / `construir_analisis_diario`),
no la forma serializada del SPA: asi `/reporte` (serializa) y `/comparar` (combina dos
reportes crudos) reutilizan la misma entrada. La serializacion al SPA sigue en
`api/metricas.py`.

REGLAS
======
  - LAZY FILL: si un combo no esta en cache, se calcula al vuelo, se guarda y se
    devuelve (la 1a apertura puede tardar; las siguientes son instantaneas). Nunca
    pantalla vacia.
  - FRESCURA GARANTIZADA: el barrido refresca TODOS los tipos de TODOS los combos
    (presets + meses recientes). Ademas, una entrada mas vieja que el TTL (1.25x el
    intervalo del daemon) se sirve al instante PERO dispara un refresco en fondo
    (stale-while-revalidate): aunque el daemon muera o el combo no entre al barrido
    (meses historicos), ninguna vista se queda con datos viejos mas de un ciclo.
  - VERSION DE ESQUEMA en la clave (`v{N}:`): si cambia la FORMA del payload de la
    fachada, se sube `_VERSION_ESQUEMA` y todas las entradas viejas dejan de leerse
    (se recalculan); sin esto, un payload viejo servia campos nuevos como 0/None
    (p.ej. "Piezas publicadas: 0" en meses cacheados antes del KPI). La purga del
    barrido borra las filas sueltas.
  - Estado de refresco EN MEMORIA (un solo proceso del back; el daemon y el POST
    viven en el mismo proceso uvicorn): un Lock + un dict. Se resetea al reiniciar.
  - Conexion por operacion (via `repos`), segura entre hilos (igual que el resto).
"""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timedelta

from keni_metricas import servicio

from . import config, repos
from .tiempo import ahora_iso, hoy_utc

# Version del ESQUEMA de los payloads cacheados. Subir cuando cambie la forma de lo
# que devuelve `keni_metricas.servicio` (campos nuevos en reporte/series/listados):
# invalida toda la cache previa de golpe (las claves viejas dejan de leerse y la
# purga del barrido las borra), en vez de servir el campo nuevo como 0/None.
_VERSION_ESQUEMA = 3

# Las entradas de rangos AD-HOC (`rango:AAAA-MM-DD_AAAA-MM-DD`, las genera el comparador
# con fechas que se desplazan cada dia) caducan y se purgan pasado este margen: sus claves
# cambian a diario y las viejas son basura que solo engorda la tabla.
_PURGA_RANGOS_ADHOC_HORAS = 48

_log = logging.getLogger("keni_consola.metricas_cache")

# Tipos de entrada de cache (coinciden con las lecturas de la fachada `servicio`).
TIPO_REPORTE = "reporte"
TIPO_ANALISIS = "analisis"
TIPO_PIEZAS = "piezas"
TIPO_TENDENCIA = "tendencia"
# Analíticas R2 (seguidores + desgloses): mismo patrón de lazy fill + persistencia que
# el resto; coste 0 de API extra (se computan sobre lo que la fuente ya descarga del periodo).
TIPO_SEGUIDORES = "seguidores"
TIPO_DESGLOSE = "desglose"
TIPO_CROSSTAB = "crosstab"
TIPO_CORRELACION = "correlacion"
# Listado COMPLETO de piezas del periodo (todas, no solo top/peores): mismo patrón de
# lazy fill + persistencia; coste 0 de API extra (se construye sobre lo que ya descarga
# el dashboard). Es el listado de `servicio.construir_listado_piezas`, no las piezas
# de la Consola (eso es `piezas-rendimiento`).
TIPO_PIEZAS_LISTADO = "piezas_listado"

# Campañas de publicidad PAGADA del periodo (Meta/TikTok Ads): el INORGÁNICO. Mismo patrón
# de lazy fill + persistencia. Lo consumen el panel de Campañas (atribuye boosts a piezas)
# y el dashboard de Métricas (sección Ads). `servicio.construir_ads`.
TIPO_ADS = "ads"

# Estado del refresco en curso (en memoria; un solo proceso del back). Lo leen el
# endpoint /estado y lo escriben el daemon y el disparador manual.
_LOCK = threading.Lock()
_ESTADO: dict[str, object] = {
    "corriendo": False,
    "iniciado_en": "",
    "terminado_en": "",
    "ultimo_error": "",
}

# Anti-stampede del lazy fill: un lock POR clave de combo serializa el cálculo caro (golpe
# a la API externa) de modo que N requests concurrentes del mismo combo frío disparen UN
# solo refresco; el resto espera y lee la cache ya rellenada. `_LOCKS_GUARDIAN` protege la
# creación/lectura del dict de locks (no es el mismo `_LOCK` del estado de refresco, que se
# usa de forma reentrante vía `estado()` y no debe acoplarse a esto).
_LOCKS_GUARDIAN = threading.Lock()
_LOCKS_COMBO: dict[str, threading.Lock] = {}

# Claves con un refresco en FONDO en curso (stale-while-revalidate): evita que N lecturas
# de la misma entrada caducada disparen N recalculos. Protegido por `_LOCKS_GUARDIAN`.
_SWR_EN_PROCESO: set[str] = set()


def _lock_combo(clave: str) -> threading.Lock:
    """Lock dedicado a una clave de combo (creado al vuelo, bajo el lock guardián)."""
    with _LOCKS_GUARDIAN:
        lock = _LOCKS_COMBO.get(clave)
        if lock is None:
            lock = threading.Lock()
            _LOCKS_COMBO[clave] = lock
        return lock


def _ahora() -> str:
    return ahora_iso()


def _marca_norm(marca: str | None) -> str:
    """Marca normalizada para la clave/columna: '' significa "todas las marcas"."""
    return (marca or "").strip()


def _clave(tipo: str, rango: str, marca: str | None) -> str:
    return f"v{_VERSION_ESQUEMA}:{tipo}:{rango}:{_marca_norm(marca) or 'todas'}"


def _ttl_segundos() -> float:
    """Edad maxima de una entrada antes de revalidarla en fondo (1.25x el intervalo).

    Con el daemon sano ninguna entrada del barrido supera el intervalo (re-estampa
    `generado_en` en cada pasada): el TTL solo salta si el daemon murio o el combo no
    entra al barrido (meses historicos poco visitados). El 1.25 evita revalidar justo
    por detras del daemon.
    """
    return config.metricas_refresco_horas() * 3600.0 * 1.25


def _caducada(generado_en: str) -> bool:
    """True si la entrada supera el TTL (o su timestamp es ilegible)."""
    try:
        edad = datetime.fromisoformat(_ahora()) - datetime.fromisoformat(generado_en)
    except (TypeError, ValueError):
        return True
    return edad.total_seconds() > _ttl_segundos()


def _revalidar_en_fondo(tipo: str, rango: str, marca: str | None) -> None:
    """Dispara UN refresco en fondo del combo (idempotente mientras este en curso).

    Stale-while-revalidate: el llamante ya devolvio la entrada caducada (la UI no
    espera); aqui se recalcula en un hilo daemon y la SIGUIENTE lectura ve el dato
    fresco. Un fallo se loguea y no se propaga (quedara la entrada vieja y se
    reintentara en la proxima lectura o barrido).
    """
    clave = _clave(tipo, rango, marca)
    with _LOCKS_GUARDIAN:
        if clave in _SWR_EN_PROCESO:
            return
        _SWR_EN_PROCESO.add(clave)

    def _trabajo() -> None:
        try:
            _refrescar(tipo, rango, marca)
        except Exception:  # noqa: BLE001 -- en fondo: se loguea y la entrada vieja sobrevive
            _log.exception("Fallo el refresco en fondo de %s.", clave)
        finally:
            with _LOCKS_GUARDIAN:
                _SWR_EN_PROCESO.discard(clave)

    threading.Thread(target=_trabajo, name="revalida-metricas", daemon=True).start()


# --------------------------------------------------------------------------- #
# Lectura (lazy fill)                                                          #
# --------------------------------------------------------------------------- #


def _leer(tipo: str, rango: str, marca: str | None) -> dict | None:
    """Entrada de cache `{payload, fuente, generado_en}` o None (sin lazy fill)."""
    return repos.leer_metricas_cache(_clave(tipo, rango, marca))


def _calcular(tipo: str, rango: str, marca: str | None) -> dict:
    """Calcula el dict crudo de `servicio` para un combo (propaga errores de dominio)."""
    if tipo == TIPO_REPORTE:
        return servicio.construir_reporte(rango, marca)
    if tipo == TIPO_ANALISIS:
        return servicio.construir_analisis_diario(rango, marca)
    if tipo == TIPO_PIEZAS:
        return servicio.construir_analitica_piezas(rango, marca)
    if tipo == TIPO_TENDENCIA:
        return servicio.construir_tendencia_diaria(rango, marca)
    if tipo == TIPO_SEGUIDORES:
        return servicio.construir_serie_seguidores(rango, marca)
    if tipo == TIPO_DESGLOSE:
        return servicio.construir_desglose_interacciones(rango, marca)
    if tipo == TIPO_CROSSTAB:
        return servicio.construir_crosstab(rango, marca)
    if tipo == TIPO_CORRELACION:
        return servicio.construir_correlacion_seguidores(rango, marca)
    if tipo == TIPO_PIEZAS_LISTADO:
        # `construir_listado_piezas` devuelve una LISTA; la cache guarda dicts (lee
        # `.get("fuente")`). La envolvemos en un dict con la fuente y el periodo para
        # cumplir el contrato de la cache sin perder ningún campo de las piezas.
        from datetime import date

        piezas = servicio.construir_listado_piezas(rango, marca)
        desde, hasta, _ = servicio.resolver_rango(rango)

        def _iso(d: object) -> str:
            return d.isoformat() if isinstance(d, date) else str(d)

        return {
            "fuente": servicio.nombre_fuente(),
            "periodo": {"desde": _iso(desde), "hasta": _iso(hasta)},
            "piezas": piezas,
            "total": len(piezas),
        }
    if tipo == TIPO_ADS:
        ads = servicio.construir_ads(rango, marca)
        return {"fuente": servicio.nombre_fuente(), "ads": ads, "total": len(ads)}
    raise ValueError(f"Tipo de cache desconocido: {tipo!r}.")


def _refrescar(tipo: str, rango: str, marca: str | None) -> tuple[dict, str]:
    """Recalcula un combo (bypass cache), lo guarda y devuelve `(payload, generado_en)`."""
    payload = _calcular(tipo, rango, marca)
    fuente = payload.get("fuente") or ""
    generado_en = _ahora()
    repos.guardar_metricas_cache(
        _clave(tipo, rango, marca),
        tipo,
        rango,
        _marca_norm(marca),
        payload,
        fuente,
        generado_en,
    )
    # Cada refresco del listado de piezas acumula además un punto en el histórico por pieza
    # (`metricas_pieza_snapshots`), para que la curva del detalle crezca aunque la pieza no
    # se siga por `id_post_metricool`. Best-effort: un fallo aquí no invalida el refresco.
    if tipo == TIPO_PIEZAS_LISTADO:
        try:
            from . import metricas_pieza

            metricas_pieza.registrar_snapshots_de_listado(payload.get("piezas") or [], generado_en)
        except Exception:  # noqa: BLE001 -- el histórico es best-effort; nunca rompe el refresco
            _log.exception("metricas_cache: fallo al acumular el histórico por pieza del listado.")
    return payload, generado_en


def _leer_o_calcular(tipo: str, rango: str, marca: str | None) -> tuple[dict, str]:
    """Devuelve `(payload, generado_en)` desde cache, o lo calcula+guarda si falta.

    Anti-stampede: si el combo está frío, se serializa el lazy fill con un lock por clave
    de combo, de modo que N requests concurrentes del mismo combo disparen UN solo cálculo
    caro (golpe a la API externa) en vez de N. Tras adquirir el lock se RE-LEE la cache por
    si otro hilo ya la rellenó mientras esperábamos (entonces no recalculamos).
    """
    entrada = _leer(tipo, rango, marca)
    if entrada is not None:
        # Caducada: se sirve igual (instantaneo) pero se revalida en fondo, asi ningun
        # combo —tampoco los que no entran al barrido— sirve datos viejos mas de un ciclo.
        if _caducada(entrada["generado_en"]):
            _revalidar_en_fondo(tipo, rango, marca)
        return entrada["payload"], entrada["generado_en"]
    with _lock_combo(_clave(tipo, rango, marca)):
        # Re-lee dentro del lock: otro hilo pudo haber rellenado la cache mientras esperábamos.
        entrada = _leer(tipo, rango, marca)
        if entrada is not None:
            return entrada["payload"], entrada["generado_en"]
        return _refrescar(tipo, rango, marca)


def reporte(rango: str, marca: str | None) -> tuple[dict, str]:
    """Reporte consolidado crudo desde cache (lazy fill). `(dict, generado_en)`."""
    return _leer_o_calcular(TIPO_REPORTE, rango, marca)


def analisis(rango: str, marca: str | None) -> tuple[dict, str]:
    """Analisis diario crudo desde cache (lazy fill). `(dict, generado_en)`."""
    return _leer_o_calcular(TIPO_ANALISIS, rango, marca)


def piezas(rango: str, marca: str | None) -> tuple[dict, str]:
    """Analitica de piezas (stats + top/peores + distribucion) desde cache (lazy fill)."""
    return _leer_o_calcular(TIPO_PIEZAS, rango, marca)


def tendencia(rango: str, marca: str | None) -> tuple[dict, str]:
    """Serie diaria del periodo desde cache (lazy fill). `(dict, generado_en)`."""
    return _leer_o_calcular(TIPO_TENDENCIA, rango, marca)


def seguidores(rango: str, marca: str | None) -> tuple[dict, str]:
    """Serie de seguidores del periodo desde cache (lazy fill). `(dict, generado_en)`."""
    return _leer_o_calcular(TIPO_SEGUIDORES, rango, marca)


def desglose(rango: str, marca: str | None) -> tuple[dict, str]:
    """Desglose de interacciones (marca×red) desde cache (lazy fill)."""
    return _leer_o_calcular(TIPO_DESGLOSE, rango, marca)


def crosstab(rango: str, marca: str | None) -> tuple[dict, str]:
    """Crosstab marca×red×formato desde cache (lazy fill)."""
    return _leer_o_calcular(TIPO_CROSSTAB, rango, marca)


def correlacion(rango: str, marca: str | None) -> tuple[dict, str]:
    """Correlación seguidores↔piezas desde cache (lazy fill)."""
    return _leer_o_calcular(TIPO_CORRELACION, rango, marca)


def piezas_listado(rango: str, marca: str | None) -> tuple[dict, str]:
    """Listado COMPLETO de piezas del periodo desde cache (lazy fill)."""
    return _leer_o_calcular(TIPO_PIEZAS_LISTADO, rango, marca)


# --------------------------------------------------------------------------- #
# Lectura ASÍNCRONA (lazy fill sin bloquear el event loop)                     #
# --------------------------------------------------------------------------- #
#
# Las funciones de arriba son SÍNCRONAS: cuando un combo no está en cache, el lazy
# fill llama a las APIs externas (Metricool/Meta), que pueden tardar decenas de
# segundos. Si eso corre en el hilo del event loop de Starlette, BLOQUEA todas las
# demás peticiones (el front se "traba" al cambiar de filtro a un combo frío). Las
# variantes `*_async` delegan ese trabajo bloqueante al thread-pool por defecto del
# loop (`run_in_executor`), de modo que el endpoint cede el control mientras espera.
# El daemon de refresco sigue usando las versiones síncronas (corre en su propio hilo).


async def _leer_o_calcular_async(tipo: str, rango: str, marca: str | None) -> tuple[dict, str]:
    """Como `_leer_o_calcular` pero sin bloquear el event loop.

    La lectura de cache es barata, pero el lazy fill (cálculo + golpe a la API externa)
    puede tardar; se ejecuta en un hilo del executor para no congelar el loop. La
    propagación de errores es idéntica a la versión síncrona (la captura el endpoint).
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _leer_o_calcular, tipo, rango, marca)


async def reporte_async(rango: str, marca: str | None) -> tuple[dict, str]:
    """Reporte consolidado desde cache (lazy fill) sin bloquear el event loop."""
    return await _leer_o_calcular_async(TIPO_REPORTE, rango, marca)


async def analisis_async(rango: str, marca: str | None) -> tuple[dict, str]:
    """Análisis diario desde cache (lazy fill) sin bloquear el event loop."""
    return await _leer_o_calcular_async(TIPO_ANALISIS, rango, marca)


async def piezas_async(rango: str, marca: str | None) -> tuple[dict, str]:
    """Analítica de piezas desde cache (lazy fill) sin bloquear el event loop."""
    return await _leer_o_calcular_async(TIPO_PIEZAS, rango, marca)


async def tendencia_async(rango: str, marca: str | None) -> tuple[dict, str]:
    """Serie diaria desde cache (lazy fill) sin bloquear el event loop."""
    return await _leer_o_calcular_async(TIPO_TENDENCIA, rango, marca)


async def seguidores_async(rango: str, marca: str | None) -> tuple[dict, str]:
    """Serie de seguidores desde cache (lazy fill) sin bloquear el event loop."""
    return await _leer_o_calcular_async(TIPO_SEGUIDORES, rango, marca)


async def desglose_async(rango: str, marca: str | None) -> tuple[dict, str]:
    """Desglose de interacciones desde cache (lazy fill) sin bloquear el event loop."""
    return await _leer_o_calcular_async(TIPO_DESGLOSE, rango, marca)


async def crosstab_async(rango: str, marca: str | None) -> tuple[dict, str]:
    """Crosstab marca×red×formato desde cache (lazy fill) sin bloquear el event loop."""
    return await _leer_o_calcular_async(TIPO_CROSSTAB, rango, marca)


async def correlacion_async(rango: str, marca: str | None) -> tuple[dict, str]:
    """Correlación seguidores↔piezas desde cache (lazy fill) sin bloquear el event loop."""
    return await _leer_o_calcular_async(TIPO_CORRELACION, rango, marca)


async def piezas_listado_async(rango: str, marca: str | None) -> tuple[dict, str]:
    """Listado COMPLETO de piezas del periodo desde cache (lazy fill) sin bloquear el loop."""
    return await _leer_o_calcular_async(TIPO_PIEZAS_LISTADO, rango, marca)


async def ads_async(rango: str, marca: str | None) -> tuple[dict, str]:
    """Campañas de Ads (inorgánico) del periodo desde cache (lazy fill) sin bloquear el loop."""
    return await _leer_o_calcular_async(TIPO_ADS, rango, marca)


# --------------------------------------------------------------------------- #
# Refresco (combo y barrido completo)                                          #
# --------------------------------------------------------------------------- #


# TODOS los tipos que sirve la cache: el barrido refresca el combo COMPLETO (incluyendo
# seguidores, desgloses, crosstab, correlacion y el listado global). Asi la alerta de ingesta
# y el grafico de seguidores del dashboard ven datos frescos sin quedar congelados.
_TIPOS_BARRIDO = (
    TIPO_REPORTE,
    TIPO_ANALISIS,
    TIPO_PIEZAS,
    TIPO_TENDENCIA,
    TIPO_SEGUIDORES,
    TIPO_DESGLOSE,
    TIPO_CROSSTAB,
    TIPO_CORRELACION,
    TIPO_PIEZAS_LISTADO,
    TIPO_ADS,
)


def refrescar_combo(rango: str, marca: str | None) -> None:
    """Recalcula TODOS los tipos de UN combo (best-effort por tipo).

    Incluye tambien `marca=None` ("todas") al completo: la alerta de ingesta lee el
    listado global y el dashboard sin filtro lee seguidores/desgloses globales; dejarlos
    en lazy-fill los congelaba en su primera version cacheada.
    """
    for tipo in _TIPOS_BARRIDO:
        try:
            _refrescar(tipo, rango, marca)
        except Exception:  # noqa: BLE001 -- un combo que falla no aborta el barrido
            _log.exception(
                "Fallo al refrescar %s (rango=%s, marca=%s).", tipo, rango, marca or "todas"
            )


def _tokens_meses_recientes() -> list[str]:
    """Tokens `mes:AAAA-MM` del mes en curso y el anterior.

    Son los filtros de mes que el equipo mira a diario (el mes corriente y el recien
    cerrado) y cuyas cifras aun se mueven (el engagement de las piezas sigue sumando):
    entran al barrido para estar siempre frescos. Meses mas viejos quedan en lazy-fill
    + revalidacion por TTL al leerse (sus cifras ya apenas cambian).
    """
    hoy = hoy_utc()
    primero_de_mes = hoy.replace(day=1)
    anterior = primero_de_mes - timedelta(days=1)
    return [f"mes:{hoy:%Y-%m}", f"mes:{anterior:%Y-%m}"]


def _combos_a_refrescar(prioritario: tuple[str, str | None] | None) -> list[tuple[str, str | None]]:
    """Lista de combos `(rango, marca)` del barrido, con el prioritario primero.

    Marcas = "todas" (None) + las que la fuente activa puede servir
    (`servicio.cuentas_disponibles`); rangos = `servicio.RANGOS_PRECALENTAR` + los tokens
    de mes recientes (en curso y anterior). Se evita duplicar el combo prioritario.

    Se precalienta solo RANGOS_PRECALENTAR (no todo RANGOS_VALIDOS): excluye los
    duplicados "7d"/"30d" y el costoso "anio". Esos rangos siguen siendo validos; si
    alguien los pide se rellenan en caliente (lazy fill), no antes en cada ciclo.
    """
    marcas: list[str | None] = [None]
    for cid, _nombre in servicio.cuentas_disponibles():
        marcas.append(cid)

    combos: list[tuple[str, str | None]] = []
    vistos: set[tuple[str, str]] = set()

    def _add(rango: str, marca: str | None) -> None:
        clave = (rango, _marca_norm(marca))
        if clave in vistos:
            return
        vistos.add(clave)
        combos.append((rango, marca))

    if prioritario is not None:
        _add(prioritario[0], prioritario[1])
    for rango in [*servicio.RANGOS_PRECALENTAR, *_tokens_meses_recientes()]:
        for marca in marcas:
            _add(rango, marca)
    return combos


def _purgar_obsoletas() -> None:
    """Borra entradas muertas: claves de esquemas viejos y rangos ad-hoc caducados.

    Best-effort (un fallo se loguea y el barrido sigue): es higiene de la tabla, no
    correctitud — las claves viejas ya no se leen (el prefijo de version cambio).
    """
    corte = datetime.fromisoformat(_ahora()) - timedelta(hours=_PURGA_RANGOS_ADHOC_HORAS)
    try:
        n = repos.purgar_metricas_cache(
            f"v{_VERSION_ESQUEMA}:", corte.isoformat(timespec="seconds"), _TIPOS_BARRIDO
        )
        if n:
            _log.info("Purga de cache de metricas: %d entrada(s) obsoleta(s).", n)
    except Exception:  # noqa: BLE001 -- higiene, no correctitud
        _log.exception("Fallo la purga de la cache de metricas.")


def refrescar_todo(prioritario: tuple[str, str | None] | None = None) -> int:
    """Refresca TODOS los combos (todos los tipos), el prioritario primero.

    Devuelve cuantos combos se procesaron. Best-effort por combo (un fallo se loguea
    y no aborta el barrido). Lo llaman el daemon (sin prioritario) y el disparo manual
    (con el combo que se esta viendo como prioritario, para que la UI lo vea antes).
    """
    _purgar_obsoletas()
    combos = _combos_a_refrescar(prioritario)
    for rango, marca in combos:
        refrescar_combo(rango, marca)
    return len(combos)


# --------------------------------------------------------------------------- #
# Estado + disparo del refresco en segundo plano                               #
# --------------------------------------------------------------------------- #


def _snapshot_estado() -> dict:
    """Copia del estado en memoria (bajo lock)."""
    with _LOCK:
        return dict(_ESTADO)


def estado(rango: str | None = None, marca: str | None = None) -> dict:
    """Estado del refresco + `generado_en` del combo consultado (si se pasa rango).

    `generado_en` es el del reporte cacheado de ese combo ("" si aun no hay), que la
    UI muestra como "Actualizado hace X".
    """
    snap = _snapshot_estado()
    generado_en = ""
    if rango:
        entrada = _leer(TIPO_REPORTE, rango, marca)
        if entrada is not None:
            generado_en = entrada["generado_en"]
    return {
        "corriendo": bool(snap["corriendo"]),
        "iniciado_en": snap["iniciado_en"],
        "terminado_en": snap["terminado_en"],
        "ultimo_error": snap["ultimo_error"],
        "generado_en": generado_en,
    }


def _ejecutar_refresco(prioritario: tuple[str, str | None] | None) -> None:
    """Cuerpo del hilo de refresco: barre todo y actualiza el estado al terminar."""
    error = ""
    try:
        n = refrescar_todo(prioritario)
        _log.info("Refresco de metricas completado (%d combos).", n)
    except Exception as e:  # noqa: BLE001 -- registramos y no propagamos (hilo daemon)
        error = str(e)
        _log.exception("Fallo el refresco de metricas.")
    finally:
        with _LOCK:
            _ESTADO["corriendo"] = False
            _ESTADO["terminado_en"] = _ahora()
            _ESTADO["ultimo_error"] = error


def disparar_refresco(rango: str | None = None, marca: str | None = None) -> dict:
    """Arranca un refresco en 2o plano (idempotente). Devuelve el estado.

    Si ya hay uno corriendo, NO arranca otro: devuelve el estado actual. Si no,
    marca `corriendo` y lanza un hilo daemon que prioriza el combo (rango, marca).
    """
    # OJO: `_LOCK` NO es reentrante. Decidimos si arrancar DENTRO del lock, pero
    # construimos la respuesta (que vuelve a pedir el lock vía `estado`) FUERA de él.
    arrancar = False
    with _LOCK:
        if not _ESTADO["corriendo"]:
            _ESTADO["corriendo"] = True
            _ESTADO["iniciado_en"] = _ahora()
            _ESTADO["terminado_en"] = ""
            _ESTADO["ultimo_error"] = ""
            arrancar = True

    if arrancar:
        prioritario = (rango, marca) if rango else None
        hilo = threading.Thread(
            target=_ejecutar_refresco,
            args=(prioritario,),
            name="refresco-metricas",
            daemon=True,
        )
        hilo.start()
    return estado(rango, marca)
