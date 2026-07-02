"""Repositorio — dominio webhooks. Implementación de repos.py (ver barrel `repos.py`)."""
from __future__ import annotations

from ._comun import (
    Any,
    db,
)

# --------------------------------------------------------------------------- #
# Webhooks salientes + bitacora de eventos internos (OPERACIONAL: Postgres)      #
# --------------------------------------------------------------------------- #


def crear_webhook(
    *,
    nombre: str = "",
    url: str = "",
    eventos: list[str] | None = None,
    formato: str = "generico",
    secreto: str = "",
    activo: bool = True,
    autor: dict[str, str] | None = None,
    id: str = "",
) -> dict[str, Any]:
    return db.crear_webhook(
        nombre=nombre,
        url=url,
        eventos=eventos,
        formato=formato,
        secreto=secreto,
        activo=activo,
        autor=autor,
        id=id,
    )


def listar_webhooks(*, solo_activos: bool = False) -> list[dict[str, Any]]:
    return db.listar_webhooks(solo_activos=solo_activos)


def listar_webhooks_para(evento: str) -> list[dict[str, Any]]:
    """Webhooks activos suscritos a `evento` (CON secreto; uso interno del repartidor)."""
    return db.listar_webhooks_para(evento)


def obtener_webhook(webhook_id: str) -> dict[str, Any] | None:
    return db.obtener_webhook(webhook_id)


def obtener_webhook_con_secreto(webhook_id: str) -> dict[str, Any] | None:
    """Suscripcion por id CON el secreto crudo (uso interno: probar/repartir)."""
    return db.obtener_webhook_con_secreto(webhook_id)


def actualizar_webhook(
    webhook_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    return db.actualizar_webhook(webhook_id, campos)


def borrar_webhook(webhook_id: str) -> bool:
    return db.borrar_webhook(webhook_id)


def registrar_evento_interno(
    *,
    tipo: str,
    publicacion_id: str = "",
    pieza_id: str = "",
    clave_idempotencia: str = "",
    payload: dict[str, Any] | None = None,
) -> bool:
    """Registra un evento interno (False si su clave de idempotencia ya existia)."""
    return db.registrar_evento_interno(
        tipo=tipo,
        publicacion_id=publicacion_id,
        pieza_id=pieza_id,
        clave_idempotencia=clave_idempotencia,
        payload=payload,
    )


def listar_eventos_internos(*, limite: int = 50) -> list[dict[str, Any]]:
    return db.listar_eventos_internos(limite=limite)
