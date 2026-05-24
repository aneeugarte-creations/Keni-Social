from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from keni_metricas.historico import Historico, historico_activo, ruta_db, variacion
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


# --- T10: ruta_db respeta las env vars --------------------------------------


def test_ruta_db_respeta_keni_metricas_db(monkeypatch, tmp_path):
    destino = tmp_path / "subdir" / "mi.db"
    monkeypatch.setenv("KENI_METRICAS_DB", str(destino))
    # KENI_METRICAS_DB tiene prioridad incluso si XDG_DATA_HOME esta definido
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert ruta_db() == destino


def test_ruta_db_expande_tilde_de_keni_metricas_db(monkeypatch):
    monkeypatch.setenv("KENI_METRICAS_DB", "~/mi-historico.db")
    resultado = ruta_db()
    assert "~" not in str(resultado)
    assert resultado == Path.home() / "mi-historico.db"


def test_ruta_db_usa_xdg_data_home(monkeypatch, tmp_path):
    monkeypatch.delenv("KENI_METRICAS_DB", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "datos"))
    assert ruta_db() == tmp_path / "datos" / "keni-metricas" / "historico.db"


def test_ruta_db_default_bajo_home(monkeypatch):
    monkeypatch.delenv("KENI_METRICAS_DB", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert ruta_db() == Path.home() / ".local" / "share" / "keni-metricas" / "historico.db"


# --- T10: historico_activo lee la env var -----------------------------------


@pytest.mark.parametrize("valor", ["0", "false", "no"])
def test_historico_activo_desactivado(monkeypatch, valor):
    monkeypatch.setenv("KENI_METRICAS_HISTORICO", valor)
    assert historico_activo() is False


@pytest.mark.parametrize("valor", ["", "1", "si", "true"])
def test_historico_activo_activado(monkeypatch, valor):
    # cualquier valor que no sea 0/false/no (incluido vacio) deja el historico activo
    monkeypatch.setenv("KENI_METRICAS_HISTORICO", valor)
    assert historico_activo() is True


def test_historico_activo_default_sin_env(monkeypatch):
    monkeypatch.delenv("KENI_METRICAS_HISTORICO", raising=False)
    assert historico_activo() is True  # default "1"


# --- T10: serie respeta el limite n -----------------------------------------


def test_serie_respeta_limite_n(tmp_path):
    h = Historico(tmp_path / "h.db")
    # cinco periodos distintos (semanales) para la misma cuenta/rango
    for semana in range(1, 6):
        h.guardar(_resumen("m", date(2026, 5, semana), semana * 100, 3.0))
    serie = h.serie("m", "semana", 3)
    # solo los 3 mas recientes, en orden cronologico ascendente
    assert [p["visualizaciones"] for p in serie] == [300, 400, 500]


def test_serie_limite_mayor_que_datos_devuelve_todo(tmp_path):
    h = Historico(tmp_path / "h.db")
    h.guardar(_resumen("m", date(2026, 5, 1), 100, 3.0))
    h.guardar(_resumen("m", date(2026, 5, 8), 200, 3.0))
    serie = h.serie("m", "semana", 10)
    assert [p["visualizaciones"] for p in serie] == [100, 200]
