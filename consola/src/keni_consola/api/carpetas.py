"""API Carpetas: crea una carpeta de proyecto nueva dentro de una RAIZ permitida,
escribe un CLAUDE.md institucional (a partir de una plantilla) y la registra en
consola.toml reutilizando `consola.proyectos`.

SEGURIDAD (critica): la carpeta SOLO puede crearse DENTRO de una raiz permitida
(env `KENI_CONSOLA_RAIZ`, def `~/keni-proyectos`). El nombre que llega del cliente
se valida y la ruta final se resuelve con `Path.resolve()`; si no queda
estrictamente dentro de la raiz (intentos con `..`, rutas absolutas, nombres
peligrosos) se rechaza con 400 y un mensaje en espanol. Nunca se crea en una ruta
arbitraria. Sin shell.

Las plantillas viven ahora en `src/keni_consola/plantillas/` (movidas desde la
antigua carpeta de features al migrar a API JSON).
"""

from __future__ import annotations

from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import config, proyectos
from .._http_json import leer_json

# Las plantillas viven en el paquete (no en features/, que se elimino).
_DIR_PLANTILLAS = Path(__file__).parent.parent / "plantillas"

# Marcador de posicion del nombre dentro de las plantillas (.md).
_MARCADOR_NOMBRE = "{NOMBRE}"

# Caracteres prohibidos en el nombre de la carpeta (separadores, control, etc.).
_CARACTERES_PROHIBIDOS = set('/\\:*?"<>|')

# Cada entrada: id estable -> (etiqueta visible, archivo .md).
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


def raiz_permitida() -> Path:
    """Raiz dentro de la cual se pueden crear carpetas. `KENI_CONSOLA_RAIZ` la
    sobreescribe (tests/equipos); por defecto `~/keni-proyectos`.

    NOTA: este default es deliberadamente literal (`~/keni-proyectos`), NO
    `rutas.raiz_proyectos()`: aqui solo se valida el destino de creacion de carpetas
    desde la UI y nunca corre bajo `KENI_DATA_DIR`. Se preserva tal cual (no se unifica
    con `ficheros.raiz_datos`) para no cambiar comportamiento.
    """
    if (p := config.override_ruta(config.ENV_RAIZ)) is not None:
        return p.resolve()
    return (Path.home() / "keni-proyectos").resolve()


class NombreInvalido(ValueError):
    """El nombre de carpeta pedido no es valido o escaparia de la raiz permitida."""


def resolver_destino(nombre: str) -> Path:
    """Resuelve la carpeta destino DENTRO de la raiz permitida.

    Valida el nombre y garantiza que la ruta final cae estrictamente dentro de la
    raiz. Lanza `NombreInvalido` (en espanol) ante cualquier intento de escape.
    """
    crudo = (nombre or "").strip()
    if not crudo:
        raise NombreInvalido("El nombre de la carpeta no puede estar vacío.")

    # Rutas absolutas: prohibidas.
    if crudo.startswith(("/", "~")) or (len(crudo) >= 2 and crudo[1] == ":"):
        raise NombreInvalido("Usa solo un nombre de carpeta, no una ruta absoluta.")

    # `..` o `.` como componentes: intento de salir de la carpeta base. Se valida
    # ANTES que los caracteres prohibidos para dar el mensaje claro de escape.
    if crudo in (".", "..") or ".." in crudo:
        raise NombreInvalido(
            "El nombre no puede contener '..': no se permite salir de la carpeta base."
        )

    # Caracteres peligrosos: separadores de ruta, control, comodines.
    if any(c in _CARACTERES_PROHIBIDOS for c in crudo):
        raise NombreInvalido("El nombre tiene caracteres no permitidos (no uses / \\ : * ? etc.).")
    if any(ord(c) < 32 for c in crudo):
        raise NombreInvalido("El nombre tiene caracteres de control no permitidos.")

    raiz = raiz_permitida()
    destino = (raiz / crudo).resolve()

    # Defensa en profundidad: la ruta resuelta debe quedar DENTRO de la base y no
    # ser la base misma. `is_relative_to` cubre cualquier escape por symlink/`..`.
    if destino == raiz or not destino.is_relative_to(raiz):
        raise NombreInvalido("La carpeta quedaría fuera de la carpeta base permitida.")

    return destino


def crear_carpeta(nombre: str, plantilla_id: str) -> proyectos.Proyecto:
    """Crea la carpeta dentro de la raiz, escribe el CLAUDE.md de la plantilla y
    registra el proyecto en consola.toml (reutilizando `consola.proyectos`).

    Lanza `NombreInvalido`/`ValueError` (en espanol) si algo no es valido, y
    `OSError` si falla la escritura en disco. No usa shell.
    """
    destino = resolver_destino(nombre)
    if destino.exists():
        raise NombreInvalido("Ya existe una carpeta con ese nombre en la carpeta base.")

    raiz = raiz_permitida()
    raiz.mkdir(parents=True, exist_ok=True)
    destino.mkdir()

    contenido = render_claude_md(plantilla_id, destino.name)
    (destino / "CLAUDE.md").write_text(contenido, encoding="utf-8")

    return proyectos.anadir_proyecto(destino.name, str(destino))


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


async def opciones(request: Request) -> Response:
    """Raiz permitida + plantillas disponibles (para poblar el formulario del SPA)."""
    plantillas = [{"id": pid, "nombre": etiqueta} for pid, etiqueta in plantillas_disponibles()]
    return JSONResponse({"raiz": str(raiz_permitida()), "plantillas": plantillas})


async def crear(request: Request) -> Response:
    datos = await leer_json(request)
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


RUTAS = [
    Route("/api/carpetas", opciones, methods=["GET"]),
    Route("/api/carpetas", crear, methods=["POST"]),
]
