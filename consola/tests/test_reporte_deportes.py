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
    # el reporte del lunes ofrece la semana cerrada (lun->dom) ademas de los rodantes
    assert {"semana_cerrada", "semana", "mes"} <= ids_rango
    # la semana cerrada va primero: es el rango por defecto (#141)
    assert data["rangos"][0]["id"] == "semana_cerrada"
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


def test_preview_rango_invalido_cae_a_semana_cerrada(cliente):
    # un rango invalido no rompe: cae al rango por defecto (la semana cerrada, #141).
    r = cliente.post("/api/reporte-deportes/preview", json={"rango": "trimestre"})
    assert r.status_code == 200
    assert r.json()["rango"] == "semana_cerrada"


def test_preview_sin_cuerpo_usa_semana_cerrada(cliente):
    # POST sin JSON: usa defaults (semana cerrada lun->dom, top 3).
    r = cliente.post("/api/reporte-deportes/preview")
    assert r.status_code == 200
    assert r.json()["rango"] == "semana_cerrada"


def test_preview_semana_cerrada_periodo_lunes_a_domingo(cliente):
    # El periodo por defecto cubre 7 dias naturales lun->dom (domingo incluido, #141).
    from datetime import date

    r = cliente.post("/api/reporte-deportes/preview", json={"rango": "semana_cerrada"})
    assert r.status_code == 200
    periodo = r.json()["periodo"]
    desde = date.fromisoformat(periodo["desde"])
    hasta = date.fromisoformat(periodo["hasta"])
    assert desde.weekday() == 0  # lunes
    assert hasta.weekday() == 6  # domingo
    assert (hasta - desde).days == 6  # 7 dias inclusive


def test_preview_hermanas_rotulan_procedencia(cliente):
    # Con la fuente muestra, cada cuenta hermana se rotula como "muestra" (honestidad #141).
    r = cliente.post("/api/reporte-deportes/preview", json={"rango": "semana_cerrada"})
    assert r.status_code == 200
    hermanas = r.json()["promocion_hermanas"]
    assert hermanas and all(h.get("datos") == "muestra" for h in hermanas)


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


def test_export_pdf_descarga_binario(cliente):
    # PDF NATIVO (reportlab, sin LibreOffice, #141).
    pytest.importorskip("reportlab")
    r = cliente.post("/api/reporte-deportes/export.pdf", json={"rango": "semana_cerrada"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert "attachment" in r.headers["content-disposition"]
    assert "reporte-deportes-semana_cerrada.pdf" in r.headers["content-disposition"]
    # un PDF empieza por "%PDF"
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 1000
