"""Constantes neutras de DOMINIO de la Consola Keni (allowlists de estados/metricas).

Modulo SIN dependencias internas: vive aparte de cualquier backend de persistencia
para que tanto el almacen de CONTENIDO (`ficheros.py`, YAML) como el OPERACIONAL
(`db.py`, SQLite) y la fachada (`repos.py`) puedan importarlo sin acoplarse entre si.

Antes estas constantes vivian en `db.py`; al separar el contenido (YAML) del dato
operacional (SQLite) se movieron aqui para que `ficheros.py` no dependa de `db.py`
por una simple allowlist (E5/H2, riesgo R5 del plan de persistencia).
"""

from __future__ import annotations

# Estados validos de una tarea/pendiente (operacional; vive en SQLite). El orden
# es el ciclo de vida: pendiente -> en curso -> hecha (#145, F5). "en_curso" se
# anadio al pasar el tablero a multiusuario; las tareas legadas solo tenian
# "pendiente"/"hecha" y siguen siendo validas (ambos estados se conservan).
ESTADOS_TAREA: tuple[str, ...] = ("pendiente", "en_curso", "hecha")

# Estados validos de una publicacion (flujo editorial; YAML). El flujo de aprobacion
# de equipo (#9, Fase 3) intercala `en_revision` entre el borrador y el aprobado:
#
#   borrador -> en_revision -> aprobado -> programado -> publicado
#                   |
#                   +-> (rechazo) -> borrador
#
# `en_revision` se anadio DESPUES del set original; un YAML legado nunca lo trae, asi
# que la lectura sigue siendo retrocompatible (los 4 estados originales validan igual).
ESTADOS_PUBLICACION: tuple[str, ...] = (
    "borrador",
    "en_revision",
    "aprobado",
    "programado",
    "publicado",
)

# Estado intermedio del flujo de aprobacion de equipo (#9): el autor envia su pieza a
# revision; un revisor/admin la aprueba o la devuelve a borrador.
ESTADO_EN_REVISION = "en_revision"
ESTADO_APROBADO = "aprobado"
ESTADO_PROGRAMADO = "programado"

# Estados del seguimiento comercial: activa (se captura), pausada (se detuvo la
# pauta), cerrada (KPI entregado / reporte hecho). Operacional; vive en SQLite.
ESTADOS_COMERCIAL: tuple[str, ...] = ("activa", "pausada", "cerrada")

# Solo las activas entran en la captura programada.
ESTADO_COMERCIAL_ACTIVA = "activa"

# Metricas que un objetivo/umbral comercial puede seguir (misma forma que el resto
# del producto).
METRICAS_COMERCIAL: tuple[str, ...] = ("interacciones", "alcance")

# Roles de usuario (auth multiusuario, #130). `admin` gestiona usuarios y todo lo
# demas; `editor` usa la consola pero NO toca /api/usuarios.
ROLES_USUARIO: tuple[str, ...] = ("admin", "editor")
ROL_ADMIN = "admin"
ROL_EDITOR = "editor"

# Cargos del equipo (transcripciones AMX): describen la FUNCION en el equipo, no los
# permisos. Ortogonal a `ROLES_USUARIO` (que sigue siendo admin/editor). `cobertura` es
# el flag separado que dice si esa persona entra en la rota de turnos: hay cargos que
# por funcion no cubren (estrategia, fotografia, gerencia) y community managers que si.
CARGOS_USUARIO: tuple[str, ...] = (
    "director",
    "gerente",
    "coordinador",
    "content_manager",
    "community_manager",
    "redactor",
    "guionista",
    "editorial",
    "estrategia",
    "fotografia",
)

# Estados de un turno de la rota (F4 · #144): `propuesto` es lo que Keni genera;
# `aprobado` es lo que Elias publica al equipo (nada se publica antes de aprobar).
# Operacional; vive en SQLite. Lo COMPARTEN los turnos de cobertura de eventos
# (`rota_turnos`) y los turnos de trabajo del horario del equipo (`rota_turnos_trabajo`):
# misma frontera de aprobacion (Keni propone -> Elias aprueba y publica).
ESTADOS_ROTA: tuple[str, ...] = ("propuesto", "aprobado")
ESTADO_ROTA_PROPUESTO = "propuesto"
ESTADO_ROTA_APROBADO = "aprobado"

# Estados del flujo de SWAPS de turno (intercambios entre companeros, #175). Cuando un
# CM (A) pide a otro (B) cubrirle un turno, la solicitud nace `propuesto`; B `acepta` o
# `rechaza`; si acepta, Elias (admin) `aprueba` (que aplica el swap en
# `rota_turnos_trabajo` y la solicitud queda `aplicado`) o `rechazado_admin`. El
# solicitante puede `cancelar` mientras la solicitud no sea terminal.
#
# Terminales: aplicado, rechazado, rechazado_admin, cancelado.
ESTADOS_SWAP: tuple[str, ...] = (
    "propuesto",
    "aceptado",
    "rechazado",
    "aprobado",
    "aplicado",
    "rechazado_admin",
    "cancelado",
)
ESTADO_SWAP_PROPUESTO = "propuesto"
ESTADO_SWAP_ACEPTADO = "aceptado"
ESTADO_SWAP_RECHAZADO = "rechazado"
ESTADO_SWAP_APROBADO = "aprobado"
ESTADO_SWAP_APLICADO = "aplicado"
ESTADO_SWAP_RECHAZADO_ADMIN = "rechazado_admin"
ESTADO_SWAP_CANCELADO = "cancelado"
ESTADOS_SWAP_TERMINALES: tuple[str, ...] = (
    ESTADO_SWAP_APLICADO,
    ESTADO_SWAP_RECHAZADO,
    ESTADO_SWAP_RECHAZADO_ADMIN,
    ESTADO_SWAP_CANCELADO,
)

# Franjas de un turno de TRABAJO del horario del equipo (F4 · #144, gestion de turnos):
# Elias reparte el dia entre `matutino` (Luis "de 8 de la manana a 4 de la tarde") y
# `vespertino` (Tescu "de 4 a 12 de la noche"); quien no entra ese dia `descansa`. Las
# VACACIONES/AUSENCIAS NO son una franja: son "ese dia no se asigna" (se excluye al
# miembro). Operacional; vive en SQLite (`rota_turnos_trabajo.franja`).
FRANJAS_TURNO: tuple[str, ...] = ("matutino", "vespertino", "descanso")
FRANJA_MATUTINO = "matutino"
FRANJA_VESPERTINO = "vespertino"
FRANJA_DESCANSO = "descanso"

# Franjas que cuentan como JORNADA LABORAL (el miembro entra a trabajar ese dia). El
# `descanso` no cubre el dia; por eso la rotacion de sabados solo mira las dos primeras.
FRANJAS_TRABAJO: tuple[str, ...] = (FRANJA_MATUTINO, FRANJA_VESPERTINO)

# Tipos de una AUSENCIA del horario (F4 · #144): el proponedor los respeta por igual
# (cualquier ausencia que cubra una fecha excluye al miembro ese dia). `vacaciones` es el
# caso de Elias ("las vacaciones, esto por el acomodo"); `descanso` es un dia libre
# planificado; `baja` una ausencia medica/forzosa; `otro` el cajon de sastre. Operacional;
# vive en SQLite (`rota_ausencias.tipo`).
TIPOS_AUSENCIA: tuple[str, ...] = ("vacaciones", "descanso", "baja", "otro")

# Tipo de COBERTURA de un evento del calendario (F4 · #144, ola B). Elias distingue tres
# casos reales: `transmision` (sale con senal/transmision), `imagenes` ("algunos no los
# vamos a transmitir, pero si los cubrimos con imagenes y fotografias") y `no_cubrir` (se
# trackea en el calendario pero NO se asigna cobertura). DEFAULT `transmision`: un evento
# legado (sin tipo) se trata como transmision, asi que el proponedor lo sigue cubriendo.
# Operacional; vive en SQLite (`rota_eventos.tipo_cobertura`).
TIPOS_COBERTURA: tuple[str, ...] = ("transmision", "imagenes", "no_cubrir")
TIPO_COBERTURA_TRANSMISION = "transmision"
TIPO_COBERTURA_IMAGENES = "imagenes"
TIPO_COBERTURA_NO_CUBRIR = "no_cubrir"

# Solo estos tipos GENERAN un turno de cobertura al proponer la rota: `no_cubrir` queda
# fuera (se trackea pero no se asigna a nadie).
TIPOS_COBERTURA_ASIGNABLES: tuple[str, ...] = (
    TIPO_COBERTURA_TRANSMISION,
    TIPO_COBERTURA_IMAGENES,
)

# Estados validos de una PIEZA (un post individual asociado a un evento o programa
# evergreen; #150 PARRILLA 2026). Una transmision como "LIV GOLF Andalucia R1" genera
# varias piezas (pre-evento FB/IG/X, reel IG/TK, historia dia, post-evento); el flujo de
# produccion va `pendiente` -> `en_curso` -> `listo` -> `publicado`. Operacional;
# vive en Postgres (`rota_piezas.estado`).
ESTADOS_PIEZA: tuple[str, ...] = ("pendiente", "en_curso", "listo", "publicado")

# Prioridad de un evento del calendario (F4 · #144, ola B): pista visual para que el
# equipo decida que cubre primero. DEFAULT `media`. Operacional (`rota_eventos.prioridad`).
PRIORIDADES_EVENTO: tuple[str, ...] = ("alta", "media", "baja")
PRIORIDAD_EVENTO_DEFECTO = "media"
