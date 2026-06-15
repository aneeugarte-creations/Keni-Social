"""Estadisticas de piezas: resumen_numerico, buckets_engagement, top_y_peores."""

from __future__ import annotations

from datetime import date

from keni_metricas.estadisticas import (
    anotar_rendimiento_relativo,
    buckets_engagement,
    resumen_numerico,
    top_y_peores,
)
from keni_metricas.schema import Pieza, Plataforma


def _pieza(
    eng: float,
    vis: int = 1000,
    i: int = 0,
    plat: Plataforma = Plataforma.instagram,
    cuenta: str | None = None,
) -> Pieza:
    return Pieza(
        id=f"{cuenta or 'x'}-{plat.value}-p{i}-{eng}",
        plataforma=plat,
        titulo=f"Pieza {i}",
        publicado=date(2026, 5, 1),
        visualizaciones=vis,
        interacciones=int(vis * eng / 100),
        engagement_pct=eng,
        cuenta=cuenta,
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
    # el intervalo abierto superior no tiene fin.
    assert buckets[-1].fin is None


def test_top_y_peores_un_solo_grupo_ranking_por_vistas():
    # Un solo grupo (una marca/red): ranking directo por VISUALIZACIONES (alcance).
    # top = las MÁS vistas; peores = las MENOS vistas (de las restantes).
    piezas = [_pieza(eng=1.0, vis=v * 1000, i=v) for v in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]]
    top, peores = top_y_peores(piezas, n=5)
    assert [p.visualizaciones for p in top] == [12000, 11000, 10000, 9000, 8000]
    assert [p.visualizaciones for p in peores] == [1000, 2000, 3000, 4000, 5000]
    # ninguna pieza aparece en ambos
    assert not ({p.id for p in top} & {p.id for p in peores})


def test_peores_vacio_cuando_caben_en_top():
    piezas = [_pieza(e, i=i) for i, e in enumerate([1, 2, 3])]
    top, peores = top_y_peores(piezas, n=5)
    assert len(top) == 3
    assert peores == []


# --- Rendimiento relativo (score normalizado por grupo) ---------------------


def test_rendimiento_relativo_normaliza_contra_mediana_de_vistas_del_grupo():
    # IG: vistas 2000,4000,6000 -> mediana 4000. La pieza de 6000 rinde 1.5x su grupo.
    ig = [_pieza(5.0, vis=v, plat=Plataforma.instagram, cuenta="m", i=i)
          for i, v in enumerate([2000, 4000, 6000])]
    # TikTok con escala de vistas más baja: 500,1000,1500 -> mediana 1000. La de 1500: 1.5x.
    tk = [_pieza(5.0, vis=v, plat=Plataforma.tiktok, cuenta="m", i=i)
          for i, v in enumerate([500, 1000, 1500])]
    anotar_rendimiento_relativo(ig + tk)
    rr = {(p.plataforma, p.visualizaciones): p.rendimiento_relativo for p in ig + tk}
    # mismo ratio (1.5x) pese a escalas de vistas dispares -> comparación JUSTA entre redes.
    assert rr[(Plataforma.instagram, 6000)] == 1.5
    assert rr[(Plataforma.tiktok, 1500)] == 1.5
    assert rr[(Plataforma.instagram, 2000)] == 0.5
    assert rr[(Plataforma.tiktok, 500)] == 0.5


def test_rendimiento_relativo_mediana_cero_sin_division():
    # Todo el grupo sin vistas: mediana 0 y media 0 -> ratio None (sin baseline), no crashea.
    grupo = [_pieza(1.0, vis=0, plat=Plataforma.x, cuenta="m", i=i) for i in range(4)]
    anotar_rendimiento_relativo(grupo)
    assert all(p.rendimiento_relativo is None for p in grupo)


def test_rendimiento_relativo_mediana_cero_cae_a_media():
    # mediana 0 (3 de 5 piezas sin vistas) pero media > 0 -> usa la media como baseline.
    grupo = [_pieza(1.0, vis=v, plat=Plataforma.x, cuenta="m", i=i)
             for i, v in enumerate([0, 0, 0, 2, 3])]
    anotar_rendimiento_relativo(grupo)
    # media = 1.0 -> la de 2 vistas rinde 2.0x; ninguna explota.
    por_v = {p.visualizaciones: p.rendimiento_relativo for p in grupo}
    assert por_v[2] == 2.0
    assert por_v[0] == 0.0


# --- Orden global de top/peores por vistas (mezcla de marcas y redes) --------


def test_top_y_peores_orden_global_por_vistas():
    # Mezcla de marcas y redes con vistas dispares: top = las MÁS vistas globalmente
    # (desc), peores = las MENOS vistas; orden GLOBAL por alcance, sin estratificar.
    datos = [
        (900_000, Plataforma.instagram, "unotv"),
        (500_000, Plataforma.tiktok, "nacion_gamer"),
        (100_000, Plataforma.instagram, "claro_sports"),
        (50_000, Plataforma.facebook, "unotv"),
        (10_000, Plataforma.youtube, "claro_sports"),
        (5_000, Plataforma.x, "unotv"),
        (500, Plataforma.tiktok, "nacion_gamer"),
        (20, Plataforma.youtube, "claro_sports"),
    ]
    piezas = [_pieza(eng=5.0, vis=v, plat=plat, cuenta=marca, i=i)
              for i, (v, plat, marca) in enumerate(datos)]
    top, peores = top_y_peores(piezas, n=3)
    assert [p.visualizaciones for p in top] == [900_000, 500_000, 100_000]
    assert [p.visualizaciones for p in peores] == [20, 500, 5_000]
    assert not ({p.id for p in top} & {p.id for p in peores})
    # el badge rendimiento_relativo queda anotado (aunque no ordena).
    assert all(p.rendimiento_relativo is not None for p in top)
