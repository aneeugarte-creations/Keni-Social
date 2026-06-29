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


# --------------------------------------------------------------------------- #
# Carril TRANSCRIPCION: servicio dedicado (whisper.cpp), fuera del worker general #
# --------------------------------------------------------------------------- #


def test_carril_routing_transcripcion_es_puro():
    """`jobspec.carril()`: transcripción -> 'transcripcion'; otros procesos -> 'proceso'. SIN BD."""
    tr = jobspec.construir_proceso(jobspec.PROC_TRANSCRIBIR_AUDIO, {"media_id": "audios/x.m4a"})
    sub = jobspec.construir_proceso(jobspec.PROC_TRANSCRIBIR, {"media_id": "videos/x.mp4"})
    render = jobspec.construir_proceso(jobspec.PROC_RENDER_VIDEO, {"composicion_id": "c1"})
    imagen = jobspec.construir_proceso(jobspec.PROC_IMAGEN, {})
    assert jobspec.carril(tr) == jobspec.CARRIL_TRANSCRIPCION
    assert jobspec.carril(sub) == jobspec.CARRIL_TRANSCRIPCION
    assert jobspec.carril(render) == jobspec.CARRIL_PROCESO
    assert jobspec.carril(imagen) == jobspec.CARRIL_PROCESO
    assert jobspec.carril(
        jobspec.construir(prompt="p", procesar=jobspec.construir_prompt_lib())
    ) == jobspec.CARRIL_INFERENCIA


def test_transcripcion_va_al_transcriptor_no_al_worker(entorno):
    """El worker de contenido (inferencia+proceso) IGNORA la transcripción; la clava el transcriptor."""
    g_tr = _gen("transcribir-audio")
    g_render = _gen("render-video")
    cola.encolar(
        g_tr,
        jobspec.construir_proceso(
            jobspec.PROC_TRANSCRIBIR_AUDIO, {"transcripcion_id": "t1", "media_id": "audios/x.m4a"}
        ),
    )
    cola.encolar(
        g_render,
        jobspec.construir_proceso(jobspec.PROC_RENDER_VIDEO, {"composicion_id": "c1"}),
    )

    # El worker de contenido reclama inferencia+proceso: ve el render, NUNCA la transcripción.
    carriles_contenido = {jobspec.CARRIL_INFERENCIA, jobspec.CARRIL_PROCESO}
    job = cola.reclamar("w-cont", carriles=carriles_contenido)
    assert job is not None and job["gen_id"] == g_render
    assert cola.reclamar("w-cont", carriles=carriles_contenido) is None

    # El transcriptor reclama solo el carril `transcripcion`: ve la transcripción.
    job_tr = cola.reclamar("w-trans", carriles={jobspec.CARRIL_TRANSCRIPCION})
    assert job_tr is not None and job_tr["gen_id"] == g_tr


# --------------------------------------------------------------------------- #
# Carriles por CUENTA de Claude (A/B): cada worker monta su CLAUDE_CONFIG_DIR  #
# --------------------------------------------------------------------------- #


def _encolar_investigacion(gen_id: str, carril: str) -> None:
    """Encola un job de INVESTIGACION (claude) en el carril de una cuenta (A/B)."""
    cola.encolar(
        gen_id,
        jobspec.construir(
            prompt="p", procesar=jobspec.construir_prompt_lib(), carril=carril
        ),
    )


def test_worker_b_solo_reclama_carril_cuenta_b(entorno):
    g_a = _gen("prompt")
    g_b = _gen("prompt")
    _encolar_investigacion(g_a, jobspec.CARRIL_CUENTA_A)
    _encolar_investigacion(g_b, jobspec.CARRIL_CUENTA_B)

    # El worker A (inferencia+proceso+cuenta-a) NUNCA ve el de la cuenta B.
    carriles_a = {jobspec.CARRIL_INFERENCIA, jobspec.CARRIL_PROCESO, jobspec.CARRIL_CUENTA_A}
    job_a = cola.reclamar("w-a", carriles=carriles_a)
    assert job_a is not None and job_a["gen_id"] == g_a
    assert cola.reclamar("w-a", carriles=carriles_a) is None

    # El worker B reclama solo `cuenta-b`: ve el suyo.
    job_b = cola.reclamar("w-b", carriles={jobspec.CARRIL_CUENTA_B})
    assert job_b is not None and job_b["gen_id"] == g_b


def test_carril_cuenta_no_lo_roba_el_hilo_de_proceso(entorno):
    # Un job de cuenta (claude, gasta tokens) NO debe caer en el carril exento de proceso:
    # el hilo de proceso (solo_proceso=True) lo IGNORA aunque su carril esté en el conjunto.
    g_b = _gen("prompt")
    _encolar_investigacion(g_b, jobspec.CARRIL_CUENTA_B)
    carriles = {jobspec.CARRIL_INFERENCIA, jobspec.CARRIL_PROCESO, jobspec.CARRIL_CUENTA_B}
    assert cola.reclamar("w-proc", solo_proceso=True, carriles=carriles) is None
    inf = cola.reclamar("w-inf", solo_proceso=False, carriles=carriles)
    assert inf is not None and inf["gen_id"] == g_b
