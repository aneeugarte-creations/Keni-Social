"""Publicacion / programacion — DRY-RUN por defecto.

**Metricool (multi-red).** `metricool.AdaptadorPublicacionMetricool`
entrega el post al scheduler de Metricool con su fecha de publicacion, usando el
MISMO token por marca que la lectura de metricas (`fuentes.metricool`). Cubre
Facebook, Instagram, X (twitter), TikTok y YouTube por un solo endpoint, con
PROGRAMACION nativa (`publicationDate` + `autoPublish`) — sin integrar cada API
oficial, y sin cola propia.

La postura del producto es **humano aprueba, nada se publica solo**: el adaptador
corre en **dry-run por defecto** y NO toca la red salvo que se pida `dry_run=False`
con credenciales reales configuradas.
"""

from __future__ import annotations

from .metricool import (
    AdaptadorPublicacionMetricool,
    BorradorMetricool,
    PeticionProgramada,
    ProgramacionNoConfigurada,
    ResultadoProgramacion,
)
from .modelos import Borrador, MediaRef, TipoMedia
from .postproxy import AdaptadorPublicacionPostproxy

__all__ = [
    "AdaptadorPublicacionMetricool",
    "AdaptadorPublicacionPostproxy",
    "Borrador",
    "BorradorMetricool",
    "MediaRef",
    "PeticionProgramada",
    "ProgramacionNoConfigurada",
    "ResultadoProgramacion",
    "TipoMedia",
]
