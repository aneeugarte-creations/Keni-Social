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
    assert "Claro Sports".lower() in md.lower() or "claro_sports" in md


def test_rango_invalido_propaga():
    with pytest.raises(ValueError):
        construir_reporte(FuenteMuestra(), "trimestre")
