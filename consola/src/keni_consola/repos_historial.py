"""Repositorio — dominio historial. Implementación de repos.py (ver barrel `repos.py`)."""
from __future__ import annotations

from ._repos_comun import (
    Any,
    db,
    ficheros,
)

# --------------------------------------------------------------------------- #
# Historial de prompts (CONTENIDO: ficheros YAML via ficheros.py)              #
# --------------------------------------------------------------------------- #


def registrar_historial_prompt(
    prompt_id: str,
    marca: str,
    resultado: str,
    *,
    piezas: list[dict[str, Any]] | None = None,
    titulo: str = "",
    metricas: dict[str, Any] | None = None,
    autor: dict[str, str] | None = None,
) -> str:
    return ficheros.registrar_historial_prompt(
        prompt_id, marca, resultado, piezas=piezas, titulo=titulo, metricas=metricas, autor=autor
    )


def listar_historial_prompts(
    *, limite: int | None = None, desplazamiento: int | None = None
) -> list[dict[str, Any]]:
    return ficheros.listar_historial_prompts(limite=limite, desplazamiento=desplazamiento)


def contar_historial_prompts() -> int:
    return ficheros.contar_historial_prompts()


def obtener_historial_prompt(historial_id: str) -> dict[str, Any] | None:
    return ficheros.obtener_historial_prompt(historial_id)


