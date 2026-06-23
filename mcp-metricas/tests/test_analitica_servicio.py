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


def test_tendencia_diaria_filtra_por_red(muestra):
    # La serie por red se deriva de las piezas de ESA red: su suma de visualizaciones
    # debe coincidir con la suma de las piezas de esa red en el listado del periodo.
    listado = servicio.construir_listado_piezas("mes", "claro_sports")
    red = listado[0]["red"]
    esperado_vis = sum(p["visualizaciones"] for p in listado if p["red"] == red)
    esperado_int = sum(p["interacciones"] for p in listado if p["red"] == red)
    t = servicio.construir_tendencia_diaria("mes", "claro_sports", red)
    assert t["cuenta"] == "claro_sports"
    assert sum(p["visualizaciones"] for p in t["puntos"]) == esperado_vis
    assert sum(p["interacciones"] for p in t["puntos"]) == esperado_int


def test_analitica_piezas_filtra_por_red(muestra):
    # El filtro por red calcula top/peores/estadísticas SOLO sobre las piezas de esa red.
    todas = servicio.construir_analitica_piezas("mes", "claro_sports")
    red = todas["top"][0]["plataforma"]  # una red presente en el resultado sin filtrar
    filtrado = servicio.construir_analitica_piezas("mes", "claro_sports", red)
    assert filtrado["total"] >= 1
    assert all(p["plataforma"] == red for p in filtrado["top"])
    assert all(p["plataforma"] == red for p in filtrado["peores"])
    # Acotar a una red nunca trae más piezas que todas las redes juntas.
    assert filtrado["total"] <= todas["total"]


# --------------------------------------------------------------------------- #
# Filtro por formato (canónico) en las builders del servicio.                  #
# --------------------------------------------------------------------------- #


def test_formato_canonico_mapea_crudos_a_los_seis_ids():
    # Cada crudo conocido cae en su id canónico; un desconocido conserva su string.
    assert servicio.formato_canonico("feed_reel") == "reel"
    assert servicio.formato_canonico("CAROUSEL") == "carrusel"
    assert servicio.formato_canonico("feed_image") == "foto"
    assert servicio.formato_canonico("short") == "video"
    assert servicio.formato_canonico("link") == "enlace"
    assert servicio.formato_canonico("status") == "texto"
    assert servicio.formato_canonico("Encuesta") == "encuesta"
    assert servicio.FORMATOS_VALIDOS == frozenset(
        {"reel", "carrusel", "foto", "video", "enlace", "texto"}
    )


def _un_formato_presente(muestra_marca="claro_sports"):
    listado = servicio.construir_listado_piezas("mes", muestra_marca)
    cuenta: dict[str, int] = {}
    for p in listado:
        c = servicio.formato_canonico(p["formato"] or "")
        cuenta[c] = cuenta.get(c, 0) + 1
    return max(cuenta, key=cuenta.get), listado


def test_listado_piezas_filtra_por_formato(muestra):
    fmt, full = _un_formato_presente()
    filtrado = servicio.construir_listado_piezas("mes", "claro_sports", (fmt,))
    assert {servicio.formato_canonico(p["formato"] or "") for p in filtrado} == {fmt}
    assert len(filtrado) == sum(
        1 for p in full if servicio.formato_canonico(p["formato"] or "") == fmt
    )


def test_analitica_piezas_filtra_por_formato(muestra):
    fmt, _ = _un_formato_presente()
    todas = servicio.construir_analitica_piezas("mes", "claro_sports")
    filtrado = servicio.construir_analitica_piezas("mes", "claro_sports", None, (fmt,))
    assert all(servicio.formato_canonico(p["formato"] or "") == fmt for p in filtrado["top"])
    assert filtrado["total"] <= todas["total"]


def test_analitica_piezas_combina_red_y_formato(muestra):
    fmt, listado = _un_formato_presente()
    red = next(p["red"] for p in listado if servicio.formato_canonico(p["formato"] or "") == fmt)
    filtrado = servicio.construir_analitica_piezas("mes", "claro_sports", red, (fmt,))
    assert all(p["plataforma"] == red for p in filtrado["top"])
    assert all(servicio.formato_canonico(p["formato"] or "") == fmt for p in filtrado["top"])


def test_tendencia_diaria_filtra_por_formato(muestra):
    fmt, listado = _un_formato_presente()
    coincide = [p for p in listado if servicio.formato_canonico(p["formato"] or "") == fmt]
    esperado_vis = sum(p["visualizaciones"] for p in coincide)
    t = servicio.construir_tendencia_diaria("mes", "claro_sports", None, (fmt,))
    assert sum(pt["visualizaciones"] for pt in t["puntos"]) == esperado_vis


def test_desglose_filtra_por_formato(muestra):
    fmt, listado = _un_formato_presente()
    coincide = [p for p in listado if servicio.formato_canonico(p["formato"] or "") == fmt]
    d = servicio.construir_desglose_interacciones("mes", "claro_sports", (fmt,))
    assert d["totales"]["visualizaciones"] == sum(p["visualizaciones"] for p in coincide)
    assert d["totales"]["interacciones"] == sum(p["interacciones"] for p in coincide)


def test_crosstab_filtra_por_formato(muestra):
    fmt, _ = _un_formato_presente()
    c = servicio.construir_crosstab("mes", "claro_sports", (fmt,))
    assert c["celdas"]
    assert all(servicio.formato_canonico(cl["formato"] or "") == fmt for cl in c["celdas"])
