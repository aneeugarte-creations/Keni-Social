"""Métricas Digitales: serializador del reporte mensual + contrato del endpoint.

El grueso (ventana de 13 meses, layout de 20 columnas, formato europeo, comparativa de los
dos últimos meses, celdas N/A y la fusión de reporte+desglose+seguidores) se prueba sobre las
funciones PURAS de `_digital`, sin tocar Postgres ni la fuente. El endpoint solo se comprueba
de CONTRATO: 200 + adjunto + los cinco bloques de plataforma; 400 sin marca concreta.
"""

from datetime import date

import pytest

from keni_consola.api.metricas import _digital as D

from .conftest import _cliente


@pytest.fixture
def cliente(entorno):
    return _cliente()


# --- Funciones puras: ventana, formato y comparativa ------------------------


def test_meses_ventana_son_13_y_terminan_en_el_mes_de_ref():
    meses = D.meses_ventana(date(2026, 6, 24))
    assert len(meses) == 13
    assert meses[0][:2] == ("mes:2025-06", "JUNIO")
    assert meses[-1][:2] == ("mes:2026-06", "JUNIO")


def test_formato_europeo_de_conteos_y_porcentajes():
    assert D._fmt_entero(2305158) == "2.305.158"
    assert D._fmt_entero(-6687794) == "-6.687.794"
    assert D._fmt_pct(7.15) == "7,15%"


def _datos_tiktok(meses):
    """Una marca con datos solo en MARZO y ABRIL 2026 (resto del año en blanco)."""
    toks = [t for t, *_ in meses]
    datos = {red: {t: None for t in toks} for red, _ in D.PLATAFORMAS}
    datos["tiktok"]["mes:2026-03"] = {
        "seguidores": 2644256, "visualizaciones": 166587525, "interacciones": 10326598,
        "engagement_pct": 6.20, "likes": 9626014, "compartidos": 457830, "comentarios": 242754,
    }
    datos["tiktok"]["mes:2026-04"] = {
        "seguidores": 3124061, "visualizaciones": 769620969, "interacciones": 28566486,
        "engagement_pct": 3.71, "likes": 25272109, "compartidos": 2277846, "comentarios": 1016531,
    }
    return datos


def test_layout_de_20_columnas_y_comparativa_de_los_dos_ultimos_meses():
    meses = D.meses_ventana(date(2026, 6, 24))
    filas = D.construir_lineas_digital(_datos_tiktok(meses), meses)
    cabecera = filas[0]
    assert cabecera[0] == "TIKTOK" and len(cabecera) == 20
    # 13 meses, un separador, y el bloque de comparativa con los dos últimos meses con datos.
    assert cabecera[16:20] == ["MARZO", "ABRIL", "Diferencia", "%"]
    seguidores = filas[1]
    assert seguidores[15:20] == ["Seguidores", "2.644.256", "3.124.061", "479.805", "18,1%"]
    engagement = filas[4]  # el delta del engagement va en puntos; el % es la variación relativa
    assert engagement[15:20] == ["Engagement Rate", "6,20%", "3,71%", "-2,49%", "-40,2%"]


def test_filas_que_la_fuente_no_provee_van_vacias():
    meses = D.meses_ventana(date(2026, 6, 24))
    lineas = D.render_csv_digital(_datos_tiktok(meses), meses).splitlines()
    # Impresiones y horas de YouTube, y la monetización USD, no existen → fila entera vacía.
    impresiones = next(l for l in lineas if l.startswith("Impresiones;"))
    assert set(impresiones.split(";")[1:14]) == {""}
    assert any(l.startswith("Monetización USD;") for l in lineas)


def test_ensamblar_funde_reporte_desglose_y_seguidores():
    tokens = ["mes:2026-03", "mes:2026-04"]
    reportes = [
        {"cuentas": [{"resumen": {"por_plataforma": [
            {"plataforma": "facebook", "visualizaciones": 100, "alcance": 80,
             "interacciones": 9, "engagement_pct": 1.5}]}}]},
        {"cuentas": [{"resumen": {"por_plataforma": [
            {"plataforma": "facebook", "visualizaciones": 200, "alcance": 160,
             "interacciones": 18, "engagement_pct": 1.6}]}}]},
    ]
    desgloses = [
        {"celdas": [{"red": "facebook", "likes": 5, "comentarios": 2,
                     "compartidos": 1, "video_views": 50}]},
        {"celdas": [{"red": "facebook", "likes": 9, "comentarios": 3,
                     "compartidos": 2, "video_views": 90}]},
    ]
    seg = {"puntos": [
        {"fecha": "2026-03-31", "por_red": {"facebook": 1000}},
        {"fecha": "2026-04-30", "por_red": {"facebook": 1100}},
    ]}
    datos = D.ensamblar_datos(tokens, reportes, desgloses, seg)
    abril = datos["facebook"]["mes:2026-04"]
    assert abril["seguidores"] == 1100  # stock absoluto a fin de mes (último punto)
    assert abril["alcance"] == 160      # del reporte (solo Meta)
    assert abril["video_views"] == 90   # del desglose
    # Una red sin NINGUNA señal ese mes queda vacía.
    assert datos["tiktok"]["mes:2026-04"] is None


# --- Contrato del endpoint --------------------------------------------------


def test_export_digitales_trae_los_cinco_bloques(cliente):
    r = cliente.get("/api/metricas/export.digitales?marca=claro_sports")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    cuerpo = r.text
    assert cuerpo.startswith("\ufeff")  # BOM para Excel es-MX
    primeras = {linea.split(";")[0] for linea in cuerpo.lstrip("\ufeff").splitlines()}
    for plataforma in ("TIKTOK", "INSTAGRAM", "FACEBOOK", "X", "YOUTUBE"):
        assert plataforma in primeras


def test_export_digitales_sin_marca_concreta_devuelve_400(cliente):
    r = cliente.get("/api/metricas/export.digitales")
    assert r.status_code == 400
