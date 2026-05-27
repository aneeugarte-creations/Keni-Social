"""Constantes neutras de DOMINIO de la Consola Keni (allowlists de estados/metricas).

Modulo SIN dependencias internas: vive aparte de cualquier backend de persistencia
para que tanto el almacen de CONTENIDO (`ficheros.py`, YAML) como el OPERACIONAL
(`db.py`, SQLite) y la fachada (`repos.py`) puedan importarlo sin acoplarse entre si.

Antes estas constantes vivian en `db.py`; al separar el contenido (YAML) del dato
operacional (SQLite) se movieron aqui para que `ficheros.py` no dependa de `db.py`
por una simple allowlist (E5/H2, riesgo R5 del plan de persistencia).
"""

from __future__ import annotations

# Estados validos de una tarea (operacional; vive en SQLite).
ESTADOS_TAREA: tuple[str, ...] = ("pendiente", "hecha")

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
