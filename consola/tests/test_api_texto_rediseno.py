"""Tests HTTP de los endpoints NUEVOS de la Texto (rediseno): facetas, registro de
pipelines, preview del prompt ensamblado y versionado git.

Misma estrategia que `test_api_texto`: monta solo `api.texto.RUTAS` con un
TestClient aislado (sin auth/Postgres). El versionado git esta apagado por la suite; los
tests que lo ejercitan lo reactivan via env antes de pegarle al endpoint.
"""

from __future__ import annotations

import shutil

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from keni_consola import generaciones, marcas
from keni_consola.api import texto as api_texto

_MARCA = marcas.opciones()[0][0]


@pytest.fixture
def cliente(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KENI_TEXTO_DIR", str(tmp_path / "texto"))
    monkeypatch.setenv("KENI_CONSOLA_GENERACIONES", str(tmp_path / "generaciones"))
    monkeypatch.setattr(generaciones, "encolar_job_claude", lambda *a, **k: None)
    return TestClient(Starlette(routes=list(api_texto.RUTAS)))


# --------------------------------------------------------------------------- #
# Campos nuevos + facetas                                                     #
# --------------------------------------------------------------------------- #


def test_crear_con_campos_nuevos(cliente):
    r = cliente.post("/api/texto", json={
        "titulo": "Voz", "tipo": "editorial", "clase": "voz", "marcas": [_MARCA],
        "estado": "borrador", "etiquetas": ["piloto"], "pipelines": ["copy"], "prioridad": 4,
    })
    assert r.status_code == 200
    doc = r.json()["documento"]
    assert doc["estado"] == "borrador"
    assert doc["etiquetas"] == ["piloto"]
    assert doc["pipelines"] == ["copy"]
    assert doc["prioridad"] == 4


def test_listar_devuelve_facetas_y_filtra(cliente):
    cliente.post("/api/texto", json={"titulo": "A", "tipo": "prompt", "etiquetas": ["x"]})
    cliente.post("/api/texto", json={"titulo": "B", "tipo": "prompt", "estado": "archivado"})
    r = cliente.get("/api/texto", params={"estado": "activo"})
    datos = r.json()
    assert [d["id"] for d in datos["documentos"]] == ["prompt/a"]
    assert "facetas" in datos
    assert any(e["valor"] == "x" for e in datos["facetas"]["etiquetas"])


def test_crear_pipeline_invalido_400(cliente):
    r = cliente.post("/api/texto", json={
        "titulo": "X", "tipo": "editorial", "clase": "reglas", "pipelines": ["nope"],
    })
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Registro de pipelines + preview                                            #
# --------------------------------------------------------------------------- #


def test_pipelines_listar(cliente):
    r = cliente.get("/api/texto/pipelines")
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()["pipelines"]}
    assert {"copy", "qa", "evergreen"} <= ids
    copy = next(p for p in r.json()["pipelines"] if p["id"] == "copy")
    assert copy["prompt_base_id"] == "prompt/copy-desde-nota"


def test_pipeline_preview_ensambla(cliente):
    cliente.post("/api/texto", json={
        "titulo": "Copy base", "tipo": "prompt", "cuerpo": "INSTRUCCION", "rol": "copy", "pipelines": ["copy"],
    })
    cliente.post("/api/texto", json={"titulo": "Reglas", "tipo": "editorial", "clase": "reglas", "cuerpo": "REGLA"})
    r = cliente.get(f"/api/texto/pipelines/copy/preview", params={"marca": _MARCA, "contexto": "CTX"})
    assert r.status_code == 200
    prev = r.json()
    assert prev["falta_base"] is False
    assert "INSTRUCCION" in prev["prompt_efectivo"]
    assert "REGLA" in prev["prompt_efectivo"]
    assert "CTX" in prev["prompt_efectivo"]


def test_pipeline_preview_desconocido_404(cliente):
    r = cliente.get("/api/texto/pipelines/nope/preview", params={"marca": _MARCA})
    assert r.status_code == 404


def test_editoriales_filtra_por_pipeline(cliente):
    cliente.post("/api/texto", json={"titulo": "Solo copy", "tipo": "editorial", "clase": "reglas", "cuerpo": "c", "pipelines": ["copy"]})
    r_copy = cliente.get("/api/texto/editoriales", params={"marca": _MARCA, "pipeline": "copy"})
    r_qa = cliente.get("/api/texto/editoriales", params={"marca": _MARCA, "pipeline": "qa"})
    assert any(d["id"] == "editorial/solo-copy" for d in r_copy.json()["editoriales"])
    assert all(d["id"] != "editorial/solo-copy" for d in r_qa.json()["editoriales"])


# --------------------------------------------------------------------------- #
# Versionado git                                                             #
# --------------------------------------------------------------------------- #


def test_historial_y_revertir(cliente, monkeypatch):
    if shutil.which("git") is None:
        pytest.skip("git no disponible")
    monkeypatch.setenv("KENI_TEXTO_GIT", "1")
    doc = cliente.post("/api/texto", json={"titulo": "Doc", "tipo": "prompt", "cuerpo": "V1"}).json()["documento"]
    cliente.put(f"/api/texto/{doc['id']}", json={"cuerpo": "V2"})

    r = cliente.get(f"/api/texto/{doc['id']}/historial")
    assert r.status_code == 200
    hist = r.json()["historial"]
    assert len(hist) >= 2

    sha = hist[-1]["sha"]
    r = cliente.get(f"/api/texto/{doc['id']}/version/{sha}")
    assert r.status_code == 200
    assert "V1" in r.json()["documento"]["cuerpo"]

    r = cliente.post(f"/api/texto/{doc['id']}/revertir/{sha}")
    assert r.status_code == 200
    assert "V1" in r.json()["documento"]["cuerpo"]


def test_historial_doc_inexistente_404(cliente, monkeypatch):
    monkeypatch.setenv("KENI_TEXTO_GIT", "1")
    r = cliente.get("/api/texto/prompt/no-existe/historial")
    assert r.status_code == 404
