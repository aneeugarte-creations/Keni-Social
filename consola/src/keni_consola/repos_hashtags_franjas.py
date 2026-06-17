"""Repositorio — dominio hashtags_franjas. Implementación de repos.py (ver barrel `repos.py`)."""
from __future__ import annotations

from ._repos_comun import (
    Any,
    db,
)

# --------------------------------------------------------------------------- #
# Franjas editoriales (OPERACIONAL: Postgres via db.py; rezago cerrado, ADR 0006) #
# --------------------------------------------------------------------------- #


def listar_franjas() -> list[dict[str, Any]]:
    return db.listar_franjas()


def crear_franja(
    dia_semana: int, hora: str, marca: str = "", red: str = "", categoria: str = ""
) -> dict[str, Any]:
    return db.crear_franja(dia_semana, hora, marca=marca, red=red, categoria=categoria)


def borrar_franja(franja_id: str) -> bool:
    return db.borrar_franja(franja_id)
