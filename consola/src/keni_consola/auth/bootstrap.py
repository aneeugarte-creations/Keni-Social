"""Bootstrap idempotente del primer admin.

Si la BD no tiene usuarios, crea un `admin` con la contrasena de
`KENI_CONSOLA_ADMIN_PASS` (o una aleatoria que se MUESTRA UNA vez en el log, como el
token de #134). Nace con `debe_cambiar_password=True`: debe cambiarla al primer acceso.
"""

from __future__ import annotations

import logging
import secrets

from .. import config
from ..estados import ROL_ADMIN
from ..observabilidad import NOMBRE_LOGGER
from .usuarios import crear_usuario

_logger = logging.getLogger(NOMBRE_LOGGER)

# Env vars del bootstrap del primer admin. Nombres/default canonicos en `config` (fuente
# unica); re-exportados aqui por compat de referencias.
ENV_ADMIN_USER = config.ENV_ADMIN_USER
ENV_ADMIN_PASS = config.ENV_ADMIN_PASS
ADMIN_POR_DEFECTO = config.ADMIN_USER_DEF


def hay_usuarios() -> bool:
    """True si ya existe al menos un usuario (el bootstrap es no-op entonces)."""
    from .. import db

    con = db.conectar()
    try:
        fila = con.execute("SELECT 1 FROM usuarios LIMIT 1").fetchone()
    finally:
        con.close()
    return fila is not None


def bootstrap_admin() -> None:
    """Crea el primer admin si la BD no tiene usuarios (idempotente y seguro en tests).

    Usuario desde `KENI_CONSOLA_ADMIN_USER` (def "admin"). Contrasena desde
    `KENI_CONSOLA_ADMIN_PASS`; si no esta, se genera una aleatoria y se MUESTRA UNA
    vez en el log (como el token de #134), para que el operador local pueda entrar.
    El admin nace con `debe_cambiar_password=True` (debe cambiarla al primer login).
    """
    if hay_usuarios():
        return

    usuario = config.admin_user()
    pass_env = config.admin_pass()
    generada = not pass_env
    password = pass_env or secrets.token_urlsafe(12)

    creado = crear_usuario(usuario, password, ROL_ADMIN, debe_cambiar_password=True)
    if creado is None:
        # Carrera improbable (otro proceso lo creo entre el check y el insert): no-op.
        return

    if generada:
        _logger.warning(
            "No hay usuarios: admin de bootstrap creado. usuario=%s contrasena=%s "
            "(temporal, debe cambiarse al primer acceso; fija KENI_CONSOLA_ADMIN_PASS "
            "para una estable).",
            usuario,
            password,
        )
    else:
        _logger.info(
            "Admin de bootstrap creado con KENI_CONSOLA_ADMIN_PASS. usuario=%s "
            "(debe cambiar la contrasena al primer acceso).",
            usuario,
        )
