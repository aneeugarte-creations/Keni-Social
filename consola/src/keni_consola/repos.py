"""Capa REPOSITORIO de la Consola Keni: fachada de persistencia.

Esta capa existe para DESACOPLAR los `api/*.py` del backend concreto de
persistencia. Re-exporta TODAS las funciones publicas con firmas IDENTICAS a
`db.py`; cada `api/*.py` consume SIEMPRE a traves de `repos`, sin saber que hay
debajo.

BACKENDS (conmutables con la env `KENI_CONSOLA_BACKEND`):
  - `ficheros` (DEFECTO): el CONTENIDO vive en ficheros YAML por marca
    (`ficheros.py`), con un indice SQLite regenerable (`indice.py`). Fuente de
    verdad = los YAML.
  - `sqlite`: el contenido vive en SQLite (`db.py`), comportamiento historico.

En AMBOS backends las `tareas` viven en SQLite (via `db.py`): se reencuadran en la
Ola 2b/Agentes; aqui la fachada de tareas delega SIEMPRE en `db.py`.

Uso en las features:

    from .. import repos

    repos.crear_publicacion(marca="unotv", red="x", titulo="Hola")
    repos.listar_franjas()
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from . import db, ficheros

# Constantes publicas (re-exportadas tal cual desde db; identicas en ambos backends).
ESTADOS_TAREA: tuple[str, ...] = db.ESTADOS_TAREA
ESTADOS_PUBLICACION: tuple[str, ...] = db.ESTADOS_PUBLICACION


def _backend():
    """Modulo de backend de CONTENIDO segun `KENI_CONSOLA_BACKEND` (def `ficheros`).

    Se resuelve en CADA llamada (no se cachea) para que los tests puedan conmutar
    el backend con `monkeypatch.setenv` sin reimportar el modulo.
    """
    elegido = (os.environ.get("KENI_CONSOLA_BACKEND") or "ficheros").strip().lower()
    return db if elegido == "sqlite" else ficheros


def ruta_db() -> Path:
    """Ruta del fichero SQLite (delega en `db.ruta_db`; las tareas siempre viven ahi)."""
    return db.ruta_db()


# --------------------------------------------------------------------------- #
# Tareas (SIEMPRE en SQLite via db.py, en ambos backends)                      #
# --------------------------------------------------------------------------- #


def listar_tareas() -> list[dict[str, Any]]:
    return db.listar_tareas()


def crear_tarea(proyecto_id: str, titulo: str, detalle: str = "") -> dict[str, Any]:
    return db.crear_tarea(proyecto_id, titulo, detalle)


def obtener_tarea(tarea_id: str) -> dict[str, Any] | None:
    return db.obtener_tarea(tarea_id)


def actualizar_estado_tarea(tarea_id: str, estado: str) -> dict[str, Any] | None:
    return db.actualizar_estado_tarea(tarea_id, estado)


def borrar_tarea(tarea_id: str) -> bool:
    return db.borrar_tarea(tarea_id)


# --------------------------------------------------------------------------- #
# Historial de skills                                                          #
# --------------------------------------------------------------------------- #


def registrar_historial_skill(
    skill: str,
    marca: str,
    resultado: str,
    *,
    piezas: list[dict[str, Any]] | None = None,
    titulo: str = "",
) -> str:
    return _backend().registrar_historial_skill(
        skill, marca, resultado, piezas=piezas, titulo=titulo
    )


def listar_historial_skills() -> list[dict[str, Any]]:
    return _backend().listar_historial_skills()


def obtener_historial_skill(historial_id: str) -> dict[str, Any] | None:
    return _backend().obtener_historial_skill(historial_id)


# --------------------------------------------------------------------------- #
# Publicaciones                                                                #
# --------------------------------------------------------------------------- #


def crear_publicacion(
    marca: str,
    red: str,
    *,
    titulo: str = "",
    contenido: str = "",
    estado: str = "borrador",
    veredicto: str = "",
    fecha_programada: str = "",
    origen: str = "",
    imagen: str = "",
    evergreen: bool = False,
) -> dict[str, Any]:
    return _backend().crear_publicacion(
        marca,
        red,
        titulo=titulo,
        contenido=contenido,
        estado=estado,
        veredicto=veredicto,
        fecha_programada=fecha_programada,
        origen=origen,
        imagen=imagen,
        evergreen=evergreen,
    )


def crear_publicaciones(lista: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _backend().crear_publicaciones(lista)


def listar_publicaciones(
    marca: str | None = None,
    red: str | None = None,
    estado: str | None = None,
    evergreen: bool | None = None,
) -> list[dict[str, Any]]:
    return _backend().listar_publicaciones(marca=marca, red=red, estado=estado, evergreen=evergreen)


def obtener_publicacion(publicacion_id: str) -> dict[str, Any] | None:
    return _backend().obtener_publicacion(publicacion_id)


def actualizar_publicacion(
    publicacion_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return _backend().actualizar_publicacion(publicacion_id, campos)


def borrar_publicacion(publicacion_id: str) -> bool:
    return _backend().borrar_publicacion(publicacion_id)


# --------------------------------------------------------------------------- #
# Grupos de hashtags                                                           #
# --------------------------------------------------------------------------- #


def listar_grupos_hashtags() -> list[dict[str, Any]]:
    return _backend().listar_grupos_hashtags()


def obtener_grupo_hashtags(grupo_id: str) -> dict[str, Any] | None:
    return _backend().obtener_grupo_hashtags(grupo_id)


def crear_grupo_hashtags(
    nombre: str, marca: str = "", hashtags: list[str] | None = None
) -> dict[str, Any]:
    return _backend().crear_grupo_hashtags(nombre, marca=marca, hashtags=hashtags)


def actualizar_grupo_hashtags(
    grupo_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return _backend().actualizar_grupo_hashtags(grupo_id, campos)


def borrar_grupo_hashtags(grupo_id: str) -> bool:
    return _backend().borrar_grupo_hashtags(grupo_id)


# --------------------------------------------------------------------------- #
# Franjas                                                                      #
# --------------------------------------------------------------------------- #


def listar_franjas() -> list[dict[str, Any]]:
    return _backend().listar_franjas()


def crear_franja(
    dia_semana: int, hora: str, marca: str = "", red: str = ""
) -> dict[str, Any]:
    return _backend().crear_franja(dia_semana, hora, marca=marca, red=red)


def borrar_franja(franja_id: str) -> bool:
    return _backend().borrar_franja(franja_id)


# --------------------------------------------------------------------------- #
# Plantillas                                                                   #
# --------------------------------------------------------------------------- #


def listar_plantillas() -> list[dict[str, Any]]:
    return _backend().listar_plantillas()


def obtener_plantilla(plantilla_id: str) -> dict[str, Any] | None:
    return _backend().obtener_plantilla(plantilla_id)


def crear_plantilla(
    nombre: str, marca: str = "", red: str = "", contenido: str = ""
) -> dict[str, Any]:
    return _backend().crear_plantilla(nombre, marca=marca, red=red, contenido=contenido)


def actualizar_plantilla(
    plantilla_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return _backend().actualizar_plantilla(plantilla_id, campos)


def borrar_plantilla(plantilla_id: str) -> bool:
    return _backend().borrar_plantilla(plantilla_id)


# --------------------------------------------------------------------------- #
# Fuentes RSS + items vistos + salud                                           #
# --------------------------------------------------------------------------- #


def listar_fuentes_rss() -> list[dict[str, Any]]:
    return _backend().listar_fuentes_rss()


def obtener_fuente_rss(fuente_id: str) -> dict[str, Any] | None:
    return _backend().obtener_fuente_rss(fuente_id)


def crear_fuente_rss(
    nombre: str,
    url: str,
    marca: str = "",
    *,
    incluir: str = "",
    excluir: str = "",
    redes_def: str = "",
) -> dict[str, Any]:
    return _backend().crear_fuente_rss(
        nombre, url, marca=marca, incluir=incluir, excluir=excluir, redes_def=redes_def
    )


def actualizar_fuente_rss(
    fuente_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return _backend().actualizar_fuente_rss(fuente_id, campos)


def registrar_salud_fuente_rss(fuente_id: str, *, conteo: int, error: str = "") -> None:
    return _backend().registrar_salud_fuente_rss(fuente_id, conteo=conteo, error=error)


def borrar_fuente_rss(fuente_id: str) -> bool:
    return _backend().borrar_fuente_rss(fuente_id)


def marcar_item(fuente_id: str, clave: str, usado: bool) -> None:
    return _backend().marcar_item(fuente_id, clave, usado)


def claves_vistas(fuente_id: str) -> set[str]:
    return _backend().claves_vistas(fuente_id)
