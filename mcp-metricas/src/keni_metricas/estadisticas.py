"""Estadisticas de piezas: media, mediana, percentiles, distribucion y top/peores.

Funciones PURAS sobre listas de `Pieza` (o de numeros). Coste 0 de API: operan sobre
las piezas que `mejores_piezas` ya descarga del periodo. Todo tolera listas vacias o de
un solo elemento (la desviacion necesita n>=2) devolviendo `None` en vez de romper, para
que la UI distinga "0" de "sin dato".
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable, Sequence

from .schema import DistribucionBucket, EstadisticasNumericas, Pieza


def _percentil(ordenados: Sequence[float], pct: float) -> float:
    """Percentil `pct` (0-100) por interpolacion lineal. `ordenados` debe venir ordenado."""
    if len(ordenados) == 1:
        return ordenados[0]
    k = (len(ordenados) - 1) * (pct / 100.0)
    inf = math.floor(k)
    sup = math.ceil(k)
    if inf == sup:
        return ordenados[int(k)]
    return ordenados[inf] * (sup - k) + ordenados[sup] * (k - inf)


def resumen_numerico(valores: Iterable[float | int | None]) -> EstadisticasNumericas:
    """Resumen estadistico de una serie (media/mediana/p25/p75/min/max/desviacion)."""
    vals = sorted(float(v) for v in valores if v is not None)
    n = len(vals)
    if n == 0:
        return EstadisticasNumericas(n=0)
    return EstadisticasNumericas(
        n=n,
        media=round(statistics.fmean(vals), 2),
        mediana=round(statistics.median(vals), 2),
        p25=round(_percentil(vals, 25), 2),
        p75=round(_percentil(vals, 75), 2),
        minimo=round(vals[0], 2),
        maximo=round(vals[-1], 2),
        # la desviacion (muestral) necesita al menos dos valores.
        desviacion=round(statistics.stdev(vals), 2) if n >= 2 else None,
    )


# Tramos fijos del histograma de engagement (%). El ultimo es abierto ("10%+").
_TRAMOS_ENGAGEMENT: tuple[tuple[float, float | None], ...] = (
    (0, 2), (2, 4), (4, 6), (6, 8), (8, 10), (10, None),
)


def buckets_engagement(piezas: Sequence[Pieza]) -> list[DistribucionBucket]:
    """Histograma de piezas por tramo de engagement (detecta concentracion del resultado)."""
    buckets: list[DistribucionBucket] = []
    for inicio, fin in _TRAMOS_ENGAGEMENT:
        if fin is None:
            n = sum(1 for p in piezas if p.engagement_pct >= inicio)
            etiqueta = f"{int(inicio)}%+"
        else:
            n = sum(1 for p in piezas if inicio <= p.engagement_pct < fin)
            etiqueta = f"{int(inicio)}–{int(fin)}%"
        buckets.append(
            DistribucionBucket(etiqueta=etiqueta, inicio=float(inicio), fin=fin, n=n)
        )
    return buckets


def top_y_peores(piezas: Sequence[Pieza], n: int = 5) -> tuple[list[Pieza], list[Pieza]]:
    """`(top, peores)` por engagement. Los peores NO solapan con el top.

    Ordena por engagement descendente: top = las `n` primeras; peores = las `n` mas
    bajas DE LAS RESTANTES (peor primero). Si hay <= n piezas, peores es []: cuando
    todo cabe en el top no hay "peores" que mostrar.
    """
    ordenadas = sorted(piezas, key=lambda p: p.engagement_pct, reverse=True)
    top = ordenadas[:n]
    restantes = ordenadas[n:]
    peores = list(reversed(restantes[-n:])) if restantes else []
    return top, peores
