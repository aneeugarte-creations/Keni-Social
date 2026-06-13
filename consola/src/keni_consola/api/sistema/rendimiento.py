"""Rendimiento de la API del panel de ADMIN (agregador en memoria de `rendimiento.py`).

GET /api/sistema/rendimiento: snapshot del agregador EN MEMORIA del proceso back.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ._comun import _es_admin, _rechazo_no_admin


async def rendimiento_api(request: Request) -> Response:
    """Latencias agregadas por ruta (solo admin): n, 5xx, p50/p95/max del TTFB.

    Snapshot del agregador EN MEMORIA del proceso back (ventana deslizante de las
    ultimas 256 peticiones por ruta normalizada; se reinicia con cada deploy).
    """
    if not _es_admin(request):
        return _rechazo_no_admin()
    from ... import rendimiento

    return JSONResponse(rendimiento.resumen())
