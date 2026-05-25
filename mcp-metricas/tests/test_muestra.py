from __future__ import annotations

import pytest

from keni_metricas.fuentes.base import CuentaNoEncontrada
from keni_metricas.fuentes.muestra import FuenteMuestra


@pytest.fixture
def fuente() -> FuenteMuestra:
    return FuenteMuestra()


def test_cuentas_listadas(fuente: FuenteMuestra):
    cuentas = fuente.cuentas()
    ids = {c.id for c in cuentas}
    assert {"claro_sports", "unotv", "nacion_gamer", "fundacion"} <= ids
    assert len(cuentas) == 5


def test_resumen_determinista(fuente: FuenteMuestra):
    a = fuente.resumen("claro_sports", "semana")
    b = fuente.resumen("claro_sports", "semana")
    assert a == b  # mismo input -> mismo output


def test_resumen_cifras_creibles(fuente: FuenteMuestra):
    r = fuente.resumen("claro_sports", "mes")
    # Claro Sports ~80M/mes; tolerancia amplia por el jitter
    assert 50_000_000 < r.visualizaciones < 110_000_000
    assert 1.0 <= r.engagement_pct <= 12.0
    assert r.fuente == "muestra"
    # las plataformas del resumen son exactamente las de la cuenta
    cuenta = next(c for c in fuente.cuentas() if c.id == "claro_sports")
    assert {m.plataforma for m in r.por_plataforma} == set(cuenta.plataformas)


def test_semana_menor_que_mes(fuente: FuenteMuestra):
    assert fuente.resumen("claro_sports", "semana").visualizaciones < fuente.resumen(
        "claro_sports", "mes"
    ).visualizaciones


def test_mejores_piezas_ordenadas(fuente: FuenteMuestra):
    piezas = fuente.mejores_piezas("claro_sports", "semana", 5)
    assert len(piezas) == 5
    eng = [p.engagement_pct for p in piezas]
    assert eng == sorted(eng, reverse=True)


def test_cuenta_desconocida(fuente: FuenteMuestra):
    with pytest.raises(CuentaNoEncontrada):
        fuente.resumen("no_existe", "semana")


def test_rango_invalido(fuente: FuenteMuestra):
    with pytest.raises(ValueError):
        fuente.resumen("claro_sports", "trimestre")


# --- B7: n negativo no debe devolver de mas --------------------------------
@pytest.mark.parametrize("n", [-1, -5, -100])
def test_mejores_piezas_n_negativo_devuelve_vacio(fuente: FuenteMuestra, n: int):
    # antes, candidatas[:n] con n<0 devolvia casi todas las candidatas (p.ej. 11)
    assert fuente.mejores_piezas("claro_sports", "mes", n) == []


def test_mejores_piezas_n_cero(fuente: FuenteMuestra):
    assert fuente.mejores_piezas("claro_sports", "mes", 0) == []


# --- T9: determinismo ------------------------------------------------------
def test_rand_determinista():
    from keni_metricas.fuentes.muestra import _rand

    assert _rand("claro_sports", "mes", "v") == _rand("claro_sports", "mes", "v")
    # inputs distintos -> (casi seguro) valores distintos
    assert _rand("claro_sports", "mes", "v") != _rand("unotv", "mes", "v")


def test_mejores_piezas_deterministas(fuente: FuenteMuestra):
    a = fuente.mejores_piezas("unotv", "mes", 5)
    b = fuente.mejores_piezas("unotv", "mes", 5)
    assert a == b  # mismo input -> mismas piezas (id, cifras, orden)


def test_resumen_cifras_estables_entre_invocaciones(fuente: FuenteMuestra):
    a = fuente.resumen("nacion_gamer", "semana")
    b = fuente.resumen("nacion_gamer", "semana")
    assert a.visualizaciones == b.visualizaciones
    assert a.engagement_pct == b.engagement_pct
    assert a.seguidores_netos == b.seguidores_netos


# --- T9: las mejores piezas baten la media de engagement de su plataforma ---
def test_mejores_piezas_baten_media_de_su_plataforma(fuente: FuenteMuestra):
    from keni_metricas.fuentes.muestra import _ENG, _ENG_FACTOR

    cuenta_id = "claro_sports"
    factor = _ENG_FACTOR[cuenta_id]
    piezas = fuente.mejores_piezas(cuenta_id, "mes", 12)
    assert piezas
    for p in piezas:
        eng_min, eng_max = _ENG[p.plataforma]
        media_plataforma = (eng_min + eng_max) / 2 * factor
        # cada pieza destacada bate (o iguala, con redondeo a 1 decimal) la media
        assert p.engagement_pct >= round(media_plataforma, 1) - 0.05


# --- T9: el factor de engagement por marca cae donde toca ------------------
def test_engagement_claro_sports_en_rango_esperado(fuente: FuenteMuestra):
    # Cifra de Mariana: Claro Sports combinado ~2-3%.
    r = fuente.resumen("claro_sports", "mes")
    assert 1.8 <= r.engagement_pct <= 3.5


def test_engagement_unotv_mas_bajo_que_claro_sports(fuente: FuenteMuestra):
    # UnoTV (noticias) prioriza alcance: engagement combinado mas bajo.
    cs = fuente.resumen("claro_sports", "mes").engagement_pct
    uno = fuente.resumen("unotv", "mes").engagement_pct
    assert uno < cs
