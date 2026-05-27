#!/usr/bin/env python3
"""Red de seguridad de tropicalizacion (es-MX) — deteccion por FLEXIONES (#139).

Este modulo AMPLIA la deteccion de espanolismos mas alla de la lista CERRADA de
~12 lemas de `checks.detecta_espanolismos` (`checks.py`, que solo casa el lema
exacto y deja pasar "mola"/"flipo"). Aqui detectamos tambien **flexiones y
variantes** de cada termino peninsular (conjugaciones de verbo, genero/numero,
diminutivos) y **registramos cobertura**, para que el gate no sea ciego a las
formas mas comunes que el modelo produce de verdad.

Decisiones de diseno (se quedan separadas a proposito):
  - **Archivo NUEVO**, no toca `checks.py` ni `detecta_espanolismos`. Asi convive
    con el detector conservador existente (que sigue siendo la fuente del gate
    `evaluar_copy`) y minimiza conflictos de merge con otras ramas que tocan
    `checks.py` (#131).
  - **Determinista y sin red / sin `claude -p`**: Python puro. Se puede correr en
    CI y como script.
  - **Generacion de flexiones por reglas**, no diccionario exhaustivo: a partir de
    un lema y su CLASE morfologica (verbo -ar, adjetivo de genero/numero,
    sustantivo, invariable) expandimos las formas plausibles. No busca perfeccion
    linguistica; busca una RED MAS ANCHA que el lema exacto, con pocos falsos
    positivos.
  - Reutiliza la normalizacion de `checks._normaliza` (minusculas + sin acentos)
    para casar igual que el resto de los chequeos.

Las formas peninsulares cubiertas salen de `contexto-editorial/tropicalizacion.md`
(tabla Espana -> Mexico y la lista de antipatrones). Cada entrada apunta a esa
guia como fuente editorial.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Reutilizamos la normalizacion del modulo de checks para casar identico al resto
# de comprobaciones (minusculas + sin acentos). Import perezoso para que este
# modulo siga siendo importable de forma aislada.
from checks import _normaliza  # noqa: E402

_RE_PALABRA = re.compile(r"[a-z]+")


# ---------------------------------------------------------------------------
# Catalogo de lemas peninsulares con su CLASE morfologica.
# ---------------------------------------------------------------------------
#
# `clase` decide como se expanden las flexiones (ver _expandir):
#   - "invariable": el lema tal cual (adverbios, interjecciones, pronombres).
#   - "sustantivo": singular + plural (+ -s / -es).
#   - "adjetivo":   genero y numero (guay es invariable, pero p. ej. "majo").
#   - "verbo_ar":   conjugacion regular de un verbo de la 1a conjugacion (-ar),
#                   que cubre el caso clave que el gate viejo NO veia: "molar" ->
#                   "mola", "molan", "molaba"...; "flipar" -> "flipo", "flipas"...
#   - "verbo_ar_pron": verbo -ar pronominal/que ademas aparece sin "se" (pillar).
#
# La "mexicana" es solo documental (que sugerir): la usa el informe de cobertura
# y los mensajes, no la deteccion.

@dataclass(frozen=True)
class Lema:
    lema: str
    clase: str
    mexicano: str = ""


# Fuente editorial: contexto-editorial/tropicalizacion.md (tabla y antipatrones).
# Se EXCLUYEN a proposito los ambiguos (piso/tio/coger), igual que el detector
# conservador de checks.py: en MX existen con otro sentido y darian falsos
# positivos. Se documentan en tropicalizacion.md, no aqui.
LEMAS: tuple[Lema, ...] = (
    # invariables (interjecciones, adverbios, pronombres peninsulares)
    Lema("vale", "invariable", "sale / va / órale"),
    Lema("guay", "invariable", "padre / chido"),
    Lema("vosotros", "invariable", "ustedes"),
    Lema("os", "invariable", "los / les"),  # pronombre atono de vosotros
    Lema("hostia", "sustantivo", "(evitar; informal)"),
    # sustantivos (singular + plural)
    Lema("coche", "sustantivo", "carro / auto"),
    Lema("ordenador", "sustantivo", "computadora"),
    Lema("movil", "sustantivo", "celular"),
    Lema("zumo", "sustantivo", "jugo"),
    Lema("patata", "sustantivo", "papa"),
    Lema("gilipollas", "invariable", "(evitar)"),  # ya termina en -s, invariable
    Lema("chaval", "sustantivo", "chavo / morro"),  # chaval/chavala -> ver adjetivo abajo
    Lema("curro", "sustantivo", "chamba"),
    # verbos de 1a conjugacion (-ar): aqui esta la GANANCIA sobre el gate viejo
    Lema("molar", "verbo_ar", "estar padre / estar chido / gustar"),
    Lema("flipar", "verbo_ar", "alucinar / sorprender"),
    Lema("currar", "verbo_ar", "chambear"),
    Lema("aparcar", "verbo_ar", "estacionar"),
    Lema("pillar", "verbo_ar_pron", "agarrar / cachar"),
    Lema("cabrear", "verbo_ar", "enojar / encabronar"),
    Lema("alucinar", "verbo_ar", ""),  # nota: en MX tambien se usa; ver AMBIGUOS
    # adjetivos/sustantivos con genero y numero
    Lema("chaval", "genero_l", "chavo/a / morro/a"),  # chaval/chavala/chavales/chavalas
    Lema("majo", "genero_o", "buena onda / agradable"),
    Lema("guarro", "genero_o", "cochino / sucio"),
)

# `alucinar` en MX tambien existe ("alucinar a alguien" = caerle muy mal / ignorar),
# por eso lo dejamos FUERA del set activo por defecto (ambiguo). Se documenta.
AMBIGUOS_FUERA = frozenset({"alucinar"})


# ---------------------------------------------------------------------------
# Expansion de flexiones por clase.
# ---------------------------------------------------------------------------

def _flexiones_verbo_ar(lema: str) -> set[str]:
    """Formas regulares plausibles de un verbo -ar (normalizadas, sin acentos).

    No es la conjugacion completa del espanol: cubre las formas que de verdad
    aparecen en copy de redes (presente, preterito, imperfecto, futuro simple,
    condicional, gerundio, participio e infinitivo). Suficiente para cazar
    "mola/molan/molaba/molaria/flipo/flipas/flipando" que el gate viejo dejaba
    pasar, sin pretender exhaustividad.
    """
    if not lema.endswith("ar"):
        return {lema}
    raiz = lema[:-2]  # quita "-ar"
    sufijos = {
        "ar",  # infinitivo
        # presente de indicativo
        "o", "as", "a", "amos", "ais", "an",
        # preterito perfecto simple
        "e", "aste", "o", "amos", "asteis", "aron",
        # imperfecto
        "aba", "abas", "abamos", "abais", "aban",
        # futuro simple
        "are", "aras", "ara", "aremos", "areis", "aran",
        # condicional
        "aria", "arias", "ariamos", "ariais", "arian",
        # gerundio y participio
        "ando", "ado", "ada", "ados", "adas",
        # presente de subjuntivo (regular)
        "e", "es", "emos", "eis", "en",
    }
    return {_normaliza(raiz + s) for s in sufijos}


def _flexiones_verbo_ar_pron(lema: str) -> set[str]:
    """Verbo -ar que aparece tambien con cliticos (pillar -> pillalo, pillate).

    Anade al conjunto base las formas con clitico pegado mas comunes en redes.
    """
    base = _flexiones_verbo_ar(lema)
    if lema.endswith("ar"):
        raiz = lema[:-2]
        # imperativo + clitico: pilla, pillalo, pillala, pillate, pillalos, pillalas
        imperativo = raiz + "a"
        for cl in ("", "lo", "la", "los", "las", "te", "me", "nos"):
            base.add(_normaliza(imperativo + cl))
    return base


def _flexiones_sustantivo(lema: str) -> set[str]:
    """Singular + plural regular de un sustantivo (normalizados)."""
    n = _normaliza(lema)
    formas = {n}
    if n.endswith("s"):
        return formas  # ya invariable en plural (gilipollas)
    # plural: vocal -> +s ; consonante -> +es
    if n and n[-1] in "aeiou":
        formas.add(n + "s")
    else:
        formas.add(n + "es")
    return formas


def _flexiones_genero_o(lema: str) -> set[str]:
    """Adjetivo/sustantivo en -o con genero y numero (majo/maja/majos/majas)."""
    n = _normaliza(lema)
    if not n.endswith("o"):
        return {n}
    raiz = n[:-1]
    return {raiz + g for g in ("o", "a", "os", "as")}


def _flexiones_genero_l(lema: str) -> set[str]:
    """Sustantivo en -l con genero/numero a la espanola (chaval/chavala/...)."""
    n = _normaliza(lema)
    formas = {n}
    if n.endswith("l"):
        formas.add(n + "es")          # chavales
        formas.add(n + "a")           # chavala
        formas.add(n + "as")          # chavalas
    return formas


def _expandir(lema: Lema) -> set[str]:
    """Conjunto de formas normalizadas a detectar para un lema, segun su clase."""
    clase = lema.clase
    if clase == "verbo_ar":
        return _flexiones_verbo_ar(lema.lema)
    if clase == "verbo_ar_pron":
        return _flexiones_verbo_ar_pron(lema.lema)
    if clase == "sustantivo":
        return _flexiones_sustantivo(lema.lema)
    if clase == "genero_o":
        return _flexiones_genero_o(lema.lema)
    if clase == "genero_l":
        return _flexiones_genero_l(lema.lema)
    # invariable
    return {_normaliza(lema.lema)}


def _construir_indice() -> dict[str, str]:
    """Mapa {forma_normalizada -> lema} de todas las flexiones del catalogo.

    Excluye los lemas ambiguos (AMBIGUOS_FUERA). Si dos lemas generan la misma
    forma, se queda con el primero (orden del catalogo): es solo para reportar a
    que lema atribuir el hallazgo.
    """
    indice: dict[str, str] = {}
    for lema in LEMAS:
        if lema.lema in AMBIGUOS_FUERA:
            continue
        for forma in _expandir(lema):
            if forma and forma not in indice:
                indice[forma] = lema.lema
    return indice


# Indice construido una vez al importar (determinista).
INDICE_FLEXIONES: dict[str, str] = _construir_indice()


# ---------------------------------------------------------------------------
# Deteccion y cobertura.
# ---------------------------------------------------------------------------

@dataclass
class HallazgoTropicalizacion:
    """Una forma peninsular detectada en el texto."""

    forma: str   # la palabra hallada (normalizada) tal cual aparece
    lema: str    # el lema peninsular al que se atribuye
    mexicano: str = ""  # sugerencia es-MX (documental)


@dataclass
class CoberturaTropicalizacion:
    """Resumen de cobertura del detector por flexiones.

    Registra cuantos lemas y cuantas formas vigila el detector, y cuales lemas
    se activaron en el texto. Sirve para DOCUMENTAR el alcance de la red de
    seguridad (cuanto mas que el lema exacto cubrimos).
    """

    lemas_totales: int
    formas_totales: int
    lemas_disparados: list[str] = field(default_factory=list)

    def texto(self) -> str:
        return (
            f"cobertura tropicalizacion: {self.lemas_totales} lemas / "
            f"{self.formas_totales} formas vigiladas; "
            f"disparados: {', '.join(self.lemas_disparados) or '(ninguno)'}"
        )


_LEMA_A_MEX: dict[str, str] = {l.lema: l.mexicano for l in LEMAS}


def detecta_flexiones_es_es(texto: str) -> list[HallazgoTropicalizacion]:
    """Espanolismos detectados POR FLEXION (no solo el lema exacto). [] = ok.

    Tokeniza el texto normalizado (minusculas, sin acentos), y por cada palabra
    busca si es una de las formas vigiladas (INDICE_FLEXIONES). Casa por PALABRA
    COMPLETA (no subcadena), preserva el orden de aparicion y no repite la misma
    forma.

    A diferencia de `checks.detecta_espanolismos`, aqui "mola", "flipo",
    "molaban", "flipando", "coches", "movil"/"moviles" SI se detectan, porque el
    indice incluye las flexiones del lema, no solo el lema.
    """
    norm = _normaliza(texto)
    hallazgos: list[HallazgoTropicalizacion] = []
    vistos: set[str] = set()
    for palabra in _RE_PALABRA.findall(norm):
        if palabra in vistos:
            continue
        lema = INDICE_FLEXIONES.get(palabra)
        if lema is not None:
            vistos.add(palabra)
            hallazgos.append(
                HallazgoTropicalizacion(
                    forma=palabra, lema=lema, mexicano=_LEMA_A_MEX.get(lema, "")
                )
            )
    return hallazgos


def cobertura() -> CoberturaTropicalizacion:
    """Cobertura ESTATICA del detector (sin texto): lemas y formas vigiladas."""
    lemas = sorted({l.lema for l in LEMAS if l.lema not in AMBIGUOS_FUERA})
    return CoberturaTropicalizacion(
        lemas_totales=len(lemas),
        formas_totales=len(INDICE_FLEXIONES),
    )


def evaluar_tropicalizacion(texto: str) -> tuple[list[HallazgoTropicalizacion], CoberturaTropicalizacion]:
    """Devuelve (hallazgos, cobertura) de un texto.

    `cobertura.lemas_disparados` lista los lemas que se activaron en este texto.
    Pensado para que el corredor local / un futuro check de golden lo registre.
    """
    hallazgos = detecta_flexiones_es_es(texto)
    cob = cobertura()
    cob.lemas_disparados = sorted({h.lema for h in hallazgos})
    return hallazgos, cob


def _main(argv: list[str] | None = None) -> int:
    """CLI minima: lee un fichero (o stdin) y reporta hallazgos + cobertura.

    Uso:
        python3 tropicalizacion.py [fichero.txt]
    Sale 0 si no hay hallazgos, 1 si los hay (gate determinista, sin modelo).
    """
    import sys

    if argv is None:
        argv = sys.argv[1:]
    if argv:
        texto = open(argv[0], encoding="utf-8").read()
    else:
        texto = sys.stdin.read()
    hallazgos, cob = evaluar_tropicalizacion(texto)
    print(cob.texto())
    if not hallazgos:
        print("RESULTADO: PASA (sin flexiones peninsulares detectadas)")
        return 0
    for h in hallazgos:
        sug = f" -> {h.mexicano}" if h.mexicano else ""
        print(f'  [es-ES] "{h.forma}" (lema: {h.lema}){sug}')
    print(f"RESULTADO: FALLA ({len(hallazgos)} forma(s) peninsular(es))")
    return 1


if __name__ == "__main__":
    raise SystemExit(_main())
