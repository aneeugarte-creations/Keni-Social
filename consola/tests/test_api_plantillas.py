"""Tests de la API Plantillas (/api/plantillas). OFFLINE, DB en tmp.

Cubre: CRUD, validaciones (nombre obligatorio, marca/red allowlist) y resolucion de
nombres legibles.
"""

from __future__ import annotations


def _crear(cliente, **campos):
    base = {"nombre": "Plantilla", "contenido": "Cuerpo"}
    base.update(campos)
    return cliente.post("/api/plantillas", json=base)


def test_crear_y_listar(cliente):
    r = _crear(cliente, marca="unotv", red="x")
    assert r.status_code == 200
    p = r.json()["plantilla"]
    assert p["id"]
    assert p["nombre"] == "Plantilla"
    assert p["contenido"] == "Cuerpo"
    assert p["marca_nombre"] == "UnoTV"
    assert p["red_nombre"] == "X"
    assert len(cliente.get("/api/plantillas").json()["plantillas"]) == 1


def test_crear_sin_marca_ni_red(cliente):
    p = _crear(cliente).json()["plantilla"]
    assert p["marca"] == "" and p["red"] == ""
    assert p["marca_nombre"] == "" and p["red_nombre"] == ""


def test_crear_nombre_vacio_400(cliente):
    assert _crear(cliente, nombre="").status_code == 400
    assert _crear(cliente, nombre="   ").status_code == 400
    assert _crear(cliente, nombre=5).status_code == 400


def test_crear_marca_invalida_400(cliente):
    r = _crear(cliente, marca="marca_falsa")
    assert r.status_code == 400
    assert "marca" in r.json()["error"].lower()


def test_crear_marca_golf_visible(cliente):
    # Catalogo unico: golf YA es marca de pleno derecho, visible como destino de copy.
    r = _crear(cliente, marca="claro-sports-golf")
    assert r.status_code == 200
    assert r.json()["plantilla"]["marca_nombre"] == "Claro Sports Golf"


def test_crear_id_metricas_no_es_id_canonico_400(cliente):
    # La forma id_metricas (guion_bajo) NO es un id canonico => no vale como marca.
    assert _crear(cliente, marca="claro_sports_golf").status_code == 400


def test_crear_red_invalida_400(cliente):
    r = _crear(cliente, red="myspace")
    assert r.status_code == 400
    assert "red" in r.json()["error"].lower()


def test_crear_contenido_no_texto_400(cliente):
    assert _crear(cliente, contenido=5).status_code == 400


def test_actualizar_parcial(cliente):
    pid = _crear(cliente, nombre="Vieja").json()["plantilla"]["id"]
    r = cliente.put(f"/api/plantillas/{pid}", json={"nombre": "Nueva", "contenido": "X"})
    assert r.status_code == 200
    p = r.json()["plantilla"]
    assert p["nombre"] == "Nueva"
    assert p["contenido"] == "X"


def test_actualizar_marca_invalida_400(cliente):
    pid = _crear(cliente).json()["plantilla"]["id"]
    assert cliente.put(f"/api/plantillas/{pid}", json={"marca": "marca_falsa"}).status_code == 400


def test_actualizar_nombre_vacio_400(cliente):
    pid = _crear(cliente).json()["plantilla"]["id"]
    assert cliente.put(f"/api/plantillas/{pid}", json={"nombre": "  "}).status_code == 400


def test_actualizar_sin_campos_400(cliente):
    pid = _crear(cliente).json()["plantilla"]["id"]
    assert cliente.put(f"/api/plantillas/{pid}", json={}).status_code == 400


def test_actualizar_404(cliente):
    assert cliente.put("/api/plantillas/noexiste", json={"nombre": "x"}).status_code == 404


def test_borrar(cliente):
    pid = _crear(cliente).json()["plantilla"]["id"]
    assert cliente.delete(f"/api/plantillas/{pid}").status_code == 200
    assert cliente.delete(f"/api/plantillas/{pid}").status_code == 404
