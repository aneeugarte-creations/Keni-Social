"""Helpers compartidos por las areas del paquete `api/sistema`.

SOLO dependencias hacia arriba (`..` paquete `keni_consola`): este modulo NO importa de
los handlers de area, para no crear ciclos. El cerrojo de rol (#150/#153) vive aqui en un
unico sitio: la info de sistema/S3 es sensible -> exige SESION admin real (el token de
mantenimiento NO es admin: recibe 403).
"""

from __future__ import annotations

import logging

from starlette.requests import Request
from starlette.responses import Response

from ... import permisos
from ...observabilidad import NOMBRE_LOGGER

_logger = logging.getLogger(NOMBRE_LOGGER)

_MSG_SOLO_ADMIN = "Solo un administrador puede ver el estado del sistema."


def _es_admin(request: Request) -> bool:
    """True SOLO si la peticion la hace una SESION admin real (token NO cuenta, #150)."""
    return permisos.es_admin(request)


def _rechazo_no_admin() -> Response:
    return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
