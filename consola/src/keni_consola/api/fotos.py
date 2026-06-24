"""API HTTP de la app «Fotos» — el LANZADOR de la herramienta local keni-fotos.

Fotos no procesa imágenes en la nube: la consola no puede leer el disco del equipo de
Ale, así que esta superficie sirve para DESCARGAR la herramienta local (`keni-fotos.zip`)
y entregar el prompt + los comandos para montarla y ejecutarla con un Claude local sobre
la carpeta de fotos de un partido.

QUE VIVE AQUI
=============
  - `GET /api/fotos/info`    -> `{version, prompt_claude, comandos, instrucciones}`: el texto
                                que la página muestra para copiar (prompt de Claude, comandos y
                                pasos). Constantes legibles, fuente única de verdad del lanzador.
  - `GET /api/fotos/bundle`  -> descarga `keni-fotos.zip` (FileResponse, attachment). La ruta del
                                zip sale de la env `KENI_FOTOS_BUNDLE`; por defecto, el fichero
                                colocado junto a este módulo en `_fotos_bundle/keni-fotos.zip`. Si
                                falta (otro agente coloca el zip real), responde 404 claro, no casca.

App propia (`apps/fotos.toml`, modulos_backend=["fotos"]): sin cruces de frontera. SOLO LECTURA;
no encola nada ni publica. Errores como JSON `{"error": ...}` en español, sin tracebacks.
"""

from __future__ import annotations

import os
from pathlib import Path

from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Route

# Versión de la herramienta local que sirve este lanzador (informativa para la página).
VERSION = "0.1.0"

# Prompt que el equipo pega en su Claude local tras descomprimir el bundle: arranca al agente
# que monta y ejecuta keni-fotos sobre la carpeta del partido.
PROMPT_CLAUDE = (
    "Eres el agente local de keni-fotos. Lee el CLAUDE.md de esta carpeta y monta y "
    "ejecuta la app sobre mi carpeta de fotos del partido. Pregúntame la ruta de la "
    "carpeta y el nombre del partido si no te los doy."
)

# Comandos para montar y arrancar la herramienta, en orden (se copian tal cual a la terminal).
COMANDOS = [
    "unzip keni-fotos.zip && cd keni-fotos",
    "claude",
]

# Pasos 1·2·3 que guían a la persona desde la descarga hasta procesar sus fotos.
INSTRUCCIONES = [
    "Descarga keni-fotos.zip y descomprímelo en tu equipo.",
    "Abre Claude Code en la carpeta keni-fotos y pega el prompt de arriba.",
    "Indícale la ruta de tu carpeta de fotos del partido y su nombre.",
]

# Nombre del fichero que se ofrece al descargar (Content-Disposition attachment).
_NOMBRE_BUNDLE = "keni-fotos.zip"

# Ruta por defecto del zip: junto a este módulo, en `_fotos_bundle/keni-fotos.zip`. El zip real
# lo coloca otro agente; el directorio se versiona con un `.gitkeep` aunque el zip aún no exista.
_BUNDLE_DEFECTO = Path(__file__).parent / "_fotos_bundle" / _NOMBRE_BUNDLE


def _ruta_bundle() -> Path:
    """Ruta del zip a servir: `KENI_FOTOS_BUNDLE` si está definida, si no la de por defecto."""
    env = (os.environ.get("KENI_FOTOS_BUNDLE") or "").strip()
    return Path(env) if env else _BUNDLE_DEFECTO


async def info(request: Request) -> Response:
    """GET /api/fotos/info: el texto del lanzador (prompt, comandos y pasos) + la versión."""
    return JSONResponse(
        {
            "version": VERSION,
            "prompt_claude": PROMPT_CLAUDE,
            "comandos": COMANDOS,
            "instrucciones": INSTRUCCIONES,
        }
    )


async def bundle(request: Request) -> Response:
    """GET /api/fotos/bundle: descarga `keni-fotos.zip` (attachment). 404 si aún no está colocado."""
    ruta = _ruta_bundle()
    if not ruta.is_file():
        return JSONResponse(
            {"error": "La herramienta keni-fotos aún no está disponible para descargar."},
            status_code=404,
        )
    return FileResponse(
        ruta,
        media_type="application/zip",
        filename=_NOMBRE_BUNDLE,
    )


RUTAS = [
    Route("/api/fotos/info", info, methods=["GET"]),
    Route("/api/fotos/bundle", bundle, methods=["GET"]),
]
