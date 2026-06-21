"""Carga del PAQUETE DE CLIENTE: marcas y cuentas, externalizadas a configuracion.

Las marcas/cuentas viven en ficheros `.toml` empaquetados en `clientes/` (uno por cliente,
declarativo, como ya hace el corpus editorial de skills). `marcas.py` y `cuentas.py` se
LIMITAN a leer de aqui.

SELECCION DEL CLIENTE (sin tocar codigo), por prioridad:
  1. env `KENI_CLIENTE_CONFIG` — ruta ABSOLUTA a un `.toml` de cliente propio.
  2. env `KENI_CLIENTE`          — nombre de un `.toml` dentro de `clientes/`
                                   (p.ej. `KENI_CLIENTE=amx` => `clientes/amx.toml`).
  3. defecto                     — `clientes/amx.toml` (las 5 marcas del piloto), asi
                                   que SIN configurar nada el comportamiento es el
                                   historico y no se rompe nada.

ANADIR UN CLIENTE NUEVO = anadir un `.toml` en `clientes/` (o apuntar la env a uno);
nunca hace falta editar la capa base. Ver `clientes/amx.toml` para la forma.

Solo LECTURA y `tomllib` (stdlib): `keni_shared` es la capa mas baja, sin
dependencias externas. El paquete se carga UNA vez (cache de modulo) al importar
`marcas`/`cuentas`; para recargarlo en tests usa `cargar_cliente.cache_clear()`.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

# Nombre del cliente por defecto (su fichero es `clientes/<DEFECTO>.toml`).
CLIENTE_DEFECTO = "amx"

# Directorio empaquetado con los ficheros de cliente. Vive junto a este modulo.
_DIR_CLIENTES = Path(__file__).parent / "clientes"


class ClienteInvalido(ValueError):
    """El fichero de cliente existe pero no se puede usar (sintaxis o contenido).

    Hereda de `ValueError` para que sea tratable como error de dominio (mensaje en
    espanol, sin traceback crudo de `tomllib` ni `KeyError`).
    """


@dataclass(frozen=True)
class _MarcaCruda:
    """Una marca tal como viene del TOML, ya validada. La consume `marcas.Marca`."""

    id: str
    etiqueta: str
    id_metricas: str
    # 'noticias' (pasa por la cadena de investigación) o 'propio' (contenido propio que se
    # salta la investigación: no se le clasifican historias ni aparece en el panel de Noticias).
    tipo: str
    # Nombre que ve el equipo para el panel de investigación de esta marca (p.ej.
    # "Curiosidades" en una marca de datos curiosos). Solo aplica a marcas de tipo 'noticias';
    # por defecto "Noticias".
    etiqueta_investigacion: str = "Noticias"


@dataclass(frozen=True)
class Cliente:
    """Paquete de cliente cargado: su identidad, sus marcas y sus cuentas de deportes."""

    id: str
    nombre: str
    marcas: tuple[_MarcaCruda, ...]
    deportes_principal: str
    deportes_hermanas: tuple[str, ...]


def ruta_cliente() -> Path:
    """Ruta del `.toml` de cliente ACTIVO, segun env vars (ver docstring del modulo)."""
    if (p := os.environ.get("KENI_CLIENTE_CONFIG")):
        return Path(p).expanduser()
    nombre = os.environ.get("KENI_CLIENTE") or CLIENTE_DEFECTO
    return _DIR_CLIENTES / f"{nombre}.toml"


def _exigir_str(valor: object, contexto: str) -> str:
    if not (isinstance(valor, str) and valor.strip()):
        raise ClienteInvalido(
            f"El cliente declara {contexto} invalido (obligatorio y no vacio)."
        )
    return valor


def normalizar_tipo(valor: object) -> str:
    """Normaliza el `tipo` de una marca a 'noticias' (defecto) o 'propio'. Tolerante."""
    return "propio" if isinstance(valor, str) and valor.strip().lower() == "propio" else "noticias"


def normalizar_etiqueta_investigacion(valor: object) -> str:
    """Etiqueta del panel de investigación de una marca; 'Noticias' por defecto. Tolerante."""
    return valor.strip() if isinstance(valor, str) and valor.strip() else "Noticias"


def _parsear_marca(idx: int, m: object) -> _MarcaCruda:
    n = f"#{idx + 1}"
    if not isinstance(m, dict):
        raise ClienteInvalido(f"La marca {n} del cliente no es una tabla [[marca]] valida.")
    etiqueta_n = f"{n} (id={m.get('id')!r})" if m.get("id") else n
    return _MarcaCruda(
        id=_exigir_str(m.get("id"), f"un 'id' en la marca {etiqueta_n}"),
        etiqueta=_exigir_str(m.get("etiqueta"), f"una 'etiqueta' en la marca {etiqueta_n}"),
        id_metricas=_exigir_str(m.get("id_metricas"), f"un 'id_metricas' en la marca {etiqueta_n}"),
        tipo=normalizar_tipo(m.get("tipo")),
        etiqueta_investigacion=normalizar_etiqueta_investigacion(m.get("etiqueta_investigacion")),
    )


def _parsear_hermanas(valor: object) -> tuple[str, ...]:
    if valor is None:
        return ()
    if not isinstance(valor, list):
        raise ClienteInvalido("El campo 'cuentas.deportes_hermanas' debe ser una lista de ids.")
    return tuple(_exigir_str(v, "una cuenta en 'deportes_hermanas'") for v in valor)


@cache
def cargar_cliente() -> Cliente:
    """Lee y valida el `.toml` del cliente activo. Cacheada (un import = una lectura).

    Lanza `ClienteInvalido` (subclase de `ValueError`) ante TOML mal formado, fichero
    ausente o contenido invalido, con un mensaje en espanol. Los tests que cambian de
    cliente (env var) deben llamar a `cargar_cliente.cache_clear()` antes.
    """
    ruta = ruta_cliente()
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError as e:
        raise ClienteInvalido(
            f"No se pudo leer el fichero de cliente en {ruta}: {e}."
        ) from e
    try:
        datos = tomllib.loads(texto)
    except tomllib.TOMLDecodeError as e:
        raise ClienteInvalido(
            f"El fichero de cliente en {ruta} tiene un error de sintaxis TOML: {e}."
        ) from e

    marcas_crudas = datos.get("marca")
    if not isinstance(marcas_crudas, list) or not marcas_crudas:
        raise ClienteInvalido(
            f"El cliente en {ruta} no declara ninguna marca ([[marca]] es obligatorio)."
        )
    marcas = tuple(_parsear_marca(i, m) for i, m in enumerate(marcas_crudas))

    ids = [m.id for m in marcas]
    if len(ids) != len(set(ids)):
        raise ClienteInvalido(f"El cliente en {ruta} tiene ids de marca duplicados.")

    cuentas = datos.get("cuentas") or {}
    if not isinstance(cuentas, dict):
        raise ClienteInvalido("La seccion [cuentas] del cliente debe ser una tabla.")

    return Cliente(
        id=str(datos.get("id") or ruta.stem),
        nombre=str(datos.get("nombre") or datos.get("id") or ruta.stem),
        marcas=marcas,
        deportes_principal=str(cuentas.get("deportes_principal") or ""),
        deportes_hermanas=_parsear_hermanas(cuentas.get("deportes_hermanas")),
    )
