"""Repositorio — dominio rota. Implementación de repos.py (ver barrel `repos.py`)."""
from __future__ import annotations

from ._repos_comun import (
    ESTADO_ROTA_PROPUESTO,
    Any,
    db,
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
    marca: str = "",
) -> dict[str, Any]:
    return db.crear_evento_rota(
        titulo,
        fecha=fecha,
        hora=hora,
        contenido=contenido,
        nota=nota,
        tipo_cobertura=tipo_cobertura,
        prioridad=prioridad,
        marca=marca,
    )


def listar_eventos_rota(
    desde: str | None = None,
    hasta: str | None = None,
    *,
    solo_cambiados: bool = False,
    tipo_cobertura: str | None = None,
    marca: str | None = None,
) -> list[dict[str, Any]]:
    return db.listar_eventos_rota(
        desde=desde,
        hasta=hasta,
        solo_cambiados=solo_cambiados,
        tipo_cobertura=tipo_cobertura,
        marca=marca,
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
    marca: str = "",
) -> dict[str, Any]:
    """Crea un turno (horario `(fecha, franja_id)` para un miembro). Delegado en `db.py`.

    GRID POR MARCA: `marca` ata el turno a la rejilla de esa marca.

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
        marca=marca,
    )


def crear_turnos_rota_lote(turnos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Crea varios turnos en lote (delegado en `db.py`)."""
    return db.crear_turnos_rota_lote(turnos)


def listar_turnos_rota(
    semana: str | None = None, marca: str | None = None
) -> list[dict[str, Any]]:
    return db.listar_turnos_rota(semana=semana, marca=marca)


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
    de_lunes: str, a_lunes: str, *, reemplazar: bool = False, marca: str | None = None
) -> int:
    """Copia los turnos de una semana a otra (offset +N dias por fila). `marca` acota la rejilla."""
    return db.copiar_turnos_rota(de_lunes, a_lunes, reemplazar=reemplazar, marca=marca)


def borrar_turnos_semana_rota(semana: str) -> int:
    return db.borrar_turnos_semana_rota(semana)


def borrar_turno_rota(turno_id: str) -> bool:
    return db.borrar_turno_rota(turno_id)


def borrar_turnos_rota_lote(ids: list[str]) -> int:
    return db.borrar_turnos_rota_lote(ids)


def aprobar_semana_rota(semana: str, marca: str | None = None) -> int:
    return db.aprobar_semana_rota(semana, marca)


def desaprobar_semana_rota(semana: str, marca: str | None = None) -> int:
    return db.desaprobar_semana_rota(semana, marca)


def duplicar_turno_rota(
    turno_id: str,
    *,
    fecha: str | None = None,
    miembro_id: str | None = None,
    miembro_nombre: str | None = None,
    franja_id: str | None = None,
    semana: str | None = None,
) -> dict[str, Any] | None:
    """Clona un turno con overrides (delegado en `db.py`). El clon hereda la marca del original."""
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
    marca: str = "",
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
        marca=marca,
    )


def listar_swaps_turno(
    estado: str | None = None,
    solicitante_id: str | None = None,
    destinatario_id: str | None = None,
    *,
    mio_id: str | None = None,
    marca: str | None = None,
) -> list[dict[str, Any]]:
    return db.listar_swaps_turno(
        estado=estado,
        solicitante_id=solicitante_id,
        destinatario_id=destinatario_id,
        mio_id=mio_id,
        marca=marca,
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
# Config de franjas (#185)                                                     #
# --------------------------------------------------------------------------- #



# --------------------------------------------------------------------------- #
# Franjas POR SEMANA (modelo "Mundial": N franjas/semana, solapes permitidos)   #
# --------------------------------------------------------------------------- #


def listar_franjas_semana(
    lunes: str, marca: str | None = None
) -> list[dict[str, Any]]:
    """Franjas vivas de la semana `lunes` (delegado en `db.py`). `marca` acota la rejilla."""
    return db.listar_franjas_semana(lunes, marca)


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
    marca: str = "",
) -> dict[str, Any] | None:
    return db.crear_franja_semana(
        lunes, nombre, inicio, fin, orden=orden, es_descanso=es_descanso, marca=marca
    )


def actualizar_franja_semana(
    franja_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_franja_semana(franja_id, campos)


def borrar_franja_semana(franja_id: str, *, forzar: bool = False) -> dict[str, Any]:
    return db.borrar_franja_semana(franja_id, forzar=forzar)


def contar_turnos_de_franja(franja_id: str) -> int:
    return db.contar_turnos_de_franja(franja_id)


def sembrar_franjas_por_defecto(lunes: str, marca: str = "") -> list[dict[str, Any]]:
    return db.sembrar_franjas_por_defecto(lunes, marca)



# --------------------------------------------------------------------------- #
# Coordinador por turno (ola "coord")                                          #
# --------------------------------------------------------------------------- #


def listar_coordinacion_semana(
    lunes: str, marca: str | None = None
) -> list[dict[str, Any]]:
    """Coordinaciones de la semana (delegado en `db.py`). `marca` acota la rejilla."""
    return db.listar_coordinacion_semana(lunes, marca)


def actualizar_coordinador_rota(
    lunes: str, fecha: str, franja_id: str, coordinador_id: str, marca: str = ""
) -> dict[str, Any]:
    """UPSERT por (fecha, franja_id) del coordinador asignado a la celda."""
    return db.actualizar_coordinador_rota(lunes, fecha, franja_id, coordinador_id, marca)


def quitar_coordinador_rota(fecha: str, franja_id: str) -> bool:
    """Borra la coordinacion de la celda (fecha, franja_id)."""
    return db.quitar_coordinador_rota(fecha, franja_id)


def obtener_franjas_config(marca: str = "") -> dict[str, str]:
    return db.obtener_franjas_config(marca)


def guardar_franjas_config(
    matutino_inicio: str,
    matutino_fin: str,
    vespertino_inicio: str,
    vespertino_fin: str,
    marca: str = "",
) -> dict[str, str]:
    return db.guardar_franjas_config(
        matutino_inicio, matutino_fin, vespertino_inicio, vespertino_fin, marca
    )
