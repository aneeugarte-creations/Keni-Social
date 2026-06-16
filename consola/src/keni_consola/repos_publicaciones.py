"""Repositorio — dominio publicaciones. Implementación de repos.py (ver barrel `repos.py`)."""
from __future__ import annotations

from collections.abc import Sequence

from ._repos_comun import (
    Any,
    Iterator,
    db,
    verificar_publicacion_inmutable,
)

# --------------------------------------------------------------------------- #
# Publicaciones (OPERACIONAL: Postgres via db.py; fusión sobre `contenido`, paso 3)    #
# --------------------------------------------------------------------------- #


def crear_publicacion(
    marca: str,
    red: str,
    *,
    titulo: str = "",
    contenido: str = "",
    copy_in: str = "",
    estado: str = "borrador",
    revision: str = "",
    fecha_programada: str = "",
    origen: str = "",
    imagen: str = "",
    imagen_fuente: str = "",
    tipo_contenido: str = "",
    evergreen: bool = False,
    autor: dict[str, str] | None = None,
    id: str = "",
    fecha_creacion: str = "",
) -> dict[str, Any]:
    return db.crear_publicacion(
        marca,
        red,
        titulo=titulo,
        contenido=contenido,
        copy_in=copy_in,
        estado=estado,
        revision=revision,
        fecha_programada=fecha_programada,
        origen=origen,
        imagen=imagen,
        imagen_fuente=imagen_fuente,
        tipo_contenido=tipo_contenido,
        evergreen=evergreen,
        autor=autor,
        id=id,
        fecha_creacion=fecha_creacion,
    )


def crear_publicaciones(lista: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return db.crear_publicaciones(lista)


def listar_publicaciones(
    marca: str | Sequence[str] | None = None,
    red: str | None = None,
    estado: str | None = None,
    evergreen: bool | None = None,
    linea: str | None = None,
    responsable: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
    *,
    limite: int | None = None,
    desplazamiento: int | None = None,
    cursor: tuple[str, str] | None = None,
) -> list[dict[str, Any]]:
    # `responsable` ("la lista"): "" = piezas libres (por coger); otro valor = de ese usuario.
    # `desde`/`hasta` (ISO): rango de `fecha_programada` para el calendario (sin fecha = fuera).
    return db.listar_publicaciones(
        marca=marca,
        red=red,
        estado=estado,
        evergreen=evergreen,
        linea=linea,
        responsable=responsable,
        desde=desde,
        hasta=hasta,
        limite=limite,
        desplazamiento=desplazamiento,
        cursor=cursor,
    )


def contar_publicaciones(
    marca: str | Sequence[str] | None = None,
    red: str | None = None,
    estado: str | None = None,
    evergreen: bool | None = None,
    linea: str | None = None,
    responsable: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
) -> int:
    return db.contar_publicaciones(
        marca=marca, red=red, estado=estado, evergreen=evergreen, linea=linea,
        responsable=responsable, desde=desde, hasta=hasta,
    )


def obtener_publicacion(publicacion_id: str) -> dict[str, Any] | None:
    return db.obtener_publicacion(publicacion_id)


def actualizar_publicacion(
    publicacion_id: str,
    campos: dict[str, Any],
    *,
    estado_esperado: str | None = None,
) -> dict[str, Any] | None:
    # `estado_esperado` (opcional): CAS sobre el estado actual; si otro flujo movio la pieza
    # entre el snapshot del caller y esta escritura, devuelve None sin tocar nada.
    # INMUTABILIDAD: una pieza ya `publicado` es read-only en lo editorial/visual (lo que salió
    # no puede diferir de lo mostrado). La transición A `publicado` no se bloquea: en ese momento
    # la pieza aún NO está publicada, así que el guard la deja pasar.
    verificar_publicacion_inmutable(db.obtener_publicacion(publicacion_id), campos)
    return db.actualizar_publicacion(
        publicacion_id, campos, estado_esperado=estado_esperado
    )


def borrar_publicacion(publicacion_id: str) -> bool:
    return db.borrar_publicacion(publicacion_id)


def reclamar_preparacion(publicacion_id: str, ts: str) -> bool:
    return db.reclamar_preparacion(publicacion_id, ts)


def transicionar_estado_publicacion(
    publicacion_id: str,
    estado_origen: str,
    estado_destino: str,
    campos_extra: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    # CAS de transicion de estado (cierra el TOCTOU de enviar-a-revision/programar). None si
    # el estado origen ya cambió (el caller lo traduce a 409).
    return db.transicionar_estado_publicacion(
        publicacion_id, estado_origen, estado_destino, campos_extra
    )


def existe_cadena_aprobacion(plataforma_id: str) -> bool:
    return db.existe_cadena_aprobacion(plataforma_id)


def decidir_nivel_aprobacion_tx(
    plataforma_id: str,
    nivel_id: str,
    validar: Any,
) -> tuple[dict[str, Any] | None, str | None]:
    return db.decidir_nivel_aprobacion_tx(plataforma_id, nivel_id, validar)


def lock_barrido(nombre: str) -> Iterator[bool]:
    # Passthrough del single-flight cross-proceso (advisory lock). `with repos.lock_barrido(x) as ok:`
    return db.lock_barrido(nombre)
