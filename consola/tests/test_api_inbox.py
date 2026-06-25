"""API Inbox (lectura): endpoints `/api/inbox/conversaciones` y `/api/inbox/comentarios`.

Se MOCKEAN las `servicio.construir_inbox_*` con shapes deterministas: lo que se prueba es
el camino de consola (resolución de marca, validación, serialización), no la fuente de
métricas (esa se cubre en `mcp-metricas/tests/test_inbox.py`).
"""

from __future__ import annotations

import pytest
from keni_metricas import servicio

from .conftest import _cliente


@pytest.fixture
def cliente(entorno):
    return _cliente()


def _mock_servicio(monkeypatch, **fns):
    for nombre, fn in fns.items():
        monkeypatch.setattr(servicio, nombre, fn, raising=False)


def _conversaciones(marca):
    return {
        "por_red": [
            {
                "red": "facebook",
                "conversaciones": [
                    {
                        "id": "c1",
                        "red": "facebook",
                        "pendiente": True,
                        "participantes": [{"id": "u1", "nombre": "Ana", "avatar": None}],
                        "mensajes": [{"id": "m1", "texto": "hola", "adjuntos": 0}],
                    }
                ],
            }
        ]
    }


def _comentarios(marca, dias):
    return {
        "por_red": [
            {
                "red": "instagram",
                "comentarios": [
                    {
                        "id": "k1",
                        "red": "instagram",
                        "pendiente": False,
                        "texto": "golazo",
                        "post_texto": "Resumen",
                        "respuestas": [],
                    }
                ],
            }
        ]
    }


# --------------------------------------------------------------------------- #
# /api/inbox/conversaciones                                                    #
# --------------------------------------------------------------------------- #


def test_conversaciones_200_shape(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_inbox_conversaciones=_conversaciones)
    r = cliente.get("/api/inbox/conversaciones?marca=claro_sports")
    assert r.status_code == 200
    data = r.json()
    assert data["por_red"][0]["red"] == "facebook"
    assert data["por_red"][0]["conversaciones"][0]["id"] == "c1"
    assert "generado_en" in data


def test_conversaciones_acepta_id_canonico(cliente, monkeypatch):
    vistas = {}

    def fn(marca):
        vistas["marca"] = marca
        return {"por_red": []}

    _mock_servicio(monkeypatch, construir_inbox_conversaciones=fn)
    r = cliente.get("/api/inbox/conversaciones?marca=claro-sports")  # id canónico (guion-medio)
    assert r.status_code == 200
    assert vistas["marca"] == "claro_sports"  # resuelto a id_metricas (guion_bajo)


def test_conversaciones_marca_desconocida_400(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_inbox_conversaciones=_conversaciones)
    r = cliente.get("/api/inbox/conversaciones?marca=no_existe")
    assert r.status_code == 400
    assert "error" in r.json()


def test_conversaciones_sin_marca_400(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_inbox_conversaciones=_conversaciones)
    r = cliente.get("/api/inbox/conversaciones")
    assert r.status_code == 400
    assert "error" in r.json()


# --------------------------------------------------------------------------- #
# /api/inbox/comentarios                                                       #
# --------------------------------------------------------------------------- #


def test_comentarios_200_shape(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_inbox_comentarios=_comentarios)
    r = cliente.get("/api/inbox/comentarios?marca=claro_sports&dias=7")
    assert r.status_code == 200
    data = r.json()
    assert data["por_red"][0]["red"] == "instagram"
    assert data["por_red"][0]["comentarios"][0]["id"] == "k1"
    assert data["dias"] == 7
    assert "generado_en" in data


def test_comentarios_dias_se_acota(cliente, monkeypatch):
    vistos = {}

    def fn(marca, dias):
        vistos["dias"] = dias
        return {"por_red": []}

    _mock_servicio(monkeypatch, construir_inbox_comentarios=fn)
    r = cliente.get("/api/inbox/comentarios?marca=claro_sports&dias=999")
    assert r.status_code == 200
    assert vistos["dias"] == 30  # tope; def 7 si falta o no numérico


def test_comentarios_marca_desconocida_400(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_inbox_comentarios=_comentarios)
    r = cliente.get("/api/inbox/comentarios?marca=no_existe")
    assert r.status_code == 400
    assert "error" in r.json()
