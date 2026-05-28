"""Bootstrap idempotente del equipo real (16 personas de AMX Contenido).

Fuente de verdad: organigrama dictado por Bernardo (transcripcion
`03-entrega/unotv-clarosports/transcripciones/organizacion/organigrama.txt`) y resumen
de participantes (`03-entrega/unotv-clarosports/equipo/RESUMEN-PARTICIPANTES.md`).

Cada persona tiene:
  - `cargo`     : su FUNCION en el equipo (allowlist en `estados.CARGOS_USUARIO`).
  - `cobertura` : True si entra en la rota de turnos. Comunity/content managers + redactor
                  + guionista + editorial cubren (10 personas). Directivos, gerencia,
                  estrategia, fotografia y coordinacion de YouTube NO cubren (6 personas).

Idempotente: si el usuario `usuario` ya existe, NO se borra ni se pisa la contrasena; solo
se actualizan `cargo` y `cobertura` para que la BD refleje el organigrama actual sin
forzar a nadie a recambiar la contrasena. Si no existe, se crea con password "cambiar" y
`debe_cambiar_password=True` (debe cambiarla al primer login). Bernardo es el unico admin
del equipo real (los demas son editor).
"""

from __future__ import annotations

import logging

from ..estados import ROL_ADMIN, ROL_EDITOR
from ..observabilidad import NOMBRE_LOGGER
from .usuarios import actualizar_perfil, crear_usuario, listar_usuarios

_logger = logging.getLogger(NOMBRE_LOGGER)

# Password inicial obligatoria a cambiar al primer login (`debe_cambiar_password=True`).
# Cada persona se la cambia al entrar; este valor solo vive en el seed inicial.
PASSWORD_INICIAL = "cambiar"

# Equipo real (16): (usuario, rol_permisos, cargo, cobertura).
# `cobertura=True` = entra en la rota de turnos. Lectura del organigrama (Bernardo dice de
# Claro Sports fin de semana "aca no son dos, son cuatro" -> Tezcu+Luis+Roger+Elias). UnoTV
# en fin de semana son DOS (Lalo y Angel). Yustine refuerza WhatsApp UnoTV. Jose es copy de
# redes. Daiana se integra a UnoTV. Jonathan es copy digital de Nacion Gamer.
EQUIPO_AMX: tuple[tuple[str, str, str, bool], ...] = (
    ("bernardo", ROL_ADMIN, "director", False),
    ("diana", ROL_EDITOR, "coordinador", False),
    ("elias", ROL_EDITOR, "coordinador", True),
    ("maira", ROL_EDITOR, "gerente", False),
    ("lalo", ROL_EDITOR, "content_manager", True),
    ("angel", ROL_EDITOR, "content_manager", True),
    ("tezcu", ROL_EDITOR, "community_manager", True),
    ("luis", ROL_EDITOR, "community_manager", True),
    ("roger", ROL_EDITOR, "community_manager", True),
    ("daiana", ROL_EDITOR, "community_manager", True),
    ("mariana", ROL_EDITOR, "estrategia", False),
    ("ale", ROL_EDITOR, "fotografia", False),
    ("jonathan", ROL_EDITOR, "guionista", True),
    ("jose", ROL_EDITOR, "redactor", True),
    ("yustine", ROL_EDITOR, "editorial", True),
    ("laloyt", ROL_EDITOR, "coordinador", False),
)


def sembrar_equipo() -> None:
    """Asegura los 16 usuarios del equipo AMX en la BD (idempotente).

    - Usuarios nuevos: se crean con `PASSWORD_INICIAL` y `debe_cambiar_password=True`.
    - Usuarios ya existentes: NO se toca la contrasena ni el rol; solo se sincronizan
      `cargo` y `cobertura` con el organigrama vigente. Asi el seed se puede correr en
      cada arranque sin efectos secundarios y la BD queda al dia si el organigrama
      cambia.
    """
    existentes = {u["usuario"]: u for u in listar_usuarios()}
    nuevos = 0
    actualizados = 0
    for usuario, _rol, cargo, cobertura in EQUIPO_AMX:
        if usuario in existentes:
            actual = existentes[usuario]
            if actual.get("cargo") != cargo or bool(actual.get("cobertura")) != cobertura:
                actualizar_perfil(actual["id"], cargo=cargo, cobertura=cobertura)
                actualizados += 1
            continue
        creado = crear_usuario(
            usuario,
            PASSWORD_INICIAL,
            _rol,
            debe_cambiar_password=True,
            cargo=cargo,
            cobertura=cobertura,
        )
        if creado is not None:
            nuevos += 1
    if nuevos or actualizados:
        _logger.info(
            "Seed equipo AMX: %d usuarios creados, %d actualizados (cargo/cobertura).",
            nuevos,
            actualizados,
        )
