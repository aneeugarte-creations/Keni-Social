"""API del reporte semanal de deportes (deck): opciones, preview y export .pptx.

TODO OFFLINE: fuente de muestra (KENI_METRICAS_CONFIG inexistente, lo fija `entorno`).
"""

from __future__ import annotations

import pytest

from .conftest import _cliente


@pytest.fixture
def cliente(entorno):
    return _cliente()


def test_opciones_trae_rangos_y_cuenta(cliente):
    r = cliente.get("/api/reporte-deportes/opciones")
    assert r.status_code == 200
    data = r.json()
    ids_rango = {x["id"] for x in data["rangos"]}
    assert {"semana", "mes"} <= ids_rango
    assert data["cuenta"]["id"] == "claro_sports"
    assert data["cuenta"]["nombre"] == "Claro Sports"
    ids_herm = {h["id"] for h in data["hermanas"]}
    assert {"claro_sports_tv", "csport_golf"} <= ids_herm


def test_preview_estructura(cliente):
    r = cliente.post("/api/reporte-deportes/preview", json={"rango": "semana", "top": 3})
    assert r.status_code == 200
    data = r.json()
    assert data["tipo"] == "reporte_deportes"
    assert data["cuenta"]["id"] == "claro_sports"
    plats = [b["plataforma"] for b in data["mejores_por_plataforma"]]
    assert plats == ["instagram", "tiktok", "facebook"]
    assert all(len(b["piezas"]) == 3 for b in data["mejores_por_plataforma"])
    assert [h["cuenta"] for h in data["promocion_hermanas"]] == ["claro_sports_tv", "csport_golf"]


def test_preview_refleja_agenda(cliente):
    cuerpo = {
        "rango": "semana",
        "agenda": {
            "principales": [{"nombre": "Champions", "plan": "en vivo"}],
            "propios": [{"nombre": "Camino al Mundial", "plan": "cápsulas"}],
        },
    }
    r = cliente.post("/api/reporte-deportes/preview", json=cuerpo)
    assert r.status_code == 200
    ag = r.json()["agenda"]
    assert [e["nombre"] for e in ag["principales"]] == ["Champions"]
    assert [e["nombre"] for e in ag["propios"]] == ["Camino al Mundial"]


def test_preview_rango_invalido_cae_a_semana(cliente):
    # como en /api/metricas, un rango invalido no rompe: cae al rango por defecto.
    r = cliente.post("/api/reporte-deportes/preview", json={"rango": "trimestre"})
    assert r.status_code == 200
    assert r.json()["rango"] == "semana"


def test_preview_sin_cuerpo(cliente):
    # POST sin JSON: usa defaults (semana, top 3).
    r = cliente.post("/api/reporte-deportes/preview")
    assert r.status_code == 200
    assert r.json()["rango"] == "semana"


def test_export_pptx_descarga_binario(cliente):
    pytest.importorskip("pptx")
    r = cliente.post("/api/reporte-deportes/export.pptx", json={"rango": "semana"})
    assert r.status_code == 200
    assert r.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    assert "attachment" in r.headers["content-disposition"]
    assert "reporte-deportes-semana.pptx" in r.headers["content-disposition"]
    # un .pptx es un zip: empieza por "PK"
    assert r.content[:2] == b"PK"
    assert len(r.content) > 1000


def test_export_pptx_es_zip_valido(cliente):
    pptx = pytest.importorskip("pptx")
    import io

    r = cliente.post("/api/reporte-deportes/export.pptx", json={"rango": "semana"})
    assert r.status_code == 200
    prs = pptx.Presentation(io.BytesIO(r.content))
    # portada + 3 plataformas + hermanas + 2 de agenda = 7 laminas
    assert len(prs.slides) == 7
