"""Tests de la API del almacén de bloques (/api/bloques). OFFLINE."""

from __future__ import annotations

_CAPA = {"tipo": "texto", "x": 40, "y": 1200, "w": 1000, "h": 0, "texto": "GOL", "color": "#FFFFFF"}
_CAPAS = [
    _CAPA,
    {"tipo": "marco", "x": 0, "y": 0, "w": 1080, "h": 200, "forma": "rect", "relleno": "#E30613"},
]


def test_listar_vacio(cliente):
    r = cliente.get("/api/bloques")
    assert r.status_code == 200
    assert r.json() == {"bloques": []}


def test_crear_y_listar(cliente):
    r = cliente.post("/api/bloques", json={
        "marca": "claro-sports", "nombre": "Lower-third gol", "capas": _CAPAS, "categorias": ["l1"],
    })
    assert r.status_code == 200, r.text
    b = r.json()["bloque"]
    assert b["nombre"] == "Lower-third gol" and b["marca"] == "claro-sports"
    assert len(b["capas"]) == 2
    assert all("id" in c for c in b["capas"])  # capas normalizadas por el dominio
    assert b["categorias"] == ["l1"] and b["marca_nombre"]

    assert len(cliente.get("/api/bloques?marca=claro-sports").json()["bloques"]) == 1
    assert len(cliente.get("/api/bloques?marca=unotv").json()["bloques"]) == 0


def test_crear_sin_capas_400(cliente):
    assert cliente.post("/api/bloques", json={"marca": "unotv", "capas": []}).status_code == 400


def test_crear_capa_invalida_400(cliente):
    r = cliente.post("/api/bloques", json={"marca": "unotv", "capas": [{"tipo": "video"}]})
    assert r.status_code == 400


def test_obtener_actualizar_borrar(cliente):
    bid = cliente.post("/api/bloques", json={"marca": "unotv", "nombre": "Pleca", "capas": [_CAPA]}).json()["bloque"]["id"]

    assert cliente.get(f"/api/bloques/{bid}").json()["bloque"]["nombre"] == "Pleca"
    assert cliente.get("/api/bloques/inexistente").status_code == 404

    r = cliente.patch(f"/api/bloques/{bid}", json={"nombre": "Pleca roja"})
    assert r.status_code == 200 and r.json()["bloque"]["nombre"] == "Pleca roja"

    assert cliente.patch(f"/api/bloques/{bid}", json={"capas": []}).status_code == 400

    assert cliente.delete(f"/api/bloques/{bid}").status_code == 200
    assert cliente.delete(f"/api/bloques/{bid}").status_code == 404
