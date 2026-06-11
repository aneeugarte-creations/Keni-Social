"""Dominio HASHTAGS: prompt de sugerencia + parseo de la salida (PURO, sin HTTP).

Extraido de `api/hashtags.py` para que el WORKER de generacion (#130 Fase 2 / ADR 0002
Fase B) pueda reconstruir el post-procesado de un job de hashtags SIN importar de `api/`
(el worker corre fuera del proceso del back, posiblemente en otro contenedor). `api/
hashtags.py` reexporta estas funciones, asi que sus contratos HTTP no cambian.
"""

from __future__ import annotations

import logging
import re

from .. import redes

_log = logging.getLogger("keni_consola.dominio.hashtags")

# Caracteres validos dentro de un hashtag (letras Unicode, digitos y _). Sin espacios.
_RE_TAG = re.compile(r"#?([\wÀ-ɏ]+)", re.UNICODE)

# El prompt vive en la Biblioteca de Texto como documento EDITABLE (pestaña «Prompts», doc
# `prompt/hashtags`): el equipo lo ajusta sin tocar código. Las variables {{RED}}, {{MARCA}}
# y {{TEXTO}} se sustituyen aquí al componer la llamada. `_PROMPT_FALLBACK` es la red
# defensiva (mismo texto que la semilla) por si un store viejo no tuviera el doc ni la
# semilla disponible: la sugerencia de hashtags NUNCA se queda sin prompt.
_PROMPT_ID = "prompt/hashtags"
_PROMPT_FALLBACK = (
    "Sugiere entre 8 y 15 hashtags relevantes en español para {{RED}} para la marca "
    "{{MARCA}}, a partir del siguiente texto. Responde SOLO con los hashtags, uno por "
    "línea, cada uno empezando por #, sin numeración ni explicaciones:\n\n{{TEXTO}}"
)


def _plantilla() -> str:
    """Cuerpo EFECTIVO del prompt (publicado > store del equipo > semilla del paquete).

    Import diferido de `libtexto` (evita ciclos). Si la lectura fallara o viniera vacía,
    cae al `_PROMPT_FALLBACK` del módulo (con warning) para no dejar la herramienta sin prompt.
    """
    try:
        from .. import libtexto

        cuerpo = (libtexto.cuerpo_efectivo(_PROMPT_ID) or "").strip()
    except Exception:  # noqa: BLE001 -- best-effort: nunca dejar la sugerencia sin prompt
        cuerpo = ""
    if cuerpo:
        return cuerpo
    _log.warning(
        "hashtags: %s no disponible en la Biblioteca; uso el fallback del módulo.", _PROMPT_ID
    )
    return _PROMPT_FALLBACK


def normalizar_tag(crudo: str) -> str | None:
    """Normaliza un hashtag a `#xxx` (un solo token). None si queda vacio."""
    if not isinstance(crudo, str):
        return None
    crudo = crudo.strip()
    if not crudo:
        return None
    m = _RE_TAG.search(crudo)
    if m is None:
        return None
    return f"#{m.group(1)}"


def construir_prompt_sugerencia(texto: str, marca: str, red: str | None = None) -> str:
    """Prompt para pedir hashtags (plantilla editable de la Biblioteca + sustitución).

    El texto viaja como argumento (sin shell). Sin red destino, {{RED}} se rellena con el
    genérico «redes sociales» (la plantilla queda gramatical en ambos casos).
    """
    destino = redes.nombre_por_id(red) if red else "redes sociales"
    return (
        _plantilla()
        .replace("{{RED}}", destino)
        .replace("{{MARCA}}", marca)
        .replace("{{TEXTO}}", texto)
    )


def parsear_hashtags(salida: str) -> list[str]:
    """Extrae hashtags de la salida cruda del asistente (tolerante).

    Estrategia: primero busca tokens `#xxx`; si no hay ninguno, cae a tratar cada
    LINEA no vacia como un hashtag (normalizandola). Quita duplicados preservando el
    orden. Devuelve `[]` si no hay nada utilizable.
    """
    salida = salida or ""
    encontrados = re.findall(r"#([\wÀ-ɏ]+)", salida, re.UNICODE)
    if encontrados:
        crudos = [f"#{t}" for t in encontrados]
    else:
        crudos = [linea for linea in salida.splitlines() if linea.strip()]
    salida_norm: list[str] = []
    vistos: set[str] = set()
    for crudo in crudos:
        tag = normalizar_tag(crudo)
        if tag is None or tag in vistos:
            continue
        vistos.add(tag)
        salida_norm.append(tag)
    return salida_norm
