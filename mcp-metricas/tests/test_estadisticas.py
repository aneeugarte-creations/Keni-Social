"""Estadisticas de piezas: resumen_numerico, buckets_engagement, top_y_peores."""

from __future__ import annotations

from datetime import date

from keni_metricas.estadisticas import (
    buckets_engagement,
    resumen_numerico,
    top_y_peores,
)
from keni_metricas.schema import Pieza, Plataforma


def _pieza(eng: float, vis: int = 1000, i: int = 0) -> Pieza:
    return Pieza(
        id=f"p{i}-{eng}",
        plataforma=Plataforma.instagram,
        titulo=f"Pieza {i}",
        publicado=date(2026, 5, 1),
        visualizaciones=vis,
        interacciones=int(vis * eng / 100),
        engagement_pct=eng,
    )


def test_resumen_numerico_vacio():
    r = resumen_numerico([])
    assert r.n == 0
    assert r.media is None and r.desviacion is None


def test_resumen_numerico_un_valor_sin_desviacion():
    r = resumen_numerico([5.0])
    assert r.n == 1
    assert r.media == 5.0 and r.mediana == 5.0
    assert r.minimo == 5.0 and r.maximo == 5.0
    assert r.desviacion is None  # necesita n>=2


def test_resumen_numerico_varios():
    r = resumen_numerico([1, 2, 3, 4])
    assert r.n == 4
    assert r.media == 2.5
    assert r.mediana == 2.5
    assert r.minimo == 1.0 and r.maximo == 4.0
    assert r.p25 == 1.75 and r.p75 == 3.25
    assert r.desviacion is not None


def test_buckets_engagement_cuenta_por_tramo():
    piezas = [_pieza(1), _pieza(3), _pieza(3.5), _pieza(11)]
    buckets = buckets_engagement(piezas)
    por_etiqueta = {b.etiqueta: b.n for b in buckets}
    assert por_etiqueta["0–2%"] == 1
    assert por_etiqueta["2–4%"] == 2
    assert por_etiqueta["10%+"] == 1
    # el tramo abierto superior no tiene fin.
    assert buckets[-1].fin is None


def test_top_y_peores_no_solapan():
    piezas = [_pieza(e, i=i) for i, e in enumerate([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])]
    top, peores = top_y_peores(piezas, n=5)
    assert [p.engagement_pct for p in top] == [12, 11, 10, 9, 8]
    assert [p.engagement_pct for p in peores] == [1, 2, 3, 4, 5]
    # ninguna pieza aparece en ambos
    assert not ({p.id for p in top} & {p.id for p in peores})


def test_peores_vacio_cuando_caben_en_top():
    piezas = [_pieza(e, i=i) for i, e in enumerate([1, 2, 3])]
    top, peores = top_y_peores(piezas, n=5)
    assert len(top) == 3
    assert peores == []
