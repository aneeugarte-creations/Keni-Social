"""Tests de la API del Estudio de imagen (/api/imagenes). OFFLINE: nunca se toca la red.

El dominio (`estudio_imagen.generar_variante/editar/expandir`) se mockea; el lanzador de
imagen EJECUTA el callable sincronicamente (`lanzador_imagen_ejecuta`) para cubrir el
pipeline endpoint -> registro de generacion -> resultado.
"""

from __future__ import annotations

from keni_consola.dominio import estudio_imagen

from .conftest import _cliente, lanzador_imagen_ejecuta

# --------------------------------------------------------------------------- #
# POST /api/imagenes/generar                                                  #
# --------------------------------------------------------------------------- #


def test_generar_no_configurado_400(cliente):
    r = cliente.post("/api/imagenes/generar", json={"prompt": "un estadio"})
    assert r.status_code == 400
    assert "no esta configurada" in r.json()["error"].lower() or "configurada" in r.json()["error"]


def test_generar_sin_prompt_400(cliente):
    r = cliente.post("/api/imagenes/generar", json={})
    assert r.status_code == 400


def test_generar_marca_invalida_400(entorno, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "clave")
    cli = _cliente()
    r = cli.post("/api/imagenes/generar", json={"prompt": "x", "marca": "no-existe"})
    assert r.status_code == 400


def test_generar_n_variantes(entorno, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "clave")
    monkeypatch.setattr(
        estudio_imagen, "generar_variante", lambda prompt: {"id": "v.png", "url": "/api/media/v.png"}
    )
    cli = _cliente(lanzar_imagen=lanzador_imagen_ejecuta())
    r = cli.post("/api/imagenes/generar", json={"prompt": "estadio", "marca": "claro-sports", "variantes": 3})
    assert r.status_code == 200
    gens = r.json()["generaciones"]
    assert len(gens) == 3
    assert all(g["estado"] == "completado" for g in gens)
    assert gens[0]["resultado"]["url"] == "/api/media/v.png"


def test_generar_variantes_se_acota(entorno, monkeypatch):
    """variantes fuera de rango se acota a [1, 4]."""
    monkeypatch.setenv("OPENAI_API_KEY", "clave")
    monkeypatch.setattr(estudio_imagen, "generar_variante", lambda prompt: {"id": "v.png", "url": "/x"})
    cli = _cliente(lanzar_imagen=lanzador_imagen_ejecuta())
    r = cli.post("/api/imagenes/generar", json={"prompt": "x", "variantes": 99})
    assert len(r.json()["generaciones"]) == 4


# --------------------------------------------------------------------------- #
# POST /api/imagenes/editar                                                   #
# --------------------------------------------------------------------------- #


def test_editar_op_invalida_400(cliente):
    r = cliente.post("/api/imagenes/editar", json={"imagen": "x.png", "op": "destruir"})
    assert r.status_code == 400


def test_editar_sin_imagen_400(cliente):
    r = cliente.post("/api/imagenes/editar", json={"op": "recortar"})
    assert r.status_code == 400


def test_editar_redimensionar_sin_max_400(cliente):
    r = cliente.post("/api/imagenes/editar", json={"imagen": "x.png", "op": "redimensionar"})
    assert r.status_code == 400


def test_editar_placa_marca_invalida_400(cliente):
    r = cliente.post(
        "/api/imagenes/editar",
        json={"op": "placa", "texto": "Gol", "marca": "piso-15", "formato": "feed"},
    )
    assert r.status_code == 400  # placa solo unotv/claro-sports


def test_editar_recortar_ok(entorno, monkeypatch):
    captado = {}

    def _fake_editar(imagen, op, params):
        captado.update(imagen=imagen, op=op, params=params)
        return {"id": "r.png", "url": "/api/media/r.png", "imagenes": [{"id": "r.png", "url": "/api/media/r.png"}]}

    monkeypatch.setattr(estudio_imagen, "editar", _fake_editar)
    cli = _cliente(lanzar_imagen=lanzador_imagen_ejecuta())
    r = cli.post("/api/imagenes/editar", json={"imagen": "src.png", "op": "recortar", "formato": "cuadrado"})
    assert r.status_code == 200
    gen = r.json()["generacion"]
    assert gen["estado"] == "completado"
    assert gen["resultado"]["id"] == "r.png"
    assert captado["op"] == "recortar"
    assert captado["params"]["formato"] == "cuadrado"


# --------------------------------------------------------------------------- #
# POST /api/imagenes/expandir                                                 #
# --------------------------------------------------------------------------- #


def test_expandir_sin_imagen_400(cliente):
    r = cliente.post("/api/imagenes/expandir", json={"formato": "feed"})
    assert r.status_code == 400


def test_expandir_no_configurado_400(cliente):
    r = cliente.post("/api/imagenes/expandir", json={"imagen": "x.png"})
    assert r.status_code == 400


def test_expandir_ok(entorno, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "clave")
    monkeypatch.setattr(
        estudio_imagen, "expandir",
        lambda imagen, **kw: {"id": "e.png", "url": "/api/media/e.png", "imagenes": []},
    )
    cli = _cliente(lanzar_imagen=lanzador_imagen_ejecuta())
    r = cli.post("/api/imagenes/expandir", json={"imagen": "src.png", "formato": "feed", "strength": 0.4})
    assert r.status_code == 200
    assert r.json()["generacion"]["resultado"]["id"] == "e.png"
