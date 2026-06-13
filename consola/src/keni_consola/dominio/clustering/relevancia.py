"""Relevancia de una historia para una marca por VOCABULARIO (capa pura).

Conteo graduado de coincidencias del vocabulario de marca en título/resumen (con
saturación suave), su explicación (palabras que casaron) y la asignación de marca a
historias sin marca dominante. Movido VERBATIM desde el antiguo `clustering.py`.
"""

from __future__ import annotations

import re
from typing import Any

from ._comun import _sin_acentos

# Saturación SUAVE de la señal de marca: ~3 coincidencias de vocabulario ≈ señal plena.
# Antes la señal era ESCALONADA (1 keyword puntuaba igual que 12) y SATURADA (un vocabulario
# genérico daba ~1.0 casi siempre); ahora el conteo gradúa y las frases casan por LÍMITE de
# palabra (no por subcadena).
_MARCA_SATURA_COINCIDENCIAS = 3.0
_PESO_MARCA_RESUMEN = 0.6


def _relevancia_marca(cluster: dict[str, Any], palabras_marca: frozenset[str]) -> float:
    """Relevancia GRADUADA de la historia para una marca [0,1] según sus palabras clave.

    Cuenta las coincidencias de vocabulario (las del TÍTULO a peso pleno; las del resumen a
    0.6) y satura suave: `min(1, n_ponderado / 3)`. 0.0 sin vocabulario o sin coincidencias.
    El texto se normaliza sin acentos para casar 'fútbol' con la keyword 'futbol'. Monótona:
    más coincidencias ⇒ más relevancia (hasta saturar).
    """
    return relevancia_marca_detalle(cluster, palabras_marca)[0]


def relevancia_marca_detalle(
    cluster: dict[str, Any], palabras_marca: frozenset[str]
) -> tuple[float, tuple[str, ...]]:
    """Relevancia de marca [0,1] MÁS las palabras del vocabulario que casaron (explicable).

    Misma graduación que `_relevancia_marca` (título a peso pleno, resumen a 0.6, saturación
    suave a 3 coincidencias). Las `palabras` devueltas son los términos del vocabulario
    presentes en título o resumen (orden alfabético, sin duplicar): son la EXPLICACIÓN de la
    señal de marca que la UI/el listón muestran al equipo. PURA y determinista.

    Historias EXTRANJERAS: el vocabulario es español, así que un titular en inglés solo casa
    los términos neutrales (nintendo, nfl…). Si la historia trae TRADUCCIÓN (`titulo_es` /
    `resumen_es`, Ola D), se evalúa ADEMÁS sobre ella: la relevancia no penaliza el idioma de
    origen. Un término que casa en ambos idiomas cuenta una sola vez por campo.
    """
    if not palabras_marca:
        return 0.0, ()
    titulo = _sin_acentos(
        " ".join(str(cluster.get(k) or "") for k in ("titulo", "titulo_es")).strip()
    )
    resumen = _sin_acentos(
        " ".join(str(cluster.get(k) or "") for k in ("resumen", "resumen_es")).strip()
    )
    en_titulo = _coincidencias(titulo, palabras_marca)
    en_resumen = _coincidencias(resumen, palabras_marca)
    n = len(en_titulo) + _PESO_MARCA_RESUMEN * len(en_resumen)
    if n <= 0:
        return 0.0, ()
    casadas = tuple(sorted(set(en_titulo) | set(en_resumen)))
    return min(1.0, n / _MARCA_SATURA_COINCIDENCIAS), casadas


def _coincidencias(texto: str, vocabulario: frozenset[str]) -> list[str]:
    """Entradas del vocabulario presentes en el texto normalizado (orden alfabético).

    Tokens sueltos casan por igualdad de token; FRASES por límite de palabra (regex), no por
    subcadena: 'liga mx' ya no se cuela dentro de otra palabra. La tokenización separa por
    NO-alfanuméricos (antes era `split()` y la puntuación pegada — "méxico:" — impedía casar
    el token "mexico" en titulares reales). Determinista.
    """
    if not texto or not vocabulario:
        return []
    tokens = set(re.findall(r"\w+", texto))
    casadas: list[str] = []
    for termino in sorted(vocabulario):
        if " " in termino:
            if re.search(rf"(?<!\w){re.escape(termino)}(?!\w)", texto):
                casadas.append(termino)
        elif termino in tokens:
            casadas.append(termino)
    return casadas


# Umbral por defecto para ASIGNAR marca por vocabulario a una historia sin marca dominante.
# Equivale a ≥1 keyword en el título (1/3 con la saturación suave); coincidencias solo de
# resumen (0.2) no bastan. Si ninguna marca lo alcanza, la historia queda sin marca (honesto).
UMBRAL_MARCA_VOCABULARIO = 0.3


def marca_por_vocabulario(
    cluster: dict[str, Any],
    vocabularios: dict[str, frozenset[str]],
    *,
    umbral: float = UMBRAL_MARCA_VOCABULARIO,
) -> str:
    """Mejor marca para una historia SIN marca dominante, por matching de vocabulario. PURA.

    Los clusters formados solo por items sin marca (Trends, agencias) quedaban con `marca=''`
    y eran INVISIBLES para la promoción por marca. Esto evalúa la relevancia del título/resumen
    contra el vocabulario de CADA marca y devuelve la mejor por encima de `umbral`; "" si
    ninguna pasa (se queda sin marca, como antes). Determinista: a empate gana la marca
    alfabéticamente menor.
    """
    mejor = ""
    mejor_s = 0.0
    for marca in sorted(vocabularios):
        s = _relevancia_marca(cluster, vocabularios.get(marca) or frozenset())
        if s >= umbral and s > mejor_s:
            mejor_s = s
            mejor = marca
    return mejor
