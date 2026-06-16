"""Tests HTTP del API de la Texto, montando solo sus RUTAS (sin auth/Postgres).

Construye una app Starlette minima con `api.prompts.RUTAS` y un TestClient, e intercepta
`encolar_job_claude` (no toca cola ni `claude`). Cubre el CRUD, papelera, editoriales y
el lanzar (contenido / area / errores). El harness completo (auth + Postgres) cubre estos
endpoints en CI; aqui validamos el contrato HTTP de forma aislada.
"""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from keni_consola import libprompts, generaciones, marcas
from keni_consola.api import prompts as api_prompts

_MARCA = marcas.opciones()[0][0]


@pytest.fixture
def cliente(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_DATA_DIR", str(tmp_path))  # aisla dir_config() (cwd_generacion)
    monkeypatch.setenv("KENI_PROMPTS_DIR", str(tmp_path / "texto"))
    monkeypatch.setenv("KENI_CONSOLA_GENERACIONES", str(tmp_path / "generaciones"))
    monkeypatch.setattr(generaciones, "encolar_job_claude", lambda *a, **k: None)
    return TestClient(Starlette(routes=list(api_prompts.RUTAS)))


# --------------------------------------------------------------------------- #
# CRUD                                                                         #
# --------------------------------------------------------------------------- #


def test_crear_listar_obtener(cliente):
    r = cliente.post("/api/prompts", json={"titulo": "Mi prompt", "tipo": "prompt", "cuerpo": "haz algo"})
    assert r.status_code == 200
    doc = r.json()["documento"]
    assert doc["id"] == "prompt/mi-prompt"

    r = cliente.get("/api/prompts", params={"tipo": "prompt"})
    assert [d["id"] for d in r.json()["documentos"]] == ["prompt/mi-prompt"]

    r = cliente.get(f"/api/prompts/{doc['id']}")
    assert r.status_code == 200
    assert r.json()["documento"]["cuerpo"].strip() == "haz algo"


def test_crear_y_guardar_descripcion(cliente):
    # La descripcion (metadata humana) entra por POST y PUT y vuelve en el JSON del documento.
    r = cliente.post("/api/prompts", json={
        "titulo": "Validación", "tipo": "prompt", "cuerpo": "Eres el revisor…",
        "descripcion": "Verificación editorial de la fuente.",
    })
    doc = r.json()["documento"]
    assert doc["descripcion"] == "Verificación editorial de la fuente."
    r = cliente.put(f"/api/prompts/{doc['id']}", json={"descripcion": "Otra."})
    assert r.json()["documento"]["descripcion"] == "Otra."
    # Se conserva al releer.
    assert cliente.get(f"/api/prompts/{doc['id']}").json()["documento"]["descripcion"] == "Otra."


def test_doc_incluye_procesos_de_transparencia(cliente):
    # `procesos` (solo lectura) sale del catálogo en código: un prompt CATALOGADO lo trae; uno
    # cualquiera lo trae vacío. Y va en TODOS los documentos del listado.
    cualq = cliente.post("/api/prompts", json={"titulo": "Mi prompt", "tipo": "prompt"}).json()["documento"]
    assert cualq["procesos"] == []
    cat = cliente.post("/api/prompts", json={"titulo": "Verificar", "tipo": "prompt"}).json()["documento"]
    assert cat["id"] == "prompt/verificar"
    # Vocabulario ADR 0011 §5 (verbos C): la etapa se llama "Verificar" (sin "verificación"/"verificación").
    assert cat["procesos"] and any("verificar" in p.lower() for p in cat["procesos"])
    docs = cliente.get("/api/prompts", params={"tipo": "prompt"}).json()["documentos"]
    assert all("procesos" in d for d in docs)


def test_crear_sin_titulo_400(cliente):
    r = cliente.post("/api/prompts", json={"tipo": "prompt"})
    assert r.status_code == 400


def test_obtener_inexistente_404(cliente):
    r = cliente.get("/api/prompts/prompt/no-existe")
    assert r.status_code == 404


def test_guardar_renombra(cliente):
    doc = cliente.post("/api/prompts", json={"titulo": "Uno", "tipo": "prompt"}).json()["documento"]
    r = cliente.put(f"/api/prompts/{doc['id']}", json={"titulo": "Dos"})
    assert r.status_code == 200
    assert r.json()["documento"]["id"] == "prompt/dos"
    assert cliente.get("/api/prompts/prompt/uno").status_code == 404


def test_borrar_papelera_restaurar(cliente):
    doc = cliente.post("/api/prompts", json={"titulo": "Tmp", "tipo": "prompt"}).json()["documento"]
    assert cliente.delete(f"/api/prompts/{doc['id']}").status_code == 200

    papelera = cliente.get("/api/prompts/papelera").json()["papelera"]
    assert len(papelera) == 1 and papelera[0]["origen"] == doc["id"]

    r = cliente.post(f"/api/prompts/papelera/{papelera[0]['id']}/restaurar")
    assert r.status_code == 200
    assert r.json()["documento"]["id"] == doc["id"]


# --------------------------------------------------------------------------- #
# Editorial                                                                    #
# --------------------------------------------------------------------------- #


def test_editoriales_por_marca(cliente):
    cliente.post("/api/prompts", json={"titulo": "Plataformas", "tipo": "editorial", "clase": "plataforma"})
    cliente.post("/api/prompts", json={"titulo": "Voz", "tipo": "editorial", "clase": "voz", "marcas": [_MARCA]})
    r = cliente.get("/api/prompts/editoriales", params={"marca": _MARCA})
    ids = {d["id"] for d in r.json()["editoriales"]}
    assert ids == {"editorial/plataformas", "editorial/voz"}


def test_validacion_marca_incompleta(cliente):
    # Solo plataforma (con cuerpo): faltan marca, voz y tropicalizacion -> incompleta.
    cliente.post(
        "/api/prompts",
        json={"titulo": "Plataformas", "tipo": "editorial", "clase": "plataforma", "cuerpo": "reglas de red"},
    )
    r = cliente.get("/api/prompts/validacion", params={"marca": _MARCA})
    datos = r.json()
    assert datos["completa"] is False
    assert set(datos["faltan"]) == {"marca", "voz", "tropicalizacion"}
    assert datos["recomendacion"]  # frase de ayuda no vacia


def test_validacion_marca_completa(cliente):
    # Los 4 pilares con cuerpo -> completa, sin recomendacion.
    for clase, marcas_doc in [
        ("plataforma", None),
        ("tropicalizacion", None),
        ("marca", [_MARCA]),
        ("voz", [_MARCA]),
    ]:
        cuerpo = {"titulo": clase, "tipo": "editorial", "clase": clase, "cuerpo": f"contenido {clase}"}
        if marcas_doc:
            cuerpo["marcas"] = marcas_doc
        cliente.post("/api/prompts", json=cuerpo)
    r = cliente.get("/api/prompts/validacion", params={"marca": _MARCA})
    datos = r.json()
    assert datos["completa"] is True
    assert datos["faltan"] == []
    assert datos["recomendacion"] == ""


def test_validacion_sin_marca_pide_marca(cliente):
    r = cliente.get("/api/prompts/validacion")
    datos = r.json()
    assert datos["completa"] is False
    assert "marca" in datos["faltan"] and "voz" in datos["faltan"]
    assert "marca" in datos["recomendacion"].lower()


def test_validacion_cuerpo_vacio_no_cubre_pilar(cliente):
    # Un editorial SIN cuerpo no cuenta como pilar cubierto.
    cliente.post("/api/prompts", json={"titulo": "Voz", "tipo": "editorial", "clase": "voz", "marcas": [_MARCA]})
    r = cliente.get("/api/prompts/validacion", params={"marca": _MARCA})
    assert "voz" in r.json()["faltan"]


# --------------------------------------------------------------------------- #
# Lanzar                                                                       #
# --------------------------------------------------------------------------- #


def test_lanzar_contenido(cliente):
    creado = cliente.post("/api/prompts", json={"titulo": "P", "tipo": "prompt", "cuerpo": "resume"})
    doc = creado.json()["documento"]
    r = cliente.post("/api/prompts/lanzar", json={
        "prompt_id": doc["id"], "marca": _MARCA,
        "target": {"tipo": "contenido", "valor": "una nota larga"},
    })
    assert r.status_code == 200
    assert r.json()["generacion"]["tipo"] == "prompt"


def test_lanzar_area_degrada_sin_bd(cliente):
    # El proveedor de area lee la BD; sin BD degrada con gracia (no rompe el lanzamiento).
    r = cliente.post("/api/prompts/lanzar", json={
        "texto": "redacta", "marca": _MARCA, "target": {"tipo": "area", "valor": "parrilla"},
    })
    assert r.status_code == 200


def test_lanzar_sin_marca_400(cliente):
    r = cliente.post("/api/prompts/lanzar", json={"texto": "x", "target": {"tipo": "ninguno"}})
    assert r.status_code == 400


def test_lanzar_area_invalida_400(cliente):
    r = cliente.post("/api/prompts/lanzar", json={
        "texto": "x", "marca": _MARCA, "target": {"tipo": "area", "valor": "inexistente"},
    })
    assert r.status_code == 400


def test_lanzar_prompt_piezas_con_redes(monkeypatch, tmp_path):
    """Un prompt salida=piezas + `redes` en el body crea el spec de COPY (borradores)."""
    monkeypatch.setenv("KENI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KENI_PROMPTS_DIR", str(tmp_path / "texto"))
    monkeypatch.setenv("KENI_CONSOLA_GENERACIONES", str(tmp_path / "generaciones"))
    capturado: dict = {}
    monkeypatch.setattr(
        generaciones, "encolar_job_claude",
        lambda *a, **k: capturado.update(k),
    )
    cli = TestClient(Starlette(routes=list(api_prompts.RUTAS)))
    creado = cli.post("/api/prompts", json={
        "titulo": "Copy por red", "tipo": "prompt", "cuerpo": "haz copy por red",
    })
    doc_id = creado.json()["documento"]["id"]
    # Marca el prompt como salida=piezas (como haria el editor de la Texto).
    ruta = libprompts._ruta_de_id(doc_id)
    ruta.write_text(
        ruta.read_text(encoding="utf-8").replace("tipo: prompt", "tipo: prompt\nsalida: piezas"),
        encoding="utf-8",
    )

    r = cli.post("/api/prompts/lanzar", json={
        "prompt_id": doc_id, "marca": _MARCA, "redes": ["instagram", "x"],
        "target": {"tipo": "contenido", "valor": "una nota"},
    })
    assert r.status_code == 200
    assert r.json()["generacion"]["tipo"] == "copy"
    assert capturado["spec"]["procesar"]["kind"] == "copy"
    assert capturado["spec"]["procesar"]["redes_ids"] == ["instagram", "x"]
