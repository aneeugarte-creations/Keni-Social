"""Limites de caracteres por plataforma — REEXPORTA `keni_shared.limites_plataforma`.

La fuente UNICA de los topes vive en `keni_shared.limites_plataforma` (la capa mas
baja del monorepo), para que keni-metricas y keni-consola la importen de la MISMA
fuente. `redes.py` la consume, el endpoint `GET /api/limites` la expone y los
guards (`test_api_limites.py` para meta.ts, `evals/test_limites.py` para
plataformas.md) anclan contra esta fuente unica.

Este modulo se conserva como reexport para no romper imports/tests existentes de
la consola (`from . import limites_plataforma`). No define NADA propio.
"""

from __future__ import annotations

from keni_shared.limites_plataforma import (  # noqa: F401  (reexport: la fuente es keni_shared)
    LIMITES,
    VIDEO_SPECS,
    como_lista,
    limite_de,
    video_specs_como_lista,
    video_specs_de,
)

__all__ = [
    "LIMITES",
    "VIDEO_SPECS",
    "como_lista",
    "limite_de",
    "video_specs_como_lista",
    "video_specs_de",
]
