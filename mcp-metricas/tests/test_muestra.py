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
    assert len(cuentas) == 6


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
