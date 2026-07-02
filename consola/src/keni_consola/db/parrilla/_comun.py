"""Fundación compartida del dominio parrilla.

Re-exporta de `_db_comun` (la fundación de la capa DB) lo que usan los submódulos
de `db_parrilla` (`piezas`, `propuestas`, `insumos`). Centraliza el import para que
los submódulos importen de aquí y el barrel `__init__.py` exponga estos nombres con
la MISMA superficie pública que el módulo `db_parrilla.py` original."""
from __future__ import annotations

from .._comun import (
    ESTADO_ROTA_PROPUESTO,
    ESTADOS_PIEZA_PARRILLA,
    UTC,
    Any,
    _conectar,
    date,
    datetime,
    json,
    timedelta,
    uuid,
)

__all__ = [
    "UTC",
    "ESTADO_ROTA_PROPUESTO",
    "ESTADOS_PIEZA_PARRILLA",
    "Any",
    "_conectar",
    "date",
    "datetime",
    "json",
    "timedelta",
    "uuid",
]
