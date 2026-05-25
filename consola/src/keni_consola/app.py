"""App Starlette de la Consola Keni: API JSON pura + servir el SPA React.

Arquitectura de MODULOS DE API auto-descubiertos: cada area funcional vive en su
propio modulo dentro de `consola/api/` y exporta una variable `RUTAS` (ver el
contrato en `consola/api/__init__.py`). Esta app NO conoce los modulos concretos:
los descubre y monta sus rutas `/api/...`. Anadir un area = soltar UN archivo en
`api/`, sin tocar este `app.py`.

El resto (todo lo que NO empieza por `/api`) sirve el SPA React que construye otra
persona: `/assets/*` desde `webapp/assets/`, los favicons/recursos sueltos de
`webapp/`, y cualquier otra ruta devuelve `webapp/index.html` (fallback SPA). Si
`webapp/index.html` no existe todavia (caso normal en este worktree), devuelve un
placeholder amable en espanol (200).

Bind SOLO a 127.0.0.1 (ver `__main__.py`).

SEGURIDAD (resumen): el guardado de CLAUDE.md y el "abrir en Claude Code" SOLO
operan sobre carpetas presentes en consola.toml (allowlist por id estable); sin
shell=True; SQL parametrizado; los errores salen como JSON en espanol (sin
tracebacks crudos).
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response
from starlette.routing import Route

from . import api, proyectos

# Carpeta donde el build del frontend deja el SPA (no existe aun en este worktree).
_DIR_WEBAPP = Path(__file__).parent / "webapp"
_INDICE_SPA = _DIR_WEBAPP / "index.html"
_DIR_ASSETS = _DIR_WEBAPP / "assets"

# Archivos sueltos de la RAIZ de webapp/ que el SPA puede pedir (favicon, manifest,
# robots...). SOLO estos nombres conocidos se sirven desde la raiz: cualquier otra
# cosa cae al index del SPA, de modo que un archivo ajeno colocado en webapp/ nunca
# se sirve por error (defensa en profundidad, ademas del anti-traversal).
_ARCHIVOS_RAIZ = frozenset(
    {
        "favicon.ico",
        "favicon.svg",
        "favicon.png",
        "apple-touch-icon.png",
        "manifest.webmanifest",
        "site.webmanifest",
        "robots.txt",
    }
)

# Placeholder amable cuando aun no hay build del frontend (caso normal aqui).
_PLACEHOLDER = (
    "<!DOCTYPE html><html lang='es'><head><meta charset='utf-8'>"
    "<title>Consola Keni</title></head><body>"
    "<main style='font-family:system-ui,sans-serif;max-width:40rem;margin:4rem auto;padding:0 1rem'>"
    "<h1>Consola Keni</h1>"
    "<p>La interfaz aún no está construida; ejecuta el build del frontend.</p>"
    "</main></body></html>"
)


def _resolver_dentro(base: Path, sub: str) -> Path | None:
    """Resuelve `sub` DENTRO de `base`; None si escaparia (defensa anti-traversal)."""
    try:
        destino = (base / sub).resolve()
    except (OSError, ValueError):
        return None
    base_res = base.resolve()
    if destino == base_res or not destino.is_relative_to(base_res):
        return None
    return destino


async def _servir_asset(request: Request) -> Response:
    """Sirve un archivo estatico del SPA desde `webapp/assets/` (404 si no esta)."""
    sub = request.path_params["ruta"]
    destino = _resolver_dentro(_DIR_ASSETS, sub)
    if destino is None or not destino.is_file():
        return PlainTextResponse("No encontrado", status_code=404)
    return FileResponse(destino)


async def _servir_spa(request: Request) -> Response:
    """Fallback SPA: sirve `webapp/index.html` o un placeholder amable (200).

    Si la ruta pedida corresponde a un archivo suelto de `webapp/` (favicon, etc.)
    lo sirve; en cualquier otro caso devuelve el index del SPA (enrutado en cliente).
    """
    sub = (request.path_params.get("resto") or "").strip("/")
    # Solo servimos archivos sueltos de webapp/ cuyo nombre este en la allowlist
    # (favicon, manifest...). Cualquier otra ruta cae al index del SPA (enrutado en
    # cliente); asi un archivo plantado en webapp/ (p.ej. secreto.txt) jamas se sirve.
    if sub in _ARCHIVOS_RAIZ:
        candidato = _resolver_dentro(_DIR_WEBAPP, sub)
        if candidato is not None and candidato.is_file():
            tipo, _ = mimetypes.guess_type(str(candidato))
            return FileResponse(candidato, media_type=tipo or "application/octet-stream")

    if _INDICE_SPA.is_file():
        return FileResponse(_INDICE_SPA, media_type="text/html; charset=utf-8")
    return HTMLResponse(_PLACEHOLDER)


async def _api_no_encontrado(request: Request) -> Response:
    """Sub-ruta /api inexistente: 404 JSON en espanol (NO debe caer al SPA)."""
    return JSONResponse({"error": "Recurso no encontrado."}, status_code=404)


def crear_app(abrir=None, lanzar_run=None, lanzar_generacion=None, lanzar_imagen=None) -> Starlette:
    """Construye la app Starlette descubriendo las rutas de la API + el SPA.

    `abrir`: funcion opcional `(Path) -> str` para lanzar Claude Code (interactivo);
    por defecto la real. `lanzar_run`: funcion opcional
    `(marca_id, run_id, prompt, *, cwd) -> None` para lanzar runs headless en background.
    `lanzar_generacion`: funcion opcional `(gen_id, *, prompt, cwd, procesar, dir_temporal)`
    para lanzar trabajos de IA (copy/RSS/hashtags) en background. `lanzar_imagen`: funcion
    opcional `(gen_id, *, generar)` para trabajos de imagen. Por defecto todas son las
    reales (Popen/hilo/stream-json); los tests pasan mocks que NO tocan `claude` ni la red.
    """
    if abrir is not None or lanzar_run is not None:
        from .api import agentes as api_agentes

    if abrir is not None:
        from .api import proyectos as api_proyectos
        from .api import tareas as api_tareas

        api_proyectos.abrir_en_claude_code = abrir
        # Tareas usa su propio wrapper (con detalle como prompt). Lo envolvemos para
        # que tambien dependa del `abrir` inyectado, ignorando el detalle (mock simple).
        api_tareas.abrir_tarea_en_claude_code = lambda ruta, detalle="": abrir(ruta)
        # Agentes (runs interactivos) abre con `prompt=`; lo envolvemos para que use el
        # `abrir` inyectado ignorando el prompt (el mock simple solo recibe la ruta).
        api_agentes.abrir_en_claude_code = lambda ruta, prompt=None: abrir(ruta)

    if lanzar_run is not None:
        # Runs headless en background: inyectamos una fake que NO usa Popen ni red.
        api_agentes.lanzar_run_background = lanzar_run

    if lanzar_generacion is not None or lanzar_imagen is not None:
        from . import generaciones as gen_modulo

        if lanzar_generacion is not None:
            gen_modulo.lanzar_job_claude = lanzar_generacion
        if lanzar_imagen is not None:
            gen_modulo.lanzar_job_imagen = lanzar_imagen

    # Aseguramos que existe el consola.toml (best-effort; no rompe si falla).
    try:
        proyectos.crear_config_si_falta()
    except OSError:
        pass

    rutas: list[Route] = list(api.descubrir(refresco=True))

    # Cualquier OTRA sub-ruta /api (no descubierta) -> 404 JSON. Va despues de las
    # rutas reales y ANTES del fallback del SPA, para que un /api/... inexistente no
    # devuelva el index.html del SPA (que confundiria al cliente).
    rutas.append(Route("/api/{resto:path}", _api_no_encontrado))

    # Estaticos del SPA y fallback. Van DESPUES de las rutas /api para no taparlas.
    rutas.append(Route("/assets/{ruta:path}", _servir_asset))
    rutas.append(Route("/", _servir_spa))
    rutas.append(Route("/{resto:path}", _servir_spa))

    return Starlette(routes=rutas)
