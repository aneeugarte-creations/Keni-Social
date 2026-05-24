from __future__ import annotations

from datetime import date

from keni_metricas.historico import Historico, variacion
from keni_metricas.schema import Periodo, ResumenMetricas


def _resumen(cuenta: str, hasta: date, vis: int, eng: float) -> ResumenMetricas:
    return ResumenMetricas(
        cuenta=cuenta,
        rango="semana",
        periodo=Periodo(desde=hasta, hasta=hasta),
        visualizaciones=vis,
        alcance=int(vis * 0.7),
        interacciones=int(vis * eng / 100),
        engagement_pct=eng,
        seguidores_netos=0,
        por_plataforma=[],
        fuente="muestra",
    )


def test_guardar_y_serie_cronologica(tmp_path):
    h = Historico(tmp_path / "h.db")
    h.guardar(_resumen("m", date(2026, 5, 8), 1000, 3.0))
    h.guardar(_resumen("m", date(2026, 5, 15), 1200, 3.5))
    serie = h.serie("m", "semana", 10)
    assert [p["visualizaciones"] for p in serie] == [1000, 1200]


def test_variacion_real_vs_periodo_anterior(tmp_path):
    h = Historico(tmp_path / "h.db")
    h.guardar(_resumen("m", date(2026, 5, 8), 1000, 3.0))
    actual = _resumen("m", date(2026, 5, 15), 1200, 3.5)
    h.aplicar_variacion(actual)
    assert actual.variacion_vs_anterior["visualizaciones_pct"] == 20.0
    assert actual.variacion_vs_anterior["engagement_pct"] == 0.5


def test_sin_periodo_anterior_no_toca_variacion(tmp_path):
    h = Historico(tmp_path / "h.db")
    actual = _resumen("m", date(2026, 5, 15), 1200, 3.5)
    actual.variacion_vs_anterior = {"visualizaciones_pct": 9.9}
    h.aplicar_variacion(actual)  # no hay lectura anterior
    assert actual.variacion_vs_anterior == {"visualizaciones_pct": 9.9}


def test_serie_una_lectura_por_periodo(tmp_path):
    h = Historico(tmp_path / "h.db")
    h.guardar(_resumen("m", date(2026, 5, 15), 1000, 3.0))
    h.guardar(_resumen("m", date(2026, 5, 15), 1100, 3.2))  # mismo periodo, lectura posterior
    serie = h.serie("m", "semana", 10)
    assert len(serie) == 1
    assert serie[0]["visualizaciones"] == 1100  # se queda la mas reciente del periodo


def test_variacion_helper():
    r = _resumen("m", date(2026, 5, 15), 1500, 4.0)
    assert variacion(r, 1000, 3.0) == {"visualizaciones_pct": 50.0, "engagement_pct": 1.0}
