"""Config — accesores del dominio contenido. Parte de config.py (ver barrel)."""
from __future__ import annotations

from ._config_comun import (
    ENV_FUSION_MODELO,
    ENV_HASHTAGS_MODELO,
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


def fusion_modelo() -> str:
    """Modelo de claude para la FUSIÓN semántica de historias (`KENI_FUSION_MODELO`, def "sonnet").

    La fusión decide qué historias se CORROBORAN entre sí: un grupo equivocado infla
    `n_fuentes`/score y puede auto-producir una pieza con fuentes que no hablan de lo mismo.
    Ese juicio fino ("mismo acontecimiento" vs "mismo tema") se le escapaba a haiku — agrupó
    el show de Shakira con una alerta de la embajada por compartir «Mundial»—, así que la
    fusión usa sonnet por defecto (pocas llamadas por barrido: el coste es menor). Mismas
    semánticas que `insumos_modelo`: "" explícito = sin `--model`.
    """
    raw = os.environ.get(ENV_FUSION_MODELO)
    if raw is None:
        return "sonnet"
    return raw.strip()


def hashtags_modelo() -> str:
    """Modelo de claude para Sugerir hashtags (`KENI_HASHTAGS_MODELO`, def "haiku").

    Elegir hashtags de la lista fija de candidatos de la marca es una tarea acotada (salida JSON
    cerrada sobre un conjunto dado), no necesita el modelo grande: por eso va con haiku por defecto.
    Mismas semánticas que `insumos_modelo`: "" explícito = sin `--model`.
    """
    raw = os.environ.get(ENV_HASHTAGS_MODELO)
    if raw is None:
        return "haiku"
    return raw.strip()
