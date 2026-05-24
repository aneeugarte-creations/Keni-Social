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


def test_detecta_caida_de_cuenta_con_historico(tmp_path):
    # Baseline historico MUY alto frente a la muestra actual (~18.8M para
    # claro_sports): una desviacion negativa fuerte debe generar `cuenta_caida`.
    h = Historico(tmp_path / "h.db")
    for d in (date(2020, 1, 1), date(2020, 1, 8)):  # baseline alto en periodos previos
        h.guardar(
            ResumenMetricas(
                cuenta="claro_sports",
                rango="semana",
                periodo=Periodo(desde=d, hasta=d),
                visualizaciones=100_000_000,
                alcance=70_000_000,
                interacciones=4_000_000,
                engagement_pct=4.0,
                seguidores_netos=0,
                por_plataforma=[],
                fuente="muestra",
            )
        )
    rep = detectar_picos(FuenteMuestra(), "semana", 50, h)
    caidas = [
        a for a in rep["alertas"] if a["tipo"] == "cuenta_caida" and a["cuenta"] == "claro_sports"
    ]
    assert caidas, "baseline alto + muestra inferior debe marcar cuenta_caida"
    assert caidas[0]["desviacion_pct"] < 0  # desviacion negativa
    # render_markdown muestra la caida (icono 📉 + verbo "cae"). Como el render
    # acota a un top-N por magnitud, renderizamos solo la(s) caida(s) para
    # comprobar su formato sin depender de que entre en el top global.
    rep_caida = {**rep, "alertas": caidas}
    md = render_markdown(rep_caida)
    assert "📉" in md
    assert "cae" in md
    # y se muestra con el NOMBRE legible de la marca, no el id crudo
    assert "Claro Sports" in md
    assert "claro_sports" not in md


def test_render_markdown():
    md = render_markdown(detectar_picos(FuenteMuestra(), "semana", 50))
    assert md.startswith("## Alertas")


def test_detectar_picos_expone_nombres_legibles():
    # el reporte de picos debe traer el mapa id->nombre legible (mismo origen
    # que usa el dashboard) para que el render no imprima el id crudo.
    rep = detectar_picos(FuenteMuestra(), "semana", 50)
    assert rep["nombres"]["claro_sports"] == "Claro Sports"


def test_render_markdown_usa_nombre_legible_no_id():
    # con varias alertas de claro_sports, el markdown debe mostrar el NOMBRE
    # legible ("Claro Sports") y no el id crudo ("claro_sports").
    rep = detectar_picos(FuenteMuestra(), "semana", 50)
    assert any(a["cuenta"] == "claro_sports" for a in rep["alertas"])
    md = render_markdown(rep)
    assert "Claro Sports" in md
    assert "claro_sports" not in md  # el id crudo no debe filtrarse al texto


def test_render_markdown_limita_a_top_n_y_resume_el_resto():
    # la muestra genera bastantes alertas (>visibles); el render debe acotar a
    # un top-N y resumir el resto en una linea, no volcarlas todas.
    from keni_metricas.formato import PICOS_VISIBLES

    rep = detectar_picos(FuenteMuestra(), "semana", 50)
    assert len(rep["alertas"]) > PICOS_VISIBLES, "la muestra debe dar mas alertas que el top-N"
    md = render_markdown(rep)
    # nº de lineas de alerta concretas (las que empiezan con un icono de pico)
    lineas_alerta = [ln for ln in md.splitlines() if ln.startswith(("- 🔼", "- 📈", "- 📉"))]
    assert len(lineas_alerta) <= PICOS_VISIBLES
    # y hay una linea-resumen del resto colapsado
    n_resto = len(rep["alertas"]) - PICOS_VISIBLES
    assert any(str(n_resto) in ln and "mas" in ln for ln in md.splitlines())


def test_render_markdown_no_resume_cuando_hay_pocas():
    # con umbral altisimo casi no hay alertas: ninguna linea de "resto".
    rep = detectar_picos(FuenteMuestra(), "semana", 100000)
    md = render_markdown(rep)
    assert "mas (ordenadas por magnitud)" not in md
