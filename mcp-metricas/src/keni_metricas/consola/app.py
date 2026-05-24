"""App Starlette de la Consola Keni (capa de gestion web LOCAL).

Arquitectura de FEATURES auto-descubiertas: cada pestana de la consola vive en su
propio modulo dentro de `consola/features/` y exporta una variable `FEATURE` (ver
el contrato documentado en `consola/features/__init__.py`). Esta app NO conoce las
pestanas concretas: las descubre, ordena su nav por `orden`, y monta sus rutas y
sus estaticos. Anadir una pestana = soltar UN archivo en `features/`, sin tocar
este `app.py`.

HTML renderizado en servidor con el cascaron compartido (`consola.layout`); CSS/JS
servidos por la app (sin CDN, sin red externa). Bind SOLO a 127.0.0.1 (ver
`__main__.py`).

SEGURIDAD (resumen): el guardado de CLAUDE.md y el "abrir en Claude Code" SOLO
operan sobre carpetas presentes en consola.toml (allowlist por id estable); sin
shell=True; los errores salen como mensajes en espanol (sin tracebacks crudos).
"""

from __future__ import annotations

from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse, Response
from starlette.routing import Route

from . import features, proyectos
from .features import RecursoEstatico

_DIR_ESTATICOS = Path(__file__).parent / "estaticos"

# Estaticos compartidos que el layout incluye SIEMPRE (no son de ninguna feature).
_ESTATICOS_COMPARTIDOS = (
    RecursoEstatico("consola.css", _DIR_ESTATICOS / "consola.css", "text/css; charset=utf-8"),
    RecursoEstatico("consola.js", _DIR_ESTATICOS / "consola.js", "application/javascript; charset=utf-8"),
)


def _servir_estatico(recurso: RecursoEstatico):
    """Devuelve un handler que sirve un archivo estatico desde disco (404 si falta)."""

    async def handler(request: Request) -> Response:
        try:
            texto = recurso.ruta.read_text(encoding="utf-8")
        except OSError:
            return PlainTextResponse("No encontrado", status_code=404)
        return Response(texto, media_type=recurso.media_type)

    return handler


def _ruta_estatica(recurso: RecursoEstatico) -> Route:
    return Route(f"/estaticos/{recurso.nombre}", _servir_estatico(recurso))


def crear_app(abrir=None) -> Starlette:
    """Construye la app Starlette de la consola descubriendo las features.

    `abrir`: funcion opcional `(Path) -> str` para lanzar Claude Code; por defecto
    la real. Los tests pasan un mock; se inyecta en la feature Proyectos.
    """
    if abrir is not None:
        # La feature Proyectos expone un punto inyectable a nivel de modulo.
        from .features import proyectos as feat_proyectos

        feat_proyectos.abrir_en_claude_code = abrir

    # Aseguramos que existe el consola.toml (best-effort; no rompe si falla).
    try:
        proyectos.crear_config_si_falta()
    except OSError:
        pass

    descubiertas = features.descubrir(refresco=True)

    rutas: list[Route] = []

    # Raiz -> landing por defecto. Apuntamos a "skills" (Generar copy), que es lo
    # que un CM usa a diario, en vez de a la primera feature por orden. Si esa
    # feature no estuviera, caemos a la primera descubierta. Sin features, una
    # pagina minima.
    if descubiertas:
        ids = {f.id for f in descubiertas}
        destino = "/skills" if "skills" in ids else f"/{descubiertas[0].id}"

        async def raiz(request: Request) -> Response:
            return RedirectResponse(url=destino)
    else:
        async def raiz(request: Request) -> Response:
            return PlainTextResponse("No hay features registradas en la consola.", status_code=200)

    rutas.append(Route("/", raiz))

    # Estaticos compartidos.
    for recurso in _ESTATICOS_COMPARTIDOS:
        rutas.append(_ruta_estatica(recurso))

    # Rutas y estaticos de cada feature.
    estaticos_vistos: set[str] = {r.nombre for r in _ESTATICOS_COMPARTIDOS}
    for feature in descubiertas:
        rutas.extend(feature.rutas)
        for recurso in feature.estaticos:
            if recurso.nombre in estaticos_vistos:
                continue  # ya servido (compartido u otra feature): no duplicar
            estaticos_vistos.add(recurso.nombre)
            rutas.append(_ruta_estatica(recurso))

    return Starlette(routes=rutas)
