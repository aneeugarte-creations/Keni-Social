"""Economia de tokens de la generacion: presupuesto diario, corte automatico y kill switch.

POR QUE EXISTE: la generacion corre `claude -p` con la MISMA suscripcion que usa el equipo
a diario (OAuth, ADR 0001). Una avalancha de noticias puede saturar la cola de jobs de fondo
y AGOTAR los tokens de todos sin que nadie lo vea venir. Este modulo es el guardian:

  - LEDGER: cada generacion CERRADA (terminal) deja su gasto en la tabla `gasto_ia`
    (Postgres, UPSERT por gen_id = idempotente ante reintentos/re-encolados). Lo escribe el
    hook de cierre del almacen de generaciones (`generaciones._almacen`), asi cubre TODOS
    los caminos (claude, imagen, procesos) sin tocar cada lanzador.
  - PRESUPUESTO: `KENI_PRESUPUESTO_TOKENS_DIA` (tokens in+out por dia UTC; 0 = sin limite).
    Editable EN CALIENTE via el store de ajustes (compartido back/worker/daemons por /data).
  - CORTE AUTOMATICO en dos escalones (gradual, no un acantilado):
      * gastado >= presupuesto            -> SOLO_MANUAL: el fondo (pipeline/autogen) se
        deja de encolar y de reclamar; lo manual del equipo sigue.
      * gastado >= presupuesto * (1+m%)   -> AGOTADO: corte TOTAL (tampoco manual). El
        margen `m` es `KENI_PRESUPUESTO_MARGEN_MANUAL` (def 20%).
  - KILL SWITCH humano: `KENI_GENERACION_PAUSADA` (toggle del Monitor) -> PAUSADO: no se
    encola nada y el worker no reclama nada; lo que corre termina y lo encolado espera.

QUIEN PREGUNTA: `cola.encolar` (gate de admision, excepciones 429 claras), `worker._bucle`
(gate de reclamo: la avalancha YA encolada tambien se corta) y la API del monitor
(`/api/actividad/cola` expone `estado()` para humanos y agentes).

CACHE: el worker pregunta en cada iteracion del bucle y el SUM del dia en Postgres no es
gratis. `nivel()`/`estado()` cachean la lectura unos segundos (`_CACHE_TTL_S`); el cierre de
una generacion invalida la cache local (la de OTROS procesos caduca sola por TTL: un corte
puede tardar ese puñado de segundos extra en propagarse, irrelevante a esta escala).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from . import config
from .tiempo import ahora_iso

_log = logging.getLogger("keni_consola.presupuesto_ia")

# Niveles de corte, de mas abierto a mas cerrado. CONTRATO con el monitor/los agentes.
NIVEL_NORMAL = "normal"            # todo corre
NIVEL_SOLO_MANUAL = "solo_manual"  # presupuesto agotado: el fondo se corta, lo manual sigue
NIVEL_AGOTADO = "agotado"          # presupuesto + margen superados: corte TOTAL
NIVEL_PAUSADO = "pausado"          # kill switch humano: corte TOTAL inmediato

# TTL de la cache del gasto del dia (s). El worker sondea en cada iteracion del bucle;
# unos segundos de cache recortan el QPS contra Postgres sin retrasar el corte de forma
# perceptible (el gasto solo crece al CERRARSE generaciones, no token a token).
_CACHE_TTL_S = 3.0

_CACHE_LOCK = threading.Lock()
_CACHE_GASTO: dict[str, Any] | None = None
_CACHE_DIA = ""
_CACHE_EXPIRA = 0.0

# Ultimo nivel observado por ESTE proceso: cada TRANSICION deja un log WARNING (entrar en
# corte) o INFO (volver a normal) — la señal operativa que consume la observabilidad (los
# gates en si son silenciosos: rechazan/esperan sin ruido por peticion).
_ULTIMO_NIVEL: str | None = None


def _hoy_utc() -> str:
    """Dia UTC actual (YYYY-MM-DD), el bucket del presupuesto."""
    return ahora_iso()[:10]


def invalidar_cache() -> None:
    """Invalida la cache del gasto y el nivel observado (cierres de generacion, y tests)."""
    global _CACHE_EXPIRA, _ULTIMO_NIVEL
    with _CACHE_LOCK:
        _CACHE_EXPIRA = 0.0
        _ULTIMO_NIVEL = None


def _gasto_hoy() -> dict[str, Any]:
    """Gasto agregado del dia UTC actual, cacheado `_CACHE_TTL_S` segundos.

    Best-effort: si Postgres no responde, devuelve el ultimo valor cacheado (aunque este
    caducado) o un gasto vacio. PREFERIMOS NO CORTAR ante un blip de la BD: el presupuesto
    es un guardian de economia, no un cinturon de seguridad funcional; un falso corte
    pararia la maquina entera por un parpadeo.
    """
    global _CACHE_GASTO, _CACHE_DIA, _CACHE_EXPIRA
    dia = _hoy_utc()
    with _CACHE_LOCK:
        if _CACHE_GASTO is not None and _CACHE_DIA == dia and time.monotonic() < _CACHE_EXPIRA:
            return _CACHE_GASTO
    from . import repos

    try:
        gasto = repos.gasto_ia_del_dia(dia)
    except Exception:  # noqa: BLE001 -- blip de BD: no cortar por un fallo de lectura
        _log.warning("presupuesto_ia: fallo al leer el gasto del dia", exc_info=True)
        with _CACHE_LOCK:
            if _CACHE_GASTO is not None and _CACHE_DIA == dia:
                return _CACHE_GASTO
        return {"tokens": 0, "tokens_in": 0, "tokens_out": 0, "coste_usd": 0.0, "generaciones": 0}
    with _CACHE_LOCK:
        _CACHE_GASTO = gasto
        _CACHE_DIA = dia
        _CACHE_EXPIRA = time.monotonic() + _CACHE_TTL_S
    return gasto


def nivel() -> str:
    """Nivel de corte VIGENTE (el kill switch manda; luego los escalones del presupuesto).

    Sin presupuesto configurado (0) no hay corte automatico: solo `normal`/`pausado`.
    Cada TRANSICION de nivel deja un log (WARNING al endurecer, INFO al relajar): es la
    señal operativa del corte; los gates por peticion no loguean (serian ruido).
    """
    if config.generacion_pausada():
        return _con_transicion(NIVEL_PAUSADO)
    presupuesto = config.presupuesto_tokens_dia()
    if presupuesto <= 0:
        return _con_transicion(NIVEL_NORMAL)
    gastado = int(_gasto_hoy().get("tokens", 0))
    if gastado >= presupuesto * (1 + config.presupuesto_margen_manual_pct() / 100.0):
        return _con_transicion(NIVEL_AGOTADO)
    if gastado >= presupuesto:
        return _con_transicion(NIVEL_SOLO_MANUAL)
    return _con_transicion(NIVEL_NORMAL)


def bloqueo_admision(nivel_actual: str, *, gasta_tokens: bool, es_fondo: bool) -> str | None:
    """El nivel de corte que BLOQUEA un job con estas características, o None si pasa.

    FUENTE ÚNICA de la regla del presupuesto: la comparten el gate de ADMISIÓN
    (`cola.encolar`, que mapea el nivel devuelto a la excepción 429 correspondiente) y el gate
    de RECLAMO (`worker._bucle`, que la consulta para un job manual y otro de fondo y decide si
    reclamar y con qué prioridad mínima). Así la política vive en UN solo sitio:

      - PAUSADO (kill switch humano): NADA entra/corre, ni manual ni procesos.
      - un job de PROCESO (render ffmpeg / ASR) NO gasta tokens de la suscripción: exento del
        corte por presupuesto (solo lo frena el kill switch).
      - AGOTADO (presupuesto + margen): no pasa NADA que gaste tokens, ni siquiera lo manual.
      - SOLO_MANUAL (presupuesto agotado): el FONDO que gasta tokens cede; lo manual sigue.

    `nivel_actual` es el nivel VIGENTE (`nivel()`), que el llamante calcula UNA vez (para no
    repetir la lectura cacheada del gasto por cada consulta).
    """
    if nivel_actual == NIVEL_PAUSADO:
        return NIVEL_PAUSADO
    if not gasta_tokens:
        return None
    if nivel_actual == NIVEL_AGOTADO:
        return NIVEL_AGOTADO
    if es_fondo and nivel_actual == NIVEL_SOLO_MANUAL:
        return NIVEL_SOLO_MANUAL
    return None


# Severidad creciente de los niveles (para distinguir endurecer de relajar al loguear).
_SEVERIDAD = {NIVEL_NORMAL: 0, NIVEL_SOLO_MANUAL: 1, NIVEL_AGOTADO: 2, NIVEL_PAUSADO: 3}


def _con_transicion(nuevo: str) -> str:
    """Devuelve `nuevo` dejando un log SOLO si el nivel cambio desde la ultima lectura."""
    global _ULTIMO_NIVEL
    with _CACHE_LOCK:
        anterior, _ULTIMO_NIVEL = _ULTIMO_NIVEL, nuevo
    if anterior is None or anterior == nuevo:
        return nuevo
    if _SEVERIDAD.get(nuevo, 0) > _SEVERIDAD.get(anterior, 0):
        _log.warning("presupuesto_ia: corte de generacion %s -> %s", anterior, nuevo)
    else:
        _log.info("presupuesto_ia: generacion reanudada %s -> %s", anterior, nuevo)
    return nuevo


def estado() -> dict[str, Any]:
    """Snapshot COMPLETO para el monitor/los agentes: presupuesto, gasto del dia y nivel.

    Forma (CONTRATO de `/api/actividad/cola`):
      {nivel, pausada, presupuesto_tokens_dia, margen_manual_pct, gastado: {tokens,
       tokens_in, tokens_out, coste_usd, generaciones}, restante_tokens, pct_usado, dia}
    `restante_tokens`/`pct_usado` son None sin presupuesto configurado (sin limite).
    """
    gasto = _gasto_hoy()
    presupuesto = config.presupuesto_tokens_dia()
    gastado = int(gasto.get("tokens", 0))
    restante = max(0, presupuesto - gastado) if presupuesto > 0 else None
    pct = round(100.0 * gastado / presupuesto, 1) if presupuesto > 0 else None
    return {
        "nivel": nivel(),
        "pausada": config.generacion_pausada(),
        "presupuesto_tokens_dia": presupuesto,
        "margen_manual_pct": config.presupuesto_margen_manual_pct(),
        "gastado": gasto,
        "restante_tokens": restante,
        "pct_usado": pct,
        "dia": _hoy_utc(),
    }


def registrar_cierre(registro: dict[str, Any]) -> None:
    """Vuelca al ledger el gasto de una generacion CERRADA (la llama el hook del almacen).

    Extrae tokens/coste de `registro["metricas"]` (los acumula el runner desde el stream de
    `claude`; los jobs de imagen/proceso no los traen y NO dejan fila: no gastan tokens de
    la suscripcion). Best-effort: nunca propaga (el cierre del job no debe fallar por el
    ledger). El `dia` es el del CIERRE (cuando se gasto), no el del encolado.
    """
    gen_id = str(registro.get("id") or "")
    metricas = registro.get("metricas")
    if not gen_id or not isinstance(metricas, dict):
        return
    try:
        tokens_in = int(metricas.get("tokens_in") or 0)
        tokens_out = int(metricas.get("tokens_out") or 0)
        coste = float(metricas.get("total_cost_usd") or 0.0)
    except (TypeError, ValueError):
        return
    if tokens_in <= 0 and tokens_out <= 0 and coste <= 0:
        return  # sin consumo medible (imagen/proceso/fallo temprano): no ensuciar el ledger
    dia = (str(registro.get("fecha_fin") or "") or ahora_iso())[:10]
    from . import repos

    try:
        prompt_chars = int(registro.get("prompt_chars") or 0)
    except (TypeError, ValueError):
        prompt_chars = 0
    try:
        repos.registrar_gasto_ia(
            gen_id,
            dia=dia,
            tipo=str(registro.get("tipo") or ""),
            marca=str(registro.get("marca") or ""),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            coste_usd=coste,
            prompt_chars=prompt_chars,
        )
    except Exception:  # noqa: BLE001 -- el ledger nunca debe romper el cierre de un job
        _log.warning("presupuesto_ia: fallo al registrar el gasto de %s", gen_id, exc_info=True)
        return
    invalidar_cache()
