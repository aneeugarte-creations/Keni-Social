"""Tests de la señal de rendimiento por línea (`dominio.rendimiento_tema`). PURO, sin BD/red."""

from __future__ import annotations

from keni_consola.produccion import rendimiento_tema as rt


def test_lineas_top_ordena_por_engagement_y_respeta_muestra_minima():
    lineas = [
        {"nombre": "Deportes", "piezas": 10, "engagement_pct": 5.0},
        {"nombre": "Política", "piezas": 8, "engagement_pct": 9.0},
        # Muestra < mínimo: aunque el engagement sea altísimo, NO cuenta (anti-sesgo "1 vez").
        {"nombre": "Suerte", "piezas": 1, "engagement_pct": 99.0},
        # Sin línea (nombre vacío): se ignora.
        {"nombre": "", "piezas": 50, "engagement_pct": 80.0},
    ]
    top = rt.lineas_top(lineas, minimo_piezas=5, n=2)
    assert top == {"Política", "Deportes"}


def test_lineas_top_n_cero_vacio():
    assert rt.lineas_top([{"nombre": "A", "piezas": 9, "engagement_pct": 1.0}], minimo_piezas=5, n=0) == set()


def test_lineas_top_sin_datos():
    assert rt.lineas_top([], minimo_piezas=5, n=3) == set()


def test_bonus_de_historia():
    top = {"Deportes", "Política"}
    assert rt.bonus_de_historia("Deportes", top) == 1.0
    assert rt.bonus_de_historia("Cultura", top) == 0.0
    assert rt.bonus_de_historia(None, top) == 0.0
    assert rt.bonus_de_historia("Política", set()) == 0.0
