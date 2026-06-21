"""Utilidades puras de calculo de metricas — fuente UNICA del monorepo.

`engagement_pct()` es el UNICO sitio donde se define la formula de engagement.
Toda metrica/pieza (real, de muestra, agregada o de reporte) la usa.

Sin estado ni I/O: solo aritmetica.
"""

from __future__ import annotations


def engagement_pct(interacciones: int, visualizaciones: int) -> float:
    """Porcentaje de engagement = interacciones / visualizaciones * 100 (1 decimal).

    Formula unica de todo el monorepo. Si no hay visualizaciones devuelve 0.0 (no
    se divide por cero).
    """
    return round(interacciones / visualizaciones * 100, 1) if visualizaciones else 0.0
