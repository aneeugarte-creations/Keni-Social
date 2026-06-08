"""Config — accesores del dominio contenido. Parte de config.py (ver barrel)."""
from __future__ import annotations

from ._config_comun import (
    ENV_INSUMOS_MODELO,
    os,
)

# --------------------------------------------------------------------------- #
# Accesor: insumos del día                                                     #
# --------------------------------------------------------------------------- #


def insumos_modelo() -> str:
    """Modelo de claude para parsear insumos del día (`KENI_INSUMOS_MODELO`, def "haiku").

    Si la var esta explicitamente vacia (""), devuelve "" -> el llamante NO pasa `--model`
    y claude usa su propio default. Si no esta fijada, devuelve "haiku". Si esta fijada a
    un valor no vacio, devuelve ese valor como nombre de modelo.
    """
    # _crudo() hace strip: si la var es "" o solo espacios, devuelve "".
    # Si la var no esta en el entorno, os.environ.get devuelve None -> _crudo da "".
    # Por eso chequeamos la var cruda del entorno para distinguir "no fijada" de "vacia".
    raw = os.environ.get(ENV_INSUMOS_MODELO)
    if raw is None:
        return "haiku"  # no fijada: default haiku
    return raw.strip()  # fijada: respeta el valor (puede ser "" para desactivar --model)
