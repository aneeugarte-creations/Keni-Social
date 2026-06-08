"""Validación / normalización de campos editoriales de un documento.

Cada helper devuelve el valor normalizado o lanza `TextoError` (mensaje en español).
"""

from __future__ import annotations

import re

from ._comun import (
    CLASES,
    ESTADO_DEFECTO,
    ESTADOS,
    PIPELINES,
    ROLES_PROMPT,
    TextoError,
)

__all__ = [
    "_validar_clase",
    "_validar_estado",
    "_validar_etiquetas",
    "_validar_pipelines",
    "_validar_rol",
    "_validar_prioridad",
    "_validar_marcas",
]


def _validar_clase(tipo: str, clase: str) -> str:
    """Valida `clase` para editoriales; para prompts debe quedar vacia."""
    if tipo != "editorial":
        return ""
    clase = (clase or "").strip()
    if not clase:
        return ""
    if clase not in CLASES:
        raise TextoError(f"La clase editorial debe ser una de: {', '.join(CLASES)}.")
    return clase


def _validar_estado(estado: str | None) -> str:
    """Valida el estado del ciclo de vida; vacio/None -> defecto."""
    if estado is None:
        return ESTADO_DEFECTO
    estado = estado.strip()
    if not estado:
        return ESTADO_DEFECTO
    if estado not in ESTADOS:
        raise TextoError(f"El estado debe ser uno de: {', '.join(ESTADOS)}.")
    return estado


def _validar_etiquetas(etiquetas: list[str] | None) -> list[str]:
    """Normaliza etiquetas (tags): minusculas, slug-safe, de-dup, orden estable."""
    if not etiquetas:
        return []
    if not isinstance(etiquetas, list):
        raise TextoError("Las etiquetas deben ser una lista de textos.")
    vistas: list[str] = []
    for e in etiquetas:
        if not isinstance(e, str):
            raise TextoError("Cada etiqueta debe ser un texto.")
        norm = re.sub(r"[^a-z0-9]+", "-", e.strip().lower()).strip("-")
        if norm and norm not in vistas:
            vistas.append(norm)
    return vistas


def _validar_pipelines(pipelines: list[str] | None) -> list[str]:
    """Valida la lista de pipelines a los que se ata el doc (deben existir en el registro)."""
    if not pipelines:
        return []
    if not isinstance(pipelines, list):
        raise TextoError("Los pipelines deben ser una lista de identificadores.")
    vistas: list[str] = []
    for p in pipelines:
        if not isinstance(p, str):
            raise TextoError("Cada pipeline debe ser un identificador.")
        p = p.strip()
        if p and p not in PIPELINES:
            raise TextoError(f"Pipeline desconocido: {p}.")
        if p and p not in vistas:
            vistas.append(p)
    return vistas


def _validar_rol(tipo: str, rol: str | None) -> str:
    """Valida el rol de un prompt; para no-prompt debe quedar vacio."""
    if tipo != "prompt" or rol is None:
        return ""
    rol = rol.strip()
    if not rol:
        return ""
    if rol not in ROLES_PROMPT:
        raise TextoError(f"El rol debe ser uno de: {', '.join(r for r in ROLES_PROMPT if r)}.")
    return rol


def _validar_prioridad(prioridad: int | None) -> int:
    """Valida la prioridad de ensamblaje (entero; None -> 0)."""
    if prioridad is None:
        return 0
    if isinstance(prioridad, bool) or not isinstance(prioridad, int):
        raise TextoError("La prioridad debe ser un número entero.")
    return prioridad


def _validar_marcas(marcas: list[str] | None) -> list[str]:
    """Normaliza la lista de marcas (ids canonicos) de un documento editorial."""
    if not marcas:
        return []
    if not isinstance(marcas, list) or not all(isinstance(m, str) for m in marcas):
        raise TextoError("Las marcas deben ser una lista de identificadores.")
    # De-dup preservando orden.
    vistas: list[str] = []
    for m in marcas:
        m = m.strip()
        if m and m not in vistas:
            vistas.append(m)
    return vistas
