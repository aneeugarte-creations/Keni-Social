"""Plantillas de `CLAUDE.md` del dominio AGENTES.

Cada agente arranca con un `CLAUDE.md` institucional renderizado desde una de estas
plantillas (por tipo de marca o por el `tipo` de un agente generico). Los ficheros
viven en `agentes/plantillas/` y traen un marcador de nombre que se sustituye al
renderizar.
"""

from __future__ import annotations

from pathlib import Path

_DIR_PLANTILLAS = Path(__file__).parent / "plantillas"

# Marcador de posicion del nombre dentro de las plantillas (.md).
_MARCADOR_NOMBRE = "{NOMBRE}"

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
    """Renderiza el CLAUDE.md de una plantilla, sustituyendo el nombre del agente."""
    texto = _leer_plantilla(plantilla_id)
    return texto.replace(_MARCADOR_NOMBRE, nombre)
