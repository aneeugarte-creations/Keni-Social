"""Publicacion en Meta (Facebook / Instagram) — DRY-RUN por defecto.

Este paquete anade el camino de PUBLICACION al servidor (que hasta ahora era
solo de lectura). La postura del producto es **humano aprueba, nada se publica
solo**: por eso `AdaptadorPublicacionMeta.publicar(...)` corre en **dry-run por
defecto** y NO toca la red salvo que se pida explicitamente `dry_run=False` con
un token real configurado. Es un andamiaje seguro, listo para cuando aterrice el
App Review de Meta.

Piezas:
- `modelos.Borrador`: el borrador editable (plataforma, cuenta, texto, media,
  hashtags) que un humano aprueba antes de publicar.
- `meta.AdaptadorPublicacionMeta`: traduce un `Borrador` a la(s) peticion(es)
  exacta(s) de Graph API (Facebook feed/photo/video; Instagram container ->
  publish). Reutiliza `_http.post_json` (solo lectura) para el POST real.
- `cola.ColaPublicacion`: cola/agendador minimo en memoria para borradores ya
  aprobados con hora opcional, porque la API de Meta no agenda IG nativamente.
"""

from __future__ import annotations

from .cola import ColaPublicacion, ItemCola
from .meta import AdaptadorPublicacionMeta, PeticionPublicacion
from .modelos import Borrador, MediaRef, TipoMedia

__all__ = [
    "AdaptadorPublicacionMeta",
    "Borrador",
    "ColaPublicacion",
    "ItemCola",
    "MediaRef",
    "PeticionPublicacion",
    "TipoMedia",
]
