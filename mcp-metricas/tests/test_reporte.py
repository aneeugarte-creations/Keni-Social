from __future__ import annotations

import pytest

from keni_metricas.fuentes.muestra import FuenteMuestra
from keni_metricas.reporte import construir_reporte, render_markdown


def test_reporte_recorre_todas_las_cuentas():
    rep = construir_reporte(FuenteMuestra(), "mes", top=3)
    assert rep["total"]["cuentas"] == 6
    assert rep["total"]["visualizaciones"] > 0
    assert 1.0 <= rep["total"]["engagement_pct"] <= 12.0
    # total = suma de las marcas
    suma = sum(f["resumen"]["visualizaciones"] for f in rep["cuentas"])
    assert rep["total"]["visualizaciones"] == suma
    # cada marca trae sus mejores piezas
    assert all(len(f["mejores_piezas"]) == 3 for f in rep["cuentas"])


def test_render_markdown():
    md = render_markdown(construir_reporte(FuenteMuestra(), "semana", top=2))
    assert md.startswith("# Reporte de redes — semana")
    assert "## Total" in md


def test_reporte_expone_nombres_legibles():
    # el reporte debe traer el mapa id->nombre legible (mismo origen que el
    # dashboard) para que el render no imprima el id crudo.
    rep = construir_reporte(FuenteMuestra(), "mes", top=1)
    assert rep["nombres"]["claro_sports"] == "Claro Sports"


def test_render_markdown_cabecera_usa_nombre_legible_no_id():
    # la cabecera de marca debe ser el NOMBRE legible ("## Claro Sports"), no el
    # id crudo ("## claro_sports").
    md = render_markdown(construir_reporte(FuenteMuestra(), "mes", top=1))
    assert "## Claro Sports" in md
    # el id crudo no debe aparecer como cabecera de marca
    assert "## claro_sports" not in md


def test_rango_invalido_propaga():
    with pytest.raises(ValueError):
        construir_reporte(FuenteMuestra(), "trimestre")
