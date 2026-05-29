"""Capa REPOSITORIO de la Consola Keni: fachada UNICA de persistencia.

Esta capa existe para DESACOPLAR los `api/*.py` del almacen concreto. Cada
`api/*.py` consume SIEMPRE a traves de `repos`, sin saber que hay debajo. La fachada
enruta cada entidad a su almacen de forma FIJA (no hay conmutador ni env var):

  - CONTENIDO editorial (editable a mano, fuente de verdad) -> ficheros YAML por
    marca (`ficheros.py`), con un indice SQLite regenerable (`indice.py`):
    publicaciones, plantillas, fuentes RSS + items vistos + salud, grupos de
    hashtags, franjas e historial de skills.
  - OPERACIONAL (no editorial, no encaja en un fichero por entidad) -> Postgres
    (`db.py`, via `motor_db`; ADR 0004): `tareas`, `comercial` (piezas + serie temporal
    de snapshots), `rota`, `usuarios`/`sesiones` (via `auth/`) y la cola de `jobs`.

Las firmas publicas son ESTABLES: ningun `api/*.py` cambia aunque cambie el almacen.

Uso en las features:

    from .. import repos

    repos.crear_publicacion(marca="unotv", red="x", titulo="Hola")  # -> YAML
    repos.crear_tarea("proy", "Revisar copy")                       # -> Postgres
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import db, ficheros

# Re-export de las constantes neutras de dominio (los `api/*.py` las leen via `repos`,
# p. ej. `repos.ESTADOS_PUBLICACION`). Viven en `estados.py`, fuera de los almacenes.
from .estados import (  # noqa: F401 -- re-exportadas como parte de la API publica
    ESTADO_COMERCIAL_ACTIVA,
    ESTADO_ROTA_APROBADO,
    ESTADO_ROTA_PROPUESTO,
    ESTADO_SWAP_PROPUESTO,
    ESTADOS_COMERCIAL,
    ESTADOS_PIEZA,
    ESTADOS_PUBLICACION,
    ESTADOS_ROTA,
    ESTADOS_SWAP,
    ESTADOS_TAREA,
    METRICAS_COMERCIAL,
    NOMBRE_FRANJA_MANANA_DEFAULT,
    NOMBRE_FRANJA_TARDE_DEFAULT,
    TIPOS_AUSENCIA,
)


def conectar() -> Any:
    """Conexion al backend operacional (delega en `db.conectar`; Postgres).

    La usa la capa de auth (`auth/`) para operar sobre `usuarios`/`sesiones`, igual que el
    resto de funciones de `db` se consumen via esta fachada. `motor_db` abre Postgres con
    `DATABASE_URL` (obligatoria, ADR 0004).
    """
    return db.conectar()


def arrancar_persistencia() -> None:
    """Arranque de la persistencia operacional (delega en `db.arrancar_persistencia`).

    Crea/migra el esquema Postgres on-demand (ADR 0004). Lo llama `crear_app`. Ver `db.py`.
    """
    return db.arrancar_persistencia()


def raiz_datos() -> Path:
    """Raiz de datos de ficheros (delega en `ficheros.raiz_datos`; CONTENIDO editorial vive ahi)."""
    return ficheros.raiz_datos()


# --------------------------------------------------------------------------- #
# Tareas (OPERACIONAL: Postgres via db.py)                                       #
# --------------------------------------------------------------------------- #


def listar_tareas(
    proyecto_id: str | None = None,
    evento_id: str | None = None,
) -> list[dict[str, Any]]:
    return db.listar_tareas(proyecto_id, evento_id)


def crear_tarea(
    proyecto_id: str,
    titulo: str,
    detalle: str = "",
    *,
    autor: dict[str, str] | None = None,
    responsable: dict[str, str] | None = None,
    enlace: str = "",
    evento_id: str = "",
) -> dict[str, Any]:
    return db.crear_tarea(
        proyecto_id,
        titulo,
        detalle,
        autor=autor,
        responsable=responsable,
        enlace=enlace,
        evento_id=evento_id,
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
# Publicaciones comerciales (OPERACIONAL: Postgres via db.py; serie temporal)    #
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


# --------------------------------------------------------------------------- #
# Cache de metricas (OPERACIONAL: Postgres via db.py; lo orquesta metricas_cache.py) #
# --------------------------------------------------------------------------- #


def leer_metricas_cache(clave: str) -> dict[str, Any] | None:
    return db.leer_metricas_cache(clave)


def guardar_metricas_cache(
    clave: str,
    tipo: str,
    rango: str,
    marca: str,
    payload: dict[str, Any],
    fuente: str,
    generado_en: str,
) -> None:
    return db.guardar_metricas_cache(
        clave, tipo, rango, marca, payload, fuente, generado_en
    )


# --------------------------------------------------------------------------- #
# Rota de horarios del equipo (OPERACIONAL: Postgres via db.py)                  #
# --------------------------------------------------------------------------- #
#
# Eventos/transmisiones + turnos (asignaciones) de la parrilla del equipo (F4 · #144).
# No es contenido editorial por marca: es dato operacional de coordinacion interna,
# por eso vive en Postgres. La fachada delega 1:1 en db.py.


def crear_evento_rota(
    titulo: str,
    *,
    fecha: str = "",
    hora: str = "",
    contenido: str = "",
    nota: str = "",
    tipo_cobertura: str = "transmision",
    prioridad: str = "media",
) -> dict[str, Any]:
    return db.crear_evento_rota(
        titulo,
        fecha=fecha,
        hora=hora,
        contenido=contenido,
        nota=nota,
        tipo_cobertura=tipo_cobertura,
        prioridad=prioridad,
    )


def listar_eventos_rota(
    desde: str | None = None,
    hasta: str | None = None,
    *,
    solo_cambiados: bool = False,
    tipo_cobertura: str | None = None,
) -> list[dict[str, Any]]:
    return db.listar_eventos_rota(
        desde=desde, hasta=hasta, solo_cambiados=solo_cambiados, tipo_cobertura=tipo_cobertura
    )


def obtener_evento_rota(evento_id: str) -> dict[str, Any] | None:
    return db.obtener_evento_rota(evento_id)


def actualizar_evento_rota(evento_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    return db.actualizar_evento_rota(evento_id, campos)


def borrar_evento_rota(evento_id: str) -> bool:
    return db.borrar_evento_rota(evento_id)


def crear_turno_rota(
    semana: str,
    fecha: str,
    *,
    miembro_id: str = "",
    miembro_nombre: str = "",
    franja_id: str = "",
    estado: str = ESTADO_ROTA_PROPUESTO,
    override: bool = False,
    motivo: str = "",
    nota_relevo: str = "",
    franja: str | None = None,
) -> dict[str, Any]:
    """Crea un turno (horario `(fecha, franja_id)` para un miembro). Delegado en `db.py`.

    Retrocompat para tests legados: acepta `franja` (literal 'matutino'/'vespertino'/
    'descanso'). El shim vive en `db.crear_turno_rota` (la traduccion necesita conexion BD
    para sembrar franjas por defecto). Codigo NUEVO debe pasar `franja_id` directamente.
    """
    return db.crear_turno_rota(
        semana,
        fecha,
        miembro_id=miembro_id,
        miembro_nombre=miembro_nombre,
        franja_id=franja_id,
        estado=estado,
        override=override,
        motivo=motivo,
        nota_relevo=nota_relevo,
        franja=franja,
    )


def crear_turnos_rota_lote(turnos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Crea varios turnos en lote (delegado en `db.py`)."""
    return db.crear_turnos_rota_lote(turnos)


def listar_turnos_rota(semana: str | None = None) -> list[dict[str, Any]]:
    return db.listar_turnos_rota(semana=semana)


def obtener_turno_rota(turno_id: str) -> dict[str, Any] | None:
    return db.obtener_turno_rota(turno_id)


def existe_turno_para(
    miembro_id: str, fecha: str, franja_id: str
) -> dict[str, Any] | None:
    """True si existe un turno para `(miembro_id, fecha, franja_id)` (delegado en `db.py`)."""
    return db.existe_turno_para(miembro_id, fecha, franja_id)


def actualizar_turno_rota(turno_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    return db.actualizar_turno_rota(turno_id, campos)


def actualizar_turnos_rota_lote(
    ids: list[str], campos: dict[str, Any]
) -> tuple[int, list[dict[str, Any]]]:
    """UPDATE masivo sobre `rota_turnos` por lista de ids (delega en `db.py`)."""
    return db.actualizar_turnos_rota_lote(ids, campos)


def copiar_turnos_rota(
    de_lunes: str, a_lunes: str, *, reemplazar: bool = False
) -> int:
    """Copia los turnos de una semana a otra (offset +N dias por fila)."""
    return db.copiar_turnos_rota(de_lunes, a_lunes, reemplazar=reemplazar)


def borrar_turnos_semana_rota(semana: str) -> int:
    return db.borrar_turnos_semana_rota(semana)


def borrar_turno_rota(turno_id: str) -> bool:
    return db.borrar_turno_rota(turno_id)


def borrar_turnos_rota_lote(ids: list[str]) -> int:
    return db.borrar_turnos_rota_lote(ids)


def aprobar_semana_rota(semana: str) -> int:
    return db.aprobar_semana_rota(semana)


def desaprobar_semana_rota(semana: str) -> int:
    return db.desaprobar_semana_rota(semana)


def duplicar_turno_rota(
    turno_id: str,
    *,
    fecha: str | None = None,
    miembro_id: str | None = None,
    miembro_nombre: str | None = None,
    franja_id: str | None = None,
    semana: str | None = None,
) -> dict[str, Any] | None:
    """Clona un turno con overrides (delegado en `db.py`)."""
    return db.duplicar_turno_rota(
        turno_id,
        fecha=fecha,
        miembro_id=miembro_id,
        miembro_nombre=miembro_nombre,
        franja_id=franja_id,
        semana=semana,
    )


def crear_ausencia_rota(
    miembro_id: str,
    desde: str,
    hasta: str,
    *,
    miembro_nombre: str = "",
    tipo: str = "otro",
    motivo: str = "",
) -> dict[str, Any]:
    return db.crear_ausencia_rota(
        miembro_id, desde, hasta, miembro_nombre=miembro_nombre, tipo=tipo, motivo=motivo
    )


def listar_ausencias_rota(
    miembro_id: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
) -> list[dict[str, Any]]:
    return db.listar_ausencias_rota(miembro_id=miembro_id, desde=desde, hasta=hasta)


def obtener_ausencia_rota(ausencia_id: str) -> dict[str, Any] | None:
    return db.obtener_ausencia_rota(ausencia_id)


def actualizar_ausencia_rota(
    ausencia_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_ausencia_rota(ausencia_id, campos)


def borrar_ausencia_rota(ausencia_id: str) -> bool:
    return db.borrar_ausencia_rota(ausencia_id)


# --------------------------------------------------------------------------- #
# Piezas de la parrilla (OPERACIONAL: Postgres via db.py; #150 PARRILLA 2026)   #
# --------------------------------------------------------------------------- #
#
# Una pieza = un POST individual (no un evento). Un evento puede generar varias piezas;
# tambien hay piezas SUELTAS (campanas evergreen sin evento). La fachada delega 1:1 en
# db.py.


def crear_pieza_rota(
    *,
    evento_id: str = "",
    programa: str = "",
    red_social: str = "",
    tipo_pieza: str = "",
    contenido_sugerido: str = "",
    dia: str = "",
    hora_post: str = "",
    estado: str = "pendiente",
    material_entregado: bool = False,
    contenido_entregado: bool = False,
    publicado: bool = False,
    enlace: str = "",
    responsable_id: str = "",
    responsable_nombre: str = "",
    notas: str = "",
    salida: str = "",
    comentarios: str = "",
    fecha_entrega_material: str = "",
    always_on: bool = False,
) -> dict[str, Any]:
    return db.crear_pieza_rota(
        evento_id=evento_id,
        programa=programa,
        red_social=red_social,
        tipo_pieza=tipo_pieza,
        contenido_sugerido=contenido_sugerido,
        dia=dia,
        hora_post=hora_post,
        estado=estado,
        material_entregado=material_entregado,
        contenido_entregado=contenido_entregado,
        publicado=publicado,
        enlace=enlace,
        responsable_id=responsable_id,
        responsable_nombre=responsable_nombre,
        notas=notas,
        salida=salida,
        comentarios=comentarios,
        fecha_entrega_material=fecha_entrega_material,
        always_on=always_on,
    )


def listar_piezas_rota(
    *,
    evento_id: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
    red: str | None = None,
    tipo: str | None = None,
    estado: str | None = None,
    responsable_id: str | None = None,
    programa: str | None = None,
) -> list[dict[str, Any]]:
    return db.listar_piezas_rota(
        evento_id=evento_id,
        desde=desde,
        hasta=hasta,
        red=red,
        tipo=tipo,
        estado=estado,
        responsable_id=responsable_id,
        programa=programa,
    )


def obtener_pieza_rota(pieza_id: str) -> dict[str, Any] | None:
    return db.obtener_pieza_rota(pieza_id)


def actualizar_pieza_rota(
    pieza_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_pieza_rota(pieza_id, campos)


def borrar_pieza_rota(pieza_id: str) -> bool:
    return db.borrar_pieza_rota(pieza_id)


def borrar_piezas_rota_lote(ids: list[str]) -> int:
    """Borra varias piezas a la vez (delegado en `db.py`)."""
    return db.borrar_piezas_rota_lote(ids)


def duplicar_pieza_rota(
    pieza_id: str, *, dia: str | None = None, evento_id: str | None = None
) -> dict[str, Any] | None:
    """Clona una pieza (workflow reset; delegado en `db.py`)."""
    return db.duplicar_pieza_rota(pieza_id, dia=dia, evento_id=evento_id)


# --------------------------------------------------------------------------- #
# Tablero de CONTENIDO unificado (OPERACIONAL: Postgres via db.py)              #
# --------------------------------------------------------------------------- #
# Padre `contenido` (item del tablero: importante/evergreen/evento, o tarea libre) +
# hijos `contenido_plataforma` (una fila por red con estado y checklist). La fachada
# delega 1:1 en `db.py`.


def crear_contenido(
    *,
    clase: str = "contenido",
    flujo: str = "",
    titulo: str = "",
    descripcion: str = "",
    marca: str = "",
    evento_id: str = "",
    programa: str = "",
    prioridad: str = "media",
    estado: str = "pendiente",
    fecha_objetivo: str = "",
    hora_objetivo: str = "",
    fecha_entrega: str = "",
    autor: dict[str, str] | None = None,
    responsable: dict[str, str] | None = None,
    origen: str = "",
    notas: str = "",
    creado: str = "",
    actualizado: str = "",
    id: str = "",
) -> dict[str, Any]:
    """Crea un item del tablero (padre). Delegado en `db.py`."""
    return db.crear_contenido(
        clase=clase,
        flujo=flujo,
        titulo=titulo,
        descripcion=descripcion,
        marca=marca,
        evento_id=evento_id,
        programa=programa,
        prioridad=prioridad,
        estado=estado,
        fecha_objetivo=fecha_objetivo,
        hora_objetivo=hora_objetivo,
        fecha_entrega=fecha_entrega,
        autor=autor,
        responsable=responsable,
        origen=origen,
        notas=notas,
        creado=creado,
        actualizado=actualizado,
        id=id,
    )


def listar_contenido(
    *,
    clase: str | None = None,
    flujo: str | None = None,
    marca: str | None = None,
    evento_id: str | None = None,
    responsable_id: str | None = None,
    estado: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
) -> list[dict[str, Any]]:
    """Lista items del tablero (padres), filtros combinables. Delegado en `db.py`."""
    return db.listar_contenido(
        clase=clase,
        flujo=flujo,
        marca=marca,
        evento_id=evento_id,
        responsable_id=responsable_id,
        estado=estado,
        desde=desde,
        hasta=hasta,
    )


def obtener_contenido(contenido_id: str) -> dict[str, Any] | None:
    return db.obtener_contenido(contenido_id)


def actualizar_contenido(
    contenido_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_contenido(contenido_id, campos)


def borrar_contenido(contenido_id: str) -> bool:
    return db.borrar_contenido(contenido_id)


def crear_contenido_plataforma(
    *,
    contenido_id: str,
    red: str,
    estado: str = "pendiente",
    falta_copy: bool | None = None,
    falta_imagen: bool | None = None,
    falta_revision: bool = True,
    falta_publicar: bool = True,
    copy: str = "",
    imagen: str = "",
    veredicto: str = "",
    revisor_id: str = "",
    revisor_nombre: str = "",
    revisado_en: str = "",
    enviado_a_revision_en: str = "",
    fecha_programada: str = "",
    preparado_en: str = "",
    id_post_metricool: str = "",
    enlace: str = "",
    evergreen: bool = False,
    hora_post: str = "",
    creado: str = "",
    actualizado: str = "",
    id: str = "",
) -> dict[str, Any]:
    """Crea una fila por plataforma de un contenido. Delegado en `db.py`."""
    return db.crear_contenido_plataforma(
        contenido_id=contenido_id,
        red=red,
        estado=estado,
        falta_copy=falta_copy,
        falta_imagen=falta_imagen,
        falta_revision=falta_revision,
        falta_publicar=falta_publicar,
        copy=copy,
        imagen=imagen,
        veredicto=veredicto,
        revisor_id=revisor_id,
        revisor_nombre=revisor_nombre,
        revisado_en=revisado_en,
        enviado_a_revision_en=enviado_a_revision_en,
        fecha_programada=fecha_programada,
        preparado_en=preparado_en,
        id_post_metricool=id_post_metricool,
        enlace=enlace,
        evergreen=evergreen,
        hora_post=hora_post,
        creado=creado,
        actualizado=actualizado,
        id=id,
    )


def listar_contenido_plataforma(
    contenido_id: str | None = None,
) -> list[dict[str, Any]]:
    return db.listar_contenido_plataforma(contenido_id)


def obtener_contenido_plataforma(plataforma_id: str) -> dict[str, Any] | None:
    return db.obtener_contenido_plataforma(plataforma_id)


def actualizar_contenido_plataforma(
    plataforma_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_contenido_plataforma(plataforma_id, campos)


def borrar_contenido_plataforma(plataforma_id: str) -> bool:
    return db.borrar_contenido_plataforma(plataforma_id)


def duplicar_evento_rota(
    evento_id: str,
    *,
    fecha: str | None = None,
    hora: str | None = None,
    titulo: str | None = None,
) -> dict[str, Any] | None:
    """Clona un evento (sin turnos, `cambiado` reset; delegado en `db.py`)."""
    return db.duplicar_evento_rota(evento_id, fecha=fecha, hora=hora, titulo=titulo)


# --------------------------------------------------------------------------- #
# Catalogo de programas (OPERACIONAL: Postgres via db.py; #150)                #
# --------------------------------------------------------------------------- #


def crear_programa_rota(
    nombre: str,
    *,
    descripcion: str = "",
    color: str = "",
    inicio: str = "",
    fin: str = "",
    activo: bool = True,
) -> dict[str, Any]:
    return db.crear_programa_rota(
        nombre,
        descripcion=descripcion,
        color=color,
        inicio=inicio,
        fin=fin,
        activo=activo,
    )


def listar_programas_rota(*, activo: bool | None = None) -> list[dict[str, Any]]:
    return db.listar_programas_rota(activo=activo)


def obtener_programa_rota(programa_id: str) -> dict[str, Any] | None:
    return db.obtener_programa_rota(programa_id)


def actualizar_programa_rota(
    programa_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_programa_rota(programa_id, campos)


def borrar_programa_rota(programa_id: str) -> bool:
    return db.borrar_programa_rota(programa_id)


def existe_programa_por_nombre(nombre: str) -> bool:
    return db.existe_programa_por_nombre(nombre)


def contar_piezas_por_programa(nombre: str) -> int:
    return db.contar_piezas_por_programa(nombre)


# --------------------------------------------------------------------------- #
# Solicitudes de cambio de turno entre companeros (OPERACIONAL; #175)          #
# --------------------------------------------------------------------------- #
#
# Cuando un CM (A) le pide a otro (B) intercambiar turnos por un asunto personal y
# Elias (admin) lo aprueba, se aplica el swap sobre `rota_turnos_trabajo`. Las ausencias
# REALES (vacaciones/baja) viven en SAP, no aqui. La fachada delega 1:1 en db.py.


def crear_swap_turno(
    solicitante_id: str,
    destinatario_id: str,
    fecha_a: str,
    franja_a: str,
    fecha_b: str,
    franja_b: str,
    *,
    solicitante_nombre: str = "",
    destinatario_nombre: str = "",
    motivo: str = "",
) -> dict[str, Any]:
    return db.crear_swap_turno(
        solicitante_id,
        destinatario_id,
        fecha_a,
        franja_a,
        fecha_b,
        franja_b,
        solicitante_nombre=solicitante_nombre,
        destinatario_nombre=destinatario_nombre,
        motivo=motivo,
    )


def listar_swaps_turno(
    estado: str | None = None,
    solicitante_id: str | None = None,
    destinatario_id: str | None = None,
    *,
    mio_id: str | None = None,
) -> list[dict[str, Any]]:
    return db.listar_swaps_turno(
        estado=estado,
        solicitante_id=solicitante_id,
        destinatario_id=destinatario_id,
        mio_id=mio_id,
    )


def obtener_swap_turno(swap_id: str) -> dict[str, Any] | None:
    return db.obtener_swap_turno(swap_id)


def actualizar_swap_turno(
    swap_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_swap_turno(swap_id, campos)


def borrar_swap_turno(swap_id: str) -> bool:
    return db.borrar_swap_turno(swap_id)


def aplicar_swap_turno(
    swap_id: str,
    *,
    solicitante_id: str,
    solicitante_nombre: str,
    destinatario_id: str,
    destinatario_nombre: str,
    fecha_a: str,
    franja_a: str,
    fecha_b: str,
    franja_b: str,
    respuesta_admin: str = "",
) -> dict[str, Any] | None:
    return db.aplicar_swap_turno(
        swap_id,
        solicitante_id=solicitante_id,
        solicitante_nombre=solicitante_nombre,
        destinatario_id=destinatario_id,
        destinatario_nombre=destinatario_nombre,
        fecha_a=fecha_a,
        franja_a=franja_a,
        fecha_b=fecha_b,
        franja_b=franja_b,
        respuesta_admin=respuesta_admin,
    )


# --------------------------------------------------------------------------- #
# Cola de jobs de generacion (OPERACIONAL: persistencia via db.py; #130 Fase 2) #
# --------------------------------------------------------------------------- #
#
# El back ENCOLA y un WORKER (in-proceso en local, servicio aparte en hosted) clava y
# ejecuta `claude -p`. La fachada delega 1:1 en db.py (Postgres).


def encolar_job(gen_id: str, spec: str) -> str:
    return db.encolar_job(gen_id, spec)


def reclamar_job(worker: str = "") -> dict[str, Any] | None:
    return db.reclamar_job(worker)


def terminar_job(job_id: str) -> None:
    return db.terminar_job(job_id)


def cancelar_job(gen_id: str) -> bool:
    return db.cancelar_job(gen_id)


def job_cancelado(job_id: str) -> bool:
    return db.job_cancelado(job_id)


# --------------------------------------------------------------------------- #
# Config de franjas (#185)                                                     #
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# Franjas POR SEMANA (modelo "Mundial": N franjas/semana, solapes permitidos)   #
# --------------------------------------------------------------------------- #


def listar_franjas_semana(lunes: str) -> list[dict[str, Any]]:
    """Franjas vivas de la semana cuyo lunes es `lunes` (delegado en `db.py`)."""
    return db.listar_franjas_semana(lunes)


def obtener_franja_semana(franja_id: str) -> dict[str, Any] | None:
    return db.obtener_franja_semana(franja_id)


def crear_franja_semana(
    lunes: str,
    nombre: str,
    inicio: str,
    fin: str,
    *,
    orden: int = 0,
    es_descanso: bool = False,
) -> dict[str, Any] | None:
    return db.crear_franja_semana(
        lunes, nombre, inicio, fin, orden=orden, es_descanso=es_descanso
    )


def actualizar_franja_semana(
    franja_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_franja_semana(franja_id, campos)


def borrar_franja_semana(franja_id: str, *, forzar: bool = False) -> dict[str, Any]:
    return db.borrar_franja_semana(franja_id, forzar=forzar)


def contar_turnos_de_franja(franja_id: str) -> int:
    return db.contar_turnos_de_franja(franja_id)


def sembrar_franjas_por_defecto(lunes: str) -> list[dict[str, Any]]:
    return db.sembrar_franjas_por_defecto(lunes)


# --------------------------------------------------------------------------- #
# Coordinador por turno (ola "coord")                                          #
# --------------------------------------------------------------------------- #


def listar_coordinacion_semana(lunes: str) -> list[dict[str, Any]]:
    """Coordinaciones de la semana (delegado en `db.py`)."""
    return db.listar_coordinacion_semana(lunes)


def set_coordinador_rota(
    lunes: str, fecha: str, franja_id: str, coordinador_id: str
) -> dict[str, Any]:
    """UPSERT por (fecha, franja_id) del coordinador asignado a la celda."""
    return db.set_coordinador_rota(lunes, fecha, franja_id, coordinador_id)


def quitar_coordinador_rota(fecha: str, franja_id: str) -> bool:
    """Borra la coordinacion de la celda (fecha, franja_id)."""
    return db.quitar_coordinador_rota(fecha, franja_id)


def obtener_franjas_config() -> dict[str, str]:
    return db.obtener_franjas_config()


def guardar_franjas_config(
    matutino_inicio: str,
    matutino_fin: str,
    vespertino_inicio: str,
    vespertino_fin: str,
) -> dict[str, str]:
    return db.guardar_franjas_config(
        matutino_inicio, matutino_fin, vespertino_inicio, vespertino_fin
    )
