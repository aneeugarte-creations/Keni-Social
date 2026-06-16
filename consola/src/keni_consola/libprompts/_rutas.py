"""Localización de la raíz del almacén + validación/resolución de ids de documento.

SEGURIDAD: el id se valida contra traversal (segmentos `[a-z0-9-]`, primer segmento =
tipo válido, sin `..`); las rutas se resuelven y se comprueba que caen ESTRICTAMENTE
dentro de `raiz()`.
"""

from __future__ import annotations

from pathlib import Path

from .. import config, rutas
from ._comun import TIPOS, PromptsError, _segmentos_validos

__all__ = [
    "raiz",
    "migrar_dir_legacy",
    "_ruta_de_id",
    "_id_de_ruta",
    "_carpeta_relativa",
    "_id_unico",
]


def raiz() -> Path:
    """Dir raiz del almacen de prompts.

    Preferencia: env `KENI_PROMPTS_DIR` (lo usan los tests con un tmp) ->
    `rutas.dir_config()/prompts` (bajo `KENI_DATA_DIR` en contenedor; `~/.config/
    keni-social/prompts` en local).
    """
    override = config.prompts_dir()
    if override is not None:
        return override
    return rutas.dir_config() / "prompts"


def migrar_dir_legacy() -> bool:
    """Renombra el almacén existente si es necesario (idempotente).

    Solo actúa si existe un directorio legacy (`texto` o, más antiguo, `biblioteca`) y aún
    no el nuevo (`prompts`), y no hay override por env. Devuelve True si renombró.
    """
    if config.prompts_dir() is not None:
        return False
    nuevo = rutas.dir_config() / "prompts"
    if nuevo.exists():
        return False
    for nombre_legacy in ("texto", "biblioteca"):
        viejo = rutas.dir_config() / nombre_legacy
        if viejo.is_dir():
            viejo.rename(nuevo)
            return True
    return False


def _ruta_de_id(doc_id: str) -> Path:
    """Resuelve `<raiz>/<id>.md` garantizando que cae ESTRICTAMENTE dentro de la raiz.

    El id debe ser una ruta POSIX relativa cuyo PRIMER segmento es un `tipo` valido y el
    resto son slugs. Lanza `PromptsError` si el id es invalido o se escapa de la raiz.
    """
    if not isinstance(doc_id, str) or not doc_id.strip():
        raise PromptsError("Identificador de documento no válido.")
    partes = doc_id.strip().strip("/").split("/")
    if len(partes) < 2 or partes[0] not in TIPOS or not _segmentos_validos(partes):
        raise PromptsError("Identificador de documento no válido.")
    base = raiz().resolve()
    destino = base.joinpath(*partes).with_suffix(".md").resolve()
    # Defensa en profundidad: el destino debe colgar de la raiz (nunca de `..`).
    if base not in destino.parents:
        raise PromptsError("Ruta de documento fuera del almacén.")
    return destino


def _id_de_ruta(ruta: Path) -> str:
    """Id (ruta relativa posix sin extension) de un `.md` bajo la raiz."""
    rel = ruta.resolve().relative_to(raiz().resolve())
    return rel.with_suffix("").as_posix()


def _carpeta_relativa(tipo: str, carpeta: str) -> list[str]:
    """Valida y trocea `carpeta` (subruta bajo el tipo); [] para la raiz del tipo."""
    carpeta = (carpeta or "").strip().strip("/")
    if not carpeta:
        return []
    partes = carpeta.split("/")
    if not _segmentos_validos(partes):
        raise PromptsError("Nombre de carpeta no válido (usa minúsculas, dígitos y guiones).")
    return partes


def _id_unico(tipo: str, partes_carpeta: list[str], slug: str) -> tuple[str, Path]:
    """Devuelve (id, ruta) libres para `tipo/carpeta/slug`, anadiendo `-2`, `-3`… si choca."""
    base = raiz()
    candidato = slug
    n = 2
    while True:
        ruta = base.joinpath(tipo, *partes_carpeta, candidato + ".md")
        if not ruta.exists():
            doc_id = ruta.resolve().relative_to(base.resolve()).with_suffix("").as_posix()
            return doc_id, ruta
        candidato = f"{slug}-{n}"
        n += 1
