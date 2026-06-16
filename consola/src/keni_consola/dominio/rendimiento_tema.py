"""Señal de RENDIMIENTO para el ranking: prioriza noticias de las líneas que MEJOR funcionan.

Idea (simple y honesta): de las piezas ya medidas (Metricool), sacamos las LÍNEAS
editoriales con mejor rendimiento y damos un empujón a las historias del pool que caen en esas
líneas. ANTI-SESGO incorporado: una línea solo cuenta como "top" si tiene una MUESTRA mínima de
piezas (`minimo_piezas`) — así "funcionó UNA vez" no la encarama — y se limita a un top-N (no se
premia todo), de modo que el feed no se monotematiza.

Este módulo es PURO (sin BD ni red): recibe la analítica por línea ya leída y devuelve el conjunto
de líneas top. El daemon obtiene la analítica (fachada de métricas, cacheada), clasifica cada
historia a su línea (léxico, `clasificador_lineas`) y aplica el bonus. GATEADO y best-effort: sin
datos suficientes el conjunto top sale vacío y la señal es inerte.
"""

from __future__ import annotations

from typing import Any


def lineas_top(
    lineas: list[dict[str, Any]], *, minimo_piezas: int, n: int
) -> set[str]:
    """Nombres de las líneas con MEJOR engagement, con muestra mínima (anti-sesgo) y tope N.

    `lineas`: cubos `{nombre|id, piezas, engagement_pct}` (de `metricas_linea`). Se descartan las
    líneas con menos de `minimo_piezas` piezas medidas (evita el sesgo de "una pieza con suerte")
    y la línea "Sin línea" (id/nombre vacío). Se ordena por engagement desc y se toman las N
    primeras. Devuelve un set de NOMBRES (lo que `clasificador_lineas` resuelve por historia).
    """
    if n <= 0:
        return set()
    candidatas = [
        c for c in lineas
        if str(c.get("nombre") or c.get("id") or "").strip()
        and int(c.get("piezas") or 0) >= max(1, minimo_piezas)
    ]
    candidatas.sort(key=lambda c: float(c.get("engagement_pct") or 0.0), reverse=True)
    return {
        str(c.get("nombre") or c.get("id")).strip()
        for c in candidatas[:n]
    }


def bonus_de_historia(linea_nombre: str | None, top: set[str]) -> float:
    """Bonus [0,1] de una historia según su línea: 1.0 si su línea está en el top, 0.0 si no."""
    if not linea_nombre:
        return 0.0
    return 1.0 if linea_nombre.strip() in top else 0.0
