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
    """Clave de ranking de top/peores: VISUALIZACIONES (alcance absoluto).

    Por decisión de producto, Mejores/Peores se ordenan por alcance (vistas): el #1 es la
    pieza MÁS vista y los peores las MENOS vistas. La estratificación marca×red (ver
    `_seleccionar`) se mantiene para que el resultado REPRESENTE varias marcas y redes en
    vez de colapsar a la de mayor volumen. El `rendimiento_relativo` se sigue anotando
    como insignia secundaria (× mediana de su grupo), pero NO ordena.
    """
    return float(p.visualizaciones)


# Una "rama" de la estratificación: una marca con sus redes, cada red ya ordenada
# por mérito (lista de piezas mejor->peor o peor->mejor según el extremo buscado).
_Rama = list[list[Pieza]]


def _seleccionar(ramas: list[_Rama], n: int, *, mejor: bool) -> list[Pieza]:
    """Estratifica por GRUPO (marca×red): round-robin entre todos los grupos.

    `ramas` es una lista por marca; cada rama es una lista de redes (grupos marca×red) ya
    ordenadas por mérito en la dirección pedida. Se APLANAN a la lista de grupos y se hace
    round-robin: en cada ronda se toma el próximo candidato de cada grupo con pendientes,
    ordenados por mérito (mayor para el top, menor para los peores). Así los primeros N
    slots salen de N grupos DISTINTOS cuando hay >= N grupos: el top muestra la pieza más
    representativa (la MÁS vista) de cada segmento marca×red, garantizando variedad de
    marca Y de red en vez de colapsar a la de mayor volumen. Con un solo grupo degrada al
    ranking directo (n mejores del grupo por mérito).
    """
    grupos = [red for rama in ramas for red in rama]  # cada grupo = (marca, red) ordenado
    indices = [0] * len(grupos)
    seleccion: list[Pieza] = []
    while len(seleccion) < n:
        # próximo candidato de cada grupo con pendientes, ordenado por mérito.
        proximos = [
            (_score(grupos[g][indices[g]]), g)
            for g in range(len(grupos))
            if indices[g] < len(grupos[g])
        ]
        if not proximos:
            break  # todos los grupos agotados
        proximos.sort(key=lambda t: t[0], reverse=mejor)
        for _, g in proximos:
            if len(seleccion) >= n:
                break
            seleccion.append(grupos[g][indices[g]])
            indices[g] += 1
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

    El problema que resuelve: ordenar por una métrica global SIN estratificar colapsa top
    y peores a una sola red/marca (IG mueve cientos de miles de vistas; TikTok cientos).
    Aquí el ranking es por VISUALIZACIONES (alcance absoluto; decisión de producto: el #1
    es la pieza MÁS vista, los peores las MENOS vistas), pero la SELECCIÓN es estratificada
    por marca×red para GARANTIZAR representación de varias marcas y redes (round-robin, ver
    `_seleccionar`). El `rendimiento_relativo` (engagement ÷ mediana de su grupo) se anota
    como insignia secundaria, no como criterio de orden.

    Estratificación (garantiza diversidad):
      - Las piezas se agrupan por GRUPO (marca×red); cada grupo se ordena por mérito
        (visualizaciones) en la dirección buscada.
      - Selección round-robin entre GRUPOS: en cada ronda se toma el próximo candidato de
        cada grupo con pendientes, ordenados por mérito (más vistas para el top, menos
        para los peores). Los primeros N slots salen de N grupos DISTINTOS cuando hay
        >= N grupos -> el top muestra la pieza MÁS vista de cada segmento marca×red, y
        cubre varias marcas Y redes en vez de colapsar a la de mayor volumen.
      - Para el TOP se toma el extremo ALTO de cada grupo; para los PEORES, el BAJO.
        Los peores NO solapan con el top (se excluyen las piezas ya elegidas).
      - El mérito se mantiene DENTRO de cada grupo (el primero de un grupo es realmente
        el más/menos visto de ese grupo); la estratificación solo decide de qué grupo
        sale cada slot.

    Caso degenerado (un solo grupo, p.ej. una marca con una red): degrada al ranking
    directo: top = `n` más vistas, peores = `n` menos vistas de las restantes. Si hay
    <= n piezas, peores es [] (todo cupo en el top).
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
