"""Consola Keni: capa de GESTION web LOCAL para equipo NO tecnico.

Filosofia: la consola gestiona; Claude Code queda DEBAJO como motor de
ejecucion, lanzado desde aqui. Privacidad por diseno: bind solo a 127.0.0.1,
sin nube. Corre sobre una pila ASGI propia (Starlette/uvicorn) y DEPENDE del
paquete `keni-metricas`, reutilizando sus funciones de metricas ya existentes
(`reporte`, `dashboard`, `picos`, `config`).

Lanzar con:  python -m keni_consola   (o el comando `keni-consola`)
"""

from __future__ import annotations

from .app import crear_app

__all__ = ["crear_app"]
