"""Config — accesores del dominio arranque. Parte de config.py (ver barrel)."""
from __future__ import annotations

from ._config_comun import (
    ENV_HOST,
    ENV_PORT,
    HOST_DEF,
    PORT_DEF,
    os,
)

# --------------------------------------------------------------------------- #
# Accesores: arranque / red                                                    #
# --------------------------------------------------------------------------- #


def host() -> str:
    """Host de bind del servidor (`KENI_CONSOLA_HOST`, def 127.0.0.1)."""
    return os.environ.get(ENV_HOST, HOST_DEF)


def port() -> int:
    """Puerto del servidor (`KENI_CONSOLA_PORT`, def 8765); valor invalido -> def."""
    crudo = os.environ.get(ENV_PORT, str(PORT_DEF))
    try:
        return int(crudo)
    except ValueError:
        return PORT_DEF
