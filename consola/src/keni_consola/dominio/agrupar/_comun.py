"""Helpers y constantes COMPARTIDAS del dominio de clustering (capa pura).

Núcleo común que reutilizan varias áreas del paquete: normalización de fechas/texto,
escalado logarítmico, y el ratio fuzzy de claves (directo + token-sort, con veto de
números incompatibles). Sin BD ni red.
"""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from difflib import SequenceMatcher

from .. import similitud

# Longitud mínima de una clave normalizada para entrar al fuzzy de la SELECCIÓN DIVERSA
# (`scoring.seleccionar_diversos`): títulos muy cortos disparan ratios altos espurios entre sí.
_MIN_LONGITUD_FUZZY = 8

# Umbral de "breaking" PONDERADO por defecto (lo fija el daemon vía config). Una historia es
# breaking si la MASA de fuentes (Σ peso por outlet) que se sumaron en la ventana ACTUAL
# alcanza este mínimo: 3 normales, 1 potente + 1 normal, o 2 potentes. Como la ventana se
# ancla en AHORA, el flag DECAE solo (un breaking de ayer deja de serlo): breaking es una
# consecuencia del ranking (corroboración ponderada × velocidad), no un carril aparte.
BREAKING_PESO_DEF = 3.0
BREAKING_VENTANA_H_DEF = 6


def _parse_iso(valor: str) -> datetime | None:
    """Parsea un ISO 8601 a datetime aware (UTC); None si no parsea. Best-effort."""
    if not valor:
        return None
    try:
        dt = datetime.fromisoformat(valor)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _sin_acentos(texto: str) -> str:
    """Minúsculas sin acentos (delega en el helper de similitud)."""
    return similitud.sin_acentos((texto or "").lower())


def _log_norm(valor: int, satura: int) -> float:
    """Escala logarítmica [0,1]: 0 → 0, `satura` → 1.0 (alineada con `parrilla`)."""
    if valor <= 0:
        return 0.0
    return min(1.0, math.log10(max(1, valor)) / math.log10(max(10, satura)))


def _tokens_ordenados(clave: str) -> str:
    """Forma TOKEN-SORT de una clave fuzzy: mismos tokens, orden alfabético, deduplicados.

    El mismo EVENTO se titula con las mismas palabras en distinto orden ("América vence a
    Chivas en el clásico" / "Clásico: Chivas cae y América vence"): el `SequenceMatcher`
    posicional castiga la reordenación aunque el contenido sea idéntico. Comparar además las
    claves con tokens ordenados (estilo token-sort-ratio) recupera esos pares sin relajar el
    umbral global.
    """
    return " ".join(sorted(set(clave.split())))


_RE_NUMEROS = re.compile(r"\d+")


def _numeros_incompatibles(ka: str, kb: str) -> bool:
    """True si AMBAS claves traen números y NO comparten ninguno (eventos distintos).

    Veto de seguridad del fuzzy: "sismo de 6.2" y "sismo de 7.1" comparten casi todo el
    texto (ratio alto) pero son acontecimientos DISTINTOS; igual con jornadas, marcadores o
    fechas. Solo veta cuando los dos lados tienen números y son disjuntos: un titular sin
    números nunca se penaliza (no se castiga la ausencia de dato).
    """
    na = frozenset(_RE_NUMEROS.findall(ka))
    if not na:
        return False
    nb = frozenset(_RE_NUMEROS.findall(kb))
    return bool(nb) and not (na & nb)


def _ratio_claves(ka: str, kb: str) -> float:
    """Ratio fuzzy [0,1] entre dos claves YA normalizadas: el MÁXIMO del directo y el token-sort.

    El directo respeta el orden (titulares casi idénticos); el token-sort tolera la
    reordenación (mismo evento, sintaxis distinta). Tomar el máximo solo puede UNIR más pares
    del mismo evento, nunca menos (monótono respecto al comportamiento anterior). VETO de
    números incompatibles (`_numeros_incompatibles`): dos titulares con cifras disjuntas son
    eventos distintos por mucho texto que compartan → ratio 0.
    """
    if _numeros_incompatibles(ka, kb):
        return 0.0
    directo = SequenceMatcher(None, ka, kb).ratio()
    ordenado = SequenceMatcher(None, _tokens_ordenados(ka), _tokens_ordenados(kb)).ratio()
    return max(directo, ordenado)
