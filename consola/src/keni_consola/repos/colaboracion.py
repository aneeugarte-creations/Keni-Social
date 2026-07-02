"""Repositorio — dominio colaboracion. Implementación de repos.py (ver barrel `repos.py`)."""
from __future__ import annotations

from ._comun import (
    Any,
    db,
)

# --------------------------------------------------------------------------- #
# Ola COLABORACION: comentarios + versiones de copy + aprobacion multinivel    #
# --------------------------------------------------------------------------- #
# Tres familias APENDIDAS al tablero de contenido (Planable-style). La fachada solo
# delega en `db.py`; la validacion y la logica de cadena viven en la API/dominio.


def crear_comentario(
    *,
    publicacion_id: str,
    pieza_id: str = "",
    texto: str,
    autor: dict[str, str] | None = None,
    menciones: list[str] | None = None,
) -> dict[str, Any]:
    return db.crear_comentario(
        publicacion_id=publicacion_id,
        pieza_id=pieza_id,
        texto=texto,
        autor=autor,
        menciones=menciones,
    )


def listar_comentarios(
    publicacion_id: str, pieza_id: str | None = None
) -> list[dict[str, Any]]:
    return db.listar_comentarios(publicacion_id, pieza_id)


def obtener_comentario(comentario_id: str) -> dict[str, Any] | None:
    return db.obtener_comentario(comentario_id)


def comentarios_sin_resolver(publicacion_id: str, pieza_id: str = "") -> int:
    """Cuenta los comentarios SIN resolver que afectan a una pieza (item B).

    Un comentario afecta a la pieza si es del item entero (`pieza_id`="") o de ESTA
    plataforma concreta. Un hilo sin resolver es una objecion editorial pendiente: bloquea
    publicar (gate en `api/aprobacion.programar`) y la UI lo muestra como contador. Lectura
    sobre `publicacion_comentarios` (sin esquema nuevo).
    """
    if not publicacion_id:
        return 0
    sin_resolver = 0
    for c in db.listar_comentarios(publicacion_id):
        if c.get("resuelto"):
            continue
        pid = (c.get("pieza_id") or "").strip()
        if not pid or (pieza_id and pid == pieza_id):
            sin_resolver += 1
    return sin_resolver


def actualizar_comentario(
    comentario_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_comentario(comentario_id, campos)


def borrar_comentario(comentario_id: str) -> bool:
    return db.borrar_comentario(comentario_id)
