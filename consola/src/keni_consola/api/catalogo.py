"""API Catálogo: el shell expone las apps ACTIVAS + la navegación data-driven.

`GET /api/catalogo` -> `{"apps": [...], "navegacion": [{etiqueta, items}, ...]}`

El catálogo lo arma el registro de manifests (`apps/registro.py`), que parsea un
TOML por app (ADR 0005) y FILTRA por el flag de activación de cada una (env var). El
SPA hidrata el sidebar desde aquí: `navegacion.ts` deja de hardcodear las entradas.

Desactivar el flag de una app (p. ej. `KENI_APP_METRICAS=0`) la oculta del catálogo
SIN romper el arranque: el endpoint simplemente no la devuelve. El Shell NO es una
app de catálogo (no aparece en `apps`), pero su entrada de nav (Panel) sí, para que
el sidebar quede idéntico.

Solo lectura, sin estado, sin tocar la BD: lee los manifests + el entorno.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from ..apps import registro


async def catalogo(request: Request) -> Response:
    """`GET /api/catalogo` -> apps activas (según flags) + entradas de navegación."""
    return JSONResponse(registro.catalogo())


RUTAS = [
    Route("/api/catalogo", catalogo, methods=["GET"]),
]
