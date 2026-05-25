"""Catalogo UNICO de las marcas editoriales de la Consola Keni.

Historicamente convivian DOS catalogos incompatibles (uno con ids `guion_bajo`
para Metricas/Config y otro con `slug-guion` para el contenido), por lo que la
misma marca tenia dos identidades. Este modulo unifica todo en un solo catalogo
con un `id` CANONICO publico.

Cada marca tiene tres campos:

  - `id`          identificador CANONICO y publico, en forma `slug-guion`
                  (p.ej. `claro-sports`). Es la forma que ya usaba casi todo el
                  contenido (Publicaciones, Skills, RSS, Franjas, Plantillas,
                  Hashtags) y la que viaja por la API. UNA marca = UN id.
  - `etiqueta`    nombre HUMANO legible, con acentos (p.ej. "Nación Gamer"). Es lo
                  unico que ve la persona; identico en TODA la consola.
  - `id_metricas` identificador con `guion_bajo` que necesita `keni_metricas` para
                  hablar con sus cuentas (p.ej. `claro_sports`). Solo se usa en la
                  FRONTERA con metricas (api/metricas.py, api/config.py); el resto
                  de la consola trabaja siempre con el `id` canonico.

El catalogo tiene 5 marcas de primer nivel. El golf NO es una marca propia: es
un matiz/sub-vertical editorial dentro del contexto de Claro Sports.

No tiene estado ni I/O: solo datos y funciones puras.

USO TIPICO:

    from .. import marcas

    # Contenido (id canonico):
    marcas.opciones()                         # -> [("unotv", "UnoTV"), ...]
    marcas.etiqueta_de("claro-sports")        # -> "Claro Sports"
    marcas.es_marca("claro-sports")           # -> True
    marcas.id_metricas_de("claro-sports")     # -> "claro_sports"  (frontera)

    # Frontera con metricas (id_metricas, guion_bajo):
    marcas.opciones_metricas()                # -> [("unotv", "UnoTV"), ...]
    marcas.etiqueta_por_id_metricas("nacion_gamer")  # -> "Nación Gamer"
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Marca:
    """Una marca editorial. Ver el docstring del modulo para los tres campos."""

    id: str
    etiqueta: str
    id_metricas: str


# Orden de presentacion estable (el que ya usaban Skills/Metricas en su UI).
# `id` es la forma canonica (slug-guion); `id_metricas` la forma guion_bajo que
# espera keni_metricas. Son 5 marcas de primer nivel: el golf es un sub-vertical
# editorial de Claro Sports, NO una marca propia.
MARCAS: tuple[Marca, ...] = (
    Marca(id="unotv", etiqueta="UnoTV", id_metricas="unotv"),
    Marca(id="claro-sports", etiqueta="Claro Sports", id_metricas="claro_sports"),
    Marca(id="nacion-gamer", etiqueta="Nación Gamer", id_metricas="nacion_gamer"),
    Marca(id="piso-15", etiqueta="Piso 15", id_metricas="piso_15"),
    Marca(id="fundacion", etiqueta="Fundación", id_metricas="fundacion"),
)

# Indices para acceso O(1). Construidos una sola vez al importar el modulo.
_POR_ID: dict[str, Marca] = {m.id: m for m in MARCAS}
_POR_ID_METRICAS: dict[str, Marca] = {m.id_metricas: m for m in MARCAS}


# --------------------------------------------------------------------------- #
# API canonica: el resto de la consola trabaja SIEMPRE con el `id` canonico    #
# --------------------------------------------------------------------------- #


def marca_de(marca_id: str) -> Marca | None:
    """Devuelve la `Marca` con ese `id` canonico, o `None` si no existe."""
    return _POR_ID.get(marca_id)


def es_marca(marca_id: str) -> bool:
    """True si `marca_id` es un id canonico conocido."""
    return marca_id in _POR_ID


def etiqueta_de(marca_id: str) -> str:
    """Nombre humano (con acentos) desde el `id` canonico; cae al propio id si no se conoce."""
    marca = _POR_ID.get(marca_id)
    return marca.etiqueta if marca is not None else marca_id


def id_metricas_de(marca_id: str) -> str:
    """Traduce el `id` canonico al `id_metricas` (guion_bajo) que espera keni_metricas.

    Es la traduccion de la FRONTERA con metricas. Cae al propio id si no se conoce.
    """
    marca = _POR_ID.get(marca_id)
    return marca.id_metricas if marca is not None else marca_id


def ids() -> list[str]:
    """Lista de `id` canonicos de todas las marcas, en orden de presentacion."""
    return [m.id for m in MARCAS]


def opciones() -> list[tuple[str, str]]:
    """Pares `(id, etiqueta)` para poblar un <select> de la consola (todas las marcas)."""
    return [(m.id, m.etiqueta) for m in MARCAS]


# --------------------------------------------------------------------------- #
# Frontera con metricas: helpers que hablan en `id_metricas` (guion_bajo)      #
# --------------------------------------------------------------------------- #


def marca_por_id_metricas(id_metricas: str) -> Marca | None:
    """Devuelve la `Marca` con ese `id_metricas` (guion_bajo), o `None` si no existe."""
    return _POR_ID_METRICAS.get(id_metricas)


def etiqueta_por_id_metricas(id_metricas: str) -> str:
    """Nombre humano (con acentos) desde el `id_metricas`; cae al propio id si no se conoce."""
    marca = _POR_ID_METRICAS.get(id_metricas)
    return marca.etiqueta if marca is not None else id_metricas


def opciones_metricas() -> list[tuple[str, str]]:
    """Pares `(id_metricas, etiqueta)` para los selects de Metricas/Config (frontera)."""
    return [(m.id_metricas, m.etiqueta) for m in MARCAS]
