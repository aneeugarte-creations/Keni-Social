"""Tests de la API de activos de marca (/api/marca-activos). OFFLINE: sin red.

`media.leer_media` se mockea para simular que el binario existe en el almacen.
"""

from __future__ import annotations

import pytest

from keni_consola import media


@pytest.fixture
def _media_ok(monkeypatch):
    """Simula que cualquier objeto existe en el almacen (bytes no vacios)."""
    monkeypatch.setattr(media, "leer_media", lambda nombre: b"bytes")


def test_listar_vacio(cliente):
    r = cliente.get("/api/marca-activos")
    assert r.status_code == 200
    assert r.json() == {"activos": []}


def test_crear_logo_y_listar(cliente, _media_ok):
    r = cliente.post("/api/marca-activos", json={
        "tipo": "logo", "marca": "claro-sports", "nombre": "Logo principal",
        "objeto": "logo-abc.png", "metadatos": {"fondo_claro": True},
        "categorias": ["cat-ligamx", "cat-ligamx", ""],
    })
    assert r.status_code == 200, r.text
    activo = r.json()["activo"]
    assert activo["tipo"] == "logo" and activo["marca"] == "claro-sports"
    assert activo["nombre"] == "Logo principal"
    assert activo["url"] == "/api/media/logo-abc.png"
    assert activo["metadatos"] == {"fondo_claro": True}
    assert activo["categorias"] == ["cat-ligamx"]  # dedup + sin vacios
    assert activo["marca_nombre"]  # nombre humano de la marca

    # Aparece al listar y se filtra por marca/tipo/categoria.
    assert len(cliente.get("/api/marca-activos").json()["activos"]) == 1
    assert len(cliente.get("/api/marca-activos?tipo=logo").json()["activos"]) == 1
    assert len(cliente.get("/api/marca-activos?tipo=arte").json()["activos"]) == 0
    assert len(cliente.get("/api/marca-activos?marca=claro-sports").json()["activos"]) == 1
    assert len(cliente.get("/api/marca-activos?categoria=cat-ligamx").json()["activos"]) == 1
    assert len(cliente.get("/api/marca-activos?categoria=otra").json()["activos"]) == 0


def test_crear_objeto_inexistente_400(cliente, monkeypatch):
    monkeypatch.setattr(media, "leer_media", lambda nombre: None)
    r = cliente.post("/api/marca-activos", json={"tipo": "arte", "objeto": "x.png"})
    assert r.status_code == 400


def test_crear_paleta_sin_objeto_ok(cliente):
    # `paleta` vive solo en metadatos: no exige binario.
    r = cliente.post("/api/marca-activos", json={
        "tipo": "paleta", "marca": "unotv", "nombre": "Paleta UnoTV",
        "metadatos": {"colores": ["#E30613", "#111315", "#FFFFFF"]},
    })
    assert r.status_code == 200, r.text
    assert r.json()["activo"]["metadatos"]["colores"][0] == "#E30613"
    assert r.json()["activo"]["url"] == ""


def test_crear_tipo_invalido_400(cliente, _media_ok):
    r = cliente.post("/api/marca-activos", json={"tipo": "video", "objeto": "x.png"})
    assert r.status_code == 400


def test_crear_marca_invalida_400(cliente, _media_ok):
    r = cliente.post("/api/marca-activos", json={"tipo": "arte", "objeto": "x.png", "marca": "no-existe"})
    assert r.status_code == 400


def test_actualizar_y_borrar(cliente, _media_ok):
    creado = cliente.post("/api/marca-activos", json={
        "tipo": "icono", "marca": "unotv", "nombre": "Flecha", "objeto": "ico.png",
    }).json()["activo"]
    aid = creado["id"]

    r = cliente.patch(f"/api/marca-activos/{aid}", json={"nombre": "Flecha azul", "categorias": ["l1"]})
    assert r.status_code == 200
    assert r.json()["activo"]["nombre"] == "Flecha azul"
    assert r.json()["activo"]["categorias"] == ["l1"]

    assert cliente.patch("/api/marca-activos/inexistente", json={"nombre": "x"}).status_code == 404

    assert cliente.delete(f"/api/marca-activos/{aid}").status_code == 200
    assert cliente.delete(f"/api/marca-activos/{aid}").status_code == 404
    assert cliente.get("/api/marca-activos").json()["activos"] == []
