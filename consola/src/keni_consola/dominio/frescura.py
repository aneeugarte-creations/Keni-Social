"""Frescura: TTL por línea de contenido.

Módulo PURO (sin dependencias de BD en las funciones de lógica); las funciones de
resolución de línea sí tocan `repos` pero están claramente separadas.

Regla de negocio:
- Una línea con `es_evergreen=True` o `ttl_dias <= 0` NUNCA caduca → "fresco".
- En cualquier otro caso, un ítem está "fresco" mientras `hoy - fecha_item <= ttl_dias`.
- Fechas vacías o malformadas → "fresco" (nunca ocultar por dato malo).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


# --------------------------------------------------------------------------- #
# Lógica pura (sin E/S)                                                        #
# --------------------------------------------------------------------------- #


def estado_frescura(
    fecha_item: str,
    ttl_dias: int,
    es_evergreen: bool,
    *,
    hoy: str,
) -> str:
    """Calcula el estado de frescura de un ítem de insumo.

    Parámetros
    ----------
    fecha_item : str
        Fecha editorial del ítem (ISO YYYY-MM-DD). Vacía o inválida → "fresco".
    ttl_dias : int
        Días de vida de la línea. 0 (o negativo) = sin caducidad / evergreen.
    es_evergreen : bool
        True = línea evergreen reutilizable en fines de semana; nunca caduca.
    hoy : str
        Fecha de referencia ISO YYYY-MM-DD (normalmente el día del servidor).

    Retorna
    -------
    "fresco" | "caduco"
    """
    # Everevergreen: nunca caduca independientemente de la fecha.
    if es_evergreen or ttl_dias <= 0:
        return "fresco"

    # Fecha inválida o vacía → tratamos como "fresco" (nunca ocultar por dato malo).
    try:
        d_item = date.fromisoformat(fecha_item.strip())
    except (ValueError, AttributeError):
        return "fresco"

    try:
        d_hoy = date.fromisoformat(hoy.strip())
    except (ValueError, AttributeError):
        return "fresco"

    # Fresco mientras la diferencia sea <= ttl_dias días.
    if (d_hoy - d_item) <= timedelta(days=ttl_dias):
        return "fresco"
    return "caduco"


# --------------------------------------------------------------------------- #
# Resolución de línea → (ttl_dias, es_evergreen) desde la BD                     #
# --------------------------------------------------------------------------- #


def resolver_linea(nombre_linea: str, marca: str) -> tuple[int, bool]:
    """Devuelve (ttl_dias, es_evergreen) para la línea indicada en la marca dada.

    Busca en `etiquetas` clase='vertical' por nombre case-insensitive.
    Si no encuentra la línea devuelve (0, False) = evergreen por defecto
    (nunca ocultar por dato desconocido).

    Esta función toca la BD; solo se llama desde la capa API.
    """
    from .. import repos  # import local para mantener el módulo testeable sin BD

    et = repos.obtener_etiqueta_por_nombre(nombre_linea, "vertical", marca)
    if et is None:
        return (0, False)
    return (int(et.get("ttl_dias") or 0), bool(et.get("es_evergreen", False)))
