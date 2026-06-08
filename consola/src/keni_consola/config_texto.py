"""Config — accesores del dominio texto. Parte de config.py (ver barrel)."""
from __future__ import annotations

from ._config_comun import (
    ENV_TEXTO_DIR,
    Path,
    os,
)

# --------------------------------------------------------------------------- #
# Accesores: texto de prompts + linea editorial                           #
# --------------------------------------------------------------------------- #


def texto_dir() -> Path | None:
    """Override del dir del almacen de la Texto (`KENI_TEXTO_DIR`); None si no esta.

    Sin override, `libtexto.raiz()` cae a `rutas.dir_config()/texto` (bajo el volumen
    `KENI_DATA_DIR` en contenedor; `~/.config/keni-social/texto` en local). Los tests lo
    apuntan a un `tmp_path` para no tocar el estado real.
    """
    crudo = os.environ.get(ENV_TEXTO_DIR)
    return Path(crudo).expanduser() if crudo else None
