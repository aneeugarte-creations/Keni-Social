"""Config — accesores del dominio jobs. Parte de config.py (ver barrel)."""
from __future__ import annotations

from ._config_comun import (
    _VERDADEROS,
    ENV_MAX_COLA,
    ENV_MAX_JOBS,
    ENV_WORKER_EXTERNO,
    ENV_WORKER_SONDEO_SEGUNDOS,
    MAX_COLA_DEF,
    MAX_JOBS_DEF,
    WORKER_SONDEO_SEGUNDOS_DEF,
    _crudo,
    _entero,
)

# --------------------------------------------------------------------------- #
# Accesores: concurrencia de jobs                                              #
# --------------------------------------------------------------------------- #


def max_jobs() -> int:
    """Maximo de jobs `claude` simultaneos (`KENI_MAX_JOBS`, def 4, minimo 1)."""
    return _entero(ENV_MAX_JOBS, MAX_JOBS_DEF, minimo=1)


def max_cola() -> int:
    """Maximo de jobs ESPERANDO un slot (`KENI_MAX_COLA`, def 16, minimo 0)."""
    return _entero(ENV_MAX_COLA, MAX_COLA_DEF, minimo=0)



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
