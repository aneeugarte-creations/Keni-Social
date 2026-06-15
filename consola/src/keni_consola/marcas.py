"""Catalogo UNICO de marca de la consola — REEXPORTA `keni_shared.marcas`.

La definicion canonica vive en `keni_shared.marcas` (H3/E1), la capa mas
baja del monorepo, para que keni-metricas y keni-consola la importen de la MISMA
fuente.

Este modulo se conserva como reexport para no romper los imports existentes de la
consola (`from . import marcas`, `from .. import marcas`): el codigo sigue usando
`marcas.opciones()`, `marcas.id_metricas_de(...)`, etc., sin saber que la fuente
cambio de paquete. No define NADA propio: todo lo reexpuesto es `keni_shared`.
"""

from __future__ import annotations

from keni_shared.marcas import (  # noqa: F401  (reexport: la fuente es keni_shared)
    MARCAS,
    Marca,
    es_marca,
    etiqueta_de,
    etiqueta_por_id_metricas,
    id_metricas_de,
    ids,
    marca_de,
    marca_por_id_metricas,
    opciones,
    opciones_metricas,
)

__all__ = [
    "MARCAS",
    "Marca",
    "es_marca",
    "etiqueta_de",
    "etiqueta_por_id_metricas",
    "id_metricas_de",
    "ids",
    "marca_de",
    "marca_por_id_metricas",
    "opciones",
    "opciones_metricas",
]
