"""Catalogo UNICO de las marcas editoriales de Keni — fuente canonica del monorepo.

Historicamente convivian DOS catalogos incompatibles (uno con ids `guion_bajo`
para Metricas/Config y otro con `slug-guion` para el contenido), por lo que la
misma marca tenia dos identidades. Este modulo unifica todo en un solo catalogo
con un `id` CANONICO publico. Antes vivia en la consola y keni_metricas/skills lo
ESPEJABAN con guards (no podian importarlo, por la direccion de dependencia);
ahora vive en `keni_shared` (H3/E1), la capa mas baja, y lo importan AMBOS
paquetes desde la misma fuente.

Cada marca tiene tres campos:

  - `id`          identificador CANONICO y publico, en forma `slug-guion`
                  (p.ej. `claro-sports`). Es la forma que ya usaba casi todo el
                  contenido (Publicaciones, Skills, RSS, Franjas, Plantillas,
                  Hashtags) y la que viaja por la API. UNA marca = UN id.
  - `etiqueta`    nombre HUMANO legible, con acentos (p.ej. "Nación Gamer"). Es lo
                  unico que ve la persona; identico en TODA la consola.
  - `id_metricas` identificador con `guion_bajo` que necesita `keni_metricas` para
                  hablar con sus cuentas (p.ej. `claro_sports`). Solo se usa en la
                  FRONTERA con metricas (api/metricas.py, api/conexiones.py); el resto
                  de la consola trabaja siempre con el `id` canonico.

El catalogo NO esta hardcodeado: se CARGA de un paquete de cliente declarativo
(`clientes/<cliente>.toml`, ver `keni_shared.cliente`), externalizado a
configuracion (#135). El cliente POR DEFECTO es `clientes/amx.toml`, con las
mismas 5 marcas de siempre, de modo que sin configurar nada nada cambia. Anadir un
cliente nuevo = anadir/seleccionar un `.toml`, sin tocar este modulo. El golf NO es
una marca propia: es un matiz/sub-vertical editorial dentro del contexto de Claro
Sports (va como cuenta hermana, ver `keni_shared.cuentas`).

El catalogo se materializa UNA vez al importar el modulo (desde el cliente activo).
Las funciones del modulo son puras sobre ese catalogo ya cargado.

USO TIPICO:

    from keni_shared import marcas

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

from .cliente import cargar_cliente


@dataclass(frozen=True)
class Marca:
    """Una marca editorial. Ver el docstring del modulo para los tres campos."""

    id: str
    etiqueta: str
    id_metricas: str


# Catalogo del cliente ACTIVO, en orden de presentacion estable (el del `.toml`).
# `id` es la forma canonica (slug-guion); `id_metricas` la forma guion_bajo que
# espera keni_metricas. Por defecto son las 5 marcas del cliente (`clientes/amx.toml`),
# pero NO estan hardcodeadas aqui: se CARGAN del paquete de cliente (#135). El golf
# es un sub-vertical editorial de Claro Sports, NO una marca propia.
MARCAS: tuple[Marca, ...] = tuple(
    Marca(id=m.id, etiqueta=m.etiqueta, id_metricas=m.id_metricas)
    for m in cargar_cliente().marcas
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
