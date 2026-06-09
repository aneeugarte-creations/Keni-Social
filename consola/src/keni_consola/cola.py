"""Cola de jobs de generacion: el back ENCOLA, un WORKER CLAVA y ejecuta (#130 Fase 2).

Capa fina sobre `repos` (persistencia SQLite local / Postgres hosted) + `dominio.jobspec`
(serializacion del trabajo). Separa el "qué se encola/clava" (aquí) del "cómo se ejecuta"
(`worker.py`) y del "qué post-procesado" (`dominio.jobspec`). El back llama a `encolar`
dentro de la peticion (y vuelve al instante); el worker llama a `reclamar`/`terminar`.

ESTADO DE LA COLA vs ESTADO DEL REGISTRO: la fila de `jobs` es el sobre de DESPACHO
(pendiente|reclamado|terminado, + flag de cancelacion); el registro de generacion
(`generaciones`) sigue siendo la FUENTE DE VERDAD del sondeo de la UI. El worker avanza el
registro igual que antes; la cola solo coordina quién ejecuta qué.
"""

from __future__ import annotations

from typing import Any

from . import config, repos
from .dominio import jobspec, runner


def tope_cola() -> int:
    """Tope TOTAL de jobs en vuelo admitidos: `max_jobs` (corriendo) + `max_cola` (esperando)."""
    return config.max_jobs() + config.max_cola()


def encolar(gen_id: str, spec: dict[str, Any]) -> str:
    """Encola el job de `gen_id` con su `spec` (dict). Devuelve el job id. NO bloquea.

    BACKPRESSURE COMPARTIDO (#130 Fase 2): el gate de admision se decide AQUI contra el conteo
    REAL de la cola en Postgres (`repos.contar_jobs_activos`), no contra un contador en memoria
    por-proceso. Asi el tope lo respetan TODOS los procesos que encolan (back, daemons) y se
    AUTOLIBERA cuando un worker marca un job `terminado`. Si ya hay `tope_cola()` jobs en vuelo,
    rechaza con `ColaLlenaError` (el llamante lo traduce a 429) ANTES de insertar.

    POR QUE CAMBIO: el contador en memoria de `runner.admitir()` solo funcionaba en el perfil
    LOCAL (back y worker en el MISMO proceso). En hosted son contenedores distintos: el back
    sumaba al encolar y el worker restaba al terminar, en memorias separadas, asi que el contador
    del back solo subia y nunca bajaba — tras `max_jobs+max_cola` generaciones el back rechazaba
    TODO para siempre ("Hay demasiadas generaciones en curso") aunque la cola real estuviera vacia.
    """
    if repos.contar_jobs_activos() >= tope_cola():
        raise runner.ColaLlenaError(
            "Hay demasiadas generaciones en curso; inténtalo en unos segundos."
        )
    # La PRIORIDAD de despacho viaja DENTRO del spec (`jobspec.prioridad`): manual > pipeline.
    # Asi los seams inyectables de encolado no cambian de firma y `reclamar_job` puede ordenar
    # por prioridad (un copy manual del equipo no espera detras del lote del pipeline/autogen).
    return repos.encolar_job(gen_id, jobspec.serializar(spec), jobspec.prioridad(spec))


def reclamar(worker: str = "") -> dict[str, Any] | None:
    """Clava UN job pendiente (concurrente-seguro) y devuelve `{id, gen_id, spec}` o None.

    `spec` se devuelve YA DESERIALIZADO (dict). Si el JSON guardado estuviera corrupto, el
    job se devuelve con `spec=None` para que el worker lo marque en error (no lo ejecuta).
    """
    fila = repos.reclamar_job(worker)
    if fila is None:
        return None
    try:
        spec = jobspec.deserializar(fila["spec"])
    except (ValueError, TypeError):
        spec = None
    return {"id": fila["id"], "gen_id": fila["gen_id"], "spec": spec}


def terminar(job_id: str) -> None:
    """Marca un job como terminado (el worker ya fijo el estado terminal del registro)."""
    repos.terminar_job(job_id)


def reencolar(gen_id: str) -> bool:
    """Devuelve el job de `gen_id` a `pendiente` (apagado gracioso): otro worker lo re-reclama."""
    return repos.reencolar_job(gen_id)


def cancelar(gen_id: str) -> bool:
    """Marca el job de `gen_id` como cancelado (cross-proceso). True si habia un job."""
    return repos.cancelar_job(gen_id)


def cancelado(job_id: str) -> bool:
    """True si el job esta marcado como cancelado (lo sondea el worker en ejecucion)."""
    return repos.job_cancelado(job_id)
