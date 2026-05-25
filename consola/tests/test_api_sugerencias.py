"""Tests de la API Buzón de sugerencias (/api/sugerencias) + el almacén JSON.

OFFLINE. El almacén se aísla en tmp via `KENI_CONSOLA_SUGERENCIAS` (ver conftest).
"""

from __future__ import annotations

import json

import pytest

from keni_consola import sugerencias

# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


def test_listar_siembra_la_idea_de_partida(cliente):
    r = cliente.get("/api/sugerencias")
    assert r.status_code == 200
    cuerpo = r.json()
    # La primera lectura siembra la idea del moderador de YouTube.
    ids = [s["id"] for s in cuerpo["sugerencias"]]
    assert "semilla-moderacion-youtube" in ids
    # Los catálogos para la UI vienen en la respuesta.
    assert cuerpo["categorias"] == list(sugerencias.CATEGORIAS)
    assert cuerpo["estados"] == list(sugerencias.ESTADOS)


def test_crear_y_listar(cliente):
    r = cliente.post(
        "/api/sugerencias",
        json={"titulo": "Exportar métricas a Slack", "detalle": "Un resumen semanal", "categoria": "mejora"},
    )
    assert r.status_code == 200
    s = r.json()["sugerencia"]
    assert s["titulo"] == "Exportar métricas a Slack"
    assert s["categoria"] == "mejora"
    assert s["estado"] == "nueva"
    assert s["id"]
    # Aparece al principio del listado (más reciente primero).
    listado = cliente.get("/api/sugerencias").json()["sugerencias"]
    assert listado[0]["id"] == s["id"]


def test_crear_sin_titulo_400(cliente):
    assert cliente.post("/api/sugerencias", json={"detalle": "sin título"}).status_code == 400
    assert cliente.post("/api/sugerencias", json={"titulo": "   "}).status_code == 400


def test_crear_categoria_invalida_400(cliente):
    r = cliente.post("/api/sugerencias", json={"titulo": "x", "categoria": "inventada"})
    assert r.status_code == 400


def test_crear_categoria_vacia_usa_defecto(cliente):
    r = cliente.post("/api/sugerencias", json={"titulo": "x", "categoria": ""})
    assert r.status_code == 200
    assert r.json()["sugerencia"]["categoria"] == sugerencias.CATEGORIA_DEFECTO


def test_actualizar_estado(cliente):
    sid = cliente.post("/api/sugerencias", json={"titulo": "Idea"}).json()["sugerencia"]["id"]
    r = cliente.patch(f"/api/sugerencias/{sid}", json={"estado": "hecha"})
    assert r.status_code == 200
    assert r.json()["sugerencia"]["estado"] == "hecha"


def test_actualizar_estado_invalido_400(cliente):
    sid = cliente.post("/api/sugerencias", json={"titulo": "Idea"}).json()["sugerencia"]["id"]
    assert cliente.patch(f"/api/sugerencias/{sid}", json={"estado": "zzz"}).status_code == 400


def test_actualizar_inexistente_404(cliente):
    assert cliente.patch("/api/sugerencias/nope", json={"estado": "hecha"}).status_code == 404


def test_borrar(cliente):
    sid = cliente.post("/api/sugerencias", json={"titulo": "Borrable"}).json()["sugerencia"]["id"]
    assert cliente.delete(f"/api/sugerencias/{sid}").status_code == 200
    ids = [s["id"] for s in cliente.get("/api/sugerencias").json()["sugerencias"]]
    assert sid not in ids


def test_borrar_inexistente_404(cliente):
    assert cliente.delete("/api/sugerencias/nope").status_code == 404


# --------------------------------------------------------------------------- #
# Almacén (módulo) — aislamiento y robustez                                    #
# --------------------------------------------------------------------------- #


@pytest.fixture
def store(monkeypatch, tmp_path):
    ruta = tmp_path / "sugerencias.json"
    monkeypatch.setenv("KENI_CONSOLA_SUGERENCIAS", str(ruta))
    return ruta


def test_vaciar_no_vuelve_a_sembrar(store):
    # Tras sembrar y borrar todo, el archivo queda vacío y NO se re-siembra.
    inicial = sugerencias.listar()
    for s in list(inicial):
        sugerencias.borrar(s["id"])
    assert sugerencias.listar() == []


def test_lectura_tolerante_a_json_corrupto(store):
    store.write_text("esto no es json {", encoding="utf-8")
    # No revienta; un archivo corrupto se trata como sin sugerencias utilizables.
    assert sugerencias.listar() == []


def test_persiste_en_disco(store):
    sugerencias.crear("Persistente")
    datos = json.loads(store.read_text(encoding="utf-8"))
    titulos = [s["titulo"] for s in datos["sugerencias"]]
    assert "Persistente" in titulos


def test_crear_titulo_vacio_lanza(store):
    with pytest.raises(ValueError):
        sugerencias.crear("   ")
