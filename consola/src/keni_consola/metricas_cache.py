"""Cache de metricas: lectura instantanea + refresco en segundo plano.

PROBLEMA QUE RESUELVE
=====================
La pantalla de Metricas y el Panel recalculaban los reportes EN CADA apertura y en
cada cambio de filtro, golpeando las APIs externas (Metricool/Meta/YouTube/X/TikTok)
en serie por cuenta y plataforma: un consolidado podia tardar 30-120 s. Aqui se
persiste el resultado en Postgres (`metricas_cache`, ver `db.py`) y la UI lo lee
instantaneamente. El dato se refresca por dos vias:

  - Un DAEMON cada N horas (def 4h; `metricas_refresco.py`) — "1 vez al dia importa".
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
  - Estado de refresco EN MEMORIA (un solo proceso del back; el daemon y el POST
    viven en el mismo proceso uvicorn): un Lock + un dict. Se resetea al reiniciar.
  - Conexion por operacion (via `repos`), segura entre hilos (igual que el resto).
"""

from __future__ import annotations

import asyncio
import logging
import threading

from keni_metricas import servicio

from . import repos
from .tiempo import ahora_iso

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
# el dashboard). Es el listado de `servicio.construir_listado_piezas`, no las publicaciones
# de la Consola (eso es `piezas-rendimiento`).
TIPO_PIEZAS_LISTADO = "piezas_listado"

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
    return f"{tipo}:{rango}:{_marca_norm(marca) or 'todas'}"


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
    raise ValueError(f"Tipo de cache desconocido: {tipo!r}.")


def _refrescar(tipo: str, rango: str, marca: str | None) -> tuple[dict, str]:
    """Recalcula un combo (bypass cache), lo guarda y devuelve `(payload, generado_en)`."""
    payload = _calcular(tipo, rango, marca)
    fuente = payload.get("fuente") or "muestra"
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


# --------------------------------------------------------------------------- #
# Refresco (combo y barrido completo)                                          #
# --------------------------------------------------------------------------- #


def refrescar_combo(rango: str, marca: str | None) -> None:
    """Recalcula reporte + analisis + piezas + tendencia de UN combo (best-effort).

    Para una marca CONCRETA refresca también el listado de piezas (`TIPO_PIEZAS_LISTADO`):
    es lo que consumen las Campañas (filtran piezas por hashtag sobre ese listado). Sin
    incluirlo aquí, la primera versión que se cacheaba por lazy-fill se servía para siempre
    —ni una pieza nueva ni un cambio de forma del payload (p.ej. añadir `texto` y los reels)
    aparecían jamás—, y la campaña quedaba en cero. Se OMITE para `marca=None` ("todas"):
    ninguna vista lo pide (las campañas son por-marca) y agregaría TODAS las cuentas, caro e
    inútil; ese combo se queda en lazy-fill bajo demanda.
    """
    tipos = [TIPO_REPORTE, TIPO_ANALISIS, TIPO_PIEZAS, TIPO_TENDENCIA]
    if _marca_norm(marca):
        tipos.append(TIPO_PIEZAS_LISTADO)
    for tipo in tipos:
        try:
            _refrescar(tipo, rango, marca)
        except Exception:  # noqa: BLE001 -- un combo que falla no aborta el barrido
            _log.exception(
                "Fallo al refrescar %s (rango=%s, marca=%s).", tipo, rango, marca or "todas"
            )


def _combos_a_refrescar(prioritario: tuple[str, str | None] | None) -> list[tuple[str, str | None]]:
    """Lista de combos `(rango, marca)` del barrido, con el prioritario primero.

    Marcas = "todas" (None) + las que la fuente activa puede servir
    (`servicio.cuentas_disponibles`); rangos = `servicio.RANGOS_VALIDOS`. Se evita
    duplicar el combo prioritario.
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
    for rango in servicio.RANGOS_VALIDOS:
        for marca in marcas:
            _add(rango, marca)
    return combos


def refrescar_todo(prioritario: tuple[str, str | None] | None = None) -> int:
    """Refresca TODOS los combos (reporte+analisis), el prioritario primero.

    Devuelve cuantos combos se procesaron. Best-effort por combo (un fallo se loguea
    y no aborta el barrido). Lo llaman el daemon (sin prioritario) y el disparo manual
    (con el combo que se esta viendo como prioritario, para que la UI lo vea antes).
    """
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
