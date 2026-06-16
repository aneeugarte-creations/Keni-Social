"""Servidor MCP `keni-tablero`: controla el tablero de contenido de la Consola Keni.

Hermano de `keni-metricas` (que es SOLO LECTURA de metricas). Este MCP es el lado de
ESCRITURA sobre el CONTENIDO: crear, mover (cambiar estado) y listar items del tablero
desde Claude Code, hablando con la API HTTP de la Consola (`/api/publicaciones`). No persiste
nada por su cuenta: la Consola sigue siendo la unica fuente de verdad.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
