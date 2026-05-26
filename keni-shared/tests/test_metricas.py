"""Tests de la formula unica de engagement (`metricas.engagement_pct`) — H3/E1."""

from __future__ import annotations

from keni_shared.metricas import engagement_pct


def test_engagement_basico():
    assert engagement_pct(50, 1000) == 5.0


def test_engagement_redondea_a_un_decimal():
    assert engagement_pct(1, 3) == 33.3


def test_engagement_sin_visualizaciones_es_cero():
    # No divide por cero: devuelve 0.0.
    assert engagement_pct(10, 0) == 0.0


def test_engagement_cero_interacciones():
    assert engagement_pct(0, 1000) == 0.0
