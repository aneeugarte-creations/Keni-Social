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

# Versión de la herramienta local que sirve este lanzador. Es la fuente de verdad del
# auto-update: la app local compara su versión contra esta y se actualiza si va por detrás.
VERSION = "0.2.0"

# Changelog corto (2-3 líneas) de la versión actual; se muestra en la ficha de la página.
CHANGELOG = [
    "App de escritorio: elige la carpeta, nombra el partido y procesa con un clic.",
    "Copia o descarta fotos y ráfagas (a la Papelera, recuperable) desde la galería.",
    "Detecta Claude y se mantiene actualizada sola.",
]

# Prompt que el equipo pega en su Claude local tras descomprimir el bundle. El Claude local NO
# procesa fotos: su único trabajo es COMPILAR y LANZAR la app; la propia app guía a la persona.
PROMPT_CLAUDE = (
    "Eres el agente local de keni-fotos. Tu ÚNICO trabajo es compilar y lanzar la app: "
    "lee el CLAUDE.md de esta carpeta y déjala abierta en el navegador. NO proceses fotos "
    "tú; la propia app guía a la persona para elegir la carpeta del partido, ponerle nombre "
    "y ejecutar el etiquetado. Cuando la app esté abierta, avísame."
)

# Comandos para descomprimir y arrancar, en orden. `ls -t … | head -1` coge el zip más reciente,
# así funciona aunque el navegador lo guarde como «keni-fotos (1).zip», «(2)», etc.
COMANDOS = [
    "cd ~/Downloads",
    'unzip -o "$(ls -t keni-fotos*.zip | head -1)"',
    "cd keni-fotos && claude",
]

# Pasos 1·2·3 que guían a la persona desde la descarga hasta tener la app abierta.
INSTRUCCIONES = [
    "Descarga keni-fotos y descomprímelo (los comandos de abajo lo hacen por ti).",
    "Abre Claude Code en la carpeta keni-fotos y pega el prompt: compila y lanza la app.",
    "En la app: elige tu carpeta de fotos, ponle nombre al partido y pulsa Procesar.",
]

# Dos artefactos descargables (Content-Disposition attachment):
#  - keni-fotos-app.zip : la app de escritorio (.app), vía principal de la página ("Descargar app").
#  - keni-fotos.zip     : el payload/bundle, que el .app baja para AUTO-ACTUALIZARSE y que también
#                         usa el modo avanzado (Claude). Ambos viven en `_fotos_bundle/`.
_NOMBRE_APP = "keni-fotos-app.zip"
_NOMBRE_BUNDLE = "keni-fotos.zip"
_DIR_BUNDLE = Path(__file__).parent / "_fotos_bundle"
_APP_DEFECTO = _DIR_BUNDLE / _NOMBRE_APP
_BUNDLE_DEFECTO = _DIR_BUNDLE / _NOMBRE_BUNDLE


def _ruta_app() -> Path:
    """Ruta del .app zipeado: `KENI_FOTOS_APP` si está definida, si no la de por defecto."""
    env = (os.environ.get("KENI_FOTOS_APP") or "").strip()
    return Path(env) if env else _APP_DEFECTO


def _ruta_bundle() -> Path:
    """Ruta del zip a servir: `KENI_FOTOS_BUNDLE` si está definida, si no la de por defecto."""
    env = (os.environ.get("KENI_FOTOS_BUNDLE") or "").strip()
    return Path(env) if env else _BUNDLE_DEFECTO


async def info(request: Request) -> Response:
    """GET /api/fotos/info: el texto del lanzador (prompt, comandos y pasos) + la versión."""
    return JSONResponse(
        {
            "version": VERSION,
            "changelog": CHANGELOG,
            "prompt_claude": PROMPT_CLAUDE,
            "comandos": COMANDOS,
            "instrucciones": INSTRUCCIONES,
        }
    )


def _servir_zip(ruta: Path, nombre: str) -> Response:
    """Sirve un zip como descarga, o 404 con mensaje si aún no está colocado."""
    if not ruta.is_file():
        return JSONResponse(
            {"error": "La herramienta keni-fotos aún no está disponible para descargar."},
            status_code=404,
        )
    return FileResponse(ruta, media_type="application/zip", filename=nombre)


async def app_descarga(request: Request) -> Response:
    """GET /api/fotos/app: descarga la app de escritorio `keni-fotos-app.zip` (.app)."""
    return _servir_zip(_ruta_app(), _NOMBRE_APP)


async def bundle(request: Request) -> Response:
    """GET /api/fotos/bundle: el payload `keni-fotos.zip` (auto-update del .app + modo avanzado)."""
    return _servir_zip(_ruta_bundle(), _NOMBRE_BUNDLE)


RUTAS = [
    Route("/api/fotos/info", info, methods=["GET"]),
    Route("/api/fotos/app", app_descarga, methods=["GET"]),
    Route("/api/fotos/bundle", bundle, methods=["GET"]),
]
