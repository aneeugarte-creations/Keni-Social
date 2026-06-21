"""Utilidades COMUNES del dominio AGENTES: imports, excepciones, constantes y helpers.

Reune lo que comparten los submodulos (`_genericos`, `_contexto`, `_runs`):

  - Excepciones de dominio (en espanol) y constantes de layout/plantillas.
  - Localizacion de la raiz y resolucion de rutas anti-escape (`_raiz`,
    `_ruta_dentro_raiz`).
  - Plantillas de `CLAUDE.md` (delegan en `._plantillas`).
  - Escritura/lectura ATOMICA de texto y YAML (delega en `io_atomico`).
  - Utilidades de tiempo/id (`ahora_iso`, `nuevo_run_id`).

Nada aqui depende de los otros submodulos del paquete: es la capa base.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from keni_shared.esquema_yaml import migrar, sellar

from .. import marcas, repos
from ..io_atomico import escribir_atomico
from ..tiempo import ahora_iso
from ._plantillas import PLANTILLAS, render_claude_md
from ._rutas import NombreAgenteInvalido

# Loader RÁPIDO (libyaml) cuando está disponible: igual que en `generaciones._almacen`, parsear
# los YAML de los runs con el parser PURO costaba segundos en Actividad IA; CSafeLoader lo baja
# ~20×. API-compatible; cae al loader puro si no hay libyaml.
_YAML_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)

__all__ = [
    # imports re-exportados (paridad de superficie del modulo original)
    "Any",
    "Path",
    "annotations",
    "datetime",
    "escribir_atomico",
    "marcas",
    "migrar",
    "re",
    "repos",
    "sellar",
    "unicodedata",
    "uuid",
    "yaml",
    # excepciones
    "AgenteInvalido",
    "NombreAgenteInvalido",
    "AgenteExistente",
    "OperacionNoPermitida",
    "NombreContextoInvalido",
    # constantes
    "MODOS_RUN",
    "_ARCHIVO_MANIFIESTO",
    "_DIR_CONTEXTO",
    "_DIR_KENI",
    "_DIR_RUNS",
    "_PLANTILLA_DEF",
    "_PLANTILLA_GENERICA_DEF",
    "_PLANTILLA_POR_MARCA",
    "_RE_NOMBRE_CONTEXTO",
    # helpers
    "_raiz",
    "_ruta_dentro_raiz",
    "_render_claude_md",
    "_render_claude_md_generico",
    "_tipo_plantilla",
    "_escribir_texto_atomico",
    "_escribir_yaml_atomico",
    "_leer_yaml",
    "ahora_iso",
    "nuevo_run_id",
]

# --------------------------------------------------------------------------- #
# Plantilla de CLAUDE.md por marca                                             #
# --------------------------------------------------------------------------- #

# Mapa marca_id -> id de plantilla. Una marca sin entrada cae a la plantilla
# "general". Asi el CLAUDE.md inicial encaja con el tipo de la marca.
_PLANTILLA_POR_MARCA: dict[str, str] = {
    "unotv": "noticias",
    "claro-sports": "deportes",
    "piso-15": "podcast",
    "fundacion": "social",
}
_PLANTILLA_DEF = "general"

# Plantilla por defecto para un agente generico recien creado.
_PLANTILLA_GENERICA_DEF = "general"

# Sub-carpetas dentro de la carpeta del agente.
_DIR_CONTEXTO = "contexto"
_DIR_RUNS = "runs"

# Manifiesto de un agente GENERICO (lo que lo distingue de una carpeta cualquiera).
_DIR_KENI = ".keni"
_ARCHIVO_MANIFIESTO = "agente.yaml"

# Nombre de sub-contexto: base sin separadores/control, terminada en `.md`.
_RE_NOMBRE_CONTEXTO = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9 ._-]*[A-Za-z0-9])?$")

# Modos validos de un run.
MODOS_RUN: tuple[str, ...] = ("headless", "interactivo")


class AgenteInvalido(ValueError):
    """El id no resuelve a un agente conocido (marca o generico). Mensaje en espanol."""


class AgenteExistente(ValueError):
    """El slug derivado choca con una marca o con un agente generico ya registrado."""


class OperacionNoPermitida(ValueError):
    """Operacion no valida sobre el agente (p.ej. renombrar/borrar una marca)."""


class NombreContextoInvalido(ValueError):
    """El nombre de sub-contexto no es valido o escaparia de `contexto/`."""


# --------------------------------------------------------------------------- #
# Localizacion de la carpeta del agente (on-demand, validada contra el catalogo)#
# --------------------------------------------------------------------------- #


def _render_claude_md(marca_id: str) -> str:
    """Renderiza el CLAUDE.md inicial del agente desde su plantilla por tipo."""
    plantilla_id = _PLANTILLA_POR_MARCA.get(marca_id, _PLANTILLA_DEF)
    return render_claude_md(plantilla_id, marcas.etiqueta_de(marca_id))


def _raiz() -> Path:
    """Raiz resuelta donde viven TODOS los agentes (misma que `repos.raiz_datos`)."""
    return repos.raiz_datos().resolve()


def _ruta_dentro_raiz(slug: str) -> Path:
    """Resuelve `<raiz>/<slug>/` garantizando que cae ESTRICTAMENTE dentro de la raiz.

    Lanza `AgenteInvalido` si el slug intentara escapar (un `..`, separador, etc.) o
    si coincidiera con la propia raiz. Esta es la unica forma de construir la carpeta
    de un agente: ni marcas ni genericos esquivan esta comprobacion.
    """
    raiz = _raiz()
    carpeta = (raiz / slug).resolve()
    if carpeta == raiz or not carpeta.is_relative_to(raiz):
        raise AgenteInvalido("Agente no permitido o fuera de la carpeta base.")
    return carpeta


def _tipo_plantilla(tipo: object) -> str:
    """Normaliza el `tipo` a un id de plantilla valido (def 'general')."""
    if isinstance(tipo, str) and tipo in PLANTILLAS:
        return tipo
    return _PLANTILLA_GENERICA_DEF


def _render_claude_md_generico(tipo: str, nombre: str) -> str:
    """Renderiza el CLAUDE.md inicial de un generico desde la plantilla `tipo`."""
    return render_claude_md(tipo, nombre)


def nuevo_run_id() -> str:
    """Nuevo id de run (12 hex, mismo formato que `ficheros._nuevo_id`)."""
    return uuid.uuid4().hex[:12]


# --------------------------------------------------------------------------- #
# Escritura atomica (delega en `io_atomico.escribir_atomico`, util comun)      #
# --------------------------------------------------------------------------- #


def _escribir_texto_atomico(ruta: Path, contenido: str) -> None:
    """Escribe texto en `ruta` de forma ATOMICA (tmp en el mismo dir + os.replace)."""
    escribir_atomico(ruta, contenido)


def _escribir_yaml_atomico(ruta: Path, datos: dict[str, Any], *, tipo: str) -> None:
    """Escribe un dict como YAML legible de forma ATOMICA (tmp + os.replace).

    `sellar(tipo, ...)` estampa la `version` de esquema antes de volcar.
    """
    texto = yaml.safe_dump(
        sellar(tipo, datos),
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=4096,
    )
    _escribir_texto_atomico(ruta, texto)


def _leer_yaml(ruta: Path, *, tipo: str) -> dict[str, Any] | None:
    """Lee un YAML como dict, o None si no existe / esta corrupto / no es un mapa.

    `migrar(tipo, ...)` sube de version el dict legado en memoria.
    """
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        datos = yaml.load(texto, Loader=_YAML_LOADER)  # noqa: S506 -- loader SAFE (libyaml o puro)
    except yaml.YAMLError:
        return None
    if not isinstance(datos, dict):
        return None
    return migrar(tipo, datos)
