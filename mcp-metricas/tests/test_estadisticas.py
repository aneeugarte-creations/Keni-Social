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
    # el tramo abierto superior no tiene fin.
    assert buckets[-1].fin is None


def test_top_y_peores_un_solo_grupo_ranking_por_engagement():
    # Una sola marca/red (grupo único): degrada al ranking por mérito (engagement).
    # top = los de mayor engagement; peores = los de menor (de las restantes).
    piezas = [_pieza(eng=float(e), i=e) for e in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]]
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


# --- Rendimiento relativo (score normalizado por grupo) ---------------------


def test_rendimiento_relativo_normaliza_contra_mediana_del_grupo():
    # IG: engagements 2,4,6 -> mediana 4. La pieza de 6 rinde 1.5x su grupo.
    ig = [_pieza(e, plat=Plataforma.instagram, cuenta="m", i=e) for e in [2.0, 4.0, 6.0]]
    # TikTok con baseline mucho más bajo: 0.5,1,1.5 -> mediana 1. La de 1.5 rinde 1.5x.
    tk = [_pieza(e, plat=Plataforma.tiktok, cuenta="m", i=int(e * 10)) for e in [0.5, 1.0, 1.5]]
    anotar_rendimiento_relativo(ig + tk)
    rr = {(p.plataforma, p.engagement_pct): p.rendimiento_relativo for p in ig + tk}
    # mismo ratio (1.5x) pese a baselines dispares -> comparación JUSTA entre redes.
    assert rr[(Plataforma.instagram, 6.0)] == 1.5
    assert rr[(Plataforma.tiktok, 1.5)] == 1.5
    assert rr[(Plataforma.instagram, 2.0)] == 0.5
    assert rr[(Plataforma.tiktok, 0.5)] == 0.5


def test_rendimiento_relativo_mediana_cero_sin_division():
    # Todo el grupo en 0: mediana 0 y media 0 -> ratio None (sin baseline), no crashea.
    grupo = [_pieza(0.0, plat=Plataforma.x, cuenta="m", i=i) for i in range(4)]
    anotar_rendimiento_relativo(grupo)
    assert all(p.rendimiento_relativo is None for p in grupo)


def test_rendimiento_relativo_mediana_cero_cae_a_media():
    # mediana 0 (3 de 5 piezas en 0) pero media > 0 -> usa la media como baseline.
    grupo = [_pieza(e, plat=Plataforma.x, cuenta="m", i=i) for i, e in enumerate([0.0, 0.0, 0.0, 2.0, 3.0])]
    anotar_rendimiento_relativo(grupo)
    # media = 1.0 -> la de eng 2.0 rinde 2.0x; ninguna explota.
    por_eng = {p.engagement_pct: p.rendimiento_relativo for p in grupo}
    assert por_eng[2.0] == 2.0
    assert por_eng[0.0] == 0.0


# --- Estratificación de top/peores (no colapsa a una red ni una marca) ------


def _muestra_baselines_dispares() -> list[Pieza]:
    """Muestra con redes y marcas de baselines ESTRUCTURALMENTE distintos.

    IG: vistas altas + engagement alto; TikTok: vistas bajas + engagement bajo;
    FB/X/YT intermedios. Tres marcas. Rankear por CUALQUIER métrica global (vistas o
    engagement) colapsaría top a IG y worst a TikTok; la estratificación no debe.
    """
    specs = {
        Plataforma.instagram: (300_000, 5.0),
        Plataforma.tiktok: (400, 1.2),
        Plataforma.facebook: (50_000, 2.0),
        Plataforma.x: (8_000, 0.8),
        Plataforma.youtube: (20_000, 3.5),
    }
    piezas: list[Pieza] = []
    for marca in ("claro_sports", "unotv", "nacion_gamer"):
        for plat, (base_vis, base_eng) in specs.items():
            for i in range(6):
                # jitter determinista (sin random): factor 0.6..1.6 por índice.
                f = 0.6 + 0.2 * i
                piezas.append(
                    _pieza(
                        eng=round(base_eng * f, 2),
                        vis=int(base_vis * f),
                        i=i,
                        plat=plat,
                        cuenta=marca,
                    )
                )
    return piezas


def test_top_y_peores_no_colapsan_a_una_red_ni_una_marca():
    piezas = _muestra_baselines_dispares()
    top, peores = top_y_peores(piezas, n=5)

    # top y worst representan VARIAS redes (no monopolio de IG ni de TikTok)...
    assert len({p.plataforma for p in top}) > 1
    assert len({p.plataforma for p in peores}) > 1
    # ...y VARIAS marcas cuando se agregan todas.
    assert len({p.cuenta for p in top}) > 1
    assert len({p.cuenta for p in peores}) > 1
    # no solapan
    assert not ({p.id for p in top} & {p.id for p in peores})
    # el score normalizado quedó anotado en las piezas seleccionadas.
    assert all(p.rendimiento_relativo is not None for p in top)


def test_top_estratificado_cubre_cada_red_con_una_marca():
    # Una sola marca, 5 redes, n=5 -> round-robin saca ~1 por red (cobertura total).
    specs = {
        Plataforma.instagram: 5.0,
        Plataforma.tiktok: 1.2,
        Plataforma.facebook: 2.0,
        Plataforma.x: 0.8,
        Plataforma.youtube: 3.5,
    }
    piezas: list[Pieza] = []
    for plat, base in specs.items():
        for i in range(4):
            piezas.append(_pieza(eng=base * (0.7 + 0.2 * i), plat=plat, cuenta="m", i=i))
    top, _ = top_y_peores(piezas, n=5)
    # las 5 redes representadas en el top (no colapsa a IG por tener vistas/eng altos).
    assert {p.plataforma for p in top} == set(specs)
