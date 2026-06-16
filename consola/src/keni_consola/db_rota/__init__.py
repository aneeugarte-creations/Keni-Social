"""Persistencia — dominio rota. Implementación de db.py (ver barrel `db.py`).

Barrel del paquete: re-exporta la MISMA superficie pública (y privada) que el módulo
`db_rota.py` original, partido por entidad en submódulos:
  - `eventos`        — eventos / transmisiones (`rota_eventos`).
  - `turnos`         — turnos (horario persona×dia×franja, `rota_turnos`) + helpers de
                       lote / copia de semana (asignacion flexible).
  - `ausencias`      — ausencias / vacaciones (`rota_ausencias`).
  - `programas`      — catalogo de programas (`rota_programas`).
  - `franjas_semana` — franjas por semana (`rota_franjas`).
  - `swaps`          — solicitudes de cambio de turno (`rota_swaps_turno`).
  - `config_franjas` — config de franjas por marca (`rota_config_franjas`).
  - `coordinacion`   — coordinador por celda (`rota_coordinacion`).
Lo compartido (fundación de `_db_comun`) vive en `_comun` y se re-exporta aquí. Importa
explícito (nunca `*`) para que `from .db_rota import X` e `import keni_consola.db_rota`
sigan funcionando igual y los consumidores (`db.py`, `db_publicaciones.py`) no cambien."""
from __future__ import annotations

# Fundación compartida re-exportada (preserva `db_rota.<nombre>` para los consumidores).
from ._comun import (
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
from .ausencias import (
    _COLS_AUSENCIA_ROTA,
    _SELECT_AUSENCIA_ROTA,
    _fila_a_ausencia_rota,
    actualizar_ausencia_rota,
    borrar_ausencia_rota,
    crear_ausencia_rota,
    listar_ausencias_rota,
    obtener_ausencia_rota,
)
from .config_franjas import (
    _COLS_CONFIG_FRANJAS,
    guardar_franjas_config,
    guardar_plantilla_franjas,
    obtener_franjas_config,
    obtener_plantilla_franjas,
)
from .coordinacion import (
    _COLS_COORDINACION,
    _SELECT_COORDINACION,
    _fila_a_coordinacion,
    actualizar_coordinador_rota,
    listar_coordinacion_semana,
    quitar_coordinador_rota,
)
from .eventos import (
    _CAMPOS_EDITABLES_EVENTO_ROTA,
    _CAMPOS_REPROGRAMAN_EVENTO,
    _COLS_EVENTO_ROTA,
    _SELECT_EVENTO_ROTA,
    _fila_a_evento_rota,
    actualizar_evento_rota,
    borrar_evento_rota,
    crear_evento_rota,
    listar_eventos_rota,
    obtener_evento_rota,
)
from .franjas_semana import (
    _COLS_FRANJA_SEMANA,
    _SELECT_FRANJA_SEMANA,
    _fila_a_franja_semana,
    actualizar_franja_semana,
    borrar_franja_semana,
    contar_turnos_de_franja,
    crear_franja_semana,
    listar_franjas_semana,
    obtener_franja_semana,
    inicializar_franjas_por_defecto,
)
from .programas import (
    _CAMPOS_EDITABLES_PROGRAMA_ROTA,
    _COLS_PROGRAMA_ROTA,
    _SELECT_PROGRAMA_ROTA,
    _fila_a_programa_rota,
    _programa_por_nombre,
    actualizar_programa_rota,
    borrar_programa_rota,
    contar_piezas_por_programa,
    crear_programa_rota,
    existe_programa_por_nombre,
    listar_programas_rota,
    obtener_programa_rota,
)
from .swaps import (
    _CAMPOS_EDITABLES_SWAP,
    _COLS_SWAP_TURNO,
    _SELECT_SWAP_TURNO,
    _fila_a_swap_turno,
    actualizar_swap_turno,
    aplicar_swap_turno,
    borrar_swap_turno,
    crear_swap_turno,
    listar_swaps_turno,
    obtener_swap_turno,
)
from .turnos import (
    _CAMPOS_EDITABLES_TURNO_ROTA,
    _COLS_TURNO_ROTA,
    _SELECT_TURNO_ROTA,
    _fila_a_turno_rota,
    actualizar_turno_rota,
    actualizar_turnos_rota_lote,
    aprobar_semana_rota,
    borrar_turno_rota,
    borrar_turnos_rota_lote,
    borrar_turnos_semana_rota,
    copiar_turnos_rota,
    crear_turno_rota,
    crear_turnos_rota_lote,
    desaprobar_semana_rota,
    duplicar_turno_rota,
    existe_turno_para,
    listar_turnos_rota,
    obtener_turno_rota,
)

__all__ = [
    # Fundación re-exportada (superficie `db_rota.<nombre>` original).
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
    # Eventos.
    "_CAMPOS_EDITABLES_EVENTO_ROTA",
    "_CAMPOS_REPROGRAMAN_EVENTO",
    "_COLS_EVENTO_ROTA",
    "_SELECT_EVENTO_ROTA",
    "_fila_a_evento_rota",
    "actualizar_evento_rota",
    "borrar_evento_rota",
    "crear_evento_rota",
    "listar_eventos_rota",
    "obtener_evento_rota",
    # Turnos (+ asignacion flexible).
    "_CAMPOS_EDITABLES_TURNO_ROTA",
    "_COLS_TURNO_ROTA",
    "_SELECT_TURNO_ROTA",
    "_fila_a_turno_rota",
    "actualizar_turno_rota",
    "actualizar_turnos_rota_lote",
    "aprobar_semana_rota",
    "borrar_turno_rota",
    "borrar_turnos_rota_lote",
    "borrar_turnos_semana_rota",
    "copiar_turnos_rota",
    "crear_turno_rota",
    "crear_turnos_rota_lote",
    "desaprobar_semana_rota",
    "duplicar_turno_rota",
    "existe_turno_para",
    "listar_turnos_rota",
    "obtener_turno_rota",
    # Ausencias.
    "_COLS_AUSENCIA_ROTA",
    "_SELECT_AUSENCIA_ROTA",
    "_fila_a_ausencia_rota",
    "actualizar_ausencia_rota",
    "borrar_ausencia_rota",
    "crear_ausencia_rota",
    "listar_ausencias_rota",
    "obtener_ausencia_rota",
    # Programas.
    "_CAMPOS_EDITABLES_PROGRAMA_ROTA",
    "_COLS_PROGRAMA_ROTA",
    "_SELECT_PROGRAMA_ROTA",
    "_fila_a_programa_rota",
    "_programa_por_nombre",
    "actualizar_programa_rota",
    "borrar_programa_rota",
    "contar_piezas_por_programa",
    "crear_programa_rota",
    "existe_programa_por_nombre",
    "listar_programas_rota",
    "obtener_programa_rota",
    # Franjas por semana.
    "_COLS_FRANJA_SEMANA",
    "_SELECT_FRANJA_SEMANA",
    "_fila_a_franja_semana",
    "actualizar_franja_semana",
    "borrar_franja_semana",
    "contar_turnos_de_franja",
    "crear_franja_semana",
    "listar_franjas_semana",
    "obtener_franja_semana",
    "inicializar_franjas_por_defecto",
    # Swaps.
    "_CAMPOS_EDITABLES_SWAP",
    "_COLS_SWAP_TURNO",
    "_SELECT_SWAP_TURNO",
    "_fila_a_swap_turno",
    "actualizar_swap_turno",
    "aplicar_swap_turno",
    "borrar_swap_turno",
    "crear_swap_turno",
    "listar_swaps_turno",
    "obtener_swap_turno",
    # Config de franjas.
    "_COLS_CONFIG_FRANJAS",
    "guardar_franjas_config",
    "guardar_plantilla_franjas",
    "obtener_franjas_config",
    "obtener_plantilla_franjas",
    # Coordinacion.
    "_COLS_COORDINACION",
    "_SELECT_COORDINACION",
    "_fila_a_coordinacion",
    "actualizar_coordinador_rota",
    "listar_coordinacion_semana",
    "quitar_coordinador_rota",
]
