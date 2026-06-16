"""Dominio HASHTAGS: prompt de sugerencia + parseo de la salida (PURO, sin HTTP)."""

from __future__ import annotations

import logging
import re

from .. import redes

_log = logging.getLogger("keni_consola.dominio.hashtags")

# Caracteres validos dentro de un hashtag (letras Unicode, digitos y _). Sin espacios.
_RE_TAG = re.compile(r"#?([\wÀ-ɏ]+)", re.UNICODE)

# El prompt vive en la Prompts de Texto como documento EDITABLE (pestaña «Prompts», doc
# `prompt/hashtags`): el equipo lo ajusta sin tocar código. Las variables {{RED}}, {{MARCA}}
# y {{TEXTO}} se sustituyen aquí al componer la llamada. La INICIAL del paquete
# (`prompts_inicial/prompt/hashtags.md`) es la ÚNICA fuente del texto: no hay copia duplicada
# en código (el test de cobertura inicial↔código garantiza que la inicial existe).
_PROMPT_ID = "prompt/hashtags"


def _plantilla() -> str:
    """Cuerpo EFECTIVO del prompt (publicado > store del equipo > INICIAL del paquete).

    Import diferido de `libprompts` (evita ciclos). `cuerpo_efectivo` ya cae a la inicial cuando
    el doc no está en el store; `cuerpo_inicial` es la red final si la lectura del store
    revienta (NUNCA lanza). "" solo si faltara la inicial (camino inalcanzable: lo cubre el
    test inicial↔código), y se avisa.
    """
    from .. import libprompts

    try:
        cuerpo = (libprompts.cuerpo_efectivo(_PROMPT_ID) or "").strip()
    except Exception:  # noqa: BLE001 -- best-effort: caemos a la inicial del paquete
        cuerpo = ""
    cuerpo = cuerpo or libprompts.cuerpo_inicial(_PROMPT_ID).strip()
    if not cuerpo:
        _log.warning("hashtags: %s no está en la Prompts ni en la inicial.", _PROMPT_ID)
    return cuerpo


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
    """Prompt para pedir hashtags (plantilla editable de la Prompts + sustitución).

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
