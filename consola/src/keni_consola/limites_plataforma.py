"""Limites de caracteres por plataforma — REEXPORTA `keni_shared.limites_plataforma`.

La fuente UNICA de los topes vive AHORA en `keni_shared.limites_plataforma`
(H3/E1), la capa mas baja del monorepo, para que keni-metricas y keni-consola la
importen de la MISMA fuente (antes vivia aqui y el frontend/skills la espejaban
con guards). `redes.py` la consume, el endpoint `GET /api/limites` la expone y los
guards (`test_api_limites.py` para meta.ts, `evals/test_limites.py` para
plataformas.md) anclan contra esta fuente unica.

Este modulo se conserva como reexport para no romper imports/tests existentes de
la consola (`from . import limites_plataforma`). No define NADA propio.
"""

from __future__ import annotations

from keni_shared.limites_plataforma import (  # noqa: F401  (reexport: la fuente es keni_shared)
    LIMITES,
    como_lista,
    limite_de,
)

__all__ = ["LIMITES", "como_lista", "limite_de"]
