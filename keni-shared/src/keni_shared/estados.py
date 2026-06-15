"""Allowlists CANONICAS del tablero de contenido (padre + filas por plataforma).

Fuente UNICA de los estados/clases/flujos del tablero, importada tanto por la
Consola (`keni_consola.estados`, que las re-exporta para sus consumidores) como
por el MCP de tablero (`keni_tablero.tools`, que valida ANTES de tocar la red).

Solo TUPLAS de literales: este paquete es la capa mas baja del monorepo (sin
dependencias) y aqui no debe entrar logica de negocio.
"""

from __future__ import annotations

# `clase` de un item del tablero: contenido publicable (con filas por plataforma) o
# una tarea libre del equipo (relevo/recado, sin plataformas).
CLASES_CONTENIDO: tuple[str, ...] = ("contenido", "tarea")

# `flujo` editorial de un contenido: lo importante del dia, evergreen (always-on) o
# cobertura de un evento previsto. "" para tareas libres (clase=tarea).
FLUJOS_CONTENIDO: tuple[str, ...] = ("importante", "evergreen", "evento")

# Estado de un contenido a nivel PADRE (resumen editable / estado directo de una tarea
# libre). Cubre el ciclo de una tarea (pendiente/en_curso/hecha) y sirve de resumen.
ESTADOS_CONTENIDO: tuple[str, ...] = ("pendiente", "en_curso", "hecha")

# Estado de UNA fila por plataforma (`contenido_plataforma.estado`). Ciclo unificado que
# fusiona el de pieza (pendiente/en_curso/listo/publicado) y el editorial de publicacion
# (borrador/en_revision/aprobado/programado/publicado):
#
#   pendiente -> en_curso -> en_revision -> aprobado -> programado -> publicado
#
# Mapeos de migracion: `borrador` -> `pendiente`; `listo` (pieza) -> `aprobado`.
ESTADOS_CONTENIDO_PLATAFORMA: tuple[str, ...] = (
    "pendiente",
    "en_curso",
    "en_revision",
    "aprobado",
    "programado",
    "publicado",
)
