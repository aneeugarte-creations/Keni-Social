"""Tests del CARRIL `dev` en la cola: `reclamar(carriles=...)` separa los pools de workers.

Requiere el Postgres de pruebas (fixture `entorno`; se salta si no hay). Un job de DESARROLLO
(carril=dev) solo lo clava el pool dev; el worker de contenido (inferencia+proceso) lo IGNORA.
"""

from __future__ import annotations

from keni_consola import cola, generaciones
from keni_consola.dominio import jobspec

_MARCA = "unotv"


def _gen(tipo: str) -> str:
    return generaciones.crear({"tipo": tipo, "marca": _MARCA, "etiqueta": "X"})["id"]


def test_worker_dev_solo_reclama_carril_dev(entorno):
    g_dev = _gen("dev-fase")
    g_inf = _gen("prompt")
    cola.encolar(
        g_dev,
        jobspec.construir(
            prompt="p", procesar=jobspec.construir_dev_fase(
                sugerencia_id="s1", fase="build", modelo="opus"
            ),
            carril=jobspec.CARRIL_DEV,
        ),
    )
    cola.encolar(g_inf, jobspec.construir(prompt="p", procesar=jobspec.construir_prompt_lib()))

    # El pool dev solo ve el job dev.
    dev = cola.reclamar("w-dev", carriles={jobspec.CARRIL_DEV})
    assert dev is not None
    assert dev["gen_id"] == g_dev
    assert cola.reclamar("w-dev", carriles={jobspec.CARRIL_DEV}) is None


def test_worker_contenido_excluye_carril_dev(entorno):
    g_dev = _gen("dev-discovery")
    g_inf = _gen("prompt")
    cola.encolar(
        g_dev,
        jobspec.construir(
            prompt="p", procesar=jobspec.construir_dev_discovery(sugerencia_id="s2"),
            carril=jobspec.CARRIL_DEV,
        ),
    )
    cola.encolar(g_inf, jobspec.construir(prompt="p", procesar=jobspec.construir_prompt_lib()))

    # El worker de contenido reclama inferencia+proceso: ve el de inferencia, nunca el dev.
    carriles_contenido = {jobspec.CARRIL_INFERENCIA, jobspec.CARRIL_PROCESO}
    job = cola.reclamar("w-cont", carriles=carriles_contenido)
    assert job is not None
    assert job["gen_id"] == g_inf
    assert cola.reclamar("w-cont", carriles=carriles_contenido) is None


def test_carriles_none_reclama_cualquiera(entorno):
    g_dev = _gen("dev-fase")
    cola.encolar(
        g_dev,
        jobspec.construir(
            prompt="p", procesar=jobspec.construir_dev_fase(
                sugerencia_id="s3", fase="analyze", modelo="sonnet"
            ),
            carril=jobspec.CARRIL_DEV,
        ),
    )
    # Sin filtro de carril (retrocompatible) se clava cualquier job, incluido el dev.
    job = cola.reclamar("w-any")
    assert job is not None
    assert job["gen_id"] == g_dev
