"""Config — accesores del dominio observabilidad. Parte de config.py (ver barrel)."""
from __future__ import annotations

from ._config_comun import (
    ENV_LOG_LEVEL,
    LOG_LEVEL_DEF,
    os,
)

# --------------------------------------------------------------------------- #
# Accesores: observabilidad                                                    #
# --------------------------------------------------------------------------- #


def log_level() -> str:
    """Nivel de log crudo en mayusculas (`KENI_CONSOLA_LOG_LEVEL`, def INFO).

    Devuelve el NOMBRE (DEBUG/INFO/...); el modulo de observabilidad lo mapea a un int y
    cae a INFO si no es valido (no se valida aqui para no acoplar a `logging`).
    """
    return os.environ.get(ENV_LOG_LEVEL, LOG_LEVEL_DEF).strip().upper()
