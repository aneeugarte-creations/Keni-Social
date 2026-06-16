"""Plumbing común de los `repos_<dominio>`: imports (db, ficheros), re-export de
estados y delegadores foundacionales (conectar/arrancar_persistencia/raiz_datos)."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from . import db, ficheros
from .estados import ESTADO_PUBLICADO
from .estados import (  # noqa: F401 -- re-exportadas como parte de la API publica
    ESTADO_ROTA_APROBADO,
    ESTADO_ROTA_PROPUESTO,
    ESTADO_SWAP_PROPUESTO,
    ESTADOS_PIEZA_PARRILLA,
    ESTADOS_PIEZA,
    ESTADOS_ROTA,
    ESTADOS_SWAP,
    ESTADOS_TAREA,
    NOMBRE_FRANJA_MANANA_DEFAULT,
    NOMBRE_FRANJA_TARDE_DEFAULT,
    TIPOS_AUSENCIA,
)


class PiezaPublicadaInmutable(Exception):
    """Se intentó EDITAR el contenido de una pieza ya `publicado`.

    Una pieza publicada es read-only en lo editorial/visual: lo que se muestra no puede
    diferir de lo que salió a redes. La API la traduce a 409 (ver `app.crear_app`)."""


# Campos EDITORIALES/VISUALES congelados una vez la pieza está `publicado` (cubre el
# vocabulario de publicación —`contenido`— y el de plataforma —`copy`—). NO se congelan los
# campos OPERATIVOS (estado, id_post_metricool, preparado_en, metadatos de revisión, flags
# `falta_*`, revision): el barrido, la reconciliación y la auditoría siguen escribiéndolos.
_CAMPOS_CONGELADOS_PUBLICADO: frozenset[str] = frozenset({
    "contenido", "copy", "copy_in", "titulo",
    "imagen", "imagen_fuente", "video", "enlace",
    "foto", "fotos", "foto_encuadre", "carrusel",
    "plantilla_diseno_id", "placa_oculta", "evergreen", "espejo",
    "fecha_programada", "hora_post",
})
_CAMPOS_CONGELADOS_BOOL: frozenset[str] = frozenset({"evergreen", "placa_oculta", "espejo"})


def verificar_publicacion_inmutable(
    actual: dict[str, Any] | None, campos: dict[str, Any]
) -> None:
    """Lanza `PiezaPublicadaInmutable` si `campos` intenta cambiar un campo congelado de una
    pieza ya `publicado`. No-op si la pieza no existe, no está publicada, o solo toca campos
    operativos. Compara contra el valor guardado: re-escribir el MISMO valor no rompe (idempotente).
    El borrado va por otra función y se permite (limpiar errores)."""
    if actual is None or (actual.get("estado") or "") != ESTADO_PUBLICADO:
        return
    congelados: list[str] = []
    for clave, nuevo in campos.items():
        if clave not in _CAMPOS_CONGELADOS_PUBLICADO:
            continue
        viejo = actual.get(clave)
        if clave in _CAMPOS_CONGELADOS_BOOL:
            cambia = bool(nuevo) != bool(viejo)
        else:
            cambia = (str(nuevo) if nuevo is not None else "") != (
                str(viejo) if viejo is not None else ""
            )
        if cambia:
            congelados.append(clave)
    if congelados:
        # Mensaje MÍNIMO de cara al usuario: con "Ya publicada" basta (el detalle de qué campo
        # se congeló no aporta nada accionable; lo que salió a redes no se edita).
        raise PiezaPublicadaInmutable("Ya publicada.")


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
    'ESTADO_PUBLICADO',
    'PiezaPublicadaInmutable',
    'verificar_publicacion_inmutable',
    'ESTADOS_PIEZA_PARRILLA',
    'ESTADOS_PIEZA',
    'ESTADOS_ROTA',
    'ESTADOS_SWAP',
    'ESTADOS_TAREA',
    'ESTADO_ROTA_APROBADO',
    'ESTADO_ROTA_PROPUESTO',
    'ESTADO_SWAP_PROPUESTO',
    'Iterator',
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
