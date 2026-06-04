"""Tests del editor anclado a una pieza + versionado (/api/editor/pieza/...). OFFLINE.

El render (Node) se mockea; se cubre cargar/guardar/versionar y que la imagen de la pieza se fija.
"""

from __future__ import annotations

import pytest

from keni_consola import repos
from keni_consola.dominio import estudio_imagen

_DOC = {"formato": {"w": 1080, "h": 1350, "safe_top": 60, "safe_bottom": 96}, "capas": []}


@pytest.fixture
def _render_mock(monkeypatch):
    monkeypatch.setattr(
        estudio_imagen, "renderizar_documento",
        lambda doc, **kw: {"id": "render.png", "url": "/api/media/render.png"},
    )


def _pieza(entorno):
    """Crea una fila por plataforma y devuelve (contenido_id, plataforma_id)."""
    plat = repos.crear_contenido_plataforma(contenido_id="c1", red="facebook")
    return "c1", plat["id"]


def test_pieza_documento_vacio(cliente, entorno):
    _cid, pid = _pieza(entorno)
    r = cliente.get(f"/api/editor/pieza/c1/{pid}")
    assert r.status_code == 200
    # Pieza sin editar: sin documento ni versiones. Incluye los `bindings` reales (titular/pleca):
    # vacíos aquí porque la fila no tiene copy_in y la marca de prueba no fija etiqueta_default.
    assert r.json() == {
        "documento": None,
        "versiones": 0,
        "bindings": {"copy_in": "", "etiqueta_default": ""},
    }


def test_guardar_versiona_y_fija_imagen(cliente, entorno, _render_mock):
    _cid, pid = _pieza(entorno)

    r = cliente.post(f"/api/editor/pieza/c1/{pid}", json={"documento": _DOC})
    assert r.status_code == 200, r.text
    assert r.json() == {"id": "render.png", "url": "/api/media/render.png", "version": 1}

    # La imagen de la pieza quedó fijada al PNG renderizado.
    assert repos.obtener_contenido_plataforma(pid)["imagen"] == "render.png"

    # Cargar ahora devuelve el documento y 1 versión.
    cargado = cliente.get(f"/api/editor/pieza/c1/{pid}").json()
    assert cargado["versiones"] == 1
    assert cargado["documento"]["formato"]["w"] == 1080

    # Guardar otra vez incrementa la versión.
    assert cliente.post(f"/api/editor/pieza/c1/{pid}", json={"documento": _DOC}).json()["version"] == 2

    versiones = cliente.get(f"/api/editor/pieza/c1/{pid}/versiones").json()["versiones"]
    assert [v["version"] for v in versiones] == [2, 1]  # más reciente primero
    assert versiones[0]["render_url"] == "/api/media/render.png"


def test_guardar_sin_documento_400(cliente, entorno, _render_mock):
    _cid, pid = _pieza(entorno)
    assert cliente.post(f"/api/editor/pieza/c1/{pid}", json={}).status_code == 400


def test_guardar_pieza_inexistente_404(cliente, entorno, _render_mock):
    r = cliente.post("/api/editor/pieza/c1/no-existe", json={"documento": _DOC})
    assert r.status_code == 404
