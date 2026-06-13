"""Cimientos de persistencia: conexion, locks y esquema/migraciones (Postgres) — FACADE.

Paquete troceado por areas (refactor de pura reubicacion desde el modulo `_db_core.py`):
- `conexion`: `_conectar`/`conectar`, advisory locks (`_clave_lock`, `lock_barrido`).
- `esquema`: DDL operacional (`_DDL_ESQUEMA`) + creacion/migracion (`_crear_esquema`).
- `migraciones`: framework (`Migracion`, runner) + REGISTRO (`MIGRACIONES_*`).
- `migraciones_columnas` / `migraciones_modelo`: las `_migrar_*` (columnas vs. turnos/franjas).
- `_comun`: helpers compartidos (inspeccion de esquema, parsing de horas/franjas, logger).

Este `__init__` re-exporta EXACTAMENTE la misma superficie que exponia el modulo unico, para
que `db.py`/`_db_comun.py` y los tests sigan haciendo `from ._db_core import (...)` / `_db_core.<algo>`
sin cambios. La superficie publica via `*` la fija `__all__` (identica a la del modulo original).
"""
from __future__ import annotations

from ._comun import (
    _columnas_existentes as _columnas_existentes,
)
from ._comun import (
    _franja_para_hora_migracion as _franja_para_hora_migracion,
)
from ._comun import (
    _log as _log,
)
from ._comun import (
    _parsear_hora_a_minutos as _parsear_hora_a_minutos,
)
from ._comun import (
    _tabla_existe as _tabla_existe,
)
from .conexion import (
    _LOCK_NS_BARRIDO as _LOCK_NS_BARRIDO,
)
from .conexion import (
    _clave_lock as _clave_lock,
)
from .conexion import (
    _conectar as _conectar,
)
from .conexion import (
    _esquemas_asegurados as _esquemas_asegurados,
)
from .conexion import (
    _lock_esquemas as _lock_esquemas,
)
from .conexion import (
    conectar as conectar,
)
from .conexion import (
    lock_barrido as lock_barrido,
)
from .esquema import (
    _DDL_ESQUEMA as _DDL_ESQUEMA,
)
from .esquema import (
    _crear_esquema as _crear_esquema,
)
from .esquema import (
    _crear_esquema_bajo_lock as _crear_esquema_bajo_lock,
)
from .esquema import (
    arrancar_persistencia as arrancar_persistencia,
)
from .migraciones import (
    _DDL_SCHEMA_MIGRACIONES as _DDL_SCHEMA_MIGRACIONES,
)
from .migraciones import (
    MIGRACIONES as MIGRACIONES,
)
from .migraciones import (
    MIGRACIONES_POST_DDL as MIGRACIONES_POST_DDL,
)
from .migraciones import (
    MIGRACIONES_PRE_DDL as MIGRACIONES_PRE_DDL,
)
from .migraciones import (
    Migracion as Migracion,
)
from .migraciones import (
    _aplicar_migraciones as _aplicar_migraciones,
)
from .migraciones import (
    _id_migracion as _id_migracion,
)
from .migraciones_columnas import (
    _COLUMNAS_APROBACIONES_AMPLIADAS as _COLUMNAS_APROBACIONES_AMPLIADAS,
)
from .migraciones_columnas import (
    _COLUMNAS_COMERCIAL_PUBLICACIONES_AMPLIADAS as _COLUMNAS_COMERCIAL_PUBLICACIONES_AMPLIADAS,
)
from .migraciones_columnas import (
    _COLUMNAS_COMERCIAL_SNAPSHOTS_AMPLIADAS as _COLUMNAS_COMERCIAL_SNAPSHOTS_AMPLIADAS,
)
from .migraciones_columnas import (
    _COLUMNAS_CONTENIDO_AMPLIADAS as _COLUMNAS_CONTENIDO_AMPLIADAS,
)
from .migraciones_columnas import (
    _COLUMNAS_CONTENIDO_PLATAFORMA_AMPLIADAS as _COLUMNAS_CONTENIDO_PLATAFORMA_AMPLIADAS,
)
from .migraciones_columnas import (
    _COLUMNAS_DAEMON_LATIDOS_AMPLIADAS as _COLUMNAS_DAEMON_LATIDOS_AMPLIADAS,
)
from .migraciones_columnas import (
    _COLUMNAS_EVENTO_ROTA_AMPLIADAS as _COLUMNAS_EVENTO_ROTA_AMPLIADAS,
)
from .migraciones_columnas import (
    _COLUMNAS_FUENTES_RSS_AMPLIADAS as _COLUMNAS_FUENTES_RSS_AMPLIADAS,
)
from .migraciones_columnas import (
    _COLUMNAS_GRUPOS_HASHTAGS_AMPLIADAS as _COLUMNAS_GRUPOS_HASHTAGS_AMPLIADAS,
)
from .migraciones_columnas import (
    _COLUMNAS_NOTICIAS_CLUSTERS_AMPLIADAS as _COLUMNAS_NOTICIAS_CLUSTERS_AMPLIADAS,
)
from .migraciones_columnas import (
    _COLUMNAS_NOTICIAS_ITEMS_AMPLIADAS as _COLUMNAS_NOTICIAS_ITEMS_AMPLIADAS,
)
from .migraciones_columnas import (
    _COLUMNAS_PIEZA_ROTA_AMPLIADAS as _COLUMNAS_PIEZA_ROTA_AMPLIADAS,
)
from .migraciones_columnas import (
    _COLUMNAS_PROGRAMA_AMPLIADAS as _COLUMNAS_PROGRAMA_AMPLIADAS,
)
from .migraciones_columnas import (
    _COLUMNAS_SWAP_AMPLIADAS as _COLUMNAS_SWAP_AMPLIADAS,
)
from .migraciones_columnas import (
    _COLUMNAS_TS_CANON as _COLUMNAS_TS_CANON,
)
from .migraciones_columnas import (
    _COLUMNAS_TURNO_ROTA_AMPLIADAS as _COLUMNAS_TURNO_ROTA_AMPLIADAS,
)
from .migraciones_columnas import (
    _COLUMNAS_USUARIOS_AMPLIADAS as _COLUMNAS_USUARIOS_AMPLIADAS,
)
from .migraciones_columnas import (
    _COLUMNAS_USUARIOS_RETIRADAS as _COLUMNAS_USUARIOS_RETIRADAS,
)
from .migraciones_columnas import (
    _INDICES_UNICOS_IDEMPOTENCIA as _INDICES_UNICOS_IDEMPOTENCIA,
)
from .migraciones_columnas import (
    _MARCA_PILOTO_ROTA as _MARCA_PILOTO_ROTA,
)
from .migraciones_columnas import (
    _RE_TS_CON_ZONA as _RE_TS_CON_ZONA,
)
from .migraciones_columnas import (
    _RE_TS_NAIVE_FRACCION as _RE_TS_NAIVE_FRACCION,
)
from .migraciones_columnas import (
    _TABLAS_GRID_ROTA_MARCA as _TABLAS_GRID_ROTA_MARCA,
)
from .migraciones_columnas import (
    _asegurar_marca_grid_rota as _asegurar_marca_grid_rota,
)
from .migraciones_columnas import (
    _backfill_pesos_fuente as _backfill_pesos_fuente,
)
from .migraciones_columnas import (
    _crear_indices_unicos_idempotencia as _crear_indices_unicos_idempotencia,
)
from .migraciones_columnas import (
    _dedup_turnos_rota as _dedup_turnos_rota,
)
from .migraciones_columnas import (
    _migrar_columnas_aprobaciones as _migrar_columnas_aprobaciones,
)
from .migraciones_columnas import (
    _migrar_columnas_campanias as _migrar_columnas_campanias,
)
from .migraciones_columnas import (
    _migrar_columnas_comercial as _migrar_columnas_comercial,
)
from .migraciones_columnas import (
    _migrar_columnas_contenido as _migrar_columnas_contenido,
)
from .migraciones_columnas import (
    _migrar_columnas_contenido_plataforma as _migrar_columnas_contenido_plataforma,
)
from .migraciones_columnas import (
    _migrar_columnas_daemon_latidos as _migrar_columnas_daemon_latidos,
)
from .migraciones_columnas import (
    _migrar_columnas_etiquetas as _migrar_columnas_etiquetas,
)
from .migraciones_columnas import (
    _migrar_columnas_eventos_rota as _migrar_columnas_eventos_rota,
)
from .migraciones_columnas import (
    _migrar_columnas_fuentes_rss as _migrar_columnas_fuentes_rss,
)
from .migraciones_columnas import (
    _migrar_columnas_grupos_hashtags as _migrar_columnas_grupos_hashtags,
)
from .migraciones_columnas import (
    _migrar_columnas_noticias_algoritmo as _migrar_columnas_noticias_algoritmo,
)
from .migraciones_columnas import (
    _migrar_columnas_noticias_clusters as _migrar_columnas_noticias_clusters,
)
from .migraciones_columnas import (
    _migrar_columnas_noticias_items as _migrar_columnas_noticias_items,
)
from .migraciones_columnas import (
    _migrar_columnas_piezas_rota as _migrar_columnas_piezas_rota,
)
from .migraciones_columnas import (
    _migrar_columnas_plantillas_diseno as _migrar_columnas_plantillas_diseno,
)
from .migraciones_columnas import (
    _migrar_columnas_programas as _migrar_columnas_programas,
)
from .migraciones_columnas import (
    _migrar_columnas_swaps as _migrar_columnas_swaps,
)
from .migraciones_columnas import (
    _migrar_columnas_turnos_rota as _migrar_columnas_turnos_rota,
)
from .migraciones_columnas import (
    _migrar_columnas_usuarios as _migrar_columnas_usuarios,
)
from .migraciones_columnas import (
    _migrar_columnas_video_composiciones as _migrar_columnas_video_composiciones,
)
from .migraciones_columnas import (
    _migrar_green_a_evergreen as _migrar_green_a_evergreen,
)
from .migraciones_columnas import (
    _migrar_renombre_catalogo_media as _migrar_renombre_catalogo_media,
)
from .migraciones_columnas import (
    _normalizar_timestamps_texto as _normalizar_timestamps_texto,
)
from .migraciones_modelo import (
    _MIGR_FRANJA_MATUTINO_FIN_MIN as _MIGR_FRANJA_MATUTINO_FIN_MIN,
)
from .migraciones_modelo import (
    _MIGR_FRANJA_MATUTINO_INICIO_MIN as _MIGR_FRANJA_MATUTINO_INICIO_MIN,
)
from .migraciones_modelo import (
    _MIGR_FRANJA_VESPERTINO_FIN_MIN as _MIGR_FRANJA_VESPERTINO_FIN_MIN,
)
from .migraciones_modelo import (
    _MIGR_FRANJA_VESPERTINO_INICIO_MIN as _MIGR_FRANJA_VESPERTINO_INICIO_MIN,
)
from .migraciones_modelo import (
    _NOMBRE_FRANJA_DESCANSO as _NOMBRE_FRANJA_DESCANSO,
)
from .migraciones_modelo import (
    _NOMBRE_FRANJA_MANANA as _NOMBRE_FRANJA_MANANA,
)
from .migraciones_modelo import (
    _NOMBRE_FRANJA_TARDE as _NOMBRE_FRANJA_TARDE,
)
from .migraciones_modelo import (
    _config_franjas_template as _config_franjas_template,
)
from .migraciones_modelo import (
    _migrar_modelo_franjas as _migrar_modelo_franjas,
)
from .migraciones_modelo import (
    _migrar_modelo_turnos as _migrar_modelo_turnos,
)
from .migraciones_modelo import (
    _sembrar_franjas_por_defecto_en as _sembrar_franjas_por_defecto_en,
)

__all__ = [
    '_COLUMNAS_APROBACIONES_AMPLIADAS',
    '_COLUMNAS_COMERCIAL_PUBLICACIONES_AMPLIADAS',
    '_COLUMNAS_COMERCIAL_SNAPSHOTS_AMPLIADAS',
    '_COLUMNAS_CONTENIDO_AMPLIADAS',
    '_COLUMNAS_CONTENIDO_PLATAFORMA_AMPLIADAS',
    '_COLUMNAS_EVENTO_ROTA_AMPLIADAS',
    '_COLUMNAS_FUENTES_RSS_AMPLIADAS',
    '_COLUMNAS_GRUPOS_HASHTAGS_AMPLIADAS',
    '_COLUMNAS_NOTICIAS_CLUSTERS_AMPLIADAS',
    '_COLUMNAS_NOTICIAS_ITEMS_AMPLIADAS',
    '_COLUMNAS_PIEZA_ROTA_AMPLIADAS',
    '_COLUMNAS_PROGRAMA_AMPLIADAS',
    '_COLUMNAS_SWAP_AMPLIADAS',
    '_COLUMNAS_TURNO_ROTA_AMPLIADAS',
    '_COLUMNAS_USUARIOS_AMPLIADAS',
    '_COLUMNAS_USUARIOS_RETIRADAS',
    '_DDL_ESQUEMA',
    '_DDL_SCHEMA_MIGRACIONES',
    '_INDICES_UNICOS_IDEMPOTENCIA',
    '_LOCK_NS_BARRIDO',
    'MIGRACIONES',
    'MIGRACIONES_POST_DDL',
    'MIGRACIONES_PRE_DDL',
    'Migracion',
    '_MIGR_FRANJA_MATUTINO_FIN_MIN',
    '_MIGR_FRANJA_MATUTINO_INICIO_MIN',
    '_MIGR_FRANJA_VESPERTINO_FIN_MIN',
    '_MIGR_FRANJA_VESPERTINO_INICIO_MIN',
    '_NOMBRE_FRANJA_DESCANSO',
    '_NOMBRE_FRANJA_MANANA',
    '_NOMBRE_FRANJA_TARDE',
    '_aplicar_migraciones',
    '_clave_lock',
    '_columnas_existentes',
    '_id_migracion',
    '_conectar',
    '_config_franjas_template',
    '_crear_esquema',
    '_crear_indices_unicos_idempotencia',
    '_esquemas_asegurados',
    '_franja_para_hora_migracion',
    '_lock_esquemas',
    '_migrar_columnas_aprobaciones',
    '_migrar_columnas_comercial',
    '_migrar_columnas_contenido',
    '_migrar_columnas_contenido_plataforma',
    '_migrar_columnas_etiquetas',
    '_migrar_columnas_eventos_rota',
    '_migrar_columnas_fuentes_rss',
    '_migrar_columnas_grupos_hashtags',
    '_migrar_columnas_noticias_algoritmo',
    '_migrar_columnas_noticias_clusters',
    '_migrar_columnas_piezas_rota',
    '_migrar_columnas_plantillas_diseno',
    '_migrar_columnas_programas',
    '_migrar_columnas_swaps',
    '_migrar_columnas_turnos_rota',
    '_migrar_columnas_usuarios',
    '_migrar_columnas_video_composiciones',
    '_migrar_modelo_franjas',
    '_migrar_modelo_turnos',
    '_parsear_hora_a_minutos',
    '_sembrar_franjas_por_defecto_en',
    '_tabla_existe',
    'arrancar_persistencia',
    'conectar',
    'lock_barrido',
]
