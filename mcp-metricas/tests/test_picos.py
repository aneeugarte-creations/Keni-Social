from __future__ import annotations

from datetime import date

from keni_metricas.fuentes.muestra import FuenteMuestra
from keni_metricas.historico import Historico
from keni_metricas.picos import detectar_picos, render_markdown
from keni_metricas.schema import Periodo, ResumenMetricas


def test_detecta_piezas_que_despuntan():
    rep = detectar_picos(FuenteMuestra(), "semana", 50)
    assert rep["alertas"], "muestra debería tener piezas por encima de la media"
    despuntes = [a for a in rep["alertas"] if a["tipo"] == "pieza_despunta"]
    assert despuntes
    for a in despuntes:
        assert a["factor"] >= 1.5  # (factor - 1) * 100 >= 50%


def test_umbral_imposible_no_marca_piezas():
    rep = detectar_picos(FuenteMuestra(), "semana", 100000)
    assert not any(a["tipo"] == "pieza_despunta" for a in rep["alertas"])


def test_detecta_alza_de_cuenta_con_historico(tmp_path):
    h = Historico(tmp_path / "h.db")
    for d in (date(2020, 1, 1), date(2020, 1, 8)):  # baseline bajo en periodos previos
        h.guardar(
            ResumenMetricas(
                cuenta="claro_sports",
                rango="semana",
                periodo=Periodo(desde=d, hasta=d),
                visualizaciones=1000,
                alcance=700,
                interacciones=40,
                engagement_pct=4.0,
                seguidores_netos=0,
                por_plataforma=[],
                fuente="muestra",
            )
        )
    rep = detectar_picos(FuenteMuestra(), "semana", 50, h)
    assert any(a["tipo"] == "cuenta_alza" and a["cuenta"] == "claro_sports" for a in rep["alertas"])


def test_render_markdown():
    md = render_markdown(detectar_picos(FuenteMuestra(), "semana", 50))
    assert md.startswith("## Alertas")
