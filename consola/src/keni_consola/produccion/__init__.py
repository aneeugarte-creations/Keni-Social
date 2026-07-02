"""Paquete de la app PRODUCCIÓN: motor de creación/recolección de contenido.

Reúne los módulos cuya única frontera HTTP son los routers de `apps/produccion.toml`
(actividad, algoritmos, patrones, breaking, insumos, noticias, prompts, pipelines…) y sus
daemons de fondo. Ver ADR 0005 (fronteras por app) y `tests/test_fronteras.py`.
"""
