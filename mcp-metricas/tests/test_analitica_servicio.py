"""Fachada `servicio`: analítica de piezas + tendencia diaria (sobre fuente de muestra).

TODO OFFLINE: `KENI_METRICAS_CONFIG` inexistente => fuente de muestra; nunca toca red.
"""

from __future__ import annotations

import pytest

from keni_metricas import servicio


@pytest.fixture
def muestra(monkeypatch, tmp_path):
    # Fuente única por defecto = `metricool`; estos tests usan la demo offline, fijada
    # explícita con KENI_METRICAS_FUENTE=muestra.
    monkeypatch.setenv("KENI_METRICAS_FUENTE", "muestra")
    monkeypatch.delenv("KENI_METRICAS_MARCAS", raising=False)
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(tmp_path / "noexiste.toml"))
    return tmp_path


def test_analitica_piezas_marca(muestra):
    a = servicio.construir_analitica_piezas("mes", "claro_sports")
    assert a["cuenta"] == "claro_sports"
    assert a["fuente"] == "muestra"
    assert a["total"] > 0
    assert len(a["top"]) == 10
    assert len(a["peores"]) == 10
    # top/peores ordenados por VISUALIZACIONES (alcance absoluto): top = las más vistas
    # (desc), peores = las menos vistas; el badge `rendimiento_relativo` queda anotado.
    vistas_top = [p["visualizaciones"] for p in a["top"]]
    vistas_peor = [p["visualizaciones"] for p in a["peores"]]
    assert vistas_top == sorted(vistas_top, reverse=True)
    assert max(vistas_peor) <= min(vistas_top)  # los peores son menos vistos que el top
    assert all(p["rendimiento_relativo"] is not None for p in a["top"])
    # peores no solapan con top.
    ids_top = {p["id"] for p in a["top"]}
    ids_peor = {p["id"] for p in a["peores"]}
    assert not (ids_top & ids_peor)
    # estadisticas presentes.
    assert a["engagement"]["media"] is not None
    assert sum(b["n"] for b in a["distribucion"]) == a["total"]


def test_analitica_piezas_global_orden_por_vistas(muestra):
    # marca=None agrega todas las marcas; top = las 10 más vistas globalmente (desc).
    a = servicio.construir_analitica_piezas("mes", None)
    assert len(a["top"]) == 10 and len(a["peores"]) == 10
    vistas_top = [p["visualizaciones"] for p in a["top"]]
    assert vistas_top == sorted(vistas_top, reverse=True)
    assert max(p["visualizaciones"] for p in a["peores"]) <= min(vistas_top)


def test_analitica_piezas_global_agrega_todas(muestra):
    glob = servicio.construir_analitica_piezas("mes", None)
    una = servicio.construir_analitica_piezas("mes", "claro_sports")
    assert glob["cuenta"] is None
    # el agregado global tiene al menos tantas piezas como una sola marca.
    assert glob["total"] >= una["total"]


def test_analitica_piezas_acepta_token_mes(muestra):
    a = servicio.construir_analitica_piezas("mes:2026-05", "claro_sports")
    assert a["rango"] == "mes:2026-05"
    assert a["periodo"]["desde"] == "2026-05-01"
    assert a["periodo"]["hasta"] == "2026-05-31"


def test_tendencia_diaria_muestra(muestra):
    t = servicio.construir_tendencia_diaria("rango:2026-05-01_2026-05-07", "claro_sports")
    assert t["cuenta"] == "claro_sports"
    assert len(t["puntos"]) == 7
    p0 = t["puntos"][0]
    assert p0["fecha"] == "2026-05-01"
    assert p0["visualizaciones"] >= 0 and p0["interacciones"] >= 0
