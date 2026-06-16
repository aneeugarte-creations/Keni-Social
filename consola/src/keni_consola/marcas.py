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


def __getattr__(name: str):  # PEP 562
    # `MARCAS` es VIVO en keni_shared (catalogo editable): un `from ... import MARCAS`
    # lo congelaria en un snapshot. Delegamos el acceso para que `marcas.MARCAS`
    # sea SIEMPRE el MISMO objeto que `keni_shared.marcas.MARCAS`, no una copia.
    if name == "MARCAS":
        from keni_shared import marcas as _ks

        return _ks.MARCAS
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

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
