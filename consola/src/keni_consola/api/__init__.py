"""Contrato de MODULOS DE API de la Consola Keni + auto-descubrimiento.

================================================================================
PARA QUIEN ANADE UN MODULO DE API NUEVO (leeme entero, esto es el contrato)
================================================================================

La consola es ahora una API JSON pura consumida por un SPA React (que construye
otra persona). Cada area funcional (estado, config, proyectos, ...) vive en su
propio modulo dentro de `consola/api/` y exporta una variable de modulo llamada
exactamente `RUTAS`: una secuencia de `starlette.routing.Route` con sus paths
definitivos (todos bajo `/api/...`). `app.py` NO conoce los modulos concretos:
los descubre (con `pkgutil.iter_modules` sobre este paquete) y monta sus `RUTAS`.

Anadir un area = soltar UN archivo `consola/api/<area>.py` con su `RUTAS`, sin
tocar `app.py`.

REGLAS:
  - Tus rutas deben vivir bajo `/api/...` (la app sirve el SPA en todo lo demas).
  - Devuelve SIEMPRE JSON (salvo descargas con su media type + Content-Disposition).
  - Los errores salen como `{"error": "<mensaje en espanol>"}` con status 4xx/5xx,
    nunca un traceback crudo.
  - No dupliques validaciones: reutiliza `consola.proyectos`, `consola.marcas`,
    `consola.lanzador`, `consola.db` y el paquete `keni_metricas`.

QUE EXPORTA TU MODULO:

    # consola/api/ejemplo.py
    from __future__ import annotations
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response
    from starlette.routing import Route

    async def _algo(request: Request) -> Response:
        return JSONResponse({"ok": True})

    RUTAS = [Route("/api/ejemplo", _algo)]

================================================================================
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from collections.abc import Sequence

from starlette.routing import Route

_log = logging.getLogger("keni_consola.api")

# Cache del descubrimiento (los modulos solo se importan una vez). `crear_app` lo
# reusa; los tests pueden forzar un redescubrimiento con `descubrir(refresco=True)`.
_cache: list[Route] | None = None


def descubrir(refresco: bool = False) -> list[Route]:
    """Auto-descubre los modulos de `consola/api/` y devuelve todas sus `RUTAS`.

    Cada submodulo (no `_`-privado) que exporte una secuencia `RUTAS` aporta sus
    rutas. Los modulos sin `RUTAS` (helpers) se ignoran. El orden es determinista:
    por nombre de modulo y, dentro de un modulo, el orden declarado.
    """
    global _cache
    if _cache is not None and not refresco:
        return _cache

    rutas: list[Route] = []
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda i: i.name):
        if info.name.startswith("_"):
            continue
        try:
            modulo = importlib.import_module(f"{__name__}.{info.name}")
        except ImportError as e:
            # Un modulo listado por `iter_modules` puede no poder importarse: lo mas comun es
            # una CARRERA en tests (un fichero temporal en `api/` que otro worker xdist borro
            # entre el escaneo y el import; ver test_app). Tambien un modulo a medio escribir.
            # No debe tumbar el arranque de toda la app: lo saltamos con aviso, no crasheamos.
            _log.warning("api.descubrir: omito el modulo '%s' (no importable): %s", info.name, e)
            continue
        crudas = getattr(modulo, "RUTAS", None)
        if crudas is None:
            continue  # submodulo helper, no aporta rutas
        if not isinstance(crudas, Sequence):
            raise TypeError(
                f"El modulo de API '{info.name}' debe exportar RUTAS como una "
                f"secuencia de Route (encontrado: {type(crudas).__name__})."
            )
        for r in crudas:
            if not isinstance(r, Route):
                raise TypeError(
                    f"El modulo de API '{info.name}' exporta en RUTAS algo que no es "
                    f"un Route: {type(r).__name__}."
                )
            rutas.append(r)

    _cache = rutas
    return _cache
