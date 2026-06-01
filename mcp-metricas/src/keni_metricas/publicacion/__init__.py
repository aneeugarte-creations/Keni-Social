"""Publicacion / programacion — DRY-RUN por defecto. Dos caminos:

1. **Metricool (recomendado, multi-red).** `metricool.AdaptadorPublicacionMetricool`
   entrega el post al scheduler de Metricool con su fecha de publicacion, usando el
   MISMO token por marca que la lectura de metricas (`fuentes.metricol`). Cubre
   Facebook, Instagram, X (twitter), TikTok y YouTube por un solo endpoint, con
   PROGRAMACION nativa (`publicationDate` + `autoPublish`) — sin integrar cada API
   oficial, y sin cola propia.

2. **Meta directo (opcional).** `meta.AdaptadorPublicacionMeta` traduce un `Borrador` a
   peticiones de Graph API (FB feed/photo/video; IG container -> publish). Ruta directa
   alternativa; `cola.ColaPublicacion` agenda IG porque Graph API no lo hace.

La postura del producto es **humano aprueba, nada se publica solo**: ambos adaptadores
corren en **dry-run por defecto** y NO tocan la red salvo que se pida `dry_run=False`
con credenciales reales configuradas.
"""

from __future__ import annotations

from .cola import ColaPublicacion, ItemCola
from .meta import AdaptadorPublicacionMeta, PeticionPublicacion
from .metricool import (
    AdaptadorPublicacionMetricool,
    BorradorMetricool,
    PeticionProgramada,
    ProgramacionNoConfigurada,
    ResultadoProgramacion,
)
from .modelos import Borrador, MediaRef, TipoMedia

__all__ = [
    "AdaptadorPublicacionMeta",
    "AdaptadorPublicacionMetricool",
    "Borrador",
    "BorradorMetricool",
    "ColaPublicacion",
    "ItemCola",
    "MediaRef",
    "PeticionProgramada",
    "PeticionPublicacion",
    "ProgramacionNoConfigurada",
    "ResultadoProgramacion",
    "TipoMedia",
]
