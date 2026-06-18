"""Bootstrap idempotente del primer admin.

Si la BD no tiene usuarios, crea un `admin` con la contrasena de
`KENI_CONSOLA_ADMIN_PASS`. SIN esa env NO se crea nada (y, sobre todo, NUNCA se loguea
una contrasena: antes se generaba una aleatoria y se MOSTRABA en el log, dejando una
credencial valida en claro en los logs del contenedor/CI — hardening 2026-06). El camino
de recuperacion sin env sigue existiendo: con la BD vacia, el TOKEN de mantenimiento
puede crear el primer admin via POST /api/usuarios (ver `api/usuarios`, #150).
El admin nace con `debe_cambiar_password=True`: debe cambiarla al primer acceso.
"""

from __future__ import annotations

import logging

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
    `KENI_CONSOLA_ADMIN_PASS`. SIN esa env NO se crea el admin y NO se loguea ninguna
    contrasena (una credencial valida en el log del contenedor sobrevive en `docker logs`/
    agregadores; era el hallazgo del audit 2026-06). En hosted (detras de TLS,
    `KENI_CONSOLA_HTTPS=1`) la ausencia es un ERROR de configuracion; en local, un aviso
    con los dos caminos: fijar la env, o crear el primer admin con el token de
    mantenimiento (POST /api/usuarios con la BD vacia, #150).
    El admin nace con `debe_cambiar_password=True` (debe cambiarla al primer login).
    """
    if hay_usuarios():
        return

    usuario = config.admin_user()
    password = config.admin_pass()
    if not password:
        mensaje = (
            "No hay usuarios y falta KENI_CONSOLA_ADMIN_PASS: NO se crea el admin de "
            "bootstrap (y nunca se loguea una contrasena). Fija KENI_CONSOLA_ADMIN_PASS "
            "y reinicia, o crea el primer admin con el token de mantenimiento "
            "(POST /api/usuarios con la BD vacia)."
        )
        if config.cookie_secure():
            # Hosted (detras de TLS): aqui la env es OBLIGATORIA -> severidad error.
            _logger.error(mensaje)
        else:
            _logger.warning(mensaje)
        return

    # El admin de bootstrap nace SUPERADMIN: es el unico capaz de entrar a Usuarios y dar de
    # alta/gestionar al resto (sin esto, una BD recien arrancada no tendria quien administre).
    creado = crear_usuario(
        usuario, password, ROL_ADMIN, debe_cambiar_password=True, superadmin=True
    )
    if creado is None:
        # Carrera improbable (otro proceso lo creo entre el check y el insert): no-op.
        return

    _logger.info(
        "Admin de bootstrap creado con KENI_CONSOLA_ADMIN_PASS. usuario=%s "
        "(debe cambiar la contrasena al primer acceso).",
        usuario,
    )
