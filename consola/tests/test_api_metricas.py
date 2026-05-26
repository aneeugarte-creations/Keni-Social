"""API de métricas: contrato del reporte consolidado, comparativa y exports.

TODO OFFLINE: la fuente es de muestra (`KENI_METRICAS_CONFIG` inexistente, lo fija
`entorno`). Cubre en particular que la respuesta exponga el campo `fuente`
("muestra"|"real") — N3: el frontend pinta un badge para distinguir datos ficticios
de reales (riesgo operativo del piloto AMX).
"""

from __future__ import annotations

import pytest

from .conftest import _cliente


@pytest.fixture
def cliente(entorno):
    return _cliente()


def test_reporte_expone_fuente_muestra(cliente):
    r = cliente.get("/api/metricas/reporte?rango=mes")
    assert r.status_code == 200
    data = r.json()
    # N3: el campo `fuente` viaja al frontend para el badge de datos de muestra.
    assert data["fuente"] == "muestra"
    assert "total" in data
    assert "cuentas" in data


def test_reporte_acotado_a_una_marca_sigue_trayendo_fuente(cliente):
    r = cliente.get("/api/metricas/reporte?rango=mes&marca=claro_sports")
    assert r.status_code == 200
    data = r.json()
    assert data["fuente"] == "muestra"
    ids = {c["marca_id"] for c in data["cuentas"]}
    assert ids == {"claro_sports"}


def test_opciones_trae_marcas_y_rangos(cliente):
    r = cliente.get("/api/metricas/opciones")
    assert r.status_code == 200
    data = r.json()
    assert data["marcas"]
    ids_rango = {x["id"] for x in data["rangos"]}
    assert {"semana", "mes"} <= ids_rango


def test_export_json_incluye_fuente(cliente):
    r = cliente.get("/api/metricas/export.json?rango=mes")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    # El export crudo del reporte tambien lleva `fuente` (lo pone construir_reporte).
    assert '"fuente"' in r.text


def test_export_csv_y_md_descargan(cliente):
    csv = cliente.get("/api/metricas/export.csv?rango=mes")
    assert csv.status_code == 200
    assert "text/csv" in csv.headers["content-type"]
    md = cliente.get("/api/metricas/export.md?rango=mes")
    assert md.status_code == 200
    assert "text/markdown" in md.headers["content-type"]


def test_comparar_total_y_por_marca(cliente):
    r = cliente.get("/api/metricas/comparar?rango_a=semana&rango_b=mes")
    assert r.status_code == 200
    data = r.json()
    assert "total" in data
    assert "por_marca" in data


def test_comparar_expone_fuente_muestra(cliente):
    # N6: la comparativa A vs B tambien lleva `fuente` para el badge de muestra,
    # igual que `/reporte`. Con la fuente offline de `entorno`, ambos lados son muestra.
    r = cliente.get("/api/metricas/comparar?rango_a=semana&rango_b=mes")
    assert r.status_code == 200
    assert r.json()["fuente"] == "muestra"


def test_comparar_acotado_a_una_marca_sigue_trayendo_fuente(cliente):
    r = cliente.get("/api/metricas/comparar?rango_a=7d&rango_b=30d&marca=unotv")
    assert r.status_code == 200
    assert r.json()["fuente"] == "muestra"
