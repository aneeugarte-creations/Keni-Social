"""Tokens de rango: `mes:AAAA-MM` y `rango:AAAA-MM-DD_AAAA-MM-DD` + etiqueta_rango.

Funciones puras de `schema` (sin red ni disco): la entrada extendida de `resolver_rango`
que habilita los filtros de mes concreto y rango personalizado del dashboard.
"""

from __future__ import annotations

from datetime import date

import pytest

from keni_metricas.schema import MAX_DIAS_RANGO, etiqueta_rango, resolver_rango

HOY = date(2026, 5, 29)


def test_preset_rodante_sigue_funcionando():
    desde, hasta, dias = resolver_rango("semana", HOY)
    assert hasta == HOY
    assert dias == 7
    assert desde == date(2026, 5, 23)


def test_preset_anio_son_365_dias_rodantes():
    from datetime import timedelta

    desde, hasta, dias = resolver_rango("anio", HOY)
    assert hasta == HOY
    assert dias == 365  # cabe en MAX_DIAS_RANGO (366)
    assert desde == HOY - timedelta(days=364)
    assert etiqueta_rango("anio") == "Último año"


def test_mes_concreto():
    desde, hasta, dias = resolver_rango("mes:2026-05", HOY)
    assert desde == date(2026, 5, 1)
    assert hasta == date(2026, 5, 31)
    assert dias == 31


def test_mes_concreto_febrero_no_bisiesto():
    desde, hasta, _ = resolver_rango("mes:2026-02", HOY)
    assert (desde, hasta) == (date(2026, 2, 1), date(2026, 2, 28))


def test_rango_personalizado():
    desde, hasta, dias = resolver_rango("rango:2026-05-01_2026-05-10", HOY)
    assert desde == date(2026, 5, 1)
    assert hasta == date(2026, 5, 10)
    assert dias == 10


@pytest.mark.parametrize(
    "token",
    [
        "mes:2026-13",  # mes inexistente
        "mes:no-valido",
        "rango:2026-05-10_2026-05-01",  # hasta < desde
        "rango:2026-05-01",  # falta hasta
        "trimestre",  # preset inexistente
    ],
)
def test_tokens_invalidos_lanzan_valueerror(token):
    with pytest.raises(ValueError):
        resolver_rango(token, HOY)


def test_rango_demasiado_amplio_se_rechaza():
    # MAX_DIAS_RANGO + 1 dias debe exceder el cap.
    fin = date(2026, 1, 1)
    # construye un rango de mas de MAX_DIAS_RANGO dias
    inicio = date(2024, 1, 1)
    assert (fin - inicio).days + 1 > MAX_DIAS_RANGO
    with pytest.raises(ValueError):
        resolver_rango(f"rango:{inicio.isoformat()}_{fin.isoformat()}", HOY)


def test_etiqueta_rango_legible():
    assert etiqueta_rango("mes:2026-05") == "Mayo 2026"
    assert etiqueta_rango("rango:2026-05-01_2026-05-31") == "1–31 may 2026"
    assert etiqueta_rango("rango:2026-04-28_2026-05-03") == "28 abr – 3 may 2026"
    assert etiqueta_rango("semana")  # preset: alguna etiqueta no vacia
