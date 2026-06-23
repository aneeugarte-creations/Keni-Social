"""Scoring de historias para el ranking newsroom y selección diversa (capa pura).

Pesos del score (`PesosScore`), la fórmula combinada (`puntuar`/`puntuar_detalle`), la
señal de frescura y de encaje de evento, y el top-N con diversidad (MMR).

MODELO (v2): el score NO es una suma plana de señales. La corroboración no SUMA, MULTIPLICA:
es el nivel de CONFIANZA en que la historia es real. El resto de señales componen el MÉRITO
editorial (¿vale la pena cubrirla?) y se ponderan en una combinación que suma ~1.0; ese mérito
se multiplica por la confianza. Así un rumor de fuente única, por fresco y on-brand que sea,
queda topado (confianza = piso); una historia confirmada por varios medios alcanza su mérito
pleno. Es MONÓTONA en cada señal (los tests lo verifican).
"""

from __future__ import annotations

import math
import re
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
    _sin_acentos,
)
from .corroboracion import _velocidad, peso_ventana_actual
from .relevancia import relevancia_marca_detalle

# Pesos de MÉRITO (combinación lineal que suma ~1.0): cuánto vale editorialmente la historia.
# La corroboración NO está aquí: actúa como multiplicador de confianza (ver `puntuar_detalle`).
# Son los DEFAULTS de la capa pura; el daemon inyecta perfiles por marca desde `config`.
_PESO_FRESCURA = 0.25
_PESO_MARCA = 0.25
_PESO_EVENTO = 0.15
_PESO_VIRALIDAD = 0.15
_PESO_VELOCIDAD = 0.20
# Rendimiento (Fase 2c): INERTE en la capa pura (peso 0). Los perfiles por marca del config le
# dan peso solo cuando `KENI_RENDIMIENTO_RANKING` está ON; así el default no cambia nada.
_PESO_RENDIMIENTO = 0.0
# Empujón aditivo si la historia es breaking. DEFAULT 0.0 = SIN bonus: breaking ya emerge del
# ranking (varias fuentes potentes a la vez ⇒ confianza alta + velocidad ⇒ top del pool) y de
# la exención de umbral; el knob queda por compatibilidad/rollback (config lo reactiva).
_BONUS_BREAKING = 0.0

# Forma de las señales (afinables por marca desde config).
_PISO_CONFIANZA = 0.5  # confianza de una historia SIN corroborar (1 fuente); satura a 1.0
_PESO_SATURA = 4.0  # masa ponderada (Σ peso por outlet) que satura la corroboración a 1.0
_FRESCURA_VIDA_H = 72.0  # a las `vida_h` la frescura cae a ~0 (lineal acotada)
_EVENTO_VENTANA_DIAS = 3.0  # ventana futura (días) en la que un evento próximo da encaje
_SENAL_SATURA = 1_000_000  # escala log de viralidad (alineada con parrilla)


@dataclass(frozen=True)
class PesosScore:
    """Pesos y forma del algoritmo de score de cluster (inyectables por marca desde config).

    `frescura/marca/evento/viralidad/velocidad/rendimiento` son los pesos de MÉRITO (idealmente
    suman ~1.0); su combinación lineal se MULTIPLICA por la confianza. `piso_confianza` es la
    confianza de una historia sin corroborar (corroboración 0 ⇒ confianza = piso; saturada ⇒
    1.0). `breaking` es el empujón aditivo (def 0.0). `corro_satura`, `frescura_vida_h` y
    `evento_ventana_dias` son la forma de cada señal. `puntuar()` usa estos; sin inyección cae
    a `_PESOS_DEF`.
    """

    frescura: float = _PESO_FRESCURA
    marca: float = _PESO_MARCA
    evento: float = _PESO_EVENTO
    viralidad: float = _PESO_VIRALIDAD
    velocidad: float = _PESO_VELOCIDAD
    rendimiento: float = _PESO_RENDIMIENTO
    breaking: float = _BONUS_BREAKING
    piso_confianza: float = _PISO_CONFIANZA
    corro_satura: float = _PESO_SATURA
    frescura_vida_h: float = _FRESCURA_VIDA_H
    evento_ventana_dias: float = _EVENTO_VENTANA_DIAS


_PESOS_DEF = PesosScore()


def _frescura(
    ultimo_visto: str, *, ahora: datetime | None = None, vida_h: float = _FRESCURA_VIDA_H
) -> float:
    """Frescura [0,1]: 1.0 si la historia es de ahora mismo, cae lineal a 0 en `vida_h` horas.

    Sin `ultimo_visto` parseable → 0.0 (sin señal de recencia, no se premia). `ahora`
    inyectable para tests deterministas. `vida_h` afina la vida media por marca (un resultado
    deportivo caduca en horas; un reportaje dura días).
    """
    dt = _parse_iso(ultimo_visto)
    if dt is None:
        return 0.0
    ref = ahora or datetime.now(UTC)
    horas = (ref - dt).total_seconds() / 3600.0
    if horas <= 0:
        return 1.0
    return max(0.0, 1.0 - horas / max(1.0, vida_h))


# Tokens vacíos del título de un evento (conectores, ordinales de bracket, ruido). No aportan
# encaje: "Portugal vs Uzbekistán" casa por {portugal, uzbekistan}, no por "vs".
_STOP_EVENTO: frozenset[str] = frozenset({
    "vs", "de", "del", "la", "el", "los", "las", "y", "en", "al", "por", "con", "the",
    "r16", "r32", "octavos", "cuartos", "semis", "semifinal", "final", "grupo", "fase",
})


def _tokens_evento(texto: str) -> set[str]:
    """Tokens significativos de un texto para el encaje de evento (sin acentos, sin ruido).

    Descarta conectores/ordinales conocidos, tokens de < 3 letras y los puramente numéricos:
    los nombres propios (equipos, torneos, sedes) son lo que de verdad ata una noticia a un
    evento de la agenda.
    """
    crudo = re.findall(r"\w+", _sin_acentos(texto))
    return {t for t in crudo if len(t) >= 3 and not t.isdigit() and t not in _STOP_EVENTO}


def _proximidad_evento(dias: float, ventana_dias: float) -> float:
    """Peso temporal [0,1] de un evento a `dias` de distancia (negativo = pasado).

    Plena (1.0) en la ventana de cobertura viva [-1, +1] días (ayer/hoy/mañana); decae lineal
    hasta ~0.3 al borde de `ventana_dias`; 0 fuera de [-1, ventana_dias]. Un evento de hace más
    de un día ya no es agenda (la cobertura post se hace por resultado/frescura, no por evento).
    """
    if dias < -1.0 or dias > ventana_dias:
        return 0.0
    if dias <= 1.0:
        return 1.0
    span = max(1.0, ventana_dias - 1.0)
    return max(0.3, 1.0 - 0.7 * (dias - 1.0) / span)


def encaje_evento_detalle(
    cluster: dict[str, Any],
    eventos: list[dict[str, Any]],
    *,
    ahora: datetime | None = None,
    ventana_dias: float = _EVENTO_VENTANA_DIAS,
) -> tuple[float, str]:
    """Encaje de la historia con la AGENDA de la marca [0,1] MÁS el evento que mejor casa. PURA.

    Cruza el título/resumen del cluster con los eventos próximos (`rota_eventos` de la marca,
    cada uno `{titulo, fecha, ...}`). Por evento: solape textual de nombres propios (equipos,
    torneos, sedes) × proximidad temporal. Devuelve el MÁXIMO y el título del evento ganador
    (la EXPLICACIÓN). 0.0 sin eventos, sin solape o fuera de ventana. Determinista.
    """
    if not eventos:
        return 0.0, ""
    ref = ahora or datetime.now(UTC)
    hoy = ref.date()
    texto = " ".join(
        str(cluster.get(k) or "") for k in ("titulo", "titulo_es", "resumen", "resumen_es")
    )
    tokens_noticia = _tokens_evento(texto)
    if not tokens_noticia:
        return 0.0, ""
    mejor = 0.0
    mejor_titulo = ""
    for ev in eventos:
        fecha = _parse_iso(str(ev.get("fecha") or ""))
        if fecha is None:
            continue
        dias = (fecha.date() - hoy).days
        prox = _proximidad_evento(float(dias), ventana_dias)
        if prox <= 0.0:
            continue
        tokens_ev = _tokens_evento(str(ev.get("titulo") or ""))
        if not tokens_ev:
            continue
        solape = len(tokens_ev & tokens_noticia) / len(tokens_ev)
        s = prox * solape
        if s > mejor:
            mejor = s
            mejor_titulo = str(ev.get("titulo") or "")
    return min(1.0, mejor), (mejor_titulo if mejor > 0.0 else "")


# Anclaje a la agenda: cuántos nombres propios del evento debe nombrar la historia para atarla
# a ÉL sin ambigüedad (≥2 evita casar por un solo equipo compartido entre dos partidos) y qué
# fracción de los del evento cubre (≥0.5 tolera nombres compuestos: «Bosnia y Herzegovina»).
_ANCLA_MIN_TOKENS = 2
_ANCLA_MIN_SOLAPE = 0.5


def evento_ancla(
    cluster: dict[str, Any],
    eventos: list[dict[str, Any]],
    *,
    ahora: datetime | None = None,
    ventana_dias: float = _EVENTO_VENTANA_DIAS,
) -> str:
    """El evento de la AGENDA al que la historia pertenece SIN ambigüedad -> su título; "" si ninguno.

    Más estricto que `encaje_evento_detalle` (que da una señal graduada para el score): aquí se
    exige un solape DURO —al menos `_ANCLA_MIN_TOKENS` nombres propios del evento presentes en la
    historia y al menos `_ANCLA_MIN_SOLAPE` de los del evento— dentro de la ventana viva. Sirve de
    CLAVE DE FAMILIA determinista: dos historias del mismo partido devuelven el mismo título sin
    pasar por el LLM. A empate, el de mayor (proximidad × solape). PURA.
    """
    if not eventos:
        return ""
    ref = ahora or datetime.now(UTC)
    hoy = ref.date()
    texto = " ".join(
        str(cluster.get(k) or "") for k in ("titulo", "titulo_es", "resumen", "resumen_es")
    )
    tokens_noticia = _tokens_evento(texto)
    if not tokens_noticia:
        return ""
    mejor = 0.0
    mejor_titulo = ""
    for ev in eventos:
        fecha = _parse_iso(str(ev.get("fecha") or ""))
        if fecha is None:
            continue
        prox = _proximidad_evento(float((fecha.date() - hoy).days), ventana_dias)
        if prox <= 0.0:
            continue
        tokens_ev = _tokens_evento(str(ev.get("titulo") or ""))
        if not tokens_ev:
            continue
        comunes = len(tokens_ev & tokens_noticia)
        solape = comunes / len(tokens_ev)
        if comunes < _ANCLA_MIN_TOKENS or solape < _ANCLA_MIN_SOLAPE:
            continue
        s = prox * solape
        if s > mejor:
            mejor = s
            mejor_titulo = str(ev.get("titulo") or "")
    return mejor_titulo


def puntuar(
    cluster: dict[str, Any],
    *,
    palabras_marca: frozenset[str] = frozenset(),
    eventos: list[dict[str, Any]] | None = None,
    ahora: datetime | None = None,
    pesos: PesosScore | None = None,
    breaking_peso: float = BREAKING_PESO_DEF,
    breaking_ventana_h: int = BREAKING_VENTANA_H_DEF,
) -> tuple[float, str]:
    """Puntúa una historia para el ranking newsroom. Devuelve `(score, razon)`. PURA.

    Atajo de `puntuar_detalle` para los llamantes que no necesitan el desglose por señal.
    """
    score, razon, _desglose = puntuar_detalle(
        cluster, palabras_marca=palabras_marca, eventos=eventos, ahora=ahora, pesos=pesos,
        breaking_peso=breaking_peso, breaking_ventana_h=breaking_ventana_h,
    )
    return score, razon


def puntuar_detalle(
    cluster: dict[str, Any],
    *,
    palabras_marca: frozenset[str] = frozenset(),
    eventos: list[dict[str, Any]] | None = None,
    ahora: datetime | None = None,
    pesos: PesosScore | None = None,
    breaking_peso: float = BREAKING_PESO_DEF,
    breaking_ventana_h: int = BREAKING_VENTANA_H_DEF,
) -> tuple[float, str, dict[str, Any]]:
    """Puntúa una historia y EXPLICA el porqué. Devuelve `(score, razon, desglose)`. PURA.

    FÓRMULA — score en [0, 1]:

        merito    = w_frescura·frescura + w_marca·marca + w_evento·evento
                  + w_viralidad·viralidad + w_velocidad·velocidad + w_rendimiento·rendimiento
        confianza = piso_confianza + (1 − piso_confianza)·corroboracion   (∈ [piso, 1])
        score     = merito · confianza   (+ bonus breaking si aplica)

    Las señales CRUDAS [0,1]:
        corroboracion  log(W)/log(corro_satura), W = peso_fuentes (Σ peso editorial por outlet;
                       cae a n_fuentes pre-migración). Es la CONFIANZA: multiplica, no suma.
        velocidad      masa que SE SUMÓ en la ventana actual / 4 (decae sola al envejecer).
        frescura       recencia de `ultimo_visto`; lineal, 0 a las `frescura_vida_h` horas.
        viralidad      `senal` agregada, escala log; satura a 1e6.
        marca          palabras del vocabulario de la marca en título/resumen; 0 sin marca.
        evento         encaje con la agenda de la marca (`rota_eventos` próximos); 0 sin agenda.
        rendimiento    bonus [0,1] que el daemon precalcula (líneas top por engagement).

    BREAKING emerge de aquí: varias fuentes potentes a la vez ⇒ confianza alta + velocidad ⇒
    top del pool, y el flag `breaking` (masa en ventana ≥ `breaking_peso`) exime de maduración
    en el umbral. El bonus aditivo (`pesos.breaking`) queda en 0.0 por defecto (rollback).

    `desglose` es la EXPLICACIÓN estructurada (se persiste, la lee la UI): cada señal CRUDA en
    [0,1] (`corroboracion`/`velocidad`/`frescura`/`viralidad`/`marca`/`evento`/`rendimiento`),
    `confianza` (el multiplicador efectivo), `peso_fuentes` (la masa W), `breaking` (0/1, EN
    VIVO), `palabras` (vocabulario que casó) y `evento_titulo` (el evento que ató la historia).
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
        s_corro = min(1.0, math.log(masa) / math.log(max(2.0, p.corro_satura)))
    # CONFIANZA: la corroboración no suma, multiplica. Una historia sin corroborar parte del
    # piso (no se mata, pero queda topada); confirmada por varios medios llega a 1.0.
    confianza = p.piso_confianza + (1.0 - p.piso_confianza) * s_corro

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

    s_fresca = _frescura(
        str(cluster.get("ultimo_visto") or ""), ahora=ahora, vida_h=p.frescura_vida_h
    )
    s_viral = _log_norm(senal, _SENAL_SATURA)
    s_marca, palabras_casadas = relevancia_marca_detalle(cluster, palabras_marca)
    s_evento, evento_titulo = encaje_evento_detalle(
        cluster, eventos or [], ahora=ahora, ventana_dias=p.evento_ventana_dias
    )
    s_rend = min(1.0, max(0.0, float(cluster.get("bonus_rendimiento") or 0.0)))

    merito = (
        p.frescura * s_fresca
        + p.marca * s_marca
        + p.evento * s_evento
        + p.viralidad * s_viral
        + p.velocidad * s_vel
        + p.rendimiento * s_rend
    )
    score = merito * confianza
    if es_breaking and p.breaking:
        score = score + p.breaking
    score = min(1.0, max(0.0, score))

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
    if s_evento > 0 and evento_titulo:
        razones.append(f"en agenda: {evento_titulo}")
    if senal > 0:
        razones.append(f"señal {senal}")
    if s_marca > 0:
        # Las palabras casadas EXPLICAN la relevancia (qué del vocabulario de la marca casó).
        muestra = ", ".join(palabras_casadas[:4])
        razones.append(f"relevante para la marca ({muestra})" if muestra else "relevante para la marca")
    razon = " · ".join(razones) if razones else "historia única"
    desglose: dict[str, Any] = {
        "corroboracion": round(s_corro, 3),
        "confianza": round(confianza, 3),
        "velocidad": round(s_vel, 3),
        "frescura": round(s_fresca, 3),
        "viralidad": round(s_viral, 3),
        "marca": round(s_marca, 3),
        "evento": round(s_evento, 3),
        "rendimiento": round(s_rend, 3),
        "peso_fuentes": round(masa, 3),
        "breaking": 1 if es_breaking else 0,
        "palabras": list(palabras_casadas),
        "evento_titulo": evento_titulo,
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
