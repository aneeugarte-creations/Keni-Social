"""Tests de la API del kanban de sugerencias (/api/sugerencias).

Requiere el Postgres de pruebas (fixture `cliente`/`entorno`; se salta si no hay). Los
disparadores del motor (discovery/construir/checkpoint/promover) se prueban con la capa de
lanzamiento monkeypatcheada (no encolan jobs reales).
"""

from __future__ import annotations

from keni_consola import sugerencias

# --------------------------------------------------------------------------- #
# CRUD                                                                         #
# --------------------------------------------------------------------------- #


def test_listar_vacio_y_catalogos(cliente):
    r = cliente.get("/api/sugerencias")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["sugerencias"] == []
    assert cuerpo["categorias"] == list(sugerencias.CATEGORIAS)
    assert cuerpo["estados"] == list(sugerencias.ESTADOS)


def test_crear_y_listar(cliente):
    r = cliente.post(
        "/api/sugerencias",
        json={"titulo": "Exportar métricas", "detalle": "resumen", "categoria": "mejora"},
    )
    assert r.status_code == 200
    s = r.json()["sugerencia"]
    assert s["titulo"] == "Exportar métricas"
    assert s["categoria"] == "mejora"
    assert s["estado"] == "nueva"
    assert s["id"]
    listado = cliente.get("/api/sugerencias").json()["sugerencias"]
    assert listado[0]["id"] == s["id"]


def test_crear_sin_titulo_400(cliente):
    assert cliente.post("/api/sugerencias", json={"detalle": "x"}).status_code == 400
    assert cliente.post("/api/sugerencias", json={"titulo": "   "}).status_code == 400


def test_crear_categoria_invalida_400(cliente):
    r = cliente.post("/api/sugerencias", json={"titulo": "x", "categoria": "inventada"})
    assert r.status_code == 400


def test_crear_categoria_vacia_usa_defecto(cliente):
    r = cliente.post("/api/sugerencias", json={"titulo": "x", "categoria": ""})
    assert r.status_code == 200
    assert r.json()["sugerencia"]["categoria"] == sugerencias.CATEGORIA_DEFECTO


def test_patch_estado_valido(cliente):
    sid = cliente.post("/api/sugerencias", json={"titulo": "Idea"}).json()["sugerencia"]["id"]
    r = cliente.patch(f"/api/sugerencias/{sid}", json={"estado": "discovery"})
    assert r.status_code == 200
    assert r.json()["sugerencia"]["estado"] == "discovery"


def test_patch_estado_transicion_invalida_400(cliente):
    sid = cliente.post("/api/sugerencias", json={"titulo": "Idea"}).json()["sugerencia"]["id"]
    # nueva -> hecha no es una transición permitida.
    assert cliente.patch(f"/api/sugerencias/{sid}", json={"estado": "hecha"}).status_code == 400


def test_patch_estado_desconocido_400(cliente):
    sid = cliente.post("/api/sugerencias", json={"titulo": "Idea"}).json()["sugerencia"]["id"]
    assert cliente.patch(f"/api/sugerencias/{sid}", json={"estado": "zzz"}).status_code == 400


def test_patch_texto(cliente):
    sid = cliente.post("/api/sugerencias", json={"titulo": "Idea"}).json()["sugerencia"]["id"]
    r = cliente.patch(f"/api/sugerencias/{sid}", json={"titulo": "Otra", "categoria": "bug"})
    assert r.status_code == 200
    s = r.json()["sugerencia"]
    assert s["titulo"] == "Otra"
    assert s["categoria"] == "bug"


def test_patch_inexistente_404(cliente):
    assert cliente.patch("/api/sugerencias/nope", json={"estado": "discovery"}).status_code == 404


def test_descartar_desde_nueva(cliente):
    sid = cliente.post("/api/sugerencias", json={"titulo": "Idea"}).json()["sugerencia"]["id"]
    r = cliente.patch(f"/api/sugerencias/{sid}", json={"estado": "descartada"})
    assert r.status_code == 200
    assert r.json()["sugerencia"]["estado"] == "descartada"


def test_borrar(cliente):
    sid = cliente.post("/api/sugerencias", json={"titulo": "Borrable"}).json()["sugerencia"]["id"]
    r = cliente.delete(f"/api/sugerencias/{sid}")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    ids = [s["id"] for s in cliente.get("/api/sugerencias").json()["sugerencias"]]
    assert sid not in ids


def test_borrar_inexistente_404(cliente):
    assert cliente.delete("/api/sugerencias/nope").status_code == 404


# --------------------------------------------------------------------------- #
# Disparadores del motor (lanzamiento monkeypatcheado)                        #
# --------------------------------------------------------------------------- #


def test_discovery_encola(cliente, monkeypatch):
    sid = cliente.post("/api/sugerencias", json={"titulo": "Idea"}).json()["sugerencia"]["id"]
    monkeypatch.setattr(sugerencias, "lanzar_discovery", lambda _id: {"id": "gen-x"})
    r = cliente.post(f"/api/sugerencias/{sid}/discovery", json={})
    assert r.status_code == 200
    assert r.json()["generacion"]["id"] == "gen-x"


def test_discovery_inexistente_404(cliente, monkeypatch):
    monkeypatch.setattr(sugerencias, "lanzar_discovery", lambda _id: None)
    assert cliente.post("/api/sugerencias/nope/discovery", json={}).status_code == 404


def test_construir_encola(cliente, monkeypatch):
    sid = cliente.post("/api/sugerencias", json={"titulo": "Idea"}).json()["sugerencia"]["id"]
    capturado = {}

    def fake(_id, *, complejidad=""):
        capturado["complejidad"] = complejidad
        return {"id": "gen-y"}

    monkeypatch.setattr(sugerencias, "lanzar_construir", fake)
    r = cliente.post(f"/api/sugerencias/{sid}/construir", json={"complejidad": "simple"})
    assert r.status_code == 200
    assert r.json()["generacion"]["id"] == "gen-y"
    assert capturado["complejidad"] == "simple"


def test_checkpoint_accion_invalida_400(cliente):
    sid = cliente.post("/api/sugerencias", json={"titulo": "Idea"}).json()["sugerencia"]["id"]
    assert cliente.post(
        f"/api/sugerencias/{sid}/checkpoint", json={"accion": "zzz"}
    ).status_code == 400


def test_checkpoint_cancelar_descarta(cliente, monkeypatch):
    sid = cliente.post("/api/sugerencias", json={"titulo": "Idea"}).json()["sugerencia"]["id"]
    r = cliente.post(f"/api/sugerencias/{sid}/checkpoint", json={"accion": "cancelar"})
    assert r.status_code == 200
    assert r.json()["sugerencia"]["estado"] == "descartada"


def test_promover_desde_estado_invalido_400(cliente):
    sid = cliente.post("/api/sugerencias", json={"titulo": "Idea"}).json()["sugerencia"]["id"]
    # `nueva` no es promovible (solo desde `revision`).
    assert cliente.post(f"/api/sugerencias/{sid}/promover", json={}).status_code == 400


def test_promover_inexistente_404(cliente):
    assert cliente.post("/api/sugerencias/nope/promover", json={}).status_code == 404
