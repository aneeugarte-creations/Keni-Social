"""Escritura atomica de texto a fichero — REEXPORTA `keni_shared.io_atomico`.

La implementacion UNICA vive AHORA en `keni_shared.io_atomico` (H3/E1), la capa
mas baja del monorepo, para que keni-consola y keni-metricas la importen de la
MISMA fuente (antes vivia aqui y el asistente de keni-metricas tenia una copia).

Este modulo se conserva como reexport para no romper los imports existentes de los
~10 modulos de dominio de la consola (`from .io_atomico import escribir_atomico`).
No define NADA propio.
"""

from __future__ import annotations

from keni_shared.io_atomico import escribir_atomico  # noqa: F401  (reexport)

__all__ = ["escribir_atomico"]
