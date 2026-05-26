"""keni-metricas — servidor MCP de metricas de redes sociales multi-plataforma.

`servicio` es la fachada estable que consumen los procesos en proceso (la Consola):
el contrato que no debe romperse al refactorizar los internals (config/reporte/
reporte_deck/fuentes). Su seccion de metricas es de SOLO LECTURA.
"""

from . import servicio

__version__ = "0.1.0"

__all__ = ["servicio"]
