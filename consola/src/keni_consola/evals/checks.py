"""Checks DETERMINISTAS por dimensión: el corazón del harness, todo REUSO de lo que ya existe.

Cada dimensión es una función pura `(caso) -> ResultadoDimension` que NO inventa lógica de
verificación: envuelve la maquinaria que ya corre en producción para que el eval mida EXACTAMENTE
lo que el sistema mide. Si una edición de prompt degrada la salida por debajo de esos umbrales,
el caso golden que dependía de ello cambia de veredicto y el harness lo caza.

Dimensiones (claves estables; se referencian en los casos y en el reporte):
  - `limite_red`  : tope técnico DURO de caracteres por red, por intervalo de hilo/carrusel.
                    Reusa `keni_shared.limites_plataforma` + `dominio.copy._intervalos_publicables`
                    (la misma criba que descarta piezas inválidas en el post-procesado).
  - `voz`         : adherencia a los PATRONES medidos de la marca (longitud p-derivada, banda de
                    emojis/hashtags, gancho en mayúsculas, pregunta). Reusa
                    `patrones_marca.verificar_pieza` — el MISMO lint del post-procesado de copy.
  - `coherencia`  : solapamiento léxico copy↔nota de origen (caza alucinación / pieza cruzada).
                    Reusa `pipeline_contenido._revisar.avisos_coherencia`. Solo si hay `fuente`.
  - `prohibidos`  : términos vetados por la regla editorial de la marca (los declara el caso).
                    Normaliza con `dominio.dedup.clave` (sin acentos, tokens) para no fallar por
                    tildes/mayúsculas. Solo si el caso trae `prohibidos`.
  - `idioma`      : tropicalización MX básica — el copy debe "sonar a español". Heurística
                    CONSERVADORA: solo falla si un copy SUSTANCIAL no contiene NI UNA palabra
                    función del español (señal fuerte de que salió en otro idioma / inglés).

Todas las dimensiones son SAFE: ante un fallo interno de la maquinaria reusada degradan a `na`
(no aplica) en vez de romper la corrida — un eval que peta no debe tumbar el harness entero.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable

from .modelo import ESTADO_FALLA, ESTADO_NA, ESTADO_OK, CasoEval, ResultadoDimension

# Firma de un check de dimensión.
Check = Callable[[CasoEval], ResultadoDimension]


def _ok(nombre: str) -> ResultadoDimension:
    return ResultadoDimension(nombre=nombre, estado=ESTADO_OK)


def _falla(nombre: str, avisos: list[str]) -> ResultadoDimension:
    return ResultadoDimension(nombre=nombre, estado=ESTADO_FALLA, avisos=tuple(avisos))


def _na(nombre: str) -> ResultadoDimension:
    return ResultadoDimension(nombre=nombre, estado=ESTADO_NA)


# --- limite_red: tope técnico duro por red (reuso de keni_shared + dominio.copy) ----------- #


def check_limite_red(caso: CasoEval) -> ResultadoDimension:
    """Falla si algún intervalo publicable del copy supera el límite técnico DURO de la red."""
    from keni_shared import limites_plataforma

    limite = limites_plataforma.limite_de(caso.red)
    if limite is None:
        return _na("limite_red")  # red sin tope práctico (Facebook / YouTube): nada que medir
    intervalos = _intervalos(caso.copy)
    excesos = [len(t) for t in intervalos if len(t) > limite]
    if excesos:
        return _falla(
            "limite_red",
            [f"{caso.red}: intervalo de {max(excesos)} caracteres (límite técnico {limite})"],
        )
    return _ok("limite_red")


def _intervalos(texto: str) -> list[str]:
    """Intervalos publicables (tuit de un hilo / slide de carrusel / pieza simple). Reusa la criba
    del post-procesado de copy; si no estuviera disponible, cae al texto entero (best-effort)."""
    try:
        from keni_consola.dominio import copy as dom_copy

        intervalos = dom_copy._intervalos_publicables(texto)  # noqa: SLF001 -- reuso del contrato de piezas
        return intervalos or [texto]
    except Exception:  # noqa: BLE001 -- sin la criba, mide el texto entero
        return [texto]


# --- voz: patrones medidos de la marca (reuso del MISMO lint del post-procesado) ----------- #


def check_voz(caso: CasoEval) -> ResultadoDimension:
    """Falla si el copy se sale de los patrones medidos de la marca en su red.

    `copy_unico=False`: el copy del caso es el copy FINAL (puede llevar hashtags de línea), no
    el copy unificado del contrato de generación. Sin perfil para la marca/red, el lint no
    avisa (degradación honesta) y la dimensión queda OK."""
    try:
        from keni_consola import patrones_marca

        avisos = patrones_marca.verificar_pieza(caso.marca, caso.red, caso.copy, copy_unico=False)
    except Exception:  # noqa: BLE001 -- el lint es un extra; nunca tumba el harness
        return _na("voz")
    return _falla("voz", list(avisos)) if avisos else _ok("voz")


# --- coherencia: solapamiento léxico copy↔nota (reuso del gate de calidad advisory) -------- #


def check_coherencia(caso: CasoEval) -> ResultadoDimension:
    """Falla si el copy no comparte NINGÚN término de contenido con su nota de origen.

    Solo aplica si el caso trae `fuente` sustancial; si no, `na`. Reusa la heurística
    conservadora de `pipeline_contenido._revisar` (mismo umbral que el gate de producción)."""
    if not caso.fuente.strip():
        return _na("coherencia")
    try:
        from keni_consola.pipeline_contenido import _revisar

        avisos = _revisar.avisos_coherencia(caso.copy, caso.fuente)
    except Exception:  # noqa: BLE001
        return _na("coherencia")
    return _falla("coherencia", list(avisos)) if avisos else _ok("coherencia")


# --- prohibidos: términos vetados por la regla editorial de la marca ----------------------- #


def _normalizar(texto: str) -> str:
    """Minúsculas, sin acentos (para casar 'Fiscalía'/'fiscalia'). Reusa el mismo NFKD que
    `dominio.dedup.clave`, pero conserva la puntuación como separador (búsqueda por palabra)."""
    desc = unicodedata.normalize("NFKD", (texto or "").lower())
    return "".join(c for c in desc if not unicodedata.combining(c))


def check_prohibidos(caso: CasoEval) -> ResultadoDimension:
    """Falla si el copy contiene algún término vetado del caso (match por PALABRA, sin acentos).

    Solo aplica si el caso declara `prohibidos`; si no, `na`. El match es por límite de palabra
    para no cazar subcadenas inocentes ('reo' dentro de 'correo')."""
    if not caso.prohibidos:
        return _na("prohibidos")
    copy_norm = _normalizar(caso.copy)
    encontrados: list[str] = []
    for termino in caso.prohibidos:
        patron = r"\b" + re.escape(_normalizar(termino)) + r"\b"
        if re.search(patron, copy_norm):
            encontrados.append(termino)
    if encontrados:
        return _falla(
            "prohibidos",
            [f"{caso.red}: usa término(s) vetado(s) por la regla editorial: {', '.join(encontrados)}"],
        )
    return _ok("prohibidos")


# --- idioma: tropicalización MX básica (heurística conservadora) --------------------------- #

# Palabras función de ALTÍSIMA frecuencia en español. Un copy sustancial que no contiene NI UNA
# casi seguro NO está en español (salió en inglés / otro idioma): señal fuerte y barata. No
# pretende detectar matices MX (eso es criterio humano); solo el "esto no es español" obvio.
_FUNCION_ES = frozenset(
    "de la el los las un una unos unas que con por para en se su sus al del lo le les y o "
    "como mas más pero no sí si este esta estos estas es son fue ser hay ya muy".split()
)
# Por debajo de esto un copy es demasiado corto para que la ausencia de palabras función
# signifique algo (un titular de 4 palabras puede no llevar ninguna por azar).
_MIN_TOKENS_IDIOMA = 8


def check_idioma(caso: CasoEval) -> ResultadoDimension:
    """Falla si un copy SUSTANCIAL no contiene ni una palabra función del español (no-MX/inglés).

    Conservador a propósito (igual filosofía que la coherencia): ante la duda, OK. Solo se
    pronuncia cuando la señal es inequívoca."""
    tokens = re.findall(r"[a-zñ]+", _normalizar(caso.copy))
    if len(tokens) < _MIN_TOKENS_IDIOMA:
        return _ok("idioma")
    if any(t in _FUNCION_ES for t in tokens):
        return _ok("idioma")
    return _falla(
        "idioma",
        [
            f"{caso.red}: el copy no parece español (0 palabras función ES en {len(tokens)} "
            "tokens) — ¿salió en inglés o sin tropicalizar?"
        ],
    )


# Registro ORDENADO de dimensiones (clave estable -> check). El orden fija el del reporte.
DIMENSIONES: dict[str, Check] = {
    "limite_red": check_limite_red,
    "voz": check_voz,
    "coherencia": check_coherencia,
    "prohibidos": check_prohibidos,
    "idioma": check_idioma,
}


def correr_dimensiones(caso: CasoEval) -> list[ResultadoDimension]:
    """Corre las dimensiones aplicables a un caso (las declaradas en `caso.dimensiones`, o todas).

    Una dimensión desconocida en `caso.dimensiones` se ignora con un aviso de configuración
    visible (estado `falla`) para que un typo en el caso no pase desapercibido."""
    if caso.dimensiones:
        seleccion = list(caso.dimensiones)
    else:
        seleccion = list(DIMENSIONES)
    resultados: list[ResultadoDimension] = []
    for nombre in seleccion:
        check = DIMENSIONES.get(nombre)
        if check is None:
            resultados.append(
                _falla(nombre, [f"dimensión desconocida en el caso: {nombre!r}"])
            )
            continue
        resultados.append(check(caso))
    return resultados
