"""Scoring de historias para el ranking newsroom y selección diversa (capa pura).

Pesos del score (`PesosScore`), la fórmula combinada (`puntuar`/`puntuar_detalle`), la
señal de frescura y el top-N con diversidad (MMR).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .. import similitud
from ._comun import (
    _MIN_LONGITUD_FUZZY,
    BREAKING_PESO_DEF,
    BREAKING_VENTANA_H_DEF,
    _log_norm,
    _parse_iso,
    _ratio_claves,
)
from .corroboracion import _velocidad, peso_ventana_actual
from .relevancia import relevancia_marca_detalle

# Pesos del score (ver `puntuar`). Suman 1.0: el score vive en [0, 1] y es comparable
# entre marcas/categorías para el ranking. Son los DEFAULTS; el daemon los puede inyectar
# desde la configuración (ajustes editables por la consola), de ahí la dataclass `PesosScore`.
_PESO_CORROBORACION = 0.30
_PESO_VELOCIDAD = 0.20
_PESO_FRESCURA = 0.20
_PESO_VIRALIDAD = 0.10
_PESO_MARCA = 0.20
# Empujón aditivo si la historia es breaking. DEFAULT 0.0 = SIN bonus: breaking ya emerge del
# ranking (2 fuentes potentes a la vez ⇒ corroboración 0.67 + velocidad 1.0 ⇒ top del pool);
# el knob queda por compatibilidad/rollback (config puede reactivarlo sin tocar código).
_BONUS_BREAKING = 0.0
# Peso de la señal de RENDIMIENTO (líneas que mejor funcionan). DEFAULT 0.0 = INERTE: la señal
# (Fase 2c) solo cuenta cuando el equipo le da peso desde config; así no cambia nada por defecto.
_PESO_RENDIMIENTO = 0.0


@dataclass(frozen=True)
class PesosScore:
    """Pesos del algoritmo de ponderación del score de cluster (inyectables desde config).

    `corroboracion/velocidad/frescura/viralidad/marca` son la combinación lineal (idealmente
    suman ~1.0); `breaking` es el empujón aditivo (def 0.0: breaking ya emerge del ranking);
    `rendimiento` es la señal de líneas que mejor funcionan (Fase 2c), INERTE por defecto
    (peso 0). `puntuar()` usa estos; el daemon construye una instancia desde
    `config.score_pesos()`. Sin inyección, `puntuar()` cae a `_PESOS_DEF`.
    """

    corroboracion: float = _PESO_CORROBORACION
    velocidad: float = _PESO_VELOCIDAD
    frescura: float = _PESO_FRESCURA
    viralidad: float = _PESO_VIRALIDAD
    marca: float = _PESO_MARCA
    breaking: float = _BONUS_BREAKING
    rendimiento: float = _PESO_RENDIMIENTO


_PESOS_DEF = PesosScore()

# Normalizadores de cada señal (ver fórmula).
_PESO_SATURA = 8.0  # masa ponderada (Σ peso por outlet) que satura la corroboración a 1.0
_SENAL_SATURA = 1_000_000  # escala log de viralidad (alineada con parrilla)
_FRESCURA_VIDA_H = 72.0  # a las 72h la frescura cae a ~0 (lineal acotada)


def _frescura(ultimo_visto: str, *, ahora: datetime | None = None) -> float:
    """Frescura [0,1]: 1.0 si la historia es de ahora mismo, cae lineal a 0 en `_FRESCURA_VIDA_H`.

    Sin `ultimo_visto` parseable → 0.0 (sin señal de recencia, no se premia). `ahora`
    inyectable para tests deterministas.
    """
    dt = _parse_iso(ultimo_visto)
    if dt is None:
        return 0.0
    ref = ahora or datetime.now(UTC)
    horas = (ref - dt).total_seconds() / 3600.0
    if horas <= 0:
        return 1.0
    return max(0.0, 1.0 - horas / _FRESCURA_VIDA_H)


def puntuar(
    cluster: dict[str, Any],
    *,
    palabras_marca: frozenset[str] = frozenset(),
    ahora: datetime | None = None,
    pesos: PesosScore | None = None,
    breaking_peso: float = BREAKING_PESO_DEF,
    breaking_ventana_h: int = BREAKING_VENTANA_H_DEF,
) -> tuple[float, str]:
    """Puntúa una historia para el ranking newsroom. Devuelve `(score, razon)`. PURA.

    Atajo de `puntuar_detalle` para los llamantes que no necesitan el desglose por señal.
    """
    score, razon, _desglose = puntuar_detalle(
        cluster, palabras_marca=palabras_marca, ahora=ahora, pesos=pesos,
        breaking_peso=breaking_peso, breaking_ventana_h=breaking_ventana_h,
    )
    return score, razon


def puntuar_detalle(
    cluster: dict[str, Any],
    *,
    palabras_marca: frozenset[str] = frozenset(),
    ahora: datetime | None = None,
    pesos: PesosScore | None = None,
    breaking_peso: float = BREAKING_PESO_DEF,
    breaking_ventana_h: int = BREAKING_VENTANA_H_DEF,
) -> tuple[float, str, dict[str, Any]]:
    """Puntúa una historia y EXPLICA el porqué. Devuelve `(score, razon, desglose)`. PURA.

    FÓRMULA — score en [0, 1], combinación lineal ponderada de cinco señales independientes:

        W     = peso_fuentes (Σ peso editorial por outlet; potente 2.0 / normal 1.0 / baja 0.5;
                cae a n_fuentes si el cluster aún no trae timeline — pre-migración)
        score = 0.30 · corroboracion    (log(W)/log(8): 1 fuente→0; 2 potentes→0.67; satura 8)
              + 0.20 · velocidad        (masa que SE SUMÓ en la ventana actual / 4; 2 potentes
                                         a la vez = 1.0; DECAE sola al envejecer)
              + 0.20 · frescura         (recencia de `ultimo_visto`; lineal, 0 a las 72h)
              + 0.10 · viralidad        (`senal` agregada, escala log; satura a 1e6)
              + 0.20 · relevancia_marca (palabras de la marca en título/resumen; 0 sin marca)

    BREAKING emerge de aquí, no es un carril aparte: 2 fuentes potentes a la vez ⇒
    corroboración 0.67 + velocidad 1.0 + frescura ≈ 1 ⇒ ~0.6+, top del pool, y el flag
    `breaking` (masa en ventana ≥ `breaking_peso`) exime de maduración en el umbral ⇒ sale
    al feed en el siguiente barrido. El bonus aditivo (`pesos.breaking`) queda en 0.0 por
    defecto (knob de rollback). Es MONÓTONA en cada señal (los tests lo verifican).

    `desglose` es la EXPLICACIÓN estructurada (se persiste junto al score, la lee la UI):
    cada señal CRUDA en [0,1] (`corroboracion`/`velocidad`/`frescura`/`viralidad`/`marca`/
    `rendimiento`), `peso_fuentes` (la masa W), `breaking` (0/1, computado EN VIVO: decae) y
    `palabras` (los términos del vocabulario que casaron). Señales crudas, no ponderadas: el
    desglose explica QUÉ tiene la historia; los pesos (editables en caliente) cuánto cuenta.
    """
    p = pesos or _PESOS_DEF
    n_fuentes = int(cluster.get("n_fuentes") or 0)
    senal = int(cluster.get("senal") or 0)

    # Corroboración PONDERADA por el peso editorial de cada outlet. Fallback honesto para
    # clusters sin timeline (pre-migración / stubs): la masa es el conteo de fuentes.
    try:
        masa = float(cluster.get("peso_fuentes") or 0.0)
    except (TypeError, ValueError):
        masa = 0.0
    if masa <= 0.0:
        masa = float(n_fuentes)
    s_corro = 0.0
    if masa > 1.0:
        s_corro = min(1.0, math.log(masa) / math.log(_PESO_SATURA))

    # Velocidad + breaking EN VIVO desde el timeline persistido (decaen con el reloj). Sin
    # timeline no se inventa señal: velocidad 0 y el flag persistido se respeta tal cual.
    detalle = cluster.get("fuentes_detalle") or []
    if isinstance(detalle, list) and detalle:
        masa_ventana, n_ventana = peso_ventana_actual(
            detalle, ventana_h=breaking_ventana_h, ahora=ahora
        )
        s_vel = _velocidad(masa_ventana, n_ventana)
        es_breaking = n_ventana >= 2 and masa_ventana >= breaking_peso
    else:
        s_vel = min(1.0, max(0.0, float(cluster.get("velocidad") or 0.0)))
        es_breaking = bool(int(cluster.get("breaking") or 0))

    s_fresca = _frescura(str(cluster.get("ultimo_visto") or ""), ahora=ahora)
    s_viral = _log_norm(senal, _SENAL_SATURA)
    s_marca, palabras_casadas = relevancia_marca_detalle(cluster, palabras_marca)
    # Señal de RENDIMIENTO (Fase 2c): 0..1 que el daemon precalcula (1 si la historia cae en una
    # línea top por engagement). INERTE salvo que `pesos.rendimiento` > 0. Acota a [0,1] por defensa.
    s_rend = min(1.0, max(0.0, float(cluster.get("bonus_rendimiento") or 0.0)))

    score = (
        p.corroboracion * s_corro
        + p.velocidad * s_vel
        + p.frescura * s_fresca
        + p.viralidad * s_viral
        + p.marca * s_marca
        + p.rendimiento * s_rend
    )
    if es_breaking and p.breaking:
        score = min(1.0, score + p.breaking)
    score = min(1.0, score)

    razones: list[str] = []
    if es_breaking:
        razones.append("última hora: varias fuentes casi a la vez")
    if n_fuentes > 1:
        potentes = sum(
            1 for d in detalle if isinstance(d, dict) and float(d.get("peso") or 1.0) >= 1.5
        ) if isinstance(detalle, list) else 0
        if potentes:
            razones.append(f"{n_fuentes} fuentes ({potentes} potente{'s' if potentes > 1 else ''})")
        else:
            razones.append(f"{n_fuentes} fuentes")
    if s_fresca >= 0.5:
        razones.append("reciente")
    if senal > 0:
        razones.append(f"señal {senal}")
    if s_marca > 0:
        # Las palabras casadas EXPLICAN la relevancia (qué del vocabulario de la marca casó).
        muestra = ", ".join(palabras_casadas[:4])
        razones.append(f"relevante para la marca ({muestra})" if muestra else "relevante para la marca")
    razon = " · ".join(razones) if razones else "historia única"
    desglose: dict[str, Any] = {
        "corroboracion": round(s_corro, 3),
        "velocidad": round(s_vel, 3),
        "frescura": round(s_fresca, 3),
        "viralidad": round(s_viral, 3),
        "marca": round(s_marca, 3),
        "rendimiento": round(s_rend, 3),
        "peso_fuentes": round(masa, 3),
        "breaking": 1 if es_breaking else 0,
        "palabras": list(palabras_casadas),
    }
    return round(score, 6), razon, desglose


def seleccionar_diversos(
    clusters: list[dict[str, Any]], *, maximo: int, umbral: float = 0.80
) -> list[dict[str, Any]]:
    """Top-N con DIVERSIDAD (MMR simple) sobre una lista YA ordenada por score. PURA.

    Recorre en orden y SALTA las historias cuyo título es muy parecido (ratio fuzzy ≥ `umbral`)
    a alguna ya elegida en esta pasada, para que un macro-tema no se coma todas las plazas.
    SUAVE: si al final faltan plazas, rellena con las saltadas en orden de score (nunca
    devuelve menos historias por diversificar). Títulos cortos no entran al fuzzy (no se
    penalizan entre sí). `umbral <= 0` desactiva (top-N puro).
    """
    if maximo <= 0:
        return []
    if umbral <= 0:
        return clusters[:maximo]
    elegidos: list[dict[str, Any]] = []
    saltados: list[dict[str, Any]] = []
    claves: list[str] = []
    for c in clusters:
        if len(elegidos) >= maximo:
            break
        kf = similitud.clave_fuzzy(str(c.get("titulo") or ""))
        parecido = len(kf) >= _MIN_LONGITUD_FUZZY and any(
            k and _ratio_claves(kf, k) >= umbral for k in claves
        )
        if parecido:
            saltados.append(c)
            continue
        elegidos.append(c)
        claves.append(kf)
    for c in saltados:
        if len(elegidos) >= maximo:
            break
        elegidos.append(c)
    return elegidos
