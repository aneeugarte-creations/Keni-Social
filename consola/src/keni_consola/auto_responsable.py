"""Responsable por defecto de una pieza nueva (Fase 3 · auto-operativa).

El modelo operativo del equipo es «la lista» (reparto PULL): una pieza nueva NACE LIBRE
(«por cubrir») y es el equipo quien la COGE —o el coordinador quien la reparte— desde el
tablero de Cobertura. Nadie nace asignado por la máquina, así el claim atómico (coger/soltar)
nunca choca ni el 409 miente («Ya la cogió X» cuando en realidad fue la rota).

Esto vale para TODAS las marcas. Antes solo ClaroSports usaba «la lista» y el resto auto-asignaba
desde la rota del día (reparto PUSH); ahora el modelo es uniforme: `responsable_automatico`
devuelve None SIEMPRE. Las marcas que aún no tenían rota cargada ya se comportaban así (None);
las que la tuvieran dejan de auto-asignar y pasan también a «la lista».

Se conserva como el ÚNICO punto de decisión de «quién posee una pieza nueva»: lo llaman
`api/contenido/{aportar,post_directo,tablero}.py` con una sola llamada. Si algún día una marca
quisiera volver al reparto PUSH (auto-asignar desde la rota), este es el sitio para reintroducirlo;
el núcleo puro `rota.responsable_por_marca_hoy` sigue disponible para ello.
"""

from __future__ import annotations


def responsable_automatico(marca: str, fecha_iso: str | None = None) -> dict[str, str] | None:
    """Responsable por defecto de una pieza nueva de `marca`: SIEMPRE None («la lista»).

    Bajo el reparto PULL —universal para todas las marcas— una pieza nace LIBRE y el equipo la
    coge desde «Por cubrir». No se consulta la rota ni se inventa un responsable. `marca` y
    `fecha_iso` se aceptan por compatibilidad con los llamadores (hoy no se usan; son el gancho
    para un eventual reparto PUSH por marca).
    """
    return None
