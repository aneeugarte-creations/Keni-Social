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

# Estados validos de una publicacion (flujo editorial borrador -> publicado; YAML).
ESTADOS_PUBLICACION: tuple[str, ...] = ("borrador", "aprobado", "programado", "publicado")

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

# Estados de un turno de la rota (F4 · #144): `propuesto` es lo que Keni genera;
# `aprobado` es lo que Elias publica al equipo (nada se publica antes de aprobar).
# Operacional; vive en SQLite.
ESTADOS_ROTA: tuple[str, ...] = ("propuesto", "aprobado")
ESTADO_ROTA_PROPUESTO = "propuesto"
ESTADO_ROTA_APROBADO = "aprobado"
