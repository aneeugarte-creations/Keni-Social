"""Config — accesores del dominio jobs. Parte de config.py (ver barrel)."""
from __future__ import annotations

from ._config_comun import (
    _VERDADEROS,
    ENV_GENERACION_PAUSADA,
    ENV_JOBS_MAX_INTENTOS,
    ENV_MAX_JOBS,
    ENV_PRESUPUESTO_MARGEN_MANUAL,
    ENV_PRESUPUESTO_TOKENS_DIA,
    ENV_PROMPT_AVISO_CHARS,
    ENV_PROMPT_MAX_CHARS,
    ENV_WORKER_EXTERNO,
    ENV_WORKER_SONDEO_SEGUNDOS,
    JOBS_MAX_INTENTOS_DEF,
    MAX_JOBS_DEF,
    PRESUPUESTO_MARGEN_MANUAL_DEF,
    PRESUPUESTO_TOKENS_DIA_DEF,
    PROMPT_AVISO_CHARS_DEF,
    PROMPT_MAX_CHARS_DEF,
    WORKER_SONDEO_SEGUNDOS_DEF,
    _crudo,
    _entero,
)

# --------------------------------------------------------------------------- #
# Accesores: concurrencia de jobs                                              #
# --------------------------------------------------------------------------- #


def max_jobs() -> int:
    """Maximo de jobs `claude` simultaneos (`KENI_MAX_JOBS`, def 4, minimo 1).

    Es el UNICO limite de la cola: cuantos `claude -p` corren a la vez. La cola NO tiene
    tope (R-NO-LIMIT); los jobs que no caben simplemente ESPERAN un slot, nada se rechaza
    por tamano de cola. El tope voluntario de presupuesto/pausa vive aparte (`presupuesto_ia`).
    """
    return _entero(ENV_MAX_JOBS, MAX_JOBS_DEF, minimo=1)


# --------------------------------------------------------------------------- #
# Accesores: economia de tokens (presupuesto diario + kill switch)             #
# --------------------------------------------------------------------------- #
#
# La generacion corre `claude -p` con la MISMA suscripcion que usa el equipo a diario: una
# rafaga de jobs de fondo puede agotar los tokens de TODOS sin que nadie lo vea venir.
# Estos knobs (editables en caliente via el store de ajustes) gobiernan el corte automatico
# (`presupuesto_ia.py`) y la pausa manual de la generacion. Todos se leen EN CALIENTE.


def presupuesto_tokens_dia() -> int:
    """Presupuesto DIARIO de tokens de generacion (`KENI_PRESUPUESTO_TOKENS_DIA`, def 0).

    Tokens in+out sumados de todas las generaciones cerradas en el dia UTC. `0` = SIN
    limite (el corte automatico queda apagado; el kill switch manual sigue funcionando).
    """
    return _entero(ENV_PRESUPUESTO_TOKENS_DIA, PRESUPUESTO_TOKENS_DIA_DEF, minimo=0)


def presupuesto_margen_manual_pct() -> int:
    """Margen extra (%) SOLO para lanzamientos manuales tras el corte del fondo.

    `KENI_PRESUPUESTO_MARGEN_MANUAL`, def 20: agotado el presupuesto, lo manual sigue
    funcionando hasta `presupuesto * (1 + margen/100)`; superado eso, corte TOTAL.
    """
    return _entero(ENV_PRESUPUESTO_MARGEN_MANUAL, PRESUPUESTO_MARGEN_MANUAL_DEF, minimo=0)


def jobs_max_intentos() -> int:
    """Intentos maximos de ejecucion de un job de la cola (`KENI_JOBS_MAX_INTENTOS`, def 3).

    Cuenta el intento normal MAS los re-reclamos de un job sin dueño (worker muerto a mitad). Al
    agotarse, el re-reclamo DESCARTA el job (registro en error con motivo `interrumpido`) en
    vez de re-ejecutarlo para siempre: un job que mata al worker (OOM por un prompt enorme,
    bug del runner) no debe convertirse en un crash-loop que ademas consume tokens en cada iteracion.
    """
    return _entero(ENV_JOBS_MAX_INTENTOS, JOBS_MAX_INTENTOS_DEF, minimo=1)


def prompt_max_chars() -> int:
    """Tope DURO del prompt de una generacion (`KENI_PROMPT_MAX_CHARS`, def 200000; 0 = sin tope).

    Economia de contexto: un prompt patologico (feeds concatenados sin criba, un documento
    gigante) consumiria decenas de miles de tokens de la suscripcion compartida en UNA generacion.
    Superarlo rechaza el encolado con un mensaje claro (`PromptExcesivoError` -> 429).
    """
    return _entero(ENV_PROMPT_MAX_CHARS, PROMPT_MAX_CHARS_DEF, minimo=0)


def prompt_aviso_chars() -> int:
    """Umbral de AVISO del tamano del prompt (`KENI_PROMPT_AVISO_CHARS`, def 80000; 0 = sin aviso).

    No corta nada: deja un warning correlacionado al gen-id para detectar la deriva del
    contexto (prompts cada vez mas gordos) ANTES de chocar con el tope duro.
    """
    return _entero(ENV_PROMPT_AVISO_CHARS, PROMPT_AVISO_CHARS_DEF, minimo=0)


def generacion_pausada() -> bool:
    """KILL SWITCH humano de la generacion (`KENI_GENERACION_PAUSADA`, def off).

    Encendido: NO se encola NADA nuevo (fondo ni manual; 429 claro) y el worker DEJA de
    reclamar jobs (lo ya encolado espera; lo que corre termina). Editable en caliente desde
    la UI (store de ajustes compartido por back/worker/daemons via /data): es el control
    manual cuando la suscripcion compartida esta al limite o algo se desboca.
    """
    return _crudo(ENV_GENERACION_PAUSADA).lower() in _VERDADEROS



# --------------------------------------------------------------------------- #
# Accesores: cola + worker de generacion (#130 Fase 2 / ADR 0002 Fase B)       #
# --------------------------------------------------------------------------- #
#
# DOS modos de ejecucion del worker que consume la cola de generacion:
#   - LOCAL / un solo proceso (def): el back arranca el worker EN PROCESO (hilo de
#     fondo). La UX de una sola maquina no cambia: no hace falta un servicio aparte y
#     `claude` esta en el mismo entorno.
#   - HOSTED: un servicio `worker` SEPARADO consume la misma cola. Se activa con
#     `KENI_WORKER_EXTERNO` afirmativo en el back (asi NO arranca su worker in-proceso) y
#     el contenedor `worker` corre `python -m keni_consola.worker` (que SI tiene `claude`).


def worker_externo() -> bool:
    """True si hay un servicio `worker` SEPARADO (hosted) que consume la cola.

    `KENI_WORKER_EXTERNO` afirmativo => el back NO arranca su worker in-proceso (lo hace
    el contenedor `worker`). Def OFF: el back arranca el worker in-proceso (perfil local /
    un solo proceso), preservando la UX de una sola maquina sin servicio aparte.
    """
    return _crudo(ENV_WORKER_EXTERNO).lower() in _VERDADEROS


def worker_sondeo_segundos() -> float:
    """Intervalo de sondeo de la cola por el worker (`KENI_WORKER_SONDEO_SEGUNDOS`, def 0.5, min 0.05)."""
    crudo = _crudo(ENV_WORKER_SONDEO_SEGUNDOS)
    if not crudo:
        return WORKER_SONDEO_SEGUNDOS_DEF
    try:
        valor = float(crudo)
    except ValueError:
        return WORKER_SONDEO_SEGUNDOS_DEF
    return max(0.05, valor)
