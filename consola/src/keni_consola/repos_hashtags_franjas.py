"""Repositorio — dominio hashtags_franjas. Implementación de repos.py (ver barrel `repos.py`)."""
from __future__ import annotations

from ._repos_comun import (
    Any,
    db,
)

# --------------------------------------------------------------------------- #
# Grupos de hashtags (OPERACIONAL: Postgres via db.py; rezago cerrado, ADR 0006) #
# --------------------------------------------------------------------------- #
# CONTENIDO editorial reutilizable que vivia file-backed (YAML + indice SQLite de rutas
# absolutas). El indice se desincronizaba al recrear contenedores; ahora vive en Postgres
# (ADR 0006). El dict devuelto conserva las mismas claves; la fachada delega 1:1 en db.py.


def listar_grupos_hashtags(
    *, limite: int | None = None, desplazamiento: int | None = None
) -> list[dict[str, Any]]:
    return db.listar_grupos_hashtags(limite=limite, desplazamiento=desplazamiento)


def contar_grupos_hashtags() -> int:
    return db.contar_grupos_hashtags()


def obtener_grupo_hashtags(grupo_id: str) -> dict[str, Any] | None:
    return db.obtener_grupo_hashtags(grupo_id)


def crear_grupo_hashtags(
    nombre: str, marca: str = "", hashtags: list[str] | None = None
) -> dict[str, Any]:
    return db.crear_grupo_hashtags(nombre, marca=marca, hashtags=hashtags)


def actualizar_grupo_hashtags(
    grupo_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_grupo_hashtags(grupo_id, campos)


def borrar_grupo_hashtags(grupo_id: str) -> bool:
    return db.borrar_grupo_hashtags(grupo_id)



# --------------------------------------------------------------------------- #
# Franjas editoriales (OPERACIONAL: Postgres via db.py; rezago cerrado, ADR 0006) #
# --------------------------------------------------------------------------- #


def listar_franjas() -> list[dict[str, Any]]:
    return db.listar_franjas()


def crear_franja(
    dia_semana: int, hora: str, marca: str = "", red: str = ""
) -> dict[str, Any]:
    return db.crear_franja(dia_semana, hora, marca=marca, red=red)


def borrar_franja(franja_id: str) -> bool:
    return db.borrar_franja(franja_id)


def listar_cadencias() -> list[dict[str, Any]]:
    return db.listar_cadencias()


def guardar_cadencia(
    *,
    marca: str,
    red: str,
    margen_min: int,
    hora_inicio: str,
    hora_fin: str,
    dias: list[int],
    activo: bool,
) -> dict[str, Any]:
    return db.guardar_cadencia(
        marca=marca,
        red=red,
        margen_min=margen_min,
        hora_inicio=hora_inicio,
        hora_fin=hora_fin,
        dias=dias,
        activo=activo,
    )


def borrar_cadencia(cadencia_id: str) -> bool:
    return db.borrar_cadencia(cadencia_id)
