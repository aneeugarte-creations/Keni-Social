"""Sugiere SECCIONES (líneas) nuevas a partir de las candidatas que el clasificador deja SIN
sección.

Idea: si un tema recurrente acumula volumen y NINGUNA línea lo captura (ninguna keyword casa), es
candidato a sección nueva — así la navegación no se queda obsoleta. Determinístico, sin IA: cuenta
la frecuencia de términos (palabras y bigramas de palabras-contenido) en los TITULARES de las
historias sin clasificar, descartando stopwords y lo que ya es keyword de alguna línea. La señal es
«cuántas historias DISTINTAS mencionan el término». Es ADVISORY: el equipo decide si crear la línea
(o añadir las keywords a una existente).

`sugerir(clusters, etiquetas)` es PURO (sin BD): recibe las candidatas y las líneas y devuelve la
lista rankeada. El envoltorio con BD vive en la API.
"""

from __future__ import annotations

from typing import Any

from . import clasificador_lineas

# Palabras que NO nombran una sección: vacías de contenido (artículos, preposiciones, verbos
# comunes) o genéricas del deporte (gol, partido, vs…). Se descartan del conteo. Normalizadas
# (sin acentos, minúsculas), igual que el clasificador.
_STOPWORDS: frozenset[str] = frozenset(
    """
    el la los las un una unos unas lo al del de en y o u a ante bajo con contra desde durante
    entre hacia hasta para por segun sin sobre tras que se su sus mi tu le les nos os me te
    es son fue era ser estar esta este estos estas eso esa ese aso asi mas menos muy ya no si
    como cuando donde quien cual cuales porque pero aunque tambien solo cada todo toda todos todas
    hoy ayer manana ahora aqui alli vs versus contra
    gol goles partido partidos juego juegos equipo equipos jugador jugadores tecnico director
    gana ganar gano vence vencer vencio pierde perder perdio empata empate
    video fotos foto galeria asi mira esto entrevista resumen previa cronica analisis
    minuto hora dia semana ano mes temporada jornada fecha resultado resultados marcador
    nuevo nueva primer primera ultimo ultima gran mejor peor
    """.split()
)

# Tope de titulares de ejemplo por sugerencia (para que el equipo reconozca el tema de un vistazo).
_EJEMPLOS_POR_SUGERENCIA = 3


def _tokens(texto: str) -> list[str]:
    """Palabras-contenido normalizadas de `texto`: sin acentos, sin stopwords, len≥3, no numéricas."""
    base = clasificador_lineas._normalizar(texto)  # noqa: SLF001 -- misma normalización que el clasificador
    crudos = "".join(c if c.isalnum() or c.isspace() else " " for c in base).split()
    return [t for t in crudos if len(t) >= 3 and not t.isdigit() and t not in _STOPWORDS]


def _terminos_cubiertos(etiquetas: list[dict[str, Any]]) -> set[str]:
    """Términos que YA cubre alguna línea: cada keyword entera + cada una de sus palabras.

    Se usan para NO sugerir lo que la taxonomía ya captura (aunque esa historia no casara).
    """
    cubiertos: set[str] = set()
    for et in etiquetas:
        for kw in (et.get("keywords") or "").split(","):
            kw_n = clasificador_lineas._normalizar(kw).strip()  # noqa: SLF001
            if not kw_n:
                continue
            cubiertos.add(kw_n)
            cubiertos.update(kw_n.split())
    return cubiertos


def sugerir(
    clusters: list[dict[str, Any]],
    etiquetas: list[dict[str, Any]],
    *,
    minimo: int = 3,
    tope: int = 8,
) -> list[dict[str, Any]]:
    """Términos recurrentes en las candidatas SIN sección, como sugerencias de sección nueva.

    `clusters`: historias con 'titulo' (y opcional 'resumen'). `etiquetas`: las líneas (clase
    vertical) de la marca, con sus 'keywords' (para clasificar y para excluir lo ya cubierto).
    `minimo`: nº mínimo de historias distintas que deben mencionar el término. `tope`: máximo de
    sugerencias. Devuelve `[{"termino", "n", "ejemplos"}]` rankeado por `n` desc (bigramas antes
    que palabras sueltas a igualdad), excluyendo lo ya cubierto por keywords.
    """
    cubiertos = _terminos_cubiertos(etiquetas)
    # Por término: historias DISTINTAS que lo mencionan + titulares de ejemplo. Separamos bigramas
    # (más específicos: nombran mejor una sección) de palabras sueltas.
    uni: dict[str, dict[str, Any]] = {}
    bi: dict[str, dict[str, Any]] = {}

    def _registrar(tabla: dict[str, dict[str, Any]], termino: str, titulo: str) -> None:
        ranura = tabla.setdefault(termino, {"n": 0, "ejemplos": []})
        ranura["n"] += 1
        if len(ranura["ejemplos"]) < _EJEMPLOS_POR_SUGERENCIA:
            ranura["ejemplos"].append(titulo)

    for c in clusters:
        # Solo las candidatas SIN sección (ninguna línea casa): son el hueco de la taxonomía.
        if clasificador_lineas.clasificar(f"{c.get('titulo', '')}\n{c.get('resumen', '')}", etiquetas):
            continue
        titulo = (c.get("titulo") or "").strip()
        toks = _tokens(titulo)
        vistos_uni = {t for t in toks if t not in cubiertos}
        vistos_bi = {
            f"{a} {b}"
            for a, b in zip(toks, toks[1:])
            if f"{a} {b}" not in cubiertos and not (a in cubiertos and b in cubiertos)
        }
        for t in vistos_uni:
            _registrar(uni, t, titulo)
        for t in vistos_bi:
            _registrar(bi, t, titulo)

    # Un bigrama que llega al mínimo «explica» a sus palabras: suprime esas palabras sueltas para no
    # duplicar la señal (p. ej. «roland garros» gana; «roland» y «garros» no salen aparte).
    palabras_de_bigrama: set[str] = set()
    for termino, datos in bi.items():
        if datos["n"] >= minimo:
            palabras_de_bigrama.update(termino.split())

    candidatas: list[dict[str, Any]] = []
    for termino, datos in bi.items():
        if datos["n"] >= minimo:
            candidatas.append({"termino": termino, "n": datos["n"], "ejemplos": datos["ejemplos"], "_bi": 1})
    for termino, datos in uni.items():
        if datos["n"] >= minimo and termino not in palabras_de_bigrama:
            candidatas.append({"termino": termino, "n": datos["n"], "ejemplos": datos["ejemplos"], "_bi": 0})

    # Ranking: más historias primero; a igualdad, el bigrama (más específico) antes; luego alfabético.
    candidatas.sort(key=lambda s: (-s["n"], -s["_bi"], s["termino"]))
    return [{"termino": s["termino"], "n": s["n"], "ejemplos": s["ejemplos"]} for s in candidatas[:tope]]
