"""Repositorio — dominio parrilla. Implementación de repos.py (ver barrel `repos.py`)."""
from __future__ import annotations

from ._repos_comun import (
    Any,
    db,
)

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
# PARRILLA: propuestas de importacion desde documento                          #
# --------------------------------------------------------------------------- #


def crear_propuesta_parrilla(
    *,
    semana: str,
    doc_nombre: str,
    doc_tipo: str = "",
    gen_id: str = "",
    autor_id: str = "",
    autor_nombre: str = "",
    estado: str = "generando",
    marca: str = "",
) -> dict[str, Any]:
    return db.crear_propuesta_parrilla(
        semana=semana,
        doc_nombre=doc_nombre,
        doc_tipo=doc_tipo,
        gen_id=gen_id,
        autor_id=autor_id,
        autor_nombre=autor_nombre,
        estado=estado,
        marca=marca,
    )


def obtener_propuesta_parrilla(propuesta_id: str) -> dict[str, Any] | None:
    return db.obtener_propuesta_parrilla(propuesta_id)


def listar_propuestas_parrilla(
    *, estado: str | None = None, limite: int = 100
) -> list[dict[str, Any]]:
    return db.listar_propuestas_parrilla(estado=estado, limite=limite)


def actualizar_propuesta_parrilla(
    propuesta_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_propuesta_parrilla(propuesta_id, campos)


def aplicar_propuesta_parrilla(
    propuesta_id: str,
    operaciones: list[dict[str, Any]],
    *,
    nombres_miembros: dict[str, str],
    origen: str = "import-doc",
    marca: str = "",
) -> dict[str, Any]:
    return db.aplicar_propuesta_parrilla(
        propuesta_id,
        operaciones,
        nombres_miembros=nombres_miembros,
        origen=origen,
        marca=marca,
    )
