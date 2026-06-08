"""Config — accesores del dominio biblioteca. Parte de config.py (ver barrel)."""
from __future__ import annotations

from ._config_comun import (
    ENV_BIBLIOTECA_DIR,
    Path,
    os,
)

# --------------------------------------------------------------------------- #
# Accesores: biblioteca de prompts + linea editorial                           #
# --------------------------------------------------------------------------- #


def biblioteca_dir() -> Path | None:
    """Override del dir del almacen de la Biblioteca (`KENI_BIBLIOTECA_DIR`); None si no esta.

    Sin override, `biblioteca.raiz()` cae a `rutas.dir_config()/biblioteca` (bajo el volumen
    `KENI_DATA_DIR` en contenedor; `~/.config/keni-social/biblioteca` en local). Los tests lo
    apuntan a un `tmp_path` para no tocar el estado real.
    """
    crudo = os.environ.get(ENV_BIBLIOTECA_DIR)
    return Path(crudo).expanduser() if crudo else None
