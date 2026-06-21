"""API Limites: fuente UNICA de verdad de los limites de caracteres por red.

`GET /api/limites` -> `{"limites": [{"id", "nombre", "limite"}, ...]}`

El frontend lo consume para hidratar `META_REDES` (en vez de hardcodear los
topes en `meta.ts`); asi el unico lugar donde se editan los limites es el backend
(`limites_plataforma.LIMITES`, de donde tambien los toma `redes.py`).

Solo lectura, sin estado: devuelve datos puros del catalogo de redes + su tope.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import limites_plataforma, redes


async def listar(request: Request) -> Response:
    """`GET /api/limites` -> limites de caracteres por red, en orden fijo.

    Reune el `id`/`nombre` de `redes` con el `limite` canonico de
    `limites_plataforma`, garantizando una sola fuente para el tope.
    """
    limites = [
        {"id": r.id, "nombre": r.nombre, "limite": limites_plataforma.limite_de(r.id)}
        for r in redes.REDES
    ]
    return JSONResponse({"limites": limites})


RUTAS = [
    Route("/api/limites", listar, methods=["GET"]),
]
