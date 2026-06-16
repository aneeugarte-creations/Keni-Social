"""Tests del editor anclado a una pieza + versionado (/api/imagen/pieza/...). OFFLINE.

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


def _pieza(entorno, publicacion_id="c1"):
    """Crea el `contenido` padre + una fila por plataforma; devuelve (publicacion_id, pieza_id).

    El padre se crea explicito (con su id) porque `pieza.publicacion_id` es ahora
    una FK real a `contenido(id)` (ADR 0012): una fila por plataforma sin padre se rechaza.
    """
    repos.crear_publicacion(id=publicacion_id, titulo="pieza de prueba")
    plat = repos.crear_pieza_fila(publicacion_id=publicacion_id, red="facebook")
    return publicacion_id, plat["id"]


def test_pieza_documento_vacio(cliente, entorno):
    _cid, pid = _pieza(entorno)
    r = cliente.get(f"/api/imagen/pieza/c1/{pid}")
    assert r.status_code == 200
    # Pieza sin editar: sin documento ni versiones. Incluye los `bindings` reales (titular/pleca):
    # vacíos aquí porque la fila no tiene copy_in y la marca de prueba no fija etiqueta_default.
    # `plantilla`/`fotos` salen vacías: la pieza no tiene plantilla de estudio ni fotos.
    assert r.json() == {
        "documento": None,
        "versiones": 0,
        "bindings": {"copy_in": "", "etiqueta_default": ""},
        "plantilla": None,
        "fotos": [],
    }


def test_pieza_sin_version_trae_plantilla_efectiva_y_fotos(cliente, entorno, monkeypatch):
    """Sin versión guardada, el GET trae la plantilla EFECTIVA (la misma que compone el feed) y las
    fotos por hueco, para que el editor arranque del documento REAL con su foto (no la plantilla
    genérica de la marca ni una muestra)."""
    import json

    _cid, pid = _pieza(entorno)
    doc = {
        "formato": {"w": 1080, "h": 1350, "safe_top": 60, "safe_bottom": 96},
        "capas": [{"tipo": "imagen", "es_foto": True, "x": 0, "y": 0, "w": 1080, "h": 1350}],
    }
    pub = {
        "id": pid, "marca": "unotv", "plantilla_diseno_id": "pl-1",
        "foto": "", "foto_encuadre": "",
        "fotos": json.dumps([{"objeto": "foto/a.jpg", "foco": [0.4, 0.6], "zoom": 1.2}]),
    }
    monkeypatch.setattr(repos, "obtener_pieza", lambda _id: pub)
    monkeypatch.setattr(repos, "obtener_plantilla_diseno", lambda _id: {"documento": json.dumps(doc)})

    r = cliente.get(f"/api/imagen/pieza/c1/{pid}").json()
    assert r["documento"] is None  # aún sin versión guardada
    assert r["plantilla"]["capas"][0]["es_foto"] is True  # la plantilla efectiva, no la genérica
    assert r["fotos"] == [{"objeto": "foto/a.jpg", "foco": [0.4, 0.6], "zoom": 1.2}]


def test_guardar_versiona_y_fija_imagen(cliente, entorno, _render_mock):
    _cid, pid = _pieza(entorno)

    r = cliente.post(f"/api/imagen/pieza/c1/{pid}", json={"documento": _DOC})
    assert r.status_code == 200, r.text
    assert r.json() == {"id": "render.png", "url": "/api/media/render.png", "version": 1}

    # La imagen de la pieza quedó fijada al PNG renderizado.
    assert repos.obtener_pieza_fila(pid)["imagen"] == "render.png"

    # Cargar ahora devuelve el documento y 1 versión.
    cargado = cliente.get(f"/api/imagen/pieza/c1/{pid}").json()
    assert cargado["versiones"] == 1
    assert cargado["documento"]["formato"]["w"] == 1080

    # Guardar otra vez incrementa la versión.
    assert cliente.post(f"/api/imagen/pieza/c1/{pid}", json={"documento": _DOC}).json()["version"] == 2

    versiones = cliente.get(f"/api/imagen/pieza/c1/{pid}/versiones").json()["versiones"]
    assert [v["version"] for v in versiones] == [2, 1]  # más reciente primero
    assert versiones[0]["render_url"] == "/api/media/render.png"


def test_guardar_sin_documento_400(cliente, entorno, _render_mock):
    _cid, pid = _pieza(entorno)
    assert cliente.post(f"/api/imagen/pieza/c1/{pid}", json={}).status_code == 400


def test_guardar_pieza_inexistente_404(cliente, entorno, _render_mock):
    r = cliente.post("/api/imagen/pieza/c1/no-existe", json={"documento": _DOC})
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# BUG 3: pieza_guardar valida plataforma ANTES de renderizar                  #
# --------------------------------------------------------------------------- #


def test_guardar_plataforma_no_pertenece_contenido_404(cliente, entorno, _render_mock):
    """Guardar documento para plataforma que no pertenece al contenido -> 404."""
    _cid1, pid1 = _pieza(entorno, "c1")
    _cid2, pid2 = _pieza(entorno, "c2")

    # Intentar guardar documento en plataforma que pertenece a cid2 bajo cid1 -> 404.
    r = cliente.post(f"/api/imagen/pieza/{_cid1}/{pid2}", json={"documento": _DOC})
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# BUG 2: Casts inválidos retornan 400, no 500                                 #
# --------------------------------------------------------------------------- #


def test_guardar_documento_con_z_invalido_400(cliente, entorno, _render_mock):
    """Documento con z no-numérico -> 400 (no 500)."""
    _cid, pid = _pieza(entorno)
    doc = {
        "formato": {"w": 1080, "h": 1350, "safe_top": 60, "safe_bottom": 96},
        "capas": [{"tipo": "imagen", "x": 0, "y": 0, "w": 100, "h": 100, "z": "x"}],
    }
    r = cliente.post(f"/api/imagen/pieza/{_cid}/{pid}", json={"documento": doc})
    assert r.status_code == 400
    assert "error" in r.json()


def test_guardar_documento_con_tamano_invalido_400(cliente, entorno, _render_mock):
    """Documento con tamano no-numérico -> 400 (no 500)."""
    _cid, pid = _pieza(entorno)
    doc = {
        "formato": {"w": 1080, "h": 1350, "safe_top": 60, "safe_bottom": 96},
        "capas": [{"tipo": "texto", "x": 0, "y": 0, "w": 100, "h": 0,
                   "texto": "a", "color": "#FFFFFF", "tamano": {}}],
    }
    r = cliente.post(f"/api/imagen/pieza/{_cid}/{pid}", json={"documento": doc})
    assert r.status_code == 400


def test_guardar_documento_con_formato_w_invalido_400(cliente, entorno, _render_mock):
    """Documento con formato.w fuera de rango -> 400 (no 500)."""
    _cid, pid = _pieza(entorno)
    doc = {
        "formato": {"w": 9999, "h": 1350, "safe_top": 60, "safe_bottom": 96},
        "capas": [],
    }
    r = cliente.post(f"/api/imagen/pieza/{_cid}/{pid}", json={"documento": doc})
    assert r.status_code == 400
