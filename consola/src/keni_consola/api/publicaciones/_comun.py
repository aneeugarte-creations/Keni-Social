"""Helpers e infraestructura COMPARTIDA del paquete `api.publicaciones`.

Reune lo que usan varias areas (CRUD y espejo) sin crear ciclos: la serializacion de
piezas, las flags de readiness derivadas del contenido y el reset de aprobaciones al
editar contenido ya aprobado.
"""

from __future__ import annotations

from typing import Any

from ... import repos
from ...dominio import colaboracion
from ...dominio.publicaciones import flags_falta_de_contenido, publicacion_a_dict
from ...estados import (
    ESTADO_APROBADO,
    ESTADO_EN_REVISION,
    ESTADO_PROGRAMADO,
)

# Alias local para los handlers de este modulo. La serializacion vive en el dominio
# (`dominio.publicaciones.publicacion_a_dict`): asi `api/skills.py` la consume desde un
# sitio comun y publico, sin importar un simbolo privado de este handler (H6/N7).
_publicacion_a_dict = publicacion_a_dict


# Campos de CONTENIDO que el espejo propaga entre redes hermanas (la "receta" completa de la
# pieza: copy + copy-in + foto/collage + plantilla). Estado, fechas y flags NO se espejan.
# También es la lista de campos cuyo cambio invalida aprobaciones (junto con `titulo`).
_CAMPOS_ESPEJO: tuple[str, ...] = (
    "contenido", "copy_in", "imagen", "foto", "fotos", "carrusel",
    "plantilla_diseno_id", "foto_encuadre", "placa_oculta",
)

# Campos cuyo cambio altera las flags de readiness DERIVADAS del contenido (copy/foto): si la
# edición toca alguno, hay que recalcular `falta_copy`/`falta_imagen`.
_CAMPOS_CONTENIDO_FALTA: tuple[str, ...] = ("contenido", "foto", "imagen")


def _inyectar_flags_falta(actual: dict[str, Any], campos: dict[str, Any]) -> None:
    """Si la edición toca el contenido (copy/foto/imagen), recalcula e INYECTA en `campos` las
    flags `falta_copy`/`falta_imagen` del estado RESULTANTE (fila + edición), para que la LISTA
    del feed (que lee las flags ALMACENADAS) refleje el cambio sin abrir cada pieza —incluidas
    las redes ESPEJO—. NO toca las flags de aprobación/publicación (eso no se espeja)."""
    if not any(k in campos for k in _CAMPOS_CONTENIDO_FALTA):
        return
    campos.update(flags_falta_de_contenido({**actual, **campos}))

# Reset al perder aprobaciones: la pieza vuelve a borrador con la revisión limpia (reentrará
# sola a revisión cuando se reenvíe, exigiendo OK nuevos).
_RESET_APROBACIONES: dict[str, Any] = {
    "estado": "borrador",
    "revisor_id": "",
    "revisor_nombre": "",
    "revisado_en": "",
    "enviado_a_revision_en": "",
    "fecha_programada": "",
}


def _pierde_aprobaciones(actual: dict[str, Any], campos: dict[str, Any]) -> bool:
    """True si aplicar `campos` a la pieza `actual` invalida aprobaciones YA dadas.

    Editar el CONTENIDO de una pieza que acumula aprobaciones las invalida (como reescribir
    un PR aprobado). Solo cuando hay aprobaciones REALES que perder (aprobada/programada, o
    en revisión con un OK humano). No aplica si la propia petición fija `estado` (el flujo
    la está moviendo a propósito).
    """
    cambia_contenido = any(
        clave in campos and campos[clave] != actual.get(clave)
        for clave in ("titulo", *_CAMPOS_ESPEJO)
    )
    if not cambia_contenido or "estado" in campos:
        return False
    estado_actual = actual.get("estado") or ""
    if estado_actual in (ESTADO_APROBADO, ESTADO_PROGRAMADO):
        return True
    if estado_actual == ESTADO_EN_REVISION:
        cadena = repos.listar_aprobaciones(actual["id"])
        return colaboracion.contar_aprobaciones_humanas(cadena) > 0
    return False


def _limpiar_cadena(publicacion_id: str) -> None:
    """Recrea la cadena de aprobación VACÍA de la pieza (las aprobaciones previas se pierden)."""
    plat = repos.obtener_contenido_plataforma(publicacion_id)
    repos.crear_cadena_aprobacion(
        plataforma_id=publicacion_id,
        contenido_id=(plat or {}).get("contenido_id", "") or "",
        etiquetas=[],
    )
