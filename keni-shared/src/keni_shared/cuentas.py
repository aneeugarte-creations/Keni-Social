"""Cuentas hermanas de las marcas — fuente UNICA del monorepo.

Algunas marcas tienen CUENTAS HERMANAS que NO son marcas editoriales de primer
nivel pero que el equipo de redes promociona aparte (p.ej. en el reporte semanal
de deportes). Hoy la unica con hermanas es Claro Sports: su canal de TV
(`claro_sports_tv`) y el sub-vertical de golf (`csport_golf`). El golf NO es una
marca: es un matiz editorial dentro del contexto de Claro Sports.

Estos ids estaban definidos en `keni_metricas.reporte_deck` (`CUENTA_PRINCIPAL` /
`CUENTAS_HERMANAS`) y la consola los reexportaba via `keni_metricas.servicio`;
ademas la fuente `muestra` los anclaba con guards. Ahora viven aqui, en
`keni_shared` (H3/E1), la capa mas baja, para que keni_metricas, la consola y los
guards los importen de la misma fuente.

Los ids estan en forma `id_metricas` (guion_bajo), que es la que usa
`keni_metricas` para hablar con sus cuentas (igual que `marcas.Marca.id_metricas`).

Sin estado ni I/O: solo datos.
"""

from __future__ import annotations

# Cuenta principal del reporte de deportes (su `id_metricas`). Coincide con
# `marcas.id_metricas_de("claro-sports")`.
CUENTA_DEPORTES_PRINCIPAL: str = "claro_sports"

# Cuentas hermanas de Claro Sports (canal de TV + sub-vertical de golf). NO son
# marcas del catalogo: el guard de `muestra` verifica que no se solapan con el.
CUENTAS_DEPORTES_HERMANAS: tuple[str, ...] = ("claro_sports_tv", "csport_golf")
