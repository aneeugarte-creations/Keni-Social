"""Config — accesores del dominio prompts. Parte de config.py (ver barrel)."""
from __future__ import annotations

from ._config_comun import (
    ENV_PROMPTS_DIR,
    ENV_PROMPTS_DIR_LEGACY,
    Path,
    os,
)

# --------------------------------------------------------------------------- #
# Accesores: almacen de prompts + linea editorial                             #
# --------------------------------------------------------------------------- #


def prompts_dir() -> Path | None:
    """Override del dir del almacen de prompts (`KENI_PROMPTS_DIR`); None si no esta.

    Back-compat: si no esta la nueva, cae al nombre legacy `KENI_PROMPTS_DIR`.

    Sin override, `libprompts.raiz()` cae a `rutas.dir_config()/prompts` (bajo el volumen
    `KENI_DATA_DIR` en contenedor; `~/.config/keni-social/prompts` en local). Los tests lo
    apuntan a un `tmp_path` para no tocar el estado real.
    """
    crudo = os.environ.get(ENV_PROMPTS_DIR) or os.environ.get(ENV_PROMPTS_DIR_LEGACY)
    return Path(crudo).expanduser() if crudo else None
