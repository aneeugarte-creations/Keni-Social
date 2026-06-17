"""Tests de la API Hashtags (/api/hashtags): grupos reutilizables de hashtags por marca.

Cubre: CRUD de grupos, validaciones (nombre/marca/hashtags) y normalizacion de tags.
"""

from __future__ import annotations

from keni_consola.api import hashtags

# --------------------------------------------------------------------------- #
# CRUD                                                                        #
# --------------------------------------------------------------------------- #


def test_crear_y_listar(cliente):
    r = cliente.post(
        "/api/hashtags", json={"nombre": "Deportes", "marca": "unotv", "hashtags": ["gol", "#liga"]}
    )
    assert r.status_code == 200
    grupo = r.json()["grupo"]
    assert grupo["nombre"] == "Deportes"
    assert grupo["marca"] == "unotv"
    assert grupo["marca_nombre"] == "UnoTV"
    # cada tag normalizado con # inicial
    assert grupo["hashtags"] == ["#gol", "#liga"]
    listado = cliente.get("/api/hashtags").json()["grupos"]
    assert len(listado) == 1


def test_crear_sin_marca_ok(cliente):
    r = cliente.post("/api/hashtags", json={"nombre": "Generales", "hashtags": ["#a"]})
    assert r.status_code == 200
    assert r.json()["grupo"]["marca"] == ""


def test_crear_nombre_vacio_400(cliente):
    assert cliente.post("/api/hashtags", json={"nombre": "  "}).status_code == 400


def test_crear_marca_invalida_400(cliente):
    r = cliente.post("/api/hashtags", json={"nombre": "X", "marca": "marca_falsa"})
    assert r.status_code == 400


def test_crear_hashtags_no_lista_400(cliente):
    r = cliente.post("/api/hashtags", json={"nombre": "X", "hashtags": "no soy lista"})
    assert r.status_code == 400


def test_actualizar_parcial(cliente):
    gid = cliente.post("/api/hashtags", json={"nombre": "V", "hashtags": ["#a"]}).json()["grupo"]["id"]
    r = cliente.put(f"/api/hashtags/{gid}", json={"nombre": "N", "hashtags": ["#x", "#y"]})
    assert r.status_code == 200
    grupo = r.json()["grupo"]
    assert grupo["nombre"] == "N"
    assert grupo["hashtags"] == ["#x", "#y"]


def test_actualizar_404(cliente):
    assert cliente.put("/api/hashtags/noexiste", json={"nombre": "X"}).status_code == 404


def test_actualizar_sin_campos_400(cliente):
    gid = cliente.post("/api/hashtags", json={"nombre": "V"}).json()["grupo"]["id"]
    assert cliente.put(f"/api/hashtags/{gid}", json={}).status_code == 400


def test_borrar(cliente):
    gid = cliente.post("/api/hashtags", json={"nombre": "B"}).json()["grupo"]["id"]
    assert cliente.delete(f"/api/hashtags/{gid}").status_code == 200
    assert cliente.delete(f"/api/hashtags/{gid}").status_code == 404


# --------------------------------------------------------------------------- #
# _normalizar_tag (funcion pura)                                              #
# --------------------------------------------------------------------------- #


def test_normalizar_tag_antepone_almohadilla():
    assert hashtags._normalizar_tag("gol") == "#gol"
    assert hashtags._normalizar_tag("#liga") == "#liga"


def test_normalizar_tag_vacio_es_none():
    assert hashtags._normalizar_tag("   ") is None
    assert hashtags._normalizar_tag("") is None
