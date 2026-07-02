"""Paquete de la app MÉTRICAS: campañas y refrescos de caché de reportes/piezas.

Reúne los módulos cuya única frontera HTTP son los routers de `apps/metricas.toml`
(campañas, vistas, inbox…) y sus daemons de refresco. Ver ADR 0005 (fronteras por app) y
`tests/test_fronteras.py`.
"""
