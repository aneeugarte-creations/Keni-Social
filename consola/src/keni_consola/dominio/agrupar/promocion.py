"""Umbral de PROMOCIÓN a producción automática (auto-producción). PURA.

El score que lista el panel y el umbral que dispara producción son dos niveles distintos a
propósito: encolar Verificar+Redactar (coste real de tokens) exige un umbral más alto y explicable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ._comun import (
    BREAKING_PESO_DEF,
    BREAKING_VENTANA_H_DEF,
    _parse_iso,
)
from .corroboracion import peso_ventana_actual
from .scoring import puntuar_detalle

# El score que LISTA el panel y el umbral que DISPARA producción automática son dos niveles
# distintos a propósito: el panel muestra el pool jerarquizado (todo lo que pasó la entrada),
# pero encolar Verificar+Redactar (`claude -p`, coste real de tokens) exige un umbral MÁS ALTO y
# EXPLICABLE. Defaults conservadores; editables en caliente desde la consola.
LISTON_MIN_SCORE_DEF = 0.35
LISTON_MIN_MARCA_DEF = 0.2


def evaluar_liston(
    cluster: dict[str, Any],
    *,
    palabras_marca: frozenset[str] = frozenset(),
    min_score: float = LISTON_MIN_SCORE_DEF,
    min_marca: float = LISTON_MIN_MARCA_DEF,
    min_maduracion_min: int = 0,
    ahora: datetime | None = None,
    breaking_peso: float = BREAKING_PESO_DEF,
    breaking_ventana_h: int = BREAKING_VENTANA_H_DEF,
) -> tuple[bool, str]:
    """¿Esta historia supera el UMBRAL de producción automática? `(supera, motivo)`. PURA.

    Reglas, en orden (el motivo explica la PRIMERA que falla):
      1. VERIFICACIÓN: una historia `dudosa` (única fuente de baja confianza / clickbait)
         jamás dispara producción automática, puntúe lo que puntúe.
      2. MADURACIÓN: la historia debe llevar al menos `min_maduracion_min` minutos en el
         pool (desde `primer_visto`) antes de competir por plaza. Promover al primer
         avistamiento elige con UNA fuente y señal a medio acumular; esperar deja que la
         corroboración/viralidad separen lo grande de lo irrelevante y la selección compare
         historias maduras entre sí. Exentas: CURADAS por el equipo y BREAKING
         corroboradas (la urgencia real no espera). `0` desactiva la regla; sin
         `primer_visto` parseable no se retiene (no se castiga un dato ausente).
      3. SCORE: el score RECALCULADO AHORA (no el persistido, que envejece entre re-scores)
         debe alcanzar `min_score`.
      4. ENCAJE DE MARCA: la relevancia por vocabulario debe alcanzar `min_marca`. Exentas:
         las historias CURADAS por el equipo (señal artificial de cajón: el humano ya decidió)
         y las BREAKING CORROBORADAS (evento mayor confirmado por varias fuentes a la vez,
         cuyo vocabulario puede ser nuevo).
    Devuelve siempre un motivo legible (también al superar): es la explicación que se muestra.
    """
    from ..ingesta import SENAL_CURADO

    if (cluster.get("verificacion") or "") == "dudosa":
        return False, "verificación dudosa (única fuente no fiable o clickbait)"
    curada = int(cluster.get("senal") or 0) >= SENAL_CURADO
    # Breaking EN VIVO si hay timeline (misma derivación que el scoring: masa ponderada en la
    # ventana actual, decae sola); sin timeline se respeta el flag persistido. Así el umbral
    # no depende de un flag desfasado entre re-scores.
    detalle_liston = cluster.get("fuentes_detalle") or []
    if isinstance(detalle_liston, list) and detalle_liston:
        masa_v, n_v = peso_ventana_actual(
            detalle_liston, ventana_h=breaking_ventana_h, ahora=ahora
        )
        es_breaking_vivo = n_v >= 2 and masa_v >= breaking_peso
    else:
        es_breaking_vivo = bool(int(cluster.get("breaking") or 0))
    breaking_corroborada = es_breaking_vivo and (
        (cluster.get("verificacion") or "") == "corroborada"
    )
    if min_maduracion_min > 0 and not curada and not breaking_corroborada:
        visto = _parse_iso(str(cluster.get("primer_visto") or ""))
        if visto is not None:
            momento = ahora or datetime.now(UTC)
            if momento.tzinfo is None:
                momento = momento.replace(tzinfo=UTC)
            edad_min = (momento - visto).total_seconds() / 60.0
            if edad_min < min_maduracion_min:
                return False, (
                    f"madurando ({edad_min:.0f} de {min_maduracion_min} min en el pool): "
                    "se promueve cuando la corroboración haya tenido tiempo de acumularse"
                )
    score, _razon, desglose = puntuar_detalle(
        cluster, palabras_marca=palabras_marca, ahora=ahora,
        breaking_peso=breaking_peso, breaking_ventana_h=breaking_ventana_h,
    )
    if score < min_score:
        return False, f"score {score:.2f} < {min_score:.2f} (listón de producción)"
    s_marca = float(desglose["marca"])
    if s_marca < min_marca:
        if not curada and not breaking_corroborada:
            return False, (
                f"encaje con la marca {s_marca:.2f} < {min_marca:.2f} "
                "(no casa el vocabulario de la marca)"
            )
    palabras = ", ".join(desglose["palabras"][:4])
    detalle = f" — casa: {palabras}" if palabras else ""
    return True, f"score {score:.2f} ≥ {min_score:.2f}{detalle}"
