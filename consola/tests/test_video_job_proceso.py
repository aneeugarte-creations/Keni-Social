"""Seam del job GENERICO (no-claude) del motor de video (Ola VIDEO).

Cubre:
  - `encolar_job_proceso` crea la generacion con `tipo=kind` y encola un job de proceso.
  - el worker, al reclamar un job de proceso, despacha al EJECUTOR (monkeypatcheado) y NO toca
    el camino claude.
  - los STUBS de la BASE marcan la generacion en ERROR (sin crashear el worker).
  - el camino claude sigue intacto (un job de hashtags se reconstruye como siempre).
"""

from __future__ import annotations

import pytest

from keni_consola import cola, generaciones, repos, worker
from keni_consola.dominio import jobspec
from keni_consola.motores import estudio_video, transcripcion

_MARCA = "claro-sports"


def test_encolar_job_proceso_crea_generacion_y_job(entorno):
    reg = generaciones.encolar_job_proceso(
        kind=jobspec.PROC_RENDER_VIDEO, params={"composicion_id": "c1"},
        etiqueta="Render", marca=_MARCA,
    )
    assert reg["tipo"] == jobspec.PROC_RENDER_VIDEO
    assert reg["marca"] == _MARCA
    # Hay un job encolado con spec PLANO (kind a nivel raiz, sin prompt/procesar).
    clavado = cola.reclamar("w")
    assert clavado is not None and clavado["gen_id"] == reg["id"]
    assert clavado["spec"]["kind"] == jobspec.PROC_RENDER_VIDEO
    assert clavado["spec"]["composicion_id"] == "c1"
    assert "procesar" not in clavado["spec"]
    assert jobspec.es_kind_proceso(clavado["spec"]) is True
    cola.terminar(clavado["id"])
    # Al terminar el job, la cola COMPARTIDA queda libre (sin contador en memoria que liberar).
    assert repos.contar_jobs_activos() == 0


def test_encolar_job_proceso_kind_invalido_revienta(entorno):
    with pytest.raises(ValueError):
        generaciones.encolar_job_proceso(kind="no-es-proceso", params={})


def test_worker_despacha_job_proceso_al_ejecutor(entorno, monkeypatch):
    """El worker reclama un job de proceso y llama al ejecutor correcto (no a claude)."""
    llamadas: list[tuple[str, dict]] = []

    def _fake_ejecutor(gen_id: str, spec: dict) -> None:
        llamadas.append((gen_id, spec))
        generaciones.actualizar(gen_id, {
            "estado": generaciones.ESTADO_COMPLETADO,
            "resultado": {"media_id": "render/x.mp4"},
            "fecha_fin": generaciones.ahora_iso(),
        })

    # Si tocara el camino claude, lanzar_proc reventaria (no hay binario): garantiza que NO.
    monkeypatch.setattr(
        generaciones.runner, "lanzar_proc",
        lambda *a, **k: pytest.fail("un job de proceso NO debe lanzar claude"),
    )
    monkeypatch.setattr(estudio_video, "ejecutar_render", _fake_ejecutor)

    reg = generaciones.encolar_job_proceso(
        kind=jobspec.PROC_RENDER_VIDEO, params={"composicion_id": "c1"}, marca=_MARCA,
    )
    job = cola.reclamar("w")
    worker.procesar_job(job, "w")

    assert len(llamadas) == 1 and llamadas[0][0] == reg["id"]
    g = generaciones.obtener(reg["id"])
    assert g["estado"] == generaciones.ESTADO_COMPLETADO
    assert g["resultado"] == {"media_id": "render/x.mp4"}
    # El cupo de admision quedo liberado (no se fuga).
    assert repos.contar_jobs_activos() == 0


def test_stub_render_marca_error(entorno):
    """El render marca la generacion en error ante una composicion inexistente (no crashea)."""
    reg = generaciones.encolar_job_proceso(
        kind=jobspec.PROC_RENDER_VIDEO, params={"composicion_id": "c1"}, marca=_MARCA,
    )
    job = cola.reclamar("w")
    worker.procesar_job(job, "w")
    g = generaciones.obtener(reg["id"])
    assert g["estado"] == generaciones.ESTADO_ERROR
    # Ejecutor real (ya no es stub): valida y reporta en español que la composicion no existe.
    assert "composicion" in g["error"].lower()
    assert repos.contar_jobs_activos() == 0


def test_stub_transcripcion_marca_error(entorno):
    """La transcripcion marca la generacion en error ante un job sin media_id (no crashea)."""
    reg = generaciones.encolar_job_proceso(
        kind=jobspec.PROC_TRANSCRIBIR, params={"subtitulo_id": "s1"}, marca=_MARCA,
    )
    job = cola.reclamar("w")
    worker.procesar_job(job, "w")
    g = generaciones.obtener(reg["id"])
    assert g["estado"] == generaciones.ESTADO_ERROR
    # Ejecutor real: el job de transcripcion exige `media_id` (el video a transcribir).
    assert "media_id" in g["error"].lower()


def test_worker_ejecutor_que_revienta_marca_error(entorno, monkeypatch):
    """Si el ejecutor lanza una excepcion, el worker marca error y no se fuga el cupo."""
    def _explota(gen_id: str, spec: dict) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(transcripcion, "ejecutar_transcripcion", _explota)
    reg = generaciones.encolar_job_proceso(kind=jobspec.PROC_TRANSCRIBIR, params={}, marca=_MARCA)
    job = cola.reclamar("w")
    worker.procesar_job(job, "w")
    g = generaciones.obtener(reg["id"])
    assert g["estado"] == generaciones.ESTADO_ERROR
    assert repos.contar_jobs_activos() == 0


def test_camino_claude_sigue_intacto(entorno):
    """Un job claude (hashtags) NO se trata como proceso: su spec NO es kind de proceso."""
    spec = jobspec.construir(prompt="p", procesar=jobspec.construir_hashtags())
    assert jobspec.es_kind_proceso(spec) is False
    # `procesar` sigue reconstruyendose como siempre.
    procesar = jobspec.reconstruir_procesar(spec)
    assert procesar("#uno #dos", None) == {"hashtags": ["#uno", "#dos"]}
