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

# Mínimo de piezas de un formato para que su promedio sea señal y no una pieza suelta.
# Compartido por la dimensión de formato (engagement medio) y la de valor (save-rate).
MIN_PIEZAS_FORMATO = 2


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


# Intervalos fijos del histograma de engagement (%). El ultimo es abierto ("10%+").
_INTERVALOS_ENGAGEMENT: tuple[tuple[float, float | None], ...] = (
    (0, 2), (2, 4), (4, 6), (6, 8), (8, 10), (10, None),
)


def buckets_engagement(piezas: Sequence[Pieza]) -> list[DistribucionBucket]:
    """Histograma de piezas por intervalo de engagement (detecta concentracion del resultado)."""
    buckets: list[DistribucionBucket] = []
    for inicio, fin in _INTERVALOS_ENGAGEMENT:
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
    de `visualizaciones` y asigna a cada pieza del grupo:

        rendimiento_relativo = visualizaciones_pieza / mediana_vistas_del_grupo

    Mide el ALCANCE relativo (vistas) contra el baseline de su red, REFORZANDO el orden
    por vistas de top/peores: un valor 3.0 = "tuvo 3× las vistas de la mediana de su red"
    (el #1 más visto sale con un múltiplo alto/verde; los menos vistos <1×/rojo). Se usa
    vistas y no engagement a propósito: la tabla ordena por alcance, así que el badge debe
    leer en el mismo eje (un post viral tiene baja TASA de engagement pero altísimo
    alcance; comparar su tasa con la mediana lo pintaba en rojo y confundía).

    División por cero: si la mediana del grupo es 0, cae a la MEDIA del grupo; si la media
    también es 0, deja el ratio en `None` (no hay baseline). Muta y devuelve la misma lista
    de piezas (los modelos pydantic se actualizan in-place) para encadenar con `top_y_peores`.
    """
    grupos: dict[tuple[str | None, Plataforma], list[Pieza]] = {}
    for p in piezas:
        grupos.setdefault(_clave_grupo(p), []).append(p)

    for grupo in grupos.values():
        vistas = [p.visualizaciones for p in grupo]
        base = statistics.median(vistas)
        if base == 0:
            # mediana 0 (mitad o más del grupo sin vistas): cae a la media para no perder
            # toda señal; si la media también es 0, no hay baseline -> ratio None.
            base = statistics.fmean(vistas)
        for p in grupo:
            p.rendimiento_relativo = (
                round(p.visualizaciones / base, 3) if base else None
            )
    return list(piezas)


# Mínimo de piezas CON vistas para que la concentración (Pareto) sea señal y no una
# anécdota de un puñado de posts. Con <5 piezas el "80% de las vistas" no dice nada.
MIN_PIEZAS_CONCENTRACION = 5

# Cuota de vistas que la cabeza del ranking debe cubrir para el hallazgo de concentración
# (el 80/20 de Pareto). Se acumulan piezas de más a menos vistas hasta cruzar este umbral.
UMBRAL_CONCENTRACION = 0.80


def concentracion_vistas(piezas: Sequence[Pieza]) -> dict | None:
    """Concentración 80/20 (Pareto) de las visualizaciones del periodo, o None sin señal.

    Ordena las piezas por visualizaciones de mayor a menor y acumula hasta cubrir
    ≥`UMBRAL_CONCENTRACION` del total de vistas; devuelve cuántas piezas bastan para
    ello (`n_piezas_80`), el total de piezas con vistas (`total_piezas`) y qué fracción
    de piezas representan (`pct_piezas`, 0-100 redondeado). Mide si el resultado del
    periodo lo cargan unas pocas piezas o está repartido.

    None si hay menos de `MIN_PIEZAS_CONCENTRACION` piezas con vistas o el total de
    vistas es 0 (sin base para un Pareto): degradación honesta, no un dato inventado.
    """
    con_vistas = sorted(
        (p.visualizaciones for p in piezas if p.visualizaciones > 0), reverse=True
    )
    total_piezas = len(con_vistas)
    total_vistas = sum(con_vistas)
    if total_piezas < MIN_PIEZAS_CONCENTRACION or total_vistas <= 0:
        return None
    objetivo = total_vistas * UMBRAL_CONCENTRACION
    acumulado = 0
    n_piezas_80 = 0
    for vistas in con_vistas:
        acumulado += vistas
        n_piezas_80 += 1
        if acumulado >= objetivo:
            break
    return {
        "n_piezas_80": n_piezas_80,
        "total_piezas": total_piezas,
        "pct_piezas": round(n_piezas_80 / total_piezas * 100),
    }


def save_rate_por_formato(piezas: Sequence[Pieza]) -> dict[str, dict] | None:
    """Save-rate (guardados+compartidos ÷ vistas) por formato, o None si no hay dato.

    La señal de VALOR ("contenido que se guarda/comparte") es distinta del engagement:
    guardar o compartir una pieza es un voto fuerte de utilidad. Por FORMATO (necesita
    ≥`MIN_PIEZAS_FORMATO` piezas, el mismo criterio que la dimensión de formato) agrega
    guardados+compartidos y visualizaciones y calcula la tasa (0-100). Los campos
    granulares ausentes (`None`) cuentan como 0.

    None si NINGÚN formato tiene datos reales de guardados+compartidos (>0): muchas redes
    no exponen `guardados` y no se inventa una tasa sobre un cero.
    """
    acum: dict[str, dict[str, int]] = {}
    for p in piezas:
        fmt = p.formato
        if not fmt or p.visualizaciones <= 0:
            continue
        celda = acum.setdefault(fmt, {"valor": 0, "vistas": 0, "n": 0})
        celda["valor"] += (p.guardados or 0) + (p.compartidos or 0)
        celda["vistas"] += p.visualizaciones
        celda["n"] += 1
    salida: dict[str, dict] = {}
    for fmt, celda in acum.items():
        if celda["n"] < MIN_PIEZAS_FORMATO or celda["vistas"] <= 0:
            continue
        salida[fmt] = {
            "save_rate": round(celda["valor"] / celda["vistas"] * 100, 2),
            "n": celda["n"],
            "valor": celda["valor"],
        }
    if not salida or not any(c["valor"] > 0 for c in salida.values()):
        return None
    return salida


def top_y_peores(piezas: Sequence[Pieza], n: int = 5) -> tuple[list[Pieza], list[Pieza]]:
    """`(top, peores)` ordenados por VISUALIZACIONES (alcance absoluto).

    Decisión de producto (validada con el usuario): Mejores = las `n` piezas MÁS vistas;
    Peores = las `n` MENOS vistas (de las restantes, sin solapar con el top). Orden GLOBAL
    por vistas, SIN estratificar: el #1 es simplemente la pieza con más alcance, igual que
    ordenar la tabla por su columna "Vistas". (Una versión anterior estratificaba por
    marca×red para forzar variedad, pero eso metía piezas diminutas en el Top solo por
    "representar" una red de bajo volumen, lo que contradecía el orden por alcance.)

    `rendimiento_relativo` (engagement ÷ mediana de su grupo marca×red) se sigue anotando
    como insignia secundaria para contextualizar cada pieza contra su red, pero NO ordena.

    Si hay <= n piezas, peores es [] (todas caben en el top).
    """
    if not piezas:
        return [], []

    anotar_rendimiento_relativo(piezas)

    ordenadas = sorted(piezas, key=lambda p: p.visualizaciones, reverse=True)
    top = ordenadas[:n]
    # peores: las MENOS vistas de las que NO entraron en el top (sin solape).
    peores = sorted(ordenadas[n:], key=lambda p: p.visualizaciones)[:n]
    return top, peores
