"""Escritura atomica de texto a fichero — REEXPORTA `keni_shared.io_atomico`.

Este modulo se conserva como reexport para no romper los imports existentes de los
~10 modulos de dominio de la consola (`from .io_atomico import escribir_atomico`).
No define NADA propio.
"""

from __future__ import annotations

from keni_shared.io_atomico import (  # noqa: F401  (reexport)
    bloqueo_archivo,
    escribir_atomico,
)

__all__ = ["bloqueo_archivo", "escribir_atomico"]
