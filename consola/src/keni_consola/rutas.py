"""Raiz de estado UNICA de la Consola Keni (un solo volumen en contenedor, #130).

Hoy cada modulo de estado resolvia su ruta por su cuenta (su env var especifica y,
como fallback, `XDG_CONFIG_HOME` o `~/.config`). En un CONTENEDOR el estado debe
colgar de UN volumen; este modulo centraliza esa raiz para que todos los modulos la
deriven de aqui.

PRECEDENCIA (de mayor a menor prioridad):
  1. La env var ESPECIFICA de cada recurso (`KENI_CONSOLA_DB`, `KENI_CONSOLA_RAIZ`,
     `KENI_CONSOLA_MEDIA`, ...). La resuelve cada modulo, NO este; sigue siendo el
     override de maxima prioridad (los tests y el `conftest` dependen de ella para
     aislar cada recurso en su propio `tmp_path`).
  2. `KENI_DATA_DIR` (raiz para el contenedor, p.ej. `/data`): si esta, TODO el estado
     cuelga de ahi. La consume `data_dir()`.
  3. El comportamiento LOCAL de siempre (`${XDG_CONFIG_HOME:-~/.config}`), para NO
     mover los datos de un usuario que ya tiene su estado en `~/.config/keni-social`.

SUBPATHS POR RECURSO (NO cambian respecto al layout local previo, para no orfanar
datos existentes):
  - Recursos de CONFIG (db, indice, media, secretos, preferencias, sugerencias,
    termometro, consola.toml, tareas.json, generaciones): cuelgan de
    `data_dir() / "keni-social" / <recurso>`. La unica salvedad es que antes
    `generaciones` ignoraba `XDG_CONFIG_HOME` (siempre `~/.config`); ahora lo unifica
    bajo `data_dir()` (mismo subpath `keni-social/generaciones`), de modo que con
    `KENI_DATA_DIR` queda bajo el volumen sin perder retrocompat local sensata.
  - CONTENIDO editorial por marca (`ficheros.py`/`agentes.py`): cuelga de
    `raiz_proyectos()`, que LOCALMENTE es `~/keni-proyectos` (no bajo `.config`) y bajo
    `KENI_DATA_DIR` es `<data_dir>/keni-proyectos`.
"""

from __future__ import annotations

import os
from pathlib import Path

from . import config

# Variable de entorno que fija la raiz UNICA de estado en contenedor (p.ej. `/data`).
# El nombre canonico vive en `config` (fuente unica de las `KENI_*`); se re-exporta aqui
# para los call sites/tests que ya referencian `rutas.ENV_DATA_DIR`.
ENV_DATA_DIR = config.ENV_DATA_DIR

# Sub-carpeta de CONFIG bajo la raiz (historica: `<base>/keni-social/...`).
SUBDIR_CONFIG = "keni-social"

# Sub-carpeta de CONTENIDO editorial bajo la raiz (historica local: `~/keni-proyectos`).
SUBDIR_PROYECTOS = "keni-proyectos"


def data_dir() -> Path:
    """Raiz de estado de la Consola.

    Precedencia:
      - `KENI_DATA_DIR` (raiz unica para contenedor, p.ej. `/data`): si esta, todo el
        estado cuelga de ahi.
      - si no, el comportamiento LOCAL de siempre: `${XDG_CONFIG_HOME:-~/.config}`.

    NO aplica la env var especifica de cada recurso: esa la resuelve cada modulo ANTES
    de llamar aqui (override de maxima prioridad; ver el modulo). El subpath concreto
    (`keni-social/...`) lo anade el llamante via `dir_config()`.
    """
    if (raiz := os.environ.get(ENV_DATA_DIR)):
        return Path(raiz).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base)


def dir_config() -> Path:
    """Carpeta de CONFIG de la consola: `data_dir() / keni-social`.

    Es la base de la que cuelgan los recursos de config (db, indice, media, secretos,
    preferencias, sugerencias, termometro, consola.toml, tareas.json, generaciones).
    El subpath `keni-social` no cambia respecto al layout local previo.
    """
    return data_dir() / SUBDIR_CONFIG


def raiz_proyectos() -> Path:
    """Raiz del CONTENIDO editorial por marca (lo usa `ficheros.raiz_datos`).

    - Con `KENI_DATA_DIR`: `<data_dir>/keni-proyectos` (todo bajo el volumen).
    - En local (sin `KENI_DATA_DIR`): `~/keni-proyectos`, EXACTAMENTE como antes (no
      cuelga de `.config` ni respeta `XDG_CONFIG_HOME`, para no mover datos locales).
    """
    if (raiz := os.environ.get(ENV_DATA_DIR)):
        return Path(raiz).expanduser() / SUBDIR_PROYECTOS
    return Path.home() / SUBDIR_PROYECTOS
