"""Persistencia — dominio parrilla. Implementación de db.py (ver barrel `db.py`).

Barrel del paquete: re-exporta la MISMA superficie pública (y privada) que el módulo
`db_parrilla.py` original, partido por sub-área en submódulos:
  - `piezas`     — piezas de la parrilla (tabla `rota_piezas`).
  - `propuestas` — propuestas de importación desde documento (`parrilla_propuesta`).
  - `insumos`    — insumos del día / cajones (`insumos_lote` + `insumos_item`).
Lo compartido vive en `_comun` (re-export de `_db_comun`). Importa explícito (nunca `*`)
para que `from .db_parrilla import X` e `import keni_consola.db_parrilla` sigan funcionando
igual y `db.py` no necesite cambios."""
from __future__ import annotations

# Fundación compartida re-exportada (preserva `db_parrilla.<nombre>` para los consumidores).
from ._comun import (
    ESTADO_ROTA_PROPUESTO,
    ESTADOS_PIEZA_PARRILLA,
    Any,
    _conectar,
    date,
    datetime,
    json,
    timedelta,
    uuid,
)
from .insumos import (
    _CAMPOS_EDITABLES_INSUMO_ITEM,
    _COLS_INSUMO_ITEM,
    _COLS_INSUMO_LOTE,
    _SELECT_INSUMO_ITEM,
    _SELECT_INSUMO_LOTE,
    _fila_a_insumo_item,
    _fila_a_insumo_lote,
    actualizar_insumo_item,
    actualizar_insumo_lote,
    borrar_insumo_item,
    borrar_insumo_lote,
    crear_insumo_items,
    crear_insumo_lote,
    dias_con_insumos,
    listar_insumo_items,
    listar_lotes,
    marcar_insumo_item_usado,
    obtener_insumo_item,
    obtener_insumo_lote,
    reparar_lotes_parseando_sueltos,
)
from .piezas import (
    _CAMPOS_EDITABLES_PIEZA_ROTA,
    _COLS_PIEZA_ROTA,
    _SELECT_PIEZA_ROTA,
    _fila_a_pieza_rota,
    actualizar_pieza_rota,
    borrar_pieza_rota,
    borrar_piezas_rota_lote,
    crear_pieza_rota,
    duplicar_pieza_rota,
    listar_piezas_rota,
    obtener_pieza_rota,
)
from .propuestas import (
    _CAMPOS_EDITABLES_PROPUESTA,
    _COLS_PROPUESTA,
    _SELECT_PROPUESTA,
    _fila_a_propuesta,
    _lunes_iso_de,
    actualizar_propuesta_parrilla,
    aplicar_propuesta_parrilla,
    crear_propuesta_parrilla,
    listar_propuestas_parrilla,
    obtener_propuesta_parrilla,
)

__all__ = [
    # Fundación re-exportada.
    "Any",
    "ESTADOS_PIEZA_PARRILLA",
    "ESTADO_ROTA_PROPUESTO",
    "_conectar",
    "date",
    "datetime",
    "json",
    "timedelta",
    "uuid",
    # Piezas.
    "_CAMPOS_EDITABLES_PIEZA_ROTA",
    "_COLS_PIEZA_ROTA",
    "_SELECT_PIEZA_ROTA",
    "_fila_a_pieza_rota",
    "actualizar_pieza_rota",
    "borrar_pieza_rota",
    "borrar_piezas_rota_lote",
    "crear_pieza_rota",
    "duplicar_pieza_rota",
    "listar_piezas_rota",
    "obtener_pieza_rota",
    # Propuestas.
    "_CAMPOS_EDITABLES_PROPUESTA",
    "_COLS_PROPUESTA",
    "_SELECT_PROPUESTA",
    "_fila_a_propuesta",
    "_lunes_iso_de",
    "actualizar_propuesta_parrilla",
    "aplicar_propuesta_parrilla",
    "crear_propuesta_parrilla",
    "listar_propuestas_parrilla",
    "obtener_propuesta_parrilla",
    # Insumos.
    "_CAMPOS_EDITABLES_INSUMO_ITEM",
    "_COLS_INSUMO_ITEM",
    "_COLS_INSUMO_LOTE",
    "_SELECT_INSUMO_ITEM",
    "_SELECT_INSUMO_LOTE",
    "_fila_a_insumo_item",
    "_fila_a_insumo_lote",
    "actualizar_insumo_item",
    "actualizar_insumo_lote",
    "borrar_insumo_item",
    "borrar_insumo_lote",
    "crear_insumo_items",
    "crear_insumo_lote",
    "dias_con_insumos",
    "listar_insumo_items",
    "listar_lotes",
    "marcar_insumo_item_usado",
    "obtener_insumo_item",
    "obtener_insumo_lote",
    "reparar_lotes_parseando_sueltos",
]
