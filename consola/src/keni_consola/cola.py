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

from . import repos
from .dominio import jobspec


def encolar(gen_id: str, spec: dict[str, Any]) -> str:
    """Encola el job de `gen_id` con su `spec` (dict). Devuelve el job id. NO bloquea."""
    return repos.encolar_job(gen_id, jobspec.serializar(spec))


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


def cancelar(gen_id: str) -> bool:
    """Marca el job de `gen_id` como cancelado (cross-proceso). True si habia un job."""
    return repos.cancelar_job(gen_id)


def cancelado(job_id: str) -> bool:
    """True si el job esta marcado como cancelado (lo sondea el worker en ejecucion)."""
    return repos.job_cancelado(job_id)
