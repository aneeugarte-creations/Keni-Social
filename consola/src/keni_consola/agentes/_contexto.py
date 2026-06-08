"""Contexto editorial del agente: `CLAUDE.md` principal y sub-contextos `contexto/*.md`.

  - CLAUDE.md (memoria principal): `leer_claude_md`, `guardar_claude_md`.
  - Sub-contextos: `_dir_contexto`, `_sanear_nombre_contexto`, `_resolver_contexto`,
    `listar_contextos`, `guardar_contexto`, `borrar_contexto`.

Toda escritura es DEFENSIVA (dentro de la carpeta del agente / de `contexto/`) y
ATOMICA; los nombres de sub-contexto se sanean (anti-traversal) antes de tocar disco.
"""

from __future__ import annotations

from pathlib import Path

from ._comun import (
    _DIR_CONTEXTO,
    _RE_NOMBRE_CONTEXTO,
    NombreContextoInvalido,
    _escribir_texto_atomico,
)
from ._genericos import carpeta_agente

__all__ = [
    "leer_claude_md",
    "guardar_claude_md",
    "_dir_contexto",
    "_sanear_nombre_contexto",
    "_resolver_contexto",
    "listar_contextos",
    "guardar_contexto",
    "borrar_contexto",
]


# --------------------------------------------------------------------------- #
# CLAUDE.md (contexto principal): lectura / escritura defensiva                #
# --------------------------------------------------------------------------- #


def leer_claude_md(marca_id: str) -> str:
    """Contenido del `CLAUDE.md` del agente (creandolo on-demand si falta)."""
    archivo = carpeta_agente(marca_id) / "CLAUDE.md"
    if archivo.is_file():
        return archivo.read_text(encoding="utf-8")
    return ""


def guardar_claude_md(marca_id: str, contenido: str) -> Path:
    """Escribe `<marca>/CLAUDE.md` de forma DEFENSIVA (dentro de la carpeta del agente)."""
    carpeta = carpeta_agente(marca_id)
    destino = (carpeta / "CLAUDE.md").resolve()
    if destino.parent != carpeta:
        raise ValueError("Ruta de destino fuera de la carpeta del agente.")
    _escribir_texto_atomico(destino, contenido)
    return destino


# --------------------------------------------------------------------------- #
# Sub-contextos: `*.md` dentro de `contexto/` (defensivo, anti-traversal)      #
# --------------------------------------------------------------------------- #


def _dir_contexto(marca_id: str) -> Path:
    """Sub-carpeta `contexto/` del agente (creada si falta)."""
    carpeta = carpeta_agente(marca_id) / _DIR_CONTEXTO
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def _sanear_nombre_contexto(nombre: str) -> str:
    """Valida/normaliza el nombre de un sub-contexto y devuelve su nombre de fichero.

    Solo `*.md`: si no trae extension se le anade `.md`; si trae `.md` se respeta.
    El nombre BASE (sin extension) se valida contra `_RE_NOMBRE_CONTEXTO` (letras,
    digitos, espacio, `.`, `_`, `-`, sin empezar/acabar en separador) para impedir
    traversal (`/`, `\\`, `..`), rutas absolutas y caracteres de control. Lanza
    `NombreContextoInvalido` (en espanol) ante cualquier nombre no permitido.
    """
    crudo = (nombre or "").strip()
    if not crudo:
        raise NombreContextoInvalido("El nombre del contexto no puede estar vacío.")
    if crudo.lower().endswith(".md"):
        base = crudo[:-3]
    else:
        base = crudo
    base = base.strip()
    # Rechaza separadores de ruta, `..`, control y nombres que escaparian.
    if not base or base in (".", "..") or not _RE_NOMBRE_CONTEXTO.match(base):
        raise NombreContextoInvalido(
            "El nombre del contexto solo puede tener letras, dígitos, espacios, '.', '_' o '-'."
        )
    return f"{base}.md"


def _resolver_contexto(marca_id: str, nombre: str) -> Path:
    """Ruta de un sub-contexto DENTRO de `contexto/` (defensa anti-traversal)."""
    carpeta = _dir_contexto(marca_id)
    destino = (carpeta / _sanear_nombre_contexto(nombre)).resolve()
    base = carpeta.resolve()
    if destino.parent != base or not destino.is_relative_to(base):
        raise NombreContextoInvalido("El nombre del contexto saldría de la carpeta de contexto.")
    return destino


def listar_contextos(marca_id: str) -> list[dict[str, str]]:
    """Sub-contextos del agente: `[{nombre, contenido}]`, ordenados por nombre."""
    carpeta = carpeta_agente(marca_id) / _DIR_CONTEXTO
    if not carpeta.is_dir():
        return []
    salida: list[dict[str, str]] = []
    for ruta in sorted(carpeta.glob("*.md")):
        if not ruta.is_file():
            continue
        try:
            contenido = ruta.read_text(encoding="utf-8")
        except OSError:
            continue
        salida.append({"nombre": ruta.name, "contenido": contenido})
    return salida


def guardar_contexto(marca_id: str, nombre: str, contenido: str) -> Path:
    """Escribe un sub-contexto `*.md` (saneado) DENTRO de `contexto/` (atomico)."""
    destino = _resolver_contexto(marca_id, nombre)
    _escribir_texto_atomico(destino, contenido)
    return destino


def borrar_contexto(marca_id: str, nombre: str) -> bool:
    """Borra un sub-contexto; True si existia, False si no. Saneado y defensivo."""
    destino = _resolver_contexto(marca_id, nombre)
    if not destino.is_file():
        return False
    destino.unlink(missing_ok=True)
    return True
