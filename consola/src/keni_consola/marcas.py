"""Catalogo UNICO de marca de la consola — REEXPORTA `keni_shared.marcas`.

La definicion canonica vive en `keni_shared.marcas`, la capa mas
baja del monorepo, para que keni-metricas y keni-consola la importen de la MISMA
fuente.

Este modulo se conserva como reexport para no romper los imports existentes de la
consola (`from . import marcas`, `from .. import marcas`): el codigo sigue usando
`marcas.opciones()`, `marcas.id_metricas_de(...)`, etc., sin saber que la fuente
cambio de paquete. No define NADA propio: todo lo reexpuesto es `keni_shared`.

El reexport es AUTO-DERIVADO: `__getattr__`/`__dir__`/`__all__` delegan en la fuente
sin enumerar nombre a nombre, asi la fachada nunca se queda atras cuando
`keni_shared.marcas` gana o pierde simbolos publicos. `test_facades` afirma que la
fachada reexporta TODO lo publico de la fuente.
"""

from __future__ import annotations

from keni_shared import marcas as _src


def _nombres_publicos_fuente() -> list[str]:
    """Nombres publicos que expone `keni_shared.marcas`: lo que NACE en el modulo
    (funciones, clases, constantes) mas `MARCAS` (vivo, via el PEP 562 de la fuente).

    Filtra los simbolos IMPORTADOS por la fuente (modulos como `os`/`tomllib`, helpers
    de `cliente`): solo cuenta lo definido en `keni_shared.marcas` mas el caso especial
    `MARCAS`. Asi la fachada reexpone la API real, no las dependencias de implementacion."""
    nombres: set[str] = {"MARCAS"}  # vivo en la fuente (PEP 562), no aparece en `dir`.
    for nombre in dir(_src):
        if nombre.startswith("_"):
            continue
        valor = getattr(_src, nombre)
        if getattr(valor, "__module__", None) == _src.__name__:
            nombres.add(nombre)
    return sorted(nombres)


def __getattr__(name: str):  # PEP 562
    # Delega TODO acceso publico en la fuente. `MARCAS` es VIVO en keni_shared (catalogo
    # editable): delegar el acceso (en vez de un `from ... import MARCAS`) garantiza que
    # `marcas.MARCAS` sea SIEMPRE el MISMO objeto que `keni_shared.marcas.MARCAS`.
    if not name.startswith("_") and hasattr(_src, name):
        return getattr(_src, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return _nombres_publicos_fuente()


__all__ = _nombres_publicos_fuente()
