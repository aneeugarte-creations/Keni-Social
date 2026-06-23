"""Catalogo UNICO de las marcas editoriales de Keni — fuente canonica del monorepo.

Cada marca tiene tres campos:

  - `id`          identificador CANONICO y publico, en forma `slug-guion`
                  (p.ej. `claro-sports`). UNA marca = UN id.
  - `etiqueta`    nombre HUMANO legible, con acentos (p.ej. "Nación Gamer").
  - `id_metricas` identificador con `guion_bajo` que necesita `keni_metricas` para
                  hablar con sus cuentas (p.ej. `claro_sports`). Solo se usa en la
                  FRONTERA con metricas (api/metricas.py, api/conexiones.py).

FUENTE UNICA, EDITABLE EN RUNTIME (CRUD desde la consola):

  1. Si existe un fichero EDITABLE (`KENI_MARCAS_CONFIG`, o `<KENI_DATA_DIR>/marcas.toml`),
     ESE es el catalogo. La consola lo crea/edita por su API y todos los procesos que
     comparten `/data` lo ven (se RECARGA solo cuando cambia su `mtime`; no hace falta
     reiniciar). Forma: una lista de `[[marca]]` con id/etiqueta/id_metricas.
  2. Si no existe, se usa el paquete de cliente declarativo (`clientes/<cliente>.toml`,
     ver `keni_shared.cliente`) como SEMILLA. Sin configurar nada => las 5 marcas del
     piloto (comportamiento historico).

El catalogo se cachea y se reconstruye cuando cambia el fichero fuente (por `mtime`) o
cuando alguien llama a `recargar()` (la consola lo hace tras cada escritura).

USO TIPICO:

    from keni_shared import marcas

    marcas.opciones()                         # -> [("unotv", "UnoTV"), ...]
    marcas.etiqueta_de("claro-sports")        # -> "Claro Sports"
    marcas.es_marca("claro-sports")           # -> True
    marcas.id_metricas_de("claro-sports")     # -> "claro_sports"  (frontera)
    marcas.opciones_metricas()                # -> [("unotv", "UnoTV"), ...]  (frontera)
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .cliente import (
    cargar_cliente,
    normalizar_etiqueta_investigacion,
    normalizar_likes_aprobacion,
    normalizar_tipo,
)


@dataclass(frozen=True)
class Marca:
    """Una marca editorial. Ver el docstring del modulo para los campos."""

    id: str
    etiqueta: str
    id_metricas: str
    # 'noticias' (pasa por la cadena de investigación) o 'propio' (contenido propio que se
    # salta la investigación). Defecto 'noticias' si el catálogo no lo declara.
    tipo: str = "noticias"
    # Nombre del panel de investigación que ve el equipo para esta marca (p.ej.
    # "Curiosidades"). Solo aplica a marcas 'noticias'; por defecto "Noticias".
    etiqueta_investigacion: str = "Noticias"
    # Nº de OK ("likes") de personas distintas que una pieza de esta marca necesita para
    # aprobarse y programarse (umbral de "cuatro ojos" por marca; def 2, min 1).
    likes_aprobacion: int = 2


# --------------------------------------------------------------------------- #
# Fuente del catalogo: overlay editable bajo /data, o el paquete de cliente    #
# --------------------------------------------------------------------------- #


def ruta_editable() -> Path | None:
    """Ruta del fichero EDITABLE de marcas (CRUD), o None si no hay `/data` configurado.

    Prioridad: env `KENI_MARCAS_CONFIG` (ruta absoluta) -> `<KENI_DATA_DIR>/marcas.toml`.
    No exige que exista: solo dice DONDE viviria (la consola lo crea al primer CRUD).
    """
    if p := os.environ.get("KENI_MARCAS_CONFIG"):
        return Path(p).expanduser()
    if d := os.environ.get("KENI_DATA_DIR"):
        return Path(d) / "marcas.toml"
    return None


def _ruta_activa() -> Path:
    """El fichero que MANDA: el overlay editable si existe, si no el del cliente."""
    edit = ruta_editable()
    if edit is not None and edit.exists():
        return edit
    from .cliente import ruta_cliente

    return ruta_cliente()


def _semilla() -> tuple[Marca, ...]:
    """Catalogo semilla del paquete de cliente (`clientes/<cliente>.toml`)."""
    return tuple(
        Marca(
            id=m.id,
            etiqueta=m.etiqueta,
            id_metricas=m.id_metricas,
            tipo=m.tipo,
            etiqueta_investigacion=m.etiqueta_investigacion,
            likes_aprobacion=m.likes_aprobacion,
        )
        for m in cargar_cliente().marcas
    )


def _parsear_overlay(ruta: Path) -> tuple[Marca, ...]:
    """Lee el fichero editable `[[marca]]` (id/etiqueta/id_metricas). Defensivo y tolerante.

    Ignora marcas incompletas o ids duplicados (primero gana): el catalogo nunca debe
    cascar por un fichero a medias. Si no hay ninguna marca valida, cae a la semilla.
    """
    try:
        datos = tomllib.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return _semilla()
    crudas = datos.get("marca")
    if not isinstance(crudas, list):
        return _semilla()
    vistas: set[str] = set()
    marcas: list[Marca] = []
    for m in crudas:
        if not isinstance(m, dict):
            continue
        mid = m.get("id")
        etiqueta = m.get("etiqueta")
        id_metricas = m.get("id_metricas")
        if not (isinstance(mid, str) and mid.strip()):
            continue
        if mid in vistas:
            continue
        vistas.add(mid)
        marcas.append(
            Marca(
                id=mid,
                etiqueta=etiqueta if isinstance(etiqueta, str) and etiqueta.strip() else mid,
                id_metricas=(
                    id_metricas
                    if isinstance(id_metricas, str) and id_metricas.strip()
                    else mid.replace("-", "_")
                ),
                tipo=normalizar_tipo(m.get("tipo")),
                etiqueta_investigacion=normalizar_etiqueta_investigacion(
                    m.get("etiqueta_investigacion")
                ),
                likes_aprobacion=normalizar_likes_aprobacion(m.get("likes_aprobacion")),
            )
        )
    return tuple(marcas) if marcas else _semilla()


@dataclass(frozen=True)
class _Catalogo:
    marcas: tuple[Marca, ...]
    por_id: dict[str, Marca]
    por_id_metricas: dict[str, Marca]


# Cache del catalogo: (ruta fuente, mtime, catalogo). Se reconstruye al cambiar la
# fuente o su mtime, o al llamar a `recargar()`.
_cache: dict[str, object] = {"ruta": None, "mtime": None, "cat": None}


def _estado() -> _Catalogo:
    """Catalogo vigente, reconstruido si el fichero fuente cambio (por `mtime`)."""
    ruta = _ruta_activa()
    try:
        mtime = ruta.stat().st_mtime
    except OSError:
        mtime = None
    cat = _cache["cat"]
    if cat is not None and _cache["ruta"] == ruta and _cache["mtime"] == mtime:
        return cat  # type: ignore[return-value]

    edit = ruta_editable()
    if edit is not None and ruta == edit:
        marcas = _parsear_overlay(ruta)
    else:
        marcas = _semilla()
    nuevo = _Catalogo(
        marcas=marcas,
        por_id={m.id: m for m in marcas},
        por_id_metricas={m.id_metricas: m for m in marcas},
    )
    _cache.update(ruta=ruta, mtime=mtime, cat=nuevo)
    return nuevo


def recargar() -> None:
    """Fuerza la recarga del catalogo (la consola lo llama tras escribir el fichero)."""
    cargar_cliente.cache_clear()
    _cache.update(ruta=None, mtime=None, cat=None)


def __getattr__(name: str):  # PEP 562: `marcas.MARCAS` sigue funcionando, y es VIVO.
    if name == "MARCAS":
        return _estado().marcas
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# --------------------------------------------------------------------------- #
# API canonica: el resto de la consola trabaja SIEMPRE con el `id` canonico    #
# --------------------------------------------------------------------------- #


def marca_de(marca_id: str) -> Marca | None:
    """Devuelve la `Marca` con ese `id` canonico, o `None` si no existe."""
    return _estado().por_id.get(marca_id)


def es_marca(marca_id: str) -> bool:
    """True si `marca_id` es un id canonico conocido."""
    return marca_id in _estado().por_id


def etiqueta_de(marca_id: str) -> str:
    """Nombre humano (con acentos) desde el `id` canonico; cae al propio id si no se conoce."""
    marca = _estado().por_id.get(marca_id)
    return marca.etiqueta if marca is not None else marca_id


def id_metricas_de(marca_id: str) -> str:
    """Traduce el `id` canonico al `id_metricas` (guion_bajo) que espera keni_metricas.

    Es la traduccion de la FRONTERA con metricas. Cae al propio id si no se conoce.
    """
    marca = _estado().por_id.get(marca_id)
    return marca.id_metricas if marca is not None else marca_id


def ids() -> list[str]:
    """Lista de `id` canonicos de todas las marcas, en orden de presentacion."""
    return [m.id for m in _estado().marcas]


def noticias() -> list[str]:
    """Ids de las marcas de NOTICIAS (`tipo='noticias'`), en orden de presentacion.

    Es el conjunto que recorre la cadena de investigación (recolección, clasificación de
    marca, agrupado, admisión, Mesa de Noticias). Las de contenido propio (`tipo='propio'`)
    se excluyen: se saltan la investigación por completo.
    """
    return [m.id for m in _estado().marcas if m.tipo == "noticias"]


def es_noticias(marca_id: str) -> bool:
    """True si `marca_id` es una marca de NOTICIAS (existe y `tipo='noticias'`)."""
    marca = _estado().por_id.get(marca_id)
    return marca is not None and marca.tipo == "noticias"


def likes_aprobacion_de(marca_id: str) -> int:
    """Nº de OK ("likes") que una pieza de esta marca necesita para aprobarse (def 2).

    Es el umbral de "cuatro ojos" POR MARCA: gobierna cuántos niveles humanos lleva la cadena
    del feed y el mínimo de aprobaciones que exige el gate de programación. Cae a 2 si la marca
    no se conoce (defecto histórico).
    """
    marca = _estado().por_id.get(marca_id)
    return marca.likes_aprobacion if marca is not None else 2


def catalogo() -> list[Marca]:
    """Catalogo completo (lista de `Marca`), en orden de presentacion. Para CRUD/edicion."""
    return list(_estado().marcas)


def opciones() -> list[tuple[str, str]]:
    """Pares `(id, etiqueta)` para poblar un <select> de la consola (todas las marcas)."""
    return [(m.id, m.etiqueta) for m in _estado().marcas]


# --------------------------------------------------------------------------- #
# Frontera con metricas: helpers que hablan en `id_metricas` (guion_bajo)      #
# --------------------------------------------------------------------------- #


def marca_por_id_metricas(id_metricas: str) -> Marca | None:
    """Devuelve la `Marca` con ese `id_metricas` (guion_bajo), o `None` si no existe."""
    return _estado().por_id_metricas.get(id_metricas)


def etiqueta_por_id_metricas(id_metricas: str) -> str:
    """Nombre humano (con acentos) desde el `id_metricas`; cae al propio id si no se conoce."""
    marca = _estado().por_id_metricas.get(id_metricas)
    return marca.etiqueta if marca is not None else id_metricas


def opciones_metricas() -> list[tuple[str, str]]:
    """Pares `(id_metricas, etiqueta)` para los selects de Metricas/Config (frontera)."""
    return [(m.id_metricas, m.etiqueta) for m in _estado().marcas]
