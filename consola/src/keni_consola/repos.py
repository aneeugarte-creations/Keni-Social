"""Capa REPOSITORIO de la Consola Keni: fachada UNICA de persistencia.

Esta capa existe para DESACOPLAR los `api/*.py` del almacen concreto. Cada
`api/*.py` consume SIEMPRE a traves de `repos`, sin saber que hay debajo. La fachada
enruta cada entidad a su almacen de forma FIJA (no hay conmutador ni env var):

  - CONTENIDO editorial (editable a mano, fuente de verdad) -> ficheros YAML por
    marca (`ficheros.py`), con un indice SQLite regenerable (`indice.py`):
    publicaciones, plantillas, fuentes RSS + items vistos + salud, grupos de
    hashtags, franjas e historial de skills.
  - OPERACIONAL (no editorial, no encaja en un fichero por entidad) -> SQLite
    (`db.py`): `tareas` y el apartado `comercial` (piezas + su serie temporal de
    snapshots, append-only).

Las firmas publicas son ESTABLES: ningun `api/*.py` cambia aunque cambie el almacen.

Uso en las features:

    from .. import repos

    repos.crear_publicacion(marca="unotv", red="x", titulo="Hola")  # -> YAML
    repos.crear_tarea("proy", "Revisar copy")                       # -> SQLite
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from . import db, ficheros

# Re-export de las constantes neutras de dominio (los `api/*.py` las leen via `repos`,
# p. ej. `repos.ESTADOS_PUBLICACION`). Viven en `estados.py`, fuera de los almacenes.
from .estados import (  # noqa: F401 -- re-exportadas como parte de la API publica
    ESTADO_COMERCIAL_ACTIVA,
    ESTADOS_COMERCIAL,
    ESTADOS_PUBLICACION,
    ESTADOS_TAREA,
    METRICAS_COMERCIAL,
)


def ruta_db() -> Path:
    """Ruta del fichero SQLite (delega en `db.ruta_db`; tareas/comercial viven ahi)."""
    return db.ruta_db()


def conectar() -> sqlite3.Connection:
    """Conexion a la base SQLite (delega en `db.conectar`).

    La usa la capa de auth (`auth.py`) para operar sobre `usuarios`/`sesiones`, igual
    que el resto de funciones de `db` se consumen via esta fachada.
    """
    return db.conectar()


def raiz_datos() -> Path:
    """Raiz de datos de ficheros (delega en `ficheros.raiz_datos`; CONTENIDO editorial vive ahi)."""
    return ficheros.raiz_datos()


# --------------------------------------------------------------------------- #
# Tareas (OPERACIONAL: SQLite via db.py)                                       #
# --------------------------------------------------------------------------- #


def listar_tareas(proyecto_id: str | None = None) -> list[dict[str, Any]]:
    return db.listar_tareas(proyecto_id)


def crear_tarea(
    proyecto_id: str,
    titulo: str,
    detalle: str = "",
    *,
    autor: dict[str, str] | None = None,
    responsable: dict[str, str] | None = None,
    enlace: str = "",
) -> dict[str, Any]:
    return db.crear_tarea(
        proyecto_id, titulo, detalle, autor=autor, responsable=responsable, enlace=enlace
    )


def obtener_tarea(tarea_id: str) -> dict[str, Any] | None:
    return db.obtener_tarea(tarea_id)


def actualizar_tarea(tarea_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    return db.actualizar_tarea(tarea_id, campos)


def actualizar_estado_tarea(tarea_id: str, estado: str) -> dict[str, Any] | None:
    return db.actualizar_estado_tarea(tarea_id, estado)


def borrar_tarea(tarea_id: str) -> bool:
    return db.borrar_tarea(tarea_id)


# --------------------------------------------------------------------------- #
# Historial de skills (CONTENIDO: ficheros YAML via ficheros.py)               #
# --------------------------------------------------------------------------- #


def registrar_historial_skill(
    skill: str,
    marca: str,
    resultado: str,
    *,
    piezas: list[dict[str, Any]] | None = None,
    titulo: str = "",
    metricas: dict[str, Any] | None = None,
    autor: dict[str, str] | None = None,
) -> str:
    return ficheros.registrar_historial_skill(
        skill, marca, resultado, piezas=piezas, titulo=titulo, metricas=metricas, autor=autor
    )


def listar_historial_skills(
    *, limite: int | None = None, desplazamiento: int | None = None
) -> list[dict[str, Any]]:
    return ficheros.listar_historial_skills(limite=limite, desplazamiento=desplazamiento)


def contar_historial_skills() -> int:
    return ficheros.contar_historial_skills()


def obtener_historial_skill(historial_id: str) -> dict[str, Any] | None:
    return ficheros.obtener_historial_skill(historial_id)


# --------------------------------------------------------------------------- #
# Publicaciones (CONTENIDO: ficheros YAML via ficheros.py)                     #
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
    autor: dict[str, str] | None = None,
) -> dict[str, Any]:
    return ficheros.crear_publicacion(
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
        autor=autor,
    )


def crear_publicaciones(lista: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return ficheros.crear_publicaciones(lista)


def listar_publicaciones(
    marca: str | None = None,
    red: str | None = None,
    estado: str | None = None,
    evergreen: bool | None = None,
    *,
    limite: int | None = None,
    desplazamiento: int | None = None,
) -> list[dict[str, Any]]:
    return ficheros.listar_publicaciones(
        marca=marca,
        red=red,
        estado=estado,
        evergreen=evergreen,
        limite=limite,
        desplazamiento=desplazamiento,
    )


def contar_publicaciones(
    marca: str | None = None,
    red: str | None = None,
    estado: str | None = None,
    evergreen: bool | None = None,
) -> int:
    return ficheros.contar_publicaciones(marca=marca, red=red, estado=estado, evergreen=evergreen)


def obtener_publicacion(publicacion_id: str) -> dict[str, Any] | None:
    return ficheros.obtener_publicacion(publicacion_id)


def actualizar_publicacion(
    publicacion_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return ficheros.actualizar_publicacion(publicacion_id, campos)


def borrar_publicacion(publicacion_id: str) -> bool:
    return ficheros.borrar_publicacion(publicacion_id)


# --------------------------------------------------------------------------- #
# Grupos de hashtags (CONTENIDO: ficheros YAML via ficheros.py)                #
# --------------------------------------------------------------------------- #


def listar_grupos_hashtags(
    *, limite: int | None = None, desplazamiento: int | None = None
) -> list[dict[str, Any]]:
    return ficheros.listar_grupos_hashtags(limite=limite, desplazamiento=desplazamiento)


def contar_grupos_hashtags() -> int:
    return ficheros.contar_grupos_hashtags()


def obtener_grupo_hashtags(grupo_id: str) -> dict[str, Any] | None:
    return ficheros.obtener_grupo_hashtags(grupo_id)


def crear_grupo_hashtags(
    nombre: str, marca: str = "", hashtags: list[str] | None = None
) -> dict[str, Any]:
    return ficheros.crear_grupo_hashtags(nombre, marca=marca, hashtags=hashtags)


def actualizar_grupo_hashtags(
    grupo_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return ficheros.actualizar_grupo_hashtags(grupo_id, campos)


def borrar_grupo_hashtags(grupo_id: str) -> bool:
    return ficheros.borrar_grupo_hashtags(grupo_id)


# --------------------------------------------------------------------------- #
# Franjas (CONTENIDO: ficheros YAML via ficheros.py)                           #
# --------------------------------------------------------------------------- #


def listar_franjas() -> list[dict[str, Any]]:
    return ficheros.listar_franjas()


def crear_franja(
    dia_semana: int, hora: str, marca: str = "", red: str = ""
) -> dict[str, Any]:
    return ficheros.crear_franja(dia_semana, hora, marca=marca, red=red)


def borrar_franja(franja_id: str) -> bool:
    return ficheros.borrar_franja(franja_id)


# --------------------------------------------------------------------------- #
# Plantillas (CONTENIDO: ficheros YAML via ficheros.py)                        #
# --------------------------------------------------------------------------- #


def listar_plantillas(
    *, limite: int | None = None, desplazamiento: int | None = None
) -> list[dict[str, Any]]:
    return ficheros.listar_plantillas(limite=limite, desplazamiento=desplazamiento)


def contar_plantillas() -> int:
    return ficheros.contar_plantillas()


def obtener_plantilla(plantilla_id: str) -> dict[str, Any] | None:
    return ficheros.obtener_plantilla(plantilla_id)


def crear_plantilla(
    nombre: str, marca: str = "", red: str = "", contenido: str = ""
) -> dict[str, Any]:
    return ficheros.crear_plantilla(nombre, marca=marca, red=red, contenido=contenido)


def actualizar_plantilla(
    plantilla_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return ficheros.actualizar_plantilla(plantilla_id, campos)


def borrar_plantilla(plantilla_id: str) -> bool:
    return ficheros.borrar_plantilla(plantilla_id)


# --------------------------------------------------------------------------- #
# Fuentes RSS + items vistos + salud (CONTENIDO: ficheros YAML via ficheros.py) #
# --------------------------------------------------------------------------- #


def listar_fuentes_rss(
    *, limite: int | None = None, desplazamiento: int | None = None
) -> list[dict[str, Any]]:
    return ficheros.listar_fuentes_rss(limite=limite, desplazamiento=desplazamiento)


def contar_fuentes_rss() -> int:
    return ficheros.contar_fuentes_rss()


def obtener_fuente_rss(fuente_id: str) -> dict[str, Any] | None:
    return ficheros.obtener_fuente_rss(fuente_id)


def crear_fuente_rss(
    nombre: str,
    url: str,
    marca: str = "",
    *,
    incluir: str = "",
    excluir: str = "",
    redes_def: str = "",
) -> dict[str, Any]:
    return ficheros.crear_fuente_rss(
        nombre, url, marca=marca, incluir=incluir, excluir=excluir, redes_def=redes_def
    )


def actualizar_fuente_rss(
    fuente_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return ficheros.actualizar_fuente_rss(fuente_id, campos)


def registrar_salud_fuente_rss(fuente_id: str, *, conteo: int, error: str = "") -> None:
    return ficheros.registrar_salud_fuente_rss(fuente_id, conteo=conteo, error=error)


def borrar_fuente_rss(fuente_id: str) -> bool:
    return ficheros.borrar_fuente_rss(fuente_id)


def marcar_item(fuente_id: str, clave: str, usado: bool) -> None:
    return ficheros.marcar_item(fuente_id, clave, usado)


def claves_vistas(fuente_id: str) -> set[str]:
    return ficheros.claves_vistas(fuente_id)


# --------------------------------------------------------------------------- #
# Publicaciones comerciales (OPERACIONAL: SQLite via db.py; serie temporal)    #
# --------------------------------------------------------------------------- #
#
# El apartado comercial es una serie temporal append-only (snapshots de
# interacciones/alcance); no encaja en un fichero por entidad. La fachada delega 1:1
# en db.py.


def crear_publicacion_comercial(
    url: str,
    *,
    titulo: str = "",
    marca: str = "",
    cliente: str = "",
    campania: str = "",
    red: str = "",
    metrica_objetivo: str = "interacciones",
    objetivo: int = 0,
    estado: str = "activa",
    publicado: str = "",
    notas: str = "",
) -> dict[str, Any]:
    return db.crear_publicacion_comercial(
        url,
        titulo=titulo,
        marca=marca,
        cliente=cliente,
        campania=campania,
        red=red,
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
    publicacion_id: str, ts: str, interacciones: int, alcance: int
) -> bool:
    return db.registrar_snapshot_comercial(publicacion_id, ts, interacciones, alcance)


def listar_snapshots_comerciales(publicacion_id: str) -> list[dict[str, Any]]:
    return db.listar_snapshots_comerciales(publicacion_id)


def ultimo_snapshot_comercial(publicacion_id: str) -> dict[str, Any] | None:
    return db.ultimo_snapshot_comercial(publicacion_id)
