"""Tests del render del editor con OPCIONES de export (/api/imagen/render). OFFLINE.

El render (Node) se mockea; aquí se cubre la validación de `opciones` (formato/calidad/escala) y
que las opciones normalizadas llegan al dominio. La validación numérica del dominio
(`normalizar_opciones_export`) se prueba como unidad por separado.
"""

from __future__ import annotations

import pytest

from keni_consola.dominio import estudio_imagen

_DOC = {"formato": {"w": 1080, "h": 1350}, "capas": []}


@pytest.fixture
def _captura_render(monkeypatch):
    """Mockea `renderizar_documento` y captura las kwargs (para asserts sobre `opciones`)."""
    capturado: dict = {}

    def _falso(doc, **kw):
        capturado["doc"] = doc
        capturado["kw"] = kw
        return {"id": "render.png", "url": "/api/media/render.png"}

    monkeypatch.setattr(estudio_imagen, "renderizar_documento", _falso)
    return capturado


def test_render_sin_opciones_usa_defaults(cliente, entorno, _captura_render):
    r = cliente.post("/api/imagen/render", json={"documento": _DOC})
    assert r.status_code == 200, r.text
    assert r.json() == {"id": "render.png", "url": "/api/media/render.png"}
    # Sin `opciones` en el body, el endpoint igualmente pasa las normalizadas (png/90/1) al dominio.
    assert _captura_render["kw"]["opciones"] == {"formato": "png", "calidad": 90, "escala": 1.0}


def test_render_opciones_validas_se_propagan(cliente, entorno, _captura_render):
    r = cliente.post(
        "/api/imagen/render",
        json={"documento": _DOC, "opciones": {"formato": "jpg", "calidad": 80, "escala": 2}},
    )
    assert r.status_code == 200, r.text
    assert _captura_render["kw"]["opciones"] == {"formato": "jpg", "calidad": 80, "escala": 2.0}


def test_render_formato_invalido_400(cliente, entorno, _captura_render):
    r = cliente.post(
        "/api/imagen/render",
        json={"documento": _DOC, "opciones": {"formato": "gif"}},
    )
    assert r.status_code == 400
    assert "formato" in r.json()["error"].lower()


def test_render_escala_fuera_de_rango_400(cliente, entorno, _captura_render):
    r = cliente.post(
        "/api/imagen/render",
        json={"documento": _DOC, "opciones": {"escala": 9}},
    )
    assert r.status_code == 400
    assert "escala" in r.json()["error"].lower()


def test_render_calidad_fuera_de_rango_400(cliente, entorno, _captura_render):
    r = cliente.post(
        "/api/imagen/render",
        json={"documento": _DOC, "opciones": {"formato": "jpg", "calidad": 0}},
    )
    assert r.status_code == 400
    assert "calidad" in r.json()["error"].lower()


# --- Unidad: normalizar_opciones_export ---


def test_normalizar_defaults():
    assert estudio_imagen.normalizar_opciones_export(None) == {
        "formato": "png", "calidad": 90, "escala": 1.0,
    }
    assert estudio_imagen.normalizar_opciones_export({}) == {
        "formato": "png", "calidad": 90, "escala": 1.0,
    }


def test_normalizar_jpeg_alias():
    assert estudio_imagen.normalizar_opciones_export({"formato": "JPEG"})["formato"] == "jpg"


@pytest.mark.parametrize(
    "opciones",
    [
        {"formato": "webp"},
        {"escala": 0.1},
        {"escala": 5},
        {"escala": "x"},
        {"calidad": 0},
        {"calidad": 101},
        {"calidad": "alta"},
    ],
)
def test_normalizar_invalidas_lanzan(opciones):
    with pytest.raises(estudio_imagen.EstudioError):
        estudio_imagen.normalizar_opciones_export(opciones)


def test_normalizar_limites_validos():
    assert estudio_imagen.normalizar_opciones_export({"escala": 0.25})["escala"] == 0.25
    assert estudio_imagen.normalizar_opciones_export({"escala": 4})["escala"] == 4.0
    assert estudio_imagen.normalizar_opciones_export({"calidad": 1})["calidad"] == 1
    assert estudio_imagen.normalizar_opciones_export({"calidad": 100})["calidad"] == 100
