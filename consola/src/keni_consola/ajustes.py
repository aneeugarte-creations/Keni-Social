"""Almacen EDITABLE de ajustes de funcionalidad de la Consola Keni (flags + tuning).

Permite a un admin cambiar EN CALIENTE, desde la UI, los flags de automatizacion y los
parametros de afinado que hoy solo se fijaban por variable de entorno (catalogo en
`ajustes_catalogo.py`). El store persiste pares `clave -> valor` (ambos `str`, igual que
una env var) en un TOML, y `config._crudo` lo consulta ANTES que `os.environ`, dando la
precedencia STORE > ENV > DEFECTO. Solo se escriben claves del catalogo; el resto del
codigo sigue cayendo a env como hasta hoy.

El archivo vive en `KENI_CONSOLA_AJUSTES` (override de maxima prioridad; tests y deploy)
o, si no, cuelga de la raiz de estado unica (`rutas.dir_config()/ajustes.toml`). Escritura
ATOMICA (temp + os.replace), mismo patron defensivo que `preferencias.py`/`secretos.py`.
NO contiene secretos.

CICLO DE IMPORT: este modulo NO importa `config` a nivel de modulo (config importa este
modulo de forma PEREZOSA dentro de `_crudo`). Usa `rutas` directamente para resolver la
ruta y lee `KENI_CONSOLA_AJUSTES` de `os.environ` aqui mismo.

CACHE: el store se consulta MUY seguido (cada `config._crudo`, que a su vez lo llaman los
accesores en caliente). Cacheamos la lectura y la invalidamos por mtime del fichero (un
escritor distinto —otro proceso/daemon que comparte el volumen— se nota por mtime).
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from . import rutas
from .io_atomico import escribir_atomico

# Nombre de la env var que sobreescribe la ruta del store (override de maxima prioridad;
# tests y deploy multi-proceso). Se declara TAMBIEN en `config.ENV_AJUSTES` (fuente unica
# de los nombres `KENI_*`); aqui no importamos `config` para evitar el ciclo de import.
ENV_AJUSTES = "KENI_CONSOLA_AJUSTES"

_CABECERA = (
    "# Ajustes EDITABLES de la Consola Keni (flags + tuning). Los gestiona\n"
    "# keni_consola.ajustes via la API admin (no editar a mano).\n"
)

# Cache de la ultima lectura, invalidada por (ruta, mtime). `_CACHE_MTIME = -1` => sin cache.
_CACHE_DATOS: dict[str, str] = {}
_CACHE_RUTA: str | None = None
_CACHE_MTIME: float = -1.0


def ruta_ajustes() -> Path:
    """Ruta del archivo de ajustes.

    `KENI_CONSOLA_AJUSTES` la sobreescribe (override de maxima prioridad; tests y deploy
    multi-proceso). Si no, cuelga de la raiz de estado unica (`rutas.dir_config()`): local
    `${XDG_CONFIG_HOME:-~/.config}/keni-social/ajustes.toml`, o bajo `KENI_DATA_DIR`.
    """
    crudo = os.environ.get(ENV_AJUSTES)
    if crudo:
        return Path(crudo).expanduser()
    return rutas.dir_config() / "ajustes.toml"


# --------------------------------------------------------------------------- #
# Lectura / escritura del almacen                                             #
# --------------------------------------------------------------------------- #


def _leer_disco(ruta: Path) -> dict[str, str]:
    """Lee el TOML de ajustes de disco (o {} si no existe / esta corrupto). Solo lectura.

    Normaliza a `dict[str, str]`: solo claves de nivel raiz cuyo valor sea texto (lo que
    escribimos). Cualquier otra forma se ignora (lectura tolerante).
    """
    try:
        crudo = tomllib.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return {k: v for k, v in crudo.items() if isinstance(v, str)}


def leer() -> dict[str, str]:
    """Pares `clave -> valor` (ambos str) del store, con cache invalidada por mtime.

    Devuelve una COPIA (mutarla no toca la cache). {} si el fichero no existe o esta
    corrupto. Se consulta muy seguido (lo llama `config._crudo`): por eso cacheamos y solo
    releemos el disco cuando cambia el mtime (o la ruta, p.ej. al cambiar la env en tests).
    """
    global _CACHE_DATOS, _CACHE_RUTA, _CACHE_MTIME
    ruta = ruta_ajustes()
    ruta_str = str(ruta)
    try:
        mtime = ruta.stat().st_mtime
    except OSError:
        # No existe: cachea vacio (mtime -1) para no golpear el disco en cada llamada.
        if _CACHE_RUTA != ruta_str or _CACHE_MTIME != -1.0:
            _CACHE_DATOS = {}
            _CACHE_RUTA = ruta_str
            _CACHE_MTIME = -1.0
        return dict(_CACHE_DATOS)
    if _CACHE_RUTA != ruta_str or _CACHE_MTIME != mtime:
        _CACHE_DATOS = _leer_disco(ruta)
        _CACHE_RUTA = ruta_str
        _CACHE_MTIME = mtime
    return dict(_CACHE_DATOS)


def _toml_str(valor: str) -> str:
    """Escapa una cadena para un TOML basic string (comillas dobles)."""
    escapado = (
        valor.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace("\r", "\\r")
    )
    return f'"{escapado}"'


def _escribir(datos: dict[str, str]) -> None:
    """Escribe los ajustes como TOML de forma atomica (temp + os.replace) e invalida cache."""
    global _CACHE_MTIME
    lineas = [f"{clave} = {_toml_str(valor)}" for clave, valor in sorted(datos.items())]
    contenido = _CABECERA + ("\n".join(lineas) + "\n" if lineas else "")
    escribir_atomico(
        ruta_ajustes(), contenido, prefijo=".ajustes-", sufijo=".toml.tmp"
    )
    # Fuerza relectura en la proxima `leer()` (el mtime nuevo no siempre difiere al instante).
    _CACHE_MTIME = -1.0


# --------------------------------------------------------------------------- #
# API publica: pares clave -> valor                                           #
# --------------------------------------------------------------------------- #


def obtener(clave: str) -> str | None:
    """Valor (str) guardado para `clave`, o None si no esta en el store.

    Lo consume `config._crudo` para dar precedencia al store sobre `os.environ`.
    """
    return leer().get(clave)


def guardar(clave: str, valor: str) -> None:
    """Guarda `clave -> valor` (ambos str) en el store (escritura atomica).

    Sobrescribe el valor previo si lo hubiera. NO valida: la validacion (tipo/min/max/
    catalogo) la hace `ajustes_catalogo.validar_valor` aguas arriba (la API).
    """
    datos = leer()
    datos[clave] = valor
    _escribir(datos)


def borrar(clave: str) -> None:
    """Borra `clave` del store (vuelve a env/defecto). No-op si no estaba."""
    datos = leer()
    if clave in datos:
        datos.pop(clave, None)
        _escribir(datos)
