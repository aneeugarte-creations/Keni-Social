from __future__ import annotations

import pytest

from keni_metricas.dashboard import construir_html, generar_dashboard
from keni_metricas.fuentes.muestra import FuenteMuestra
from keni_metricas.picos import detectar_picos
from keni_metricas.reporte import construir_reporte


def test_dashboard_es_html_autocontenido():
    html = generar_dashboard(FuenteMuestra(), "mes", top=3)
    # documento HTML valido-ish
    assert html.lstrip().startswith("<!DOCTYPE html>")
    assert "<html" in html and "</html>" in html
    assert "<style>" in html and "</style>" in html
    # autocontenido: ningun recurso externo / red / JS externo
    assert "<script" not in html.lower()
    assert "http://" not in html
    assert "https://" not in html
    assert "cdn" not in html.lower()


def test_dashboard_contiene_nombres_de_marca():
    html = generar_dashboard(FuenteMuestra(), "mes", top=3)
    # nombres legibles de las 6 marcas de la muestra
    for nombre in ["Claro Sports", "UnoTV", "Nacion Gamer", "Piso 15", "Fundacion"]:
        assert nombre in html


def test_dashboard_contiene_totales_y_rango():
    fuente = FuenteMuestra()
    rep = construir_reporte(fuente, "mes", top=3)
    picos = detectar_picos(fuente, "mes", 50)
    nombres = {c.id: c.nombre for c in fuente.cuentas()}
    html = construir_html(rep, picos, nombres)

    assert "Dashboard de metricas — mes" in html
    # el total de visualizaciones aparece formateado con separador de miles (punto)
    total_vis = f"{rep['total']['visualizaciones']:,}".replace(",", ".")
    assert total_vis in html
    assert f"{rep['total']['engagement_pct']}%" in html


def test_dashboard_incluye_nota_de_cobertura():
    # la muestra siempre tiene cobertura completa -> la nota obligatoria debe aparecer
    html = generar_dashboard(FuenteMuestra(), "semana", top=2)
    assert "Cobertura completa" in html
    assert "NO son datos reales" in html or "respondieron" in html


def test_dashboard_seccion_de_picos():
    html = generar_dashboard(FuenteMuestra(), "mes", top=3)
    assert "Alertas (picos)" in html


def test_dashboard_escapa_html_de_titulos():
    """Los titulos de contenido se escapan (sin inyeccion de HTML)."""
    fuente = FuenteMuestra()
    rep = construir_reporte(fuente, "mes", top=2)
    # inyecta un titulo malicioso en una pieza
    rep["cuentas"][0]["mejores_piezas"][0]["titulo"] = "<script>alert(1)</script>"
    picos = detectar_picos(fuente, "mes", 50)
    nombres = {c.id: c.nombre for c in fuente.cuentas()}
    html = construir_html(rep, picos, nombres)

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_dashboard_rango_invalido_propaga():
    with pytest.raises(ValueError):
        generar_dashboard(FuenteMuestra(), "trimestre")
