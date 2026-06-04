"""Tests de la API de plantillas de diseño (/api/plantillas-diseno). OFFLINE."""

from __future__ import annotations

# Toda plantilla necesita un HUECO DE FOTO explícito (`es_foto`): el doc base lo incluye.
_DOC = {
    "formato": {"w": 1080, "h": 1350, "safe_top": 60, "safe_bottom": 96},
    "capas": [
        {"tipo": "imagen", "objeto": "", "x": 0, "y": 0, "w": 1080, "h": 1350, "z": 0, "es_foto": True},
    ],
}


def test_listar_vacio(cliente):
    r = cliente.get("/api/plantillas-diseno")
    assert r.status_code == 200
    assert r.json() == {"plantillas": []}


def test_crear_y_listar(cliente):
    r = cliente.post("/api/plantillas-diseno", json={
        "marca": "unotv", "nombre": "Última hora", "categoria": "post",
        "documento": _DOC, "lineas": ["linea-nacional", "linea-nacional"],
    })
    assert r.status_code == 200, r.text
    p = r.json()["plantilla"]
    assert p["marca"] == "unotv" and p["nombre"] == "Última hora"
    assert p["documento"]["formato"]["w"] == 1080
    assert p["documento"]["version"] == 1  # validado/normalizado por el dominio
    assert p["lineas"] == ["linea-nacional"]
    assert p["marca_nombre"]

    assert len(cliente.get("/api/plantillas-diseno?marca=unotv").json()["plantillas"]) == 1
    assert len(cliente.get("/api/plantillas-diseno?categoria=post").json()["plantillas"]) == 1
    assert len(cliente.get("/api/plantillas-diseno?categoria=historia").json()["plantillas"]) == 0
    assert len(cliente.get("/api/plantillas-diseno?linea=linea-nacional").json()["plantillas"]) == 1
    assert len(cliente.get("/api/plantillas-diseno?linea=otra").json()["plantillas"]) == 0


def test_crear_documento_invalido_400(cliente):
    r = cliente.post("/api/plantillas-diseno", json={"marca": "unotv", "documento": {"capas": "no-es-lista"}})
    assert r.status_code == 400


def test_crear_sin_documento_400(cliente):
    r = cliente.post("/api/plantillas-diseno", json={"marca": "unotv", "nombre": "x"})
    assert r.status_code == 400


def test_crear_sin_hueco_de_foto_400(cliente):
    # Sin una capa imagen marcada `es_foto`, la plantilla no declara dónde va la foto -> 400.
    sin_hueco = {"formato": {"w": 1080, "h": 1350, "safe_top": 60, "safe_bottom": 96}, "capas": []}
    r = cliente.post("/api/plantillas-diseno", json={"marca": "unotv", "documento": sin_hueco})
    assert r.status_code == 400
    assert "hueco de foto" in r.json()["error"].lower()


def test_crear_marca_invalida_400(cliente):
    r = cliente.post("/api/plantillas-diseno", json={"marca": "no-existe", "documento": _DOC})
    assert r.status_code == 400


def test_obtener_actualizar_borrar(cliente):
    pid = cliente.post("/api/plantillas-diseno", json={
        "marca": "claro-sports", "nombre": "Gol", "documento": _DOC,
    }).json()["plantilla"]["id"]

    assert cliente.get(f"/api/plantillas-diseno/{pid}").json()["plantilla"]["nombre"] == "Gol"
    assert cliente.get("/api/plantillas-diseno/inexistente").status_code == 404

    r = cliente.patch(f"/api/plantillas-diseno/{pid}", json={"nombre": "Gol de México", "categoria": "historia"})
    assert r.status_code == 200
    assert r.json()["plantilla"]["nombre"] == "Gol de México"
    assert r.json()["plantilla"]["categoria"] == "historia"

    # Documento inválido en PATCH -> 400 (no corrompe la plantilla).
    assert cliente.patch(f"/api/plantillas-diseno/{pid}", json={"documento": {"capas": 5}}).status_code == 400

    assert cliente.delete(f"/api/plantillas-diseno/{pid}").status_code == 200
    assert cliente.delete(f"/api/plantillas-diseno/{pid}").status_code == 404
