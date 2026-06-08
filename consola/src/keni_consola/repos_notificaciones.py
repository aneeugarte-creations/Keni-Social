"""Repositorio — dominio notificaciones. Implementación de repos.py (ver barrel `repos.py`)."""
from __future__ import annotations

from ._repos_comun import (
    Any,
    db,
)

# --------------------------------------------------------------------------- #
# Notificaciones IN-APP (el "cajon" de la campana; reparto en dominio/notificaciones) #
# --------------------------------------------------------------------------- #


def crear_notificacion(
    *,
    usuario_id: str,
    marca_id: str,
    tipo: str,
    contenido_id: str = "",
    plataforma_id: str = "",
    actor: dict[str, str] | None = None,
    resumen: str = "",
    enlace: str = "",
) -> dict[str, Any]:
    return db.crear_notificacion(
        usuario_id=usuario_id,
        marca_id=marca_id,
        tipo=tipo,
        contenido_id=contenido_id,
        plataforma_id=plataforma_id,
        actor=actor,
        resumen=resumen,
        enlace=enlace,
    )


def listar_notificaciones(
    usuario_id: str, marca_id: str | None = None, limite: int = 50
) -> list[dict[str, Any]]:
    return db.listar_notificaciones(usuario_id, marca_id, limite)


def contar_notificaciones_no_leidas(
    usuario_id: str, marca_id: str | None = None
) -> int:
    return db.contar_notificaciones_no_leidas(usuario_id, marca_id)


def marcar_notificacion_leida(notificacion_id: str, usuario_id: str) -> bool:
    return db.marcar_notificacion_leida(notificacion_id, usuario_id)


def marcar_notificaciones_leidas(
    usuario_id: str, marca_id: str | None = None
) -> int:
    return db.marcar_notificaciones_leidas(usuario_id, marca_id)


def registrar_copy_version(
    *,
    plataforma_id: str,
    contenido_id: str,
    copy: str,
    autor: dict[str, str] | None = None,
    nota: str = "",
) -> dict[str, Any]:
    return db.registrar_copy_version(
        plataforma_id=plataforma_id,
        contenido_id=contenido_id,
        copy=copy,
        autor=autor,
        nota=nota,
    )


def listar_copy_versiones(plataforma_id: str) -> list[dict[str, Any]]:
    return db.listar_copy_versiones(plataforma_id)


def obtener_copy_version(version_id: str) -> dict[str, Any] | None:
    return db.obtener_copy_version(version_id)


def crear_cadena_aprobacion(
    *,
    plataforma_id: str,
    contenido_id: str,
    etiquetas: list[str],
    cargos: list[str] | None = None,
) -> list[dict[str, Any]]:
    return db.crear_cadena_aprobacion(
        plataforma_id=plataforma_id,
        contenido_id=contenido_id,
        etiquetas=etiquetas,
        cargos=cargos,
    )


def listar_aprobaciones(plataforma_id: str) -> list[dict[str, Any]]:
    return db.listar_aprobaciones(plataforma_id)


def obtener_aprobacion(aprobacion_id: str) -> dict[str, Any] | None:
    return db.obtener_aprobacion(aprobacion_id)


def actualizar_aprobacion(
    aprobacion_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_aprobacion(aprobacion_id, campos)


def duplicar_evento_rota(
    evento_id: str,
    *,
    fecha: str | None = None,
    hora: str | None = None,
    titulo: str | None = None,
) -> dict[str, Any] | None:
    """Clona un evento (sin turnos, `cambiado` reset; delegado en `db.py`)."""
    return db.duplicar_evento_rota(evento_id, fecha=fecha, hora=hora, titulo=titulo)
