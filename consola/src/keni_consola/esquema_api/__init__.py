"""Esquema tipado de un SUBCONJUNTO ESTABLE del contrato `/api/*`.

Por que existe: el frontend mantenia ~179 interfaces a mano en
`frontend/src/types.ts` espejando las respuestas del backend, y se desincronizaban
en silencio. Este paquete define esas formas UNA VEZ en Python (como `TypedDict`),
emite su JSON Schema y de ahi el frontend GENERA el TypeScript (`types.gen.ts`).

Alcance deliberadamente acotado (NO todo el contrato): solo las respuestas mas
ESTABLES y respaldadas por datos canonicos del backend (estado/doctor,
limites/redes, metricas). El resto de `types.ts` sigue a mano: las ~50 rutas
construyen sus respuestas como dicts ad-hoc (`JSONResponse({...})`), no como
modelos, asi que forzar una generacion total exigiria reescribir esos handlers
(fuera de alcance y fragil). Mejor un subset robusto y reproducible.

IMPORTANTE — sin impacto en runtime ni en el JSON emitido: estos `TypedDict` son
SOLO tipos (no se instancian, no validan, no se serializan). Los handlers siguen
devolviendo exactamente los mismos dicts. Son el CONTRATO declarado del que se
deriva el TS y contra el que el guard verifica que no haya divergencia.

Para regenerar el TS: ver `frontend/README.md` (`npm run gen:types`).
"""

from __future__ import annotations

from .modelos import MODELOS
from .schema import esquema_json

__all__ = ["MODELOS", "esquema_json"]
