"""Plumbing común de los `repos_<dominio>`: imports (db, ficheros), re-export de
estados y delegadores foundacionales (conectar/arrancar_persistencia/raiz_datos)."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from . import db, ficheros
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

__all__ = [
    'Any',
    'ESTADOS_COMERCIAL',
    'ESTADOS_PIEZA',
    'ESTADOS_PUBLICACION',
    'ESTADOS_ROTA',
    'ESTADOS_SWAP',
    'ESTADOS_TAREA',
    'ESTADO_COMERCIAL_ACTIVA',
    'ESTADO_ROTA_APROBADO',
    'ESTADO_ROTA_PROPUESTO',
    'ESTADO_SWAP_PROPUESTO',
    'Iterator',
    'METRICAS_COMERCIAL',
    'NOMBRE_FRANJA_MANANA_DEFAULT',
    'NOMBRE_FRANJA_TARDE_DEFAULT',
    'Path',
    'TIPOS_AUSENCIA',
    'annotations',
    'arrancar_persistencia',
    'conectar',
    'db',
    'ficheros',
    'raiz_datos',
]
