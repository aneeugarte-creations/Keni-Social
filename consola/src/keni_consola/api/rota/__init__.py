"""API Rota: parrilla y horarios del equipo (paquete por áreas).

Refactor de pura reubicación (sin cambio de comportamiento): el antiguo módulo
`api/rota.py` (~3090 LOC) se troceó en submódulos por área funcional. El descubridor
de `api/__init__.py` (`pkgutil.iter_modules`) NO desciende dentro de subpaquetes, así
que la ÚNICA superficie pública sigue siendo la variable `RUTAS` que este `__init__`
ensambla con EXACTAMENTE las mismas rutas, métodos y ORDEN que antes (el orden importa
en Starlette para paths solapados: las rutas de lote van ANTES que las paramétricas).

  - `_comun.py`    : helpers compartidos (identidad/equipo, marca, serialización, fechas).
  - `eventos.py`   : equipo + CRUD de eventos/transmisiones + duplicar.
  - `ausencias.py` : ausencias/vacaciones del equipo (CRUD).
  - `turnos.py`    : turnos (horario persona×día×franja): CRUD + lote + duplicar + aprobar.
  - `cobertura.py` : cobertura DERIVADA de un evento (no persistida).
  - `semana.py`    : copia de semana + panel de carga.
  - `export.py`    : exports .csv / .xlsx.
  - `swaps.py`     : solicitudes de cambio de turno entre compañeros (#175).
  - `programas.py` : catálogo de programas evergreen (#150).
  - `franjas.py`   : config de franjas (#185), franjas por semana y coordinación por celda.
"""

from __future__ import annotations

from starlette.routing import Route

from .ausencias import (
    actualizar_ausencia,
    borrar_ausencia,
    crear_ausencia,
    listar_ausencias,
)
from .cobertura import (
    cobertura_evento,
    cobertura_semana,
)
from .eventos import (
    actualizar_evento,
    borrar_evento,
    crear_evento,
    duplicar_evento,
    equipo,
    listar_eventos,
    repetir_evento,
)
from .export import (
    export_csv,
    export_xlsx,
)
from .franjas import (
    actualizar_franja_de_semana,
    borrar_franja_de_semana,
    crear_franja_de_semana,
    guardar_config_franjas,
    listar_coordinacion_de_semana,
    listar_franjas_de_semana,
    obtener_config_franjas,
    quitar_coordinador_de_celda,
    set_coordinador_de_celda,
)
from .programas import (
    actualizar_programa,
    borrar_programa,
    crear_programa,
    listar_programas,
)
from .semana import (
    carga_semana,
    copiar_semana,
)
from .swaps import (
    aceptar_swap,
    aprobar_swap,
    cancelar_swap,
    crear_swap,
    listar_swaps,
    rechazar_swap,
    rechazar_swap_admin,
)
from .turnos import (
    actualizar_turno,
    actualizar_turnos_lote,
    aprobar_turnos,
    borrar_turno,
    borrar_turnos_lote,
    crear_turno,
    crear_turnos_lote,
    despublicar_turnos,
    duplicar_turno,
    mis_turnos,
    mis_turnos_mes,
    turnos_mes,
    turnos_semana,
)

__all__ = [
    "RUTAS",
    "equipo",
    "listar_eventos",
    "crear_evento",
    "actualizar_evento",
    "borrar_evento",
    "duplicar_evento",
    "repetir_evento",
    "listar_ausencias",
    "crear_ausencia",
    "actualizar_ausencia",
    "borrar_ausencia",
    "turnos_semana",
    "crear_turno",
    "actualizar_turno",
    "borrar_turno",
    "borrar_turnos_lote",
    "crear_turnos_lote",
    "actualizar_turnos_lote",
    "duplicar_turno",
    "aprobar_turnos",
    "despublicar_turnos",
    "mis_turnos",
    "mis_turnos_mes",
    "turnos_mes",
    "cobertura_semana",
    "cobertura_evento",
    "copiar_semana",
    "carga_semana",
    "export_csv",
    "export_xlsx",
    "listar_swaps",
    "crear_swap",
    "aceptar_swap",
    "rechazar_swap",
    "aprobar_swap",
    "rechazar_swap_admin",
    "cancelar_swap",
    "listar_programas",
    "crear_programa",
    "actualizar_programa",
    "borrar_programa",
    "obtener_config_franjas",
    "guardar_config_franjas",
    "listar_franjas_de_semana",
    "crear_franja_de_semana",
    "actualizar_franja_de_semana",
    "borrar_franja_de_semana",
    "listar_coordinacion_de_semana",
    "set_coordinador_de_celda",
    "quitar_coordinador_de_celda",
]


RUTAS = [
    Route("/api/rota/equipo", equipo, methods=["GET"]),
    # Eventos / transmisiones.
    Route("/api/rota/eventos", listar_eventos, methods=["GET"]),
    Route("/api/rota/eventos", crear_evento, methods=["POST"]),
    Route("/api/rota/eventos/{evento_id}", actualizar_evento, methods=["PATCH"]),
    Route("/api/rota/eventos/{evento_id}", borrar_evento, methods=["DELETE"]),
    Route("/api/rota/eventos/{evento_id}/duplicar", duplicar_evento, methods=["POST"]),
    Route("/api/rota/eventos/{evento_id}/repetir", repetir_evento, methods=["POST"]),
    # Turnos (horario persona×dia×franja). OJO: las rutas de lote DEBEN ir ANTES que las
    # paramétricas `{turno_id}`, si no Starlette captura "lote"/"lote/borrar"/"aprobar" como
    # id de turno y devuelve 404/405.
    Route("/api/rota/turnos/lote", crear_turnos_lote, methods=["POST"]),
    Route("/api/rota/turnos/lote", actualizar_turnos_lote, methods=["PATCH"]),
    Route("/api/rota/turnos/lote/borrar", borrar_turnos_lote, methods=["POST"]),
    Route("/api/rota/turnos/aprobar", aprobar_turnos, methods=["POST"]),
    Route("/api/rota/turnos/despublicar", despublicar_turnos, methods=["POST"]),
    Route("/api/rota/turnos/mes", turnos_mes, methods=["GET"]),
    Route("/api/rota/turnos", turnos_semana, methods=["GET"]),
    Route("/api/rota/turnos", crear_turno, methods=["POST"]),
    Route("/api/rota/turnos/{turno_id}/duplicar", duplicar_turno, methods=["POST"]),
    Route("/api/rota/turnos/{turno_id}", actualizar_turno, methods=["PATCH"]),
    Route("/api/rota/turnos/{turno_id}", borrar_turno, methods=["DELETE"]),
    Route("/api/rota/mis-turnos/mes", mis_turnos_mes, methods=["GET"]),
    Route("/api/rota/mis-turnos", mis_turnos, methods=["GET"]),
    # Franjas POR SEMANA ("Mundial"): cada lunes tiene sus franjas (Mañana/Tarde/Descanso
    # por defecto, configurables con N franjas y solapes permitidos).
    Route("/api/rota/semana/{lunes}/franjas", listar_franjas_de_semana, methods=["GET"]),
    Route("/api/rota/semana/{lunes}/franjas", crear_franja_de_semana, methods=["POST"]),
    Route("/api/rota/franjas/{franja_id}", actualizar_franja_de_semana, methods=["PATCH"]),
    Route("/api/rota/franjas/{franja_id}", borrar_franja_de_semana, methods=["DELETE"]),
    # Coordinador por turno (ola "coord"): cada celda (fecha, franja_id) puede tener UN
    # coordinador asignado entre usuarios con `puede_coordinar=true`.
    Route("/api/rota/semana/{lunes}/coordinacion", listar_coordinacion_de_semana, methods=["GET"]),
    Route("/api/rota/coordinacion", set_coordinador_de_celda, methods=["PUT"]),
    Route("/api/rota/coordinacion", quitar_coordinador_de_celda, methods=["DELETE"]),
    # Cobertura DERIVADA (vista, sin persistencia).
    Route("/api/rota/cobertura", cobertura_semana, methods=["GET"]),
    Route("/api/rota/cobertura/evento/{evento_id}", cobertura_evento, methods=["GET"]),
    # Ausencias / vacaciones.
    Route("/api/rota/ausencias", listar_ausencias, methods=["GET"]),
    Route("/api/rota/ausencias", crear_ausencia, methods=["POST"]),
    Route("/api/rota/ausencias/{ausencia_id}", actualizar_ausencia, methods=["PATCH"]),
    Route("/api/rota/ausencias/{ausencia_id}", borrar_ausencia, methods=["DELETE"]),
    # Copia de semana + panel de carga.
    Route("/api/rota/copiar-semana", copiar_semana, methods=["POST"]),
    Route("/api/rota/carga", carga_semana, methods=["GET"]),
    # Exports.
    Route("/api/rota/export.csv", export_csv, methods=["GET"]),
    Route("/api/rota/export.xlsx", export_xlsx, methods=["GET"]),
    # Piezas (#150 PARRILLA): RETIRADO del API. El tablero de contenido cubre la cobertura
    # de eventos (`contenido` con `evento_id`/`flujo='evento'`); `migrar_piezas()` convierte
    # las piezas legadas al arrancar. La tabla `rota_piezas` y su capa db/dominio se
    # conservan (histórico + migración), pero NO se exponen por HTTP.
    # Catálogo de programas evergreen (#150). Renombrar hace cascada sobre rota_piezas.
    Route("/api/rota/programas", listar_programas, methods=["GET"]),
    Route("/api/rota/programas", crear_programa, methods=["POST"]),
    Route("/api/rota/programas/{programa_id}", actualizar_programa, methods=["PATCH"]),
    Route("/api/rota/programas/{programa_id}", borrar_programa, methods=["DELETE"]),
    # Solicitudes de cambio de turno entre companeros (#175).
    Route("/api/rota/swaps", listar_swaps, methods=["GET"]),
    Route("/api/rota/swaps", crear_swap, methods=["POST"]),
    Route("/api/rota/swaps/{swap_id}/aceptar", aceptar_swap, methods=["POST"]),
    Route("/api/rota/swaps/{swap_id}/rechazar", rechazar_swap, methods=["POST"]),
    Route("/api/rota/swaps/{swap_id}/aprobar", aprobar_swap, methods=["POST"]),
    Route("/api/rota/swaps/{swap_id}/rechazar-admin", rechazar_swap_admin, methods=["POST"]),
    Route("/api/rota/swaps/{swap_id}/cancelar", cancelar_swap, methods=["POST"]),
    # Configuración editorial de FRANJAS de cobertura (#185). GET libre; PATCH solo admin.
    Route("/api/rota/config/franjas", obtener_config_franjas, methods=["GET"]),
    Route("/api/rota/config/franjas", guardar_config_franjas, methods=["PATCH"]),
]
