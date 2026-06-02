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

from .schema import DistribucionBucket, EstadisticasNumericas, Pieza, Plataforma


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


def _clave_grupo(p: Pieza) -> tuple[str | None, Plataforma]:
    """Grupo de comparación de una pieza: (marca, red).

    El baseline de engagement es estructuralmente distinto por red (IG mueve
    cientos de miles de vistas con engagement alto; TikTok cientos con engagement
    bajo) y por marca (deportes vs. noticias interactúan distinto). Comparar contra
    la mediana de su PROPIO grupo (marca×red) es lo único justo. Si la pieza no lleva
    marca (`cuenta=None`), el grupo es solo la red.
    """
    return (p.cuenta, p.plataforma)


def anotar_rendimiento_relativo(piezas: Sequence[Pieza]) -> list[Pieza]:
    """Anota cada pieza con su `rendimiento_relativo` vs. la mediana de su grupo.

    Para cada grupo (marca×red, o red si la pieza no lleva marca) calcula la mediana
    de `engagement_pct` y asigna a cada pieza del grupo:

        rendimiento_relativo = engagement_pct_pieza / mediana_engagement_del_grupo

    Esto NORMALIZA el rendimiento contra el baseline propio de cada red/marca, de modo
    que piezas de redes con escalas dispares (IG vs. TikTok) se comparen de forma JUSTA:
    un valor 3.0 = "rindió 3× la mediana de su grupo".

    División por cero: si la mediana del grupo es 0 (todas las piezas del grupo tienen
    engagement 0), cae a la MEDIA del grupo; si la media también es 0, deja el ratio en
    `None` (no hay baseline contra el que comparar). Muta y devuelve la misma lista de
    piezas (los modelos pydantic se actualizan in-place) para encadenar con `top_y_peores`.
    """
    grupos: dict[tuple[str | None, Plataforma], list[Pieza]] = {}
    for p in piezas:
        grupos.setdefault(_clave_grupo(p), []).append(p)

    for grupo in grupos.values():
        engs = [p.engagement_pct for p in grupo]
        base = statistics.median(engs)
        if base == 0:
            # mediana 0 (mitad o más del grupo en 0): cae a la media para no perder
            # toda señal; si la media también es 0, no hay baseline -> ratio None.
            base = statistics.fmean(engs)
        for p in grupo:
            p.rendimiento_relativo = (
                round(p.engagement_pct / base, 3) if base else None
            )
    return list(piezas)


def _score(p: Pieza) -> float:
    """Score de mérito DENTRO de su grupo para rankear top/peores.

    Prefiere el `rendimiento_relativo` (normalizado contra el baseline del grupo, lo
    JUSTO entre redes dispares); si no se computó (None), cae al `engagement_pct` crudo
    —válido porque el ranking se hace dentro de cada grupo, donde la base es homogénea.
    """
    return p.rendimiento_relativo if p.rendimiento_relativo is not None else p.engagement_pct


# Una "rama" de la estratificación: una marca con sus redes, cada red ya ordenada
# por mérito (lista de piezas mejor->peor o peor->mejor según el extremo buscado).
_Rama = list[list[Pieza]]


def _siguiente_de_rama(rama: _Rama, indices: list[int], *, mejor: bool) -> int | None:
    """Índice de la RED de `rama` cuyo próximo candidato es el más representativo.

    Recorre las redes de una marca con candidato pendiente y devuelve la que aporta el
    mejor candidato en la dirección pedida (mayor score para el top, menor para los
    peores). `None` si la marca ya no tiene candidatos. Esto da VARIEDAD de red dentro
    de la marca: en rondas sucesivas se va alternando la red de mayor mérito restante.
    """
    cand = [r for r in range(len(rama)) if indices[r] < len(rama[r])]
    if not cand:
        return None
    return (max if mejor else min)(cand, key=lambda r: _score(rama[r][indices[r]]))


def _seleccionar(ramas: list[_Rama], n: int, *, mejor: bool) -> list[Pieza]:
    """Estratifica marca×red: round-robin entre MARCAS, y dentro de cada una, por red.

    `ramas` es una lista por marca; cada rama es una lista de redes ya ordenadas por
    mérito en la dirección pedida. La selección prioriza COBERTURA DE MARCA: en cada
    ronda toma UNA pieza de cada marca con candidatos pendientes (así no sale todo de
    una marca), y dentro de cada marca elige la RED cuyo próximo candidato es el más
    representativo del extremo buscado (variedad de red). Con N=5 y 5 marcas sale ~1
    por marca; con 1 marca y 5 redes, ~1 por red; con marca×red dispares, reparte
    cubriendo primero marcas y luego variando red. Mérito conservado DENTRO de cada
    (marca, red).
    """
    indices = [[0] * len(rama) for rama in ramas]
    seleccion: list[Pieza] = []
    while len(seleccion) < n:
        # marcas con candidato pendiente, ordenadas por el mérito de su mejor próximo
        # candidato (para que, con más marcas que slots, ganen las más representativas).
        proximos: list[tuple[float, int, int]] = []
        for m, rama in enumerate(ramas):
            r = _siguiente_de_rama(rama, indices[m], mejor=mejor)
            if r is not None:
                proximos.append((_score(rama[r][indices[m][r]]), m, r))
        if not proximos:
            break  # todas las marcas agotadas
        proximos.sort(key=lambda t: t[0], reverse=mejor)
        # una ronda: una pieza de cada marca disponible antes de repetir marca.
        for _, m, r in proximos:
            if len(seleccion) >= n:
                break
            seleccion.append(ramas[m][r][indices[m][r]])
            indices[m][r] += 1
    return seleccion


def _construir_ramas(
    piezas: Sequence[Pieza], *, mejor: bool, excluir: set[int] | None = None
) -> list[_Rama]:
    """Agrupa piezas en ramas marca→red, cada red ordenada por mérito (dirección `mejor`).

    Orden estable de marcas (por id, None al final) y de redes (por valor) para una
    salida determinista. `excluir` (ids de objeto) descarta piezas ya elegidas (para que
    los peores no solapen con el top). Devuelve solo ramas/redes no vacías.
    """
    excluir = excluir or set()
    por_marca: dict[str | None, dict[Plataforma, list[Pieza]]] = {}
    for p in piezas:
        if id(p) in excluir:
            continue
        por_marca.setdefault(p.cuenta, {}).setdefault(p.plataforma, []).append(p)

    ramas: list[_Rama] = []
    for marca in sorted(por_marca, key=lambda m: (m is None, m or "")):
        redes = por_marca[marca]
        rama = [
            sorted(redes[plat], key=_score, reverse=mejor)
            for plat in sorted(redes, key=lambda x: x.value)
        ]
        if rama:
            ramas.append(rama)
    return ramas


def top_y_peores(piezas: Sequence[Pieza], n: int = 5) -> tuple[list[Pieza], list[Pieza]]:
    """`(top, peores)` REPRESENTATIVOS por marca y red, score = rendimiento vs su grupo.

    El problema que resuelve: rankear por CUALQUIER métrica global (visualizaciones o
    engagement) colapsa top y peores a una sola red/marca, porque las redes tienen
    baselines estructuralmente distintos (IG mueve cientos de miles de vistas; TikTok
    cientos; IG engagement alto, TikTok bajo). Aquí el ranking es por
    `rendimiento_relativo` (engagement de la pieza ÷ mediana de su grupo marca×red),
    que NORMALIZA contra el baseline propio y hace la comparación JUSTA entre redes:
    un score 3.0 = "rindió 3× la mediana de su grupo".

    Estratificación (garantiza diversidad), en DOS niveles:
      - Las piezas se agrupan por MARCA y, dentro de cada marca, por RED; cada grupo
        (marca×red) se ordena por mérito (score normalizado).
      - Selección round-robin: en cada ronda se toma UNA pieza de cada MARCA con
        candidatos (prioriza cubrir marcas: no sale todo de una sola), y dentro de la
        marca se elige la RED cuyo próximo candidato es el más representativo del
        extremo buscado (variedad de red). Con N=5 y 5 marcas/redes sale ~1 por
        marca/red; con menos, se reparte.
      - Para el TOP se toma el extremo ALTO de cada grupo; para los PEORES, el BAJO.
        Los peores NO solapan con el top (se excluyen las piezas ya elegidas).
      - El mérito se mantiene DENTRO de cada grupo (el primero de un grupo es realmente
        el mejor/peor de ese grupo); la estratificación solo decide de qué grupo sale
        cada slot.

    Caso degenerado (un solo grupo, p.ej. una marca con una red): degrada al
    comportamiento intuitivo: top = `n` mejores por score, peores = `n` peores de las
    restantes. Si hay <= n piezas, peores es [] (todo cupo en el top).
    """
    if not piezas:
        return [], []

    anotar_rendimiento_relativo(piezas)

    top = _seleccionar(_construir_ramas(piezas, mejor=True), n, mejor=True)

    # los peores NO deben solapar con el top: se reconstruyen las ramas (peor->mejor)
    # excluyendo las piezas ya elegidas en el top.
    ids_top = {id(p) for p in top}
    peores = _seleccionar(
        _construir_ramas(piezas, mejor=False, excluir=ids_top), n, mejor=False
    )
    return top, peores
