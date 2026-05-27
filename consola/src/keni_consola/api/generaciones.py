"""API Generaciones: sondeo de los trabajos de IA en segundo plano.

Toda generacion (copy, RSS->copy, hashtags, imagen) se lanza desde su endpoint de
siempre (`/api/skills/ejecutar`, `/api/rss/generar`, `/api/hashtags/sugerir`,
`/api/media/generar`), que ahora responde de INMEDIATO con un registro de generacion
`{estado: "ejecutando"}` en vez de bloquear. El frontend SONDEA aqui hasta el estado
terminal:

  - `GET /api/generaciones`         -> listado reciente (para una vista de actividad).
  - `GET /api/generaciones/{id}`    -> una generacion (estado + salida en vivo + metricas
                                       + `resultado` cuando completa). 404 si no existe.

La logica vive en el dominio `consola.generaciones`; aqui solo se serializa a JSON.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import generaciones
from .._http_json import envoltura_paginacion, paginacion_query


async def listar(request: Request) -> Response:
    """Generaciones recientes (recientes primero) con paginacion.

    Envelope RETROCOMPATIBLE: mantiene la clave `generaciones` y AÑADE `paginacion`.
    Sin `?limite=`, preserva el comportamiento previo (las N mas recientes, def 50) con
    un `total` exacto; con `?limite=&desplazamiento=` pagina el conjunto completo.
    """
    limite, desplazamiento = paginacion_query(request)
    if limite is None:
        # Sin parametros: comportamiento previo (las `_LISTADO_MAX` mas recientes).
        items = generaciones.listar()
    else:
        items = generaciones.listar(limite=limite, desplazamiento=desplazamiento)
    total = generaciones.contar()
    return JSONResponse(
        {
            "generaciones": items,
            "paginacion": envoltura_paginacion(total, limite, desplazamiento),
        }
    )


async def obtener(request: Request) -> Response:
    """Una generacion por id. -> `{generacion}` | 404 si no existe."""
    gen_id = request.path_params.get("generacion_id")
    generacion = generaciones.obtener(gen_id)
    if generacion is None:
        return JSONResponse({"error": "No se encontró esa generación."}, status_code=404)
    return JSONResponse({"generacion": generacion})


RUTAS = [
    Route("/api/generaciones", listar, methods=["GET"]),
    Route("/api/generaciones/{generacion_id}", obtener, methods=["GET"]),
]
