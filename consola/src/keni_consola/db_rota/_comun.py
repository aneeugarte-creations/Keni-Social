"""Fundación compartida del dominio rota.

Re-exporta de `_db_comun` (la fundación de la capa DB) lo que usan los submódulos
de `db_rota` (`eventos`, `turnos`, `ausencias`, `programas`, `franjas_semana`,
`swaps`, `config_franjas`, `coordinacion`). Centraliza el import para que los
submódulos importen de aquí y el barrel `__init__.py` exponga estos nombres con la
MISMA superficie pública (y privada) que el módulo `db_rota.py` original."""
from __future__ import annotations

from .._db_comun import (
    _NOMBRE_FRANJA_DESCANSO,
    _NOMBRE_FRANJA_MANANA,
    _NOMBRE_FRANJA_TARDE,
    ESTADO_ROTA_APROBADO,
    ESTADO_ROTA_PROPUESTO,
    ESTADO_SWAP_PROPUESTO,
    ESTADOS_ROTA,
    PRIORIDAD_EVENTO_DEFECTO,
    PRIORIDADES_EVENTO,
    TIPO_COBERTURA_TRANSMISION,
    TIPOS_AUSENCIA,
    TIPOS_COBERTURA,
    Any,
    IntegrityError,
    _conectar,
    _inicializar_franjas_por_defecto_en,
    ahora_iso,
    date,
    timedelta,
    uuid,
)

__all__ = [
    "_NOMBRE_FRANJA_DESCANSO",
    "_NOMBRE_FRANJA_MANANA",
    "_NOMBRE_FRANJA_TARDE",
    "ESTADO_ROTA_APROBADO",
    "ESTADO_ROTA_PROPUESTO",
    "ESTADO_SWAP_PROPUESTO",
    "ESTADOS_ROTA",
    "PRIORIDAD_EVENTO_DEFECTO",
    "PRIORIDADES_EVENTO",
    "TIPO_COBERTURA_TRANSMISION",
    "TIPOS_AUSENCIA",
    "TIPOS_COBERTURA",
    "Any",
    "IntegrityError",
    "_conectar",
    "_inicializar_franjas_por_defecto_en",
    "ahora_iso",
    "date",
    "timedelta",
    "uuid",
]
