"""Repositorio — contador de intentos por etapa. Implementación de repos.py (ver barrel `repos.py`)."""
from __future__ import annotations

from ._comun import (
    db,
)

# --------------------------------------------------------------------------- #
# Contador de intentos por ETAPA del pipeline (OPERACIONAL: persistencia via db.py)             #
# --------------------------------------------------------------------------- #
#
# Contador keyed por `(sujeto, etapa)` que SOBREVIVE a la purga de la cola y al "exito vacio".
# La fachada delega 1:1 en db.py (Postgres).


def intentos_etapa(sujeto: str, etapa: str) -> int:
    return db.intentos_etapa(sujeto, etapa)


def anotar_intento_etapa(sujeto: str, etapa: str) -> int:
    return db.anotar_intento_etapa(sujeto, etapa)


def intento_ts(sujeto: str, etapa: str) -> str | None:
    return db.intento_ts(sujeto, etapa)


def reset_intentos_etapa(sujeto: str, etapa: str) -> None:
    return db.reset_intentos_etapa(sujeto, etapa)
