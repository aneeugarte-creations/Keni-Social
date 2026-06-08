"""Repositorio — dominio comercial. Implementación de repos.py (ver barrel `repos.py`)."""
from __future__ import annotations

from ._repos_comun import (
    Any,
    db,
)

# --------------------------------------------------------------------------- #
# Publicaciones comerciales (OPERACIONAL: Postgres via db.py; serie temporal)    #
# --------------------------------------------------------------------------- #
#
# El apartado comercial es una serie temporal append-only (snapshots de
# interacciones/alcance); no encaja en un fichero por entidad. La fachada delega 1:1
# en db.py.


def crear_publicacion_comercial(
    url: str = "",
    *,
    id_post_metricool: str = "",
    titulo: str = "",
    marca: str = "",
    cliente: str = "",
    campania: str = "",
    red: str = "",
    formato: str = "",
    metrica_objetivo: str = "interacciones",
    objetivo: int = 0,
    estado: str = "activa",
    publicado: str = "",
    notas: str = "",
) -> dict[str, Any]:
    return db.crear_publicacion_comercial(
        url,
        id_post_metricool=id_post_metricool,
        titulo=titulo,
        marca=marca,
        cliente=cliente,
        campania=campania,
        red=red,
        formato=formato,
        metrica_objetivo=metrica_objetivo,
        objetivo=objetivo,
        estado=estado,
        publicado=publicado,
        notas=notas,
    )


def listar_publicaciones_comerciales(
    estado: str | None = None,
    cliente: str | None = None,
    campania: str | None = None,
) -> list[dict[str, Any]]:
    return db.listar_publicaciones_comerciales(estado=estado, cliente=cliente, campania=campania)


def obtener_publicacion_comercial(publicacion_id: str) -> dict[str, Any] | None:
    return db.obtener_publicacion_comercial(publicacion_id)


def actualizar_publicacion_comercial(
    publicacion_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_publicacion_comercial(publicacion_id, campos)


def marcar_aviso_comercial(publicacion_id: str, ts: str) -> None:
    return db.marcar_aviso_comercial(publicacion_id, ts)


def borrar_publicacion_comercial(publicacion_id: str) -> bool:
    return db.borrar_publicacion_comercial(publicacion_id)


def registrar_snapshot_comercial(
    publicacion_id: str,
    ts: str,
    interacciones: int,
    alcance: int,
    visualizaciones: int = 0,
    *,
    granulares: dict[str, Any] | None = None,
) -> bool:
    return db.registrar_snapshot_comercial(
        publicacion_id, ts, interacciones, alcance, visualizaciones, granulares=granulares
    )


def listar_snapshots_comerciales(
    publicacion_id: str, *, limite: int | None = None
) -> list[dict[str, Any]]:
    return db.listar_snapshots_comerciales(publicacion_id, limite=limite)


def ultimo_snapshot_comercial(publicacion_id: str) -> dict[str, Any] | None:
    return db.ultimo_snapshot_comercial(publicacion_id)
