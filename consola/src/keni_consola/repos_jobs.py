"""Repositorio — dominio jobs. Implementación de repos.py (ver barrel `repos.py`)."""
from __future__ import annotations

from ._repos_comun import (
    Any,
    db,
)

# --------------------------------------------------------------------------- #
# Cola de jobs de generacion (OPERACIONAL: persistencia via db.py; #130 Fase 2) #
# --------------------------------------------------------------------------- #
#
# El back ENCOLA y un WORKER (in-proceso en local, servicio aparte en hosted) clava y
# ejecuta `claude -p`. La fachada delega 1:1 en db.py (Postgres).


def encolar_job(gen_id: str, spec: str) -> str:
    return db.encolar_job(gen_id, spec)


def reclamar_job(worker: str = "") -> dict[str, Any] | None:
    return db.reclamar_job(worker)


def terminar_job(job_id: str) -> None:
    return db.terminar_job(job_id)


def cancelar_job(gen_id: str) -> bool:
    return db.cancelar_job(gen_id)


def job_cancelado(job_id: str) -> bool:
    return db.job_cancelado(job_id)
