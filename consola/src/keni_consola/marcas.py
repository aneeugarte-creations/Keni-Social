"""Fuente UNICA de verdad de las marcas editoriales de la Consola Keni.

Distintas partes de la consola se refieren a la misma marca con identificadores
distintos por razones historicas:

  - `id`       identificador con guion_BAJO que usan Metricas y Configuracion
               (coincide con los ids de la fuente de datos, p.ej. `claro_sports`).
  - `slug`     identificador con guion-MEDIO que usa Skills al invocar Claude
               (p.ej. `claro-sports`). NO todas las marcas tienen slug en Skills:
               las verticales en crecimiento (p.ej. Claro Sports Golf) tienen id
               y etiqueta pero todavia no estan curadas como destino de copy.
  - `etiqueta` nombre HUMANO legible, con acentos (p.ej. "Nación Gamer"). Es lo
               unico que ve la persona; debe ser identico en TODA la consola.

Este modulo centraliza ese mapeo para que las features (Skills, Metricas,
Configuracion...) dejen de declarar sus propias listas y consuman estos helpers.
No tiene estado ni I/O: solo datos y funciones puras.

USO TIPICO (lo consumiran las features en otra ola):

    from .. import marcas

    # Etiqueta humana desde el id de Metricas/Config:
    marcas.etiqueta_por_id("claro_sports")        # -> "Claro Sports"
    # Etiqueta humana desde el slug de Skills:
    marcas.etiqueta_por_slug("nacion-gamer")      # -> "Nación Gamer"
    # Poblar un <select> de Metricas/Config (id, etiqueta):
    marcas.opciones_por_id()                      # -> [("unotv", "UnoTV"), ...]
    # Poblar un <select> de Skills (slug, etiqueta), solo marcas con slug:
    marcas.opciones_por_slug()                    # -> [("unotv", "UnoTV"), ...]
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Marca:
    """Una marca editorial. Ver el docstring del modulo para los tres campos.

    `slug` es `None` cuando la marca todavia no esta curada como destino en Skills
    (tiene id/etiqueta para Metricas y Config, pero no se le genera copy aun).
    """

    id: str
    etiqueta: str
    slug: str | None = None


# Orden de presentacion estable (el que ya usaban Skills/Metricas en su UI).
MARCAS: tuple[Marca, ...] = (
    Marca(id="unotv", etiqueta="UnoTV", slug="unotv"),
    Marca(id="claro_sports", etiqueta="Claro Sports", slug="claro-sports"),
    Marca(id="claro_sports_golf", etiqueta="Claro Sports Golf", slug=None),
    Marca(id="nacion_gamer", etiqueta="Nación Gamer", slug="nacion-gamer"),
    Marca(id="piso_15", etiqueta="Piso 15", slug="piso-15"),
    Marca(id="fundacion", etiqueta="Fundación", slug="fundacion"),
)

# Indices para acceso O(1). Construidos una sola vez al importar el modulo.
_POR_ID: dict[str, Marca] = {m.id: m for m in MARCAS}
_POR_SLUG: dict[str, Marca] = {m.slug: m for m in MARCAS if m.slug is not None}


def marca_por_id(marca_id: str) -> Marca | None:
    """Devuelve la `Marca` con ese `id` (guion_bajo), o `None` si no existe."""
    return _POR_ID.get(marca_id)


def marca_por_slug(slug: str) -> Marca | None:
    """Devuelve la `Marca` con ese `slug` (guion-medio), o `None` si no existe."""
    return _POR_SLUG.get(slug)


def etiqueta_por_id(marca_id: str) -> str:
    """Nombre humano (con acentos) desde el `id`; cae al propio id si no se conoce."""
    marca = _POR_ID.get(marca_id)
    return marca.etiqueta if marca is not None else marca_id


def etiqueta_por_slug(slug: str) -> str:
    """Nombre humano (con acentos) desde el `slug`; cae al propio slug si no se conoce."""
    marca = _POR_SLUG.get(slug)
    return marca.etiqueta if marca is not None else slug


def ids() -> list[str]:
    """Lista de `id` (guion_bajo) de todas las marcas, en orden de presentacion."""
    return [m.id for m in MARCAS]


def slugs() -> list[str]:
    """Lista de `slug` (guion-medio) de las marcas que tienen slug (Skills)."""
    return [m.slug for m in MARCAS if m.slug is not None]


def opciones_por_id() -> list[tuple[str, str]]:
    """Pares `(id, etiqueta)` para poblar un <select> de Metricas/Config."""
    return [(m.id, m.etiqueta) for m in MARCAS]


def opciones_por_slug() -> list[tuple[str, str]]:
    """Pares `(slug, etiqueta)` para poblar un <select> de Skills (solo con slug)."""
    return [(m.slug, m.etiqueta) for m in MARCAS if m.slug is not None]
