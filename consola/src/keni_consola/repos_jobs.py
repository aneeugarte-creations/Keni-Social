"""Repositorio — dominio jobs. Implementación de repos.py (ver barrel `repos.py`)."""
from __future__ import annotations

from ._repos_comun import (
    Any,
    db,
)

# Estados del ciclo de la cola, re-exportados desde la capa de persistencia (fuente unica).
JOB_PENDIENTE = db.JOB_PENDIENTE
JOB_RECLAMADO = db.JOB_RECLAMADO
JOB_TERMINADO = db.JOB_TERMINADO

# --------------------------------------------------------------------------- #
# Cola de jobs de generacion (OPERACIONAL: persistencia via db.py)              #
# --------------------------------------------------------------------------- #
#
# El back ENCOLA y un WORKER (in-proceso en local, servicio aparte en hosted) clava y
# ejecuta `claude -p`. La fachada delega 1:1 en db.py (Postgres).


def encolar_job(gen_id: str, spec: str, prioridad: int = 0) -> str:
    return db.encolar_job(gen_id, spec, prioridad)


def contar_jobs_activos() -> int:
    return db.contar_jobs_activos()


def contar_jobs_por_estado() -> dict[str, int]:
    return db.contar_jobs_por_estado()


def jobs_activos(limite: int = 200) -> list[dict[str, Any]]:
    return db.jobs_activos(limite)


def encolados_por_dia(dias: int = 14) -> list[dict[str, Any]]:
    return db.encolados_por_dia(dias)


def reencolar_job(gen_id: str) -> bool:
    return db.reencolar_job(gen_id)


def reiniciar_intentos_job(gen_id: str) -> bool:
    return db.reiniciar_intentos_job(gen_id)


def reclamar_job(
    worker: str = "",
    *,
    prioridad_minima: int | None = None,
    solo_proceso: bool | None = None,
    kinds_proceso: tuple[str, ...] = (),
    kinds_transcripcion: tuple[str, ...] = (),
    carriles: set[str] | None = None,
) -> dict[str, Any] | None:
    return db.reclamar_job(
        worker, prioridad_minima=prioridad_minima,
        solo_proceso=solo_proceso, kinds_proceso=kinds_proceso,
        kinds_transcripcion=kinds_transcripcion, carriles=carriles,
    )


def terminar_job(job_id: str) -> None:
    return db.terminar_job(job_id)


def priorizar_job(gen_id: str, prioridad: int) -> bool:
    """Sube la prioridad del job pendiente de una generación. Delegado en `db.py`."""
    return db.priorizar_job(gen_id, prioridad)


def max_prioridad_pendiente() -> int:
    return db.max_prioridad_pendiente()


def cancelar_job(gen_id: str) -> bool:
    return db.cancelar_job(gen_id)


def job_cancelado(job_id: str) -> bool:
    return db.job_cancelado(job_id)


def gen_ids_jobs_pendientes() -> set[str]:
    return db.gen_ids_jobs_pendientes()


# Ledger de gasto de IA (economia de tokens; ver `presupuesto_ia.py`).


def registrar_gasto_ia(gen_id: str, **kwargs: Any) -> None:
    return db.registrar_gasto_ia(gen_id, **kwargs)


def gasto_ia_del_dia(dia: str, marca: str = "") -> dict[str, Any]:
    return db.gasto_ia_del_dia(dia, marca)


def gasto_ia_del_dia_por_proceso(dia: str, marca: str = "") -> dict[str, dict[str, Any]]:
    return db.gasto_ia_del_dia_por_proceso(dia, marca)


def gasto_ia_economia_por_proceso(dias: int = 7, marca: str = "") -> dict[str, dict[str, Any]]:
    return db.gasto_ia_economia_por_proceso(dias, marca)


def etapa_economia(proceso: str, tipo: str) -> str:
    """Etapa legible (fase del pipeline) de un job a partir de su `proceso`+`tipo`. Delegado en `db.py`."""
    return db.etapa_economia(proceso, tipo)


def tokens_promedio_por_etapa() -> dict[str, int]:
    return db.tokens_promedio_por_etapa()


def coste_promedio_por_etapa() -> dict[str, float]:
    return db.coste_promedio_por_etapa()


def gasto_ia_por_dia(dias: int = 14) -> list[dict[str, Any]]:
    return db.gasto_ia_por_dia(dias)


def coste_medio_imagen(modelo: str = "", limite: int = 50) -> dict[str, Any]:
    return db.coste_medio_imagen(modelo=modelo, limite=limite)
