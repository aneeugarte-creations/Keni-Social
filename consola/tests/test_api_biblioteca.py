"""Tests HTTP del API de la Biblioteca, montando solo sus RUTAS (sin auth/Postgres).

Construye una app Starlette minima con `api.biblioteca.RUTAS` y un TestClient, e intercepta
`encolar_job_claude` (no toca cola ni `claude`). Cubre el CRUD, papelera, editoriales, areas
y el lanzar (contenido / area / errores). El harness completo (auth + Postgres) cubre estos
endpoints en CI; aqui validamos el contrato HTTP de forma aislada.
"""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from keni_consola import generaciones, marcas
from keni_consola.api import biblioteca as api_bib

_MARCA = marcas.opciones()[0][0]


@pytest.fixture
def cliente(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_BIBLIOTECA_DIR", str(tmp_path / "biblioteca"))
    monkeypatch.setenv("KENI_CONSOLA_GENERACIONES", str(tmp_path / "generaciones"))
    monkeypatch.setenv("KENI_SKILLS_CWD", str(tmp_path))
    monkeypatch.setattr(generaciones, "encolar_job_claude", lambda *a, **k: None)
    return TestClient(Starlette(routes=list(api_bib.RUTAS)))


# --------------------------------------------------------------------------- #
# CRUD                                                                         #
# --------------------------------------------------------------------------- #


def test_crear_listar_obtener(cliente):
    r = cliente.post("/api/biblioteca", json={"titulo": "Mi prompt", "tipo": "prompt", "cuerpo": "haz algo"})
    assert r.status_code == 200
    doc = r.json()["documento"]
    assert doc["id"] == "prompt/mi-prompt"

    r = cliente.get("/api/biblioteca", params={"tipo": "prompt"})
    assert [d["id"] for d in r.json()["documentos"]] == ["prompt/mi-prompt"]

    r = cliente.get(f"/api/biblioteca/{doc['id']}")
    assert r.status_code == 200
    assert r.json()["documento"]["cuerpo"].strip() == "haz algo"


def test_crear_sin_titulo_400(cliente):
    r = cliente.post("/api/biblioteca", json={"tipo": "prompt"})
    assert r.status_code == 400


def test_obtener_inexistente_404(cliente):
    r = cliente.get("/api/biblioteca/prompt/no-existe")
    assert r.status_code == 404


def test_guardar_renombra(cliente):
    doc = cliente.post("/api/biblioteca", json={"titulo": "Uno", "tipo": "prompt"}).json()["documento"]
    r = cliente.put(f"/api/biblioteca/{doc['id']}", json={"titulo": "Dos"})
    assert r.status_code == 200
    assert r.json()["documento"]["id"] == "prompt/dos"
    assert cliente.get("/api/biblioteca/prompt/uno").status_code == 404


def test_borrar_papelera_restaurar(cliente):
    doc = cliente.post("/api/biblioteca", json={"titulo": "Tmp", "tipo": "prompt"}).json()["documento"]
    assert cliente.delete(f"/api/biblioteca/{doc['id']}").status_code == 200

    papelera = cliente.get("/api/biblioteca/papelera").json()["papelera"]
    assert len(papelera) == 1 and papelera[0]["origen"] == doc["id"]

    r = cliente.post(f"/api/biblioteca/papelera/{papelera[0]['id']}/restaurar")
    assert r.status_code == 200
    assert r.json()["documento"]["id"] == doc["id"]


# --------------------------------------------------------------------------- #
# Editorial + areas                                                            #
# --------------------------------------------------------------------------- #


def test_editoriales_por_marca(cliente):
    cliente.post("/api/biblioteca", json={"titulo": "Plataformas", "tipo": "editorial", "clase": "plataforma"})
    cliente.post("/api/biblioteca", json={"titulo": "Voz", "tipo": "editorial", "clase": "voz", "marcas": [_MARCA]})
    r = cliente.get("/api/biblioteca/editoriales", params={"marca": _MARCA})
    ids = {d["id"] for d in r.json()["editoriales"]}
    assert ids == {"editorial/plataformas", "editorial/voz"}


def test_areas_disponibles(cliente):
    r = cliente.get("/api/biblioteca/areas")
    ids = {a["id"] for a in r.json()["areas"]}
    assert {"parrilla", "pendientes"} <= ids


# --------------------------------------------------------------------------- #
# Lanzar                                                                       #
# --------------------------------------------------------------------------- #


def test_lanzar_contenido(cliente):
    creado = cliente.post("/api/biblioteca", json={"titulo": "P", "tipo": "prompt", "cuerpo": "resume"})
    doc = creado.json()["documento"]
    r = cliente.post("/api/biblioteca/lanzar", json={
        "prompt_id": doc["id"], "marca": _MARCA,
        "target": {"tipo": "contenido", "valor": "una nota larga"},
    })
    assert r.status_code == 200
    assert r.json()["generacion"]["tipo"] == "prompt"


def test_lanzar_area_degrada_sin_bd(cliente):
    # El proveedor de area lee la BD; sin BD degrada con gracia (no rompe el lanzamiento).
    r = cliente.post("/api/biblioteca/lanzar", json={
        "texto": "redacta", "marca": _MARCA, "target": {"tipo": "area", "valor": "parrilla"},
    })
    assert r.status_code == 200


def test_lanzar_sin_marca_400(cliente):
    r = cliente.post("/api/biblioteca/lanzar", json={"texto": "x", "target": {"tipo": "ninguno"}})
    assert r.status_code == 400


def test_lanzar_area_invalida_400(cliente):
    r = cliente.post("/api/biblioteca/lanzar", json={
        "texto": "x", "marca": _MARCA, "target": {"tipo": "area", "valor": "inexistente"},
    })
    assert r.status_code == 400
