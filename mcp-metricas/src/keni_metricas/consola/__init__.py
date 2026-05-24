"""Consola Keni: capa de GESTION web LOCAL para equipo NO tecnico.

Filosofia: la consola gestiona; Claude Code queda DEBAJO como motor de
ejecucion, lanzado desde aqui. Privacidad por diseno: bind solo a 127.0.0.1,
sin nube, reutiliza el stack Python del MCP (Starlette/uvicorn/httpx, que vienen
con el SDK `mcp`) y las funciones de metricas ya existentes (`reporte`,
`dashboard`, `picos`, `config`).

Lanzar con:  python -m keni_metricas.consola
"""

from __future__ import annotations

from .app import crear_app

__all__ = ["crear_app"]
