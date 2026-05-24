"""Feature Carpetas: crea una carpeta de proyecto nueva dentro de una RAIZ
permitida, escribe un CLAUDE.md institucional (a partir de una plantilla
editable) y la registra en consola.toml reutilizando `consola.proyectos`.

Filosofia: la consola da un PUNTO DE PARTIDA. El CLAUDE.md que se escribe es una
plantilla institucional pensada para que el equipo la edite, no un texto cerrado.

SEGURIDAD (critica): la carpeta SOLO puede crearse DENTRO de una raiz permitida
(env `KENI_CONSOLA_RAIZ`, def `~/keni-proyectos`). El nombre/subruta que llega
del navegador se valida y la ruta final se resuelve con `Path.resolve()`; si no
queda estrictamente dentro de la raiz (intentos con `..`, rutas absolutas,
nombres peligrosos) se rechaza con 400 y un mensaje en espanol. Nunca se crea en
una ruta arbitraria. Sin shell.
"""

from __future__ import annotations

import os
from html import escape
from pathlib import Path

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route

from .. import layout, proyectos
from . import Feature, RecursoEstatico, features_ordenadas

_ESTATICOS = Path(__file__).parent.parent / "estaticos"
_DIR_PLANTILLAS = Path(__file__).parent / "plantillas"

# Marcador de posicion del nombre dentro de las plantillas (.md).
_MARCADOR_NOMBRE = "{NOMBRE}"

# Caracteres prohibidos en el nombre de la carpeta (separadores, control, etc.).
_CARACTERES_PROHIBIDOS = set('/\\:*?"<>|')


# --------------------------------------------------------------------------- #
# Plantillas de CLAUDE.md                                                      #
# --------------------------------------------------------------------------- #


# Cada entrada: id estable (en URL/form) -> (etiqueta visible, archivo .md).
PLANTILLAS: dict[str, tuple[str, str]] = {
    "general": ("General", "claude-md-general.md"),
    "noticias": ("Marca de noticias", "claude-md-noticias.md"),
    "deportes": ("Marca de deportes", "claude-md-deportes.md"),
    "podcast": ("Podcast", "claude-md-podcast.md"),
    "social": ("Social / CSR", "claude-md-social.md"),
}

# Si una plantilla no se encuentra, caemos a este id por defecto.
_PLANTILLA_DEF = "general"


def plantillas_disponibles() -> list[tuple[str, str]]:
    """Lista [(id, etiqueta)] de plantillas, en orden estable para la UI."""
    return [(pid, etiqueta) for pid, (etiqueta, _archivo) in PLANTILLAS.items()]


def _leer_plantilla(plantilla_id: str) -> str:
    """Texto crudo de una plantilla por id (cae a la general si el id no existe)."""
    etiqueta_archivo = PLANTILLAS.get(plantilla_id) or PLANTILLAS[_PLANTILLA_DEF]
    archivo = _DIR_PLANTILLAS / etiqueta_archivo[1]
    return archivo.read_text(encoding="utf-8")


def render_claude_md(plantilla_id: str, nombre: str) -> str:
    """Renderiza el CLAUDE.md de una plantilla, sustituyendo el nombre del proyecto."""
    texto = _leer_plantilla(plantilla_id)
    return texto.replace(_MARCADOR_NOMBRE, nombre)


# --------------------------------------------------------------------------- #
# Raiz permitida + validacion de seguridad                                     #
# --------------------------------------------------------------------------- #


def raiz_permitida() -> Path:
    """Raiz dentro de la cual se pueden crear carpetas. `KENI_CONSOLA_RAIZ` la
    sobreescribe (tests/equipos); por defecto `~/keni-proyectos`."""
    if (p := os.environ.get("KENI_CONSOLA_RAIZ")):
        return Path(p).expanduser().resolve()
    return (Path.home() / "keni-proyectos").resolve()


class NombreInvalido(ValueError):
    """El nombre de carpeta pedido no es valido o escaparia de la raiz permitida."""


def resolver_destino(nombre: str) -> Path:
    """Resuelve la carpeta destino DENTRO de la raiz permitida.

    Valida el nombre y garantiza que la ruta final cae estrictamente dentro de la
    raiz. Lanza `NombreInvalido` (en espanol) ante cualquier intento de escape
    (rutas absolutas, `..`, separadores, nombres peligrosos).
    """
    crudo = (nombre or "").strip()
    if not crudo:
        raise NombreInvalido("El nombre de la carpeta no puede estar vacio.")

    # Rutas absolutas: prohibidas (la carpeta vive bajo la raiz, no fuera).
    if crudo.startswith(("/", "~")) or (len(crudo) >= 2 and crudo[1] == ":"):
        raise NombreInvalido("Usa solo un nombre de carpeta, no una ruta absoluta.")

    # Caracteres peligrosos: separadores de ruta, control, comodines.
    if any(c in _CARACTERES_PROHIBIDOS for c in crudo):
        raise NombreInvalido("El nombre tiene caracteres no permitidos (no uses / \\ : * ? etc.).")
    if any(ord(c) < 32 for c in crudo):
        raise NombreInvalido("El nombre tiene caracteres de control no permitidos.")

    # `..` o `.` como componentes: intento de salir de la raiz.
    if crudo in (".", "..") or ".." in crudo:
        raise NombreInvalido("El nombre no puede contener '..' ni intentar salir de la raiz.")

    raiz = raiz_permitida()
    destino = (raiz / crudo).resolve()

    # Defensa en profundidad: la ruta resuelta debe quedar DENTRO de la raiz y no
    # ser la raiz misma. `is_relative_to` cubre cualquier escape por symlink/`..`.
    if destino == raiz or not destino.is_relative_to(raiz):
        raise NombreInvalido("La carpeta quedaria fuera de la raiz permitida.")

    return destino


def crear_carpeta(nombre: str, plantilla_id: str) -> proyectos.Proyecto:
    """Crea la carpeta dentro de la raiz, escribe el CLAUDE.md de la plantilla y
    registra el proyecto en consola.toml (reutilizando `consola.proyectos`).

    Lanza `NombreInvalido`/`ValueError` (en espanol) si algo no es valido, y
    `OSError` si falla la escritura en disco. No usa shell.
    """
    destino = resolver_destino(nombre)
    if destino.exists():
        raise NombreInvalido("Ya existe una carpeta con ese nombre en la raiz.")

    raiz = raiz_permitida()
    raiz.mkdir(parents=True, exist_ok=True)
    destino.mkdir()

    contenido = render_claude_md(plantilla_id, destino.name)
    (destino / "CLAUDE.md").write_text(contenido, encoding="utf-8")

    # Registro en la allowlist reutilizando el helper compartido (valida que la
    # carpeta existe y no duplica). El nombre del proyecto = nombre de la carpeta.
    return proyectos.anadir_proyecto(destino.name, str(destino))


# --------------------------------------------------------------------------- #
# Render                                                                       #
# --------------------------------------------------------------------------- #


def _opciones_plantilla() -> str:
    opciones = []
    for pid, etiqueta in plantillas_disponibles():
        sel = " selected" if pid == _PLANTILLA_DEF else ""
        opciones.append(f'<option value="{escape(pid)}"{sel}>{escape(etiqueta)}</option>')
    return "".join(opciones)


def _pagina_carpetas() -> str:
    raiz = raiz_permitida()
    cuerpo = f"""
<h1>Nueva carpeta</h1>
<p class="intro">Crea una carpeta de proyecto nueva con un CLAUDE.md de partida.
La carpeta se crea SIEMPRE dentro de la raiz permitida y se registra en Proyectos.</p>
<form class="anadir" id="form-carpetas">
  <h2>Crear carpeta de proyecto</h2>
  <p class="ayuda">Por seguridad, la carpeta se crea dentro de esta raiz:
  <code>{escape(str(raiz))}</code>. Solo necesitas darle un nombre y elegir una plantilla
  de CLAUDE.md (un punto de partida que tu equipo puede editar despues).</p>
  <div class="campos">
    <label class="oculto-visual" for="carpetas-nombre">Nombre de la carpeta</label>
    <input id="carpetas-nombre" type="text" name="nombre" placeholder="nombre-del-proyecto" autocomplete="off" required>
    <label class="carpetas-label" for="carpetas-plantilla">Plantilla de CLAUDE.md
      <select id="carpetas-plantilla" name="plantilla">{_opciones_plantilla()}</select>
    </label>
    <button type="submit" class="primario">Crear carpeta</button>
  </div>
  <p class="estado" role="status" aria-live="polite" style="margin-top:8px"></p>
  <p class="carpetas-exito" role="status" aria-live="polite" hidden></p>
</form>
"""
    return layout.render_pagina(
        features=features_ordenadas(),
        activa=FEATURE.id,
        titulo="Nueva carpeta",
        contenido=cuerpo,
        css=FEATURE.css,
        js=FEATURE.js,
    )


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


async def pagina_carpetas(request: Request) -> Response:
    return HTMLResponse(_pagina_carpetas())


async def _leer_json(request: Request) -> dict:
    try:
        datos = await request.json()
    except Exception:  # noqa: BLE001 -- body invalido => dict vacio (se valida abajo)
        return {}
    return datos if isinstance(datos, dict) else {}


async def api_crear(request: Request) -> Response:
    datos = await _leer_json(request)
    nombre = datos.get("nombre")
    plantilla = datos.get("plantilla", _PLANTILLA_DEF)
    if not isinstance(nombre, str):
        return JSONResponse({"error": "Falta el nombre de la carpeta."}, status_code=400)
    if not isinstance(plantilla, str) or plantilla not in PLANTILLAS:
        plantilla = _PLANTILLA_DEF
    try:
        p = crear_carpeta(nombre, plantilla)
    except ValueError as e:  # incluye NombreInvalido
        return JSONResponse({"error": str(e)}, status_code=400)
    except OSError as e:
        return JSONResponse({"error": f"No se pudo crear la carpeta: {e}"}, status_code=400)
    return JSONResponse(
        {
            "mensaje": f"Carpeta {p.nombre} creada y registrada en Proyectos.",
            "ruta": str(p.ruta),
        }
    )


FEATURE = Feature(
    id="carpetas",
    etiqueta="Nueva carpeta",
    orden=50,
    descripcion="Crea una carpeta de proyecto con un CLAUDE.md de partida y la registra.",
    rutas=[
        Route("/carpetas", pagina_carpetas),
        Route("/api/carpetas/crear", api_crear, methods=["POST"]),
    ],
    estaticos=[
        RecursoEstatico("carpetas.css", _ESTATICOS / "carpetas.css", "text/css; charset=utf-8"),
        RecursoEstatico("carpetas.js", _ESTATICOS / "carpetas.js", "application/javascript; charset=utf-8"),
    ],
    css=["carpetas.css"],
    js=["carpetas.js"],
)
