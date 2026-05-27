"""Dominio HASHTAGS: prompt de sugerencia + parseo de la salida (PURO, sin HTTP).

Extraido de `api/hashtags.py` para que el WORKER de generacion (#130 Fase 2 / ADR 0002
Fase B) pueda reconstruir el post-procesado de un job de hashtags SIN importar de `api/`
(el worker corre fuera del proceso del back, posiblemente en otro contenedor). `api/
hashtags.py` reexporta estas funciones, asi que sus contratos HTTP no cambian.
"""

from __future__ import annotations

import re

from .. import redes

# Caracteres validos dentro de un hashtag (letras Unicode, digitos y _). Sin espacios.
_RE_TAG = re.compile(r"#?([\wÀ-ɏ]+)", re.UNICODE)


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
    """Prompt para pedir hashtags. El texto viaja como argumento (sin shell)."""
    destino = f" para {redes.nombre_por_id(red)}" if red else ""
    return (
        f"Sugiere entre 8 y 15 hashtags relevantes en español{destino} para la marca "
        f"{marca}, a partir del siguiente texto. Responde SOLO con los hashtags, uno por "
        f"línea, cada uno empezando por #, sin numeración ni explicaciones:\n\n{texto}"
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
