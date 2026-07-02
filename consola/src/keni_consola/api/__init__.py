"""Contrato de MODULOS DE API de la Consola Keni + auto-descubrimiento.

================================================================================
PARA QUIEN ANADE UN MODULO DE API NUEVO (leeme entero, esto es el contrato)
================================================================================

La consola es ahora una API JSON pura consumida por un SPA React (que construye
otra persona). Cada area funcional (estado, config, proyectos, ...) vive en su
propio modulo dentro de `consola/api/` y exporta una variable de modulo llamada
exactamente `RUTAS`: una secuencia de `starlette.routing.Route` (o `WebSocketRoute`
para un canal en vivo, p. ej. el túnel keni-fotos) con sus paths definitivos (todos bajo
`/api/...`). `app.py` NO conoce los modulos concretos: los descubre (con
`pkgutil.iter_modules` sobre este paquete) y monta sus `RUTAS`.

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

from starlette.routing import Route, WebSocketRoute

_log = logging.getLogger("keni_consola.api")

# Tipos de ruta admitidos en `RUTAS`: HTTP (`Route`) y, para los canales en vivo (el
# túnel keni-fotos), `WebSocketRoute`. Ambos son `starlette.routing.BaseRoute` y exponen
# `.path`; la app los monta igual.
_TIPOS_RUTA = (Route, WebSocketRoute)

# Cache del descubrimiento (los modulos solo se importan una vez). `crear_app` lo
# reusa; los tests pueden forzar un redescubrimiento con `descubrir(refresco=True)`.
# `_cache_por_modulo` conserva la atribucion ruta->modulo para los invariantes.
_cache: list[Route | WebSocketRoute] | None = None
_cache_por_modulo: list[tuple[str, Route | WebSocketRoute]] | None = None


def descubrir(refresco: bool = False) -> list[Route | WebSocketRoute]:
    """Auto-descubre los modulos de `consola/api/` y devuelve todas sus `RUTAS`.

    Cada submodulo (no `_`-privado) que exporte una secuencia `RUTAS` aporta sus
    rutas. Los modulos sin `RUTAS` (helpers) se ignoran. El orden es determinista:
    por nombre de modulo y, dentro de un modulo, el orden declarado.

    INVARIANTES ESTRUCTURALES (ver `problemas_invariantes`): tras montar, se verifica
    que ningun (path, metodo) este declarado dos veces (Starlette resuelve first-wins
    y la segunda ruta queda MUERTA en silencio) y que todo modulo con RUTAS figure en
    un manifest (`apps/<app>.toml`). Aqui cada problema se LOGUEA como ERROR pero no
    tumba el proceso: un deploy en marcha no debe caerse por una ruta sombreada que ya
    venia sirviendo; el fallo DURO lo da el test de CI que exige la lista vacia.
    """
    global _cache, _cache_por_modulo
    if _cache is not None and not refresco:
        return _cache

    por_modulo: list[tuple[str, Route | WebSocketRoute]] = []
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
            if not isinstance(r, _TIPOS_RUTA):
                raise TypeError(
                    f"El modulo de API '{info.name}' exporta en RUTAS algo que no es "
                    f"un Route/WebSocketRoute: {type(r).__name__}."
                )
            por_modulo.append((info.name, r))

    for problema in _problemas_invariantes(por_modulo):
        _log.error("api.descubrir: %s", problema)

    _cache_por_modulo = por_modulo
    _cache = [r for _, r in por_modulo]
    return _cache


def _problemas_invariantes(
    por_modulo: Sequence[tuple[str, Route | WebSocketRoute]],
) -> list[str]:
    """Invariantes estructurales del montaje: lista de problemas (vacia = todo bien).

    Verifica dos cosas, ambas invisibles en runtime si se rompen:
      1. RUTA DUPLICADA: dos rutas con el mismo (path, metodo) — Starlette monta la
         primera y la segunda queda muerta sin aviso. Las divisiones legitimas del
         mismo path por METODOS distintos (GET en un Route, POST en otro) no cuentan.
         El HEAD implicito de un GET se ignora para no reportar cada choque dos veces.
      2. MODULO SIN MANIFEST: un modulo que exporta RUTAS pero no figura en ningun
         `apps/<app>.toml` (modulos_backend) queda fuera del catalogo y del lint de
         fronteras (ADR 0005).
    """
    problemas: list[str] = []

    vistos: dict[tuple[str, str], str] = {}
    for modulo, ruta in por_modulo:
        if isinstance(ruta, Route):
            metodos = sorted((ruta.methods or {"GET"}) - {"HEAD"}) or ["HEAD"]
        else:
            metodos = ["WEBSOCKET"]
        for metodo in metodos:
            clave = (ruta.path, metodo)
            previo = vistos.get(clave)
            if previo is not None:
                problemas.append(
                    f"ruta duplicada: {metodo} {ruta.path} declarada en "
                    f"'{previo}' y '{modulo}' (Starlette monta la primera; la "
                    "segunda queda muerta)"
                )
            else:
                vistos[clave] = modulo

    try:
        from ..apps import registro  # perezoso: api/ no depende de apps/ al importarse

        mapa = registro.modulo_a_app()
    except Exception as e:  # noqa: BLE001 -- manifests ilegibles: problema, no crash
        problemas.append(f"no se pudo cargar el mapa modulo->app de los manifests: {e}")
        return problemas
    for modulo in sorted({m for m, _ in por_modulo}):
        if modulo not in mapa:
            problemas.append(
                f"el modulo 'api/{modulo}' exporta RUTAS pero no esta declarado en "
                "ningun manifest (apps/<app>.toml, clave modulos_backend)"
            )
    return problemas


def problemas_invariantes(refresco: bool = False) -> list[str]:
    """Problemas de invariantes del montaje ACTUAL (lista vacia = repo sano).

    Es la cara publica de `_problemas_invariantes` sobre el descubrimiento cacheado
    (o refrescado). El test de CI la exige vacia (fallo DURO); en produccion los
    mismos problemas salen como ERROR en el log de `descubrir` sin tumbar el boot.
    """
    descubrir(refresco=refresco)
    return _problemas_invariantes(_cache_por_modulo or [])
