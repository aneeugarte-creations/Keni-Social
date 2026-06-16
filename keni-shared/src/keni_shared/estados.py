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

# Estado de UNA fila por plataforma (`contenido_plataforma.estado`). LISTA CANONICA UNICA
# (colapso 2026-06): se fundió el vocabulario editorial y el del tablero en una sola lista,
# y se retiró `aprobado` (aprobar = juntar los 2 likes -> auto-programa al siguiente hueco):
#
#   borrador -> en_revision -> programado -> publicado
#
# `borrador` es la fase "en preparación": su detalle son los flags `falta_*` (copy/imagen/
# hashtags/...). Las filas viejas se migran: pendiente/en_curso -> borrador; aprobado ->
# en_revision (conserva sus likes en `contenido_aprobaciones`; se re-programa al avanzar).
ESTADOS_CONTENIDO_PLATAFORMA: tuple[str, ...] = (
    "borrador",
    "en_revision",
    "programado",
    "publicado",
)
