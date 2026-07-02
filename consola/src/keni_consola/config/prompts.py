"""Config — accesores del dominio prompts. Parte de config.py (ver barrel)."""
from __future__ import annotations

from ._comun import (
    ENV_PROMPTS_DIR,
    ENV_PROMPTS_DIR_LEGACY,
    ENV_PROMPTS_ESTRICTO,
    Path,
    _crudo,
    _VERDADEROS,
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


def prompts_estricto() -> bool:
    """Modo ESTRICTO de la biblioteca (`KENI_PROMPTS_ESTRICTO`, store > env > OFF).

    Con el flag afirmativo, un documento con puntero de produccion cuyo sha NO es
    legible en el repo git ABORTA la generacion (el job falla con un mensaje claro,
    via `libprompts.ProduccionIlegibleError`) en vez de sustituir en silencio por la
    working copy. Con el flag OFF (defecto) todo se comporta como siempre (migracion
    suave). El editor y su preview leen la working copy en ambos casos.
    """
    return _crudo(ENV_PROMPTS_ESTRICTO).lower() in _VERDADEROS
