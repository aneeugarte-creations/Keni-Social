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
        "etiquetas": ["piloto"], "pipelines": ["redactar"], "prioridad": 4,
    })
    assert r.status_code == 200
    doc = r.json()["documento"]
    assert doc["etiquetas"] == ["piloto"]
    assert doc["pipelines"] == ["redactar"]
    assert doc["prioridad"] == 4


def test_listar_devuelve_facetas_y_filtra(cliente):
    cliente.post("/api/texto", json={"titulo": "A", "tipo": "prompt", "etiquetas": ["x"]})
    cliente.post("/api/texto", json={"titulo": "B", "tipo": "prompt"})
    r = cliente.get("/api/texto", params={"etiqueta": "x"})
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
    assert {"redactar", "verificar", "idear"} <= ids
    copy = next(p for p in r.json()["pipelines"] if p["id"] == "redactar")
    assert copy["prompt_base_id"] == "prompt/redactar"


def test_pipeline_preview_ensambla(cliente):
    cliente.post("/api/texto", json={
        "titulo": "Copy base", "tipo": "prompt", "cuerpo": "INSTRUCCION", "rol": "redactar", "pipelines": ["redactar"],
    })
    cliente.post("/api/texto", json={"titulo": "Reglas", "tipo": "editorial", "clase": "reglas", "cuerpo": "REGLA"})
    r = cliente.get(f"/api/texto/pipelines/redactar/preview", params={"marca": _MARCA, "contexto": "CTX"})
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
    cliente.post("/api/texto", json={"titulo": "Solo copy", "tipo": "editorial", "clase": "reglas", "cuerpo": "c", "pipelines": ["redactar"]})
    r_copy = cliente.get("/api/texto/editoriales", params={"marca": _MARCA, "pipeline": "redactar"})
    r_qa = cliente.get("/api/texto/editoriales", params={"marca": _MARCA, "pipeline": "verificar"})
    assert any(d["id"] == "editorial/solo-copy" for d in r_copy.json()["editoriales"])
    assert all(d["id"] != "editorial/solo-copy" for d in r_qa.json()["editoriales"])


# --------------------------------------------------------------------------- #
# Versionado INTENCIONADO (historial = publicaciones; revertir = al borrador)  #
# --------------------------------------------------------------------------- #


def test_historial_vacio_sin_publicaciones_y_revertir_al_borrador(cliente, monkeypatch):
    """Sin Postgres ni publicaciones el historial es VACÍO (es el de publicaciones, no el
    git log de autosaves). `version/{sha}` y `revertir/{sha}` siguen operando por git: el
    sha del commit de creación se lee de `sha_actual`."""
    if shutil.which("git") is None:
        pytest.skip("git no disponible")
    monkeypatch.setenv("KENI_TEXTO_GIT", "1")
    doc = cliente.post("/api/texto", json={"titulo": "Doc", "tipo": "prompt", "cuerpo": "V1"}).json()["documento"]
    cliente.put(f"/api/texto/{doc['id']}", json={"cuerpo": "V2"})

    r = cliente.get(f"/api/texto/{doc['id']}/historial")
    assert r.status_code == 200
    assert r.json()["historial"] == []  # historial = publicaciones; aquí no hay ninguna

    sha_v1 = cliente.get(f"/api/texto/{doc['id']}").json()["documento"]["sha_actual"]
    assert sha_v1  # commit de creación (V1); el autosave de V2 no movió el HEAD
    r = cliente.get(f"/api/texto/{doc['id']}/version/{sha_v1}")
    assert r.status_code == 200
    assert "V1" in r.json()["documento"]["cuerpo"]

    # "Traer al borrador": el working copy vuelve a V1 sin publicar ni añadir versión.
    r = cliente.post(f"/api/texto/{doc['id']}/revertir/{sha_v1}")
    assert r.status_code == 200
    assert "V1" in r.json()["documento"]["cuerpo"]
    assert "V1" in cliente.get(f"/api/texto/{doc['id']}").json()["documento"]["cuerpo"]


def test_historial_doc_inexistente_404(cliente, monkeypatch):
    monkeypatch.setenv("KENI_TEXTO_GIT", "1")
    r = cliente.get("/api/texto/prompt/no-existe/historial")
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Concurrencia optimista (rev / ETag) por HTTP                               #
# --------------------------------------------------------------------------- #


def _crear_doc(cliente):
    r = cliente.post("/api/texto", json={"titulo": "Rev HTTP", "tipo": "prompt", "cuerpo": "uno"})
    assert r.status_code == 200
    return r.json()["documento"]


def test_get_documento_incluye_rev(cliente):
    doc = _crear_doc(cliente)
    assert isinstance(doc.get("rev"), str) and doc["rev"]


def test_put_con_rev_obsoleto_da_409(cliente):
    doc = _crear_doc(cliente)
    rev_viejo = doc["rev"]
    # Otro editor guarda primero (sin rev): mueve el working copy.
    assert cliente.put(f"/api/texto/{doc['id']}", json={"cuerpo": "dos"}).status_code == 200
    # Guardar con el rev viejo: conflicto.
    r = cliente.put(f"/api/texto/{doc['id']}", json={"cuerpo": "tres", "rev": rev_viejo})
    assert r.status_code == 409
    # No se pisó: sigue el contenido del otro editor.
    assert "dos" in cliente.get(f"/api/texto/{doc['id']}").json()["documento"]["cuerpo"]


def test_put_con_rev_correcto_ok(cliente):
    doc = _crear_doc(cliente)
    r = cliente.put(f"/api/texto/{doc['id']}", json={"cuerpo": "dos", "rev": doc["rev"]})
    assert r.status_code == 200
    assert "dos" in r.json()["documento"]["cuerpo"]
    # El rev devuelto es nuevo (cambió tras escribir).
    assert r.json()["documento"]["rev"] != doc["rev"]
