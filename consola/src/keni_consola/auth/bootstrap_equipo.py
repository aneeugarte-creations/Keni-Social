"""Bootstrap idempotente del equipo real (16 personas de AMX Contenido).

Fuente de verdad: organigrama dictado por Bernardo (transcripcion
`03-entrega/unotv-clarosports/transcripciones/organizacion/organigrama.txt`) y resumen
de participantes (`03-entrega/unotv-clarosports/equipo/RESUMEN-PARTICIPANTES.md`).

Cada persona tiene:
  - `cargo`     : su FUNCION en el equipo (allowlist en `estados.CARGOS_USUARIO`).
  - `cobertura` : True si entra en la rota de turnos. Solo los community/content managers
                  + redactor + creativo de vertical de Nacion Gamer + editorial YT cubren;
                  directivos, gerencia podcast, coordinacion de redes/operativa, fotografia
                  + QA, creativo de Fundacion y coordinacion de YouTube NO cubren.
  - `marcas`    : ids canonicos de las VERTICALES a las que pertenece (relacion N:M en la
                  tabla `usuarios_marcas`). Una persona puede estar en varias
                  (Yustine: claro-sports + unotv + piso-15; Bernardo: las 5).

Ola "feat/roles-marcas" (segunda audiencia con Bernardo):
  - Ampliacion del catalogo de cargos para reflejar el organigrama real (vertical/
    funcion); los cargos VIEJOS se conservan por retrocompat.
  - Reasignaciones reales: Diana/Elias eran "coordinador" plano -> ahora son
    `coordinador_redes` (cada uno de su marca); Maira "gerente" -> `gerente_podcast`;
    Mariana "estrategia" -> `coordinador_operativo`; Ale "fotografia" -> `fotografia_qa`;
    Jonathan "guionista" -> `creativo_vertical` (Nacion Gamer); Yustine "editorial" ->
    `editorial_youtube`; Lalo YT "coordinador" -> `coordinador_youtube`.
  - Correccion CRITICA: Daiana NO es community manager de ClaroSports; es creativo de
    Fundacion TELMEX. Sale del calendario de cobertura (`cobertura=False`) y deja de
    aparecer en la rota.

Idempotente: si el usuario `usuario` ya existe, NO se borra ni se pisa la contrasena;
SI se actualizan `cargo`, `cobertura` y `marcas` para que la BD refleje el organigrama
vigente sin forzar a nadie a recambiar la contrasena. Si no existe, se crea con
password "cambiar" y `debe_cambiar_password=True` (debe cambiarla al primer login).
Bernardo es el unico admin del equipo real (los demas son editor).
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

# Equipo real (16): (usuario, rol_permisos, cargo, cobertura, marcas).
# Bernardo dicto el organigrama en la segunda audiencia; estas son las
# verticales/funciones reales por persona. `cobertura=True` = entra en la rota de turnos
# (Claro Sports fin de semana son Tezcu+Luis+Roger+Elias; UnoTV son Lalo+Angel; Yustine
# refuerza WhatsApp UnoTV pero entra en cobertura; Jonathan cubre Nacion Gamer).
EQUIPO_AMX: tuple[tuple[str, str, str, bool, tuple[str, ...]], ...] = (
    ("bernardo", ROL_ADMIN, "director", False,
     ("claro-sports", "unotv", "piso-15", "nacion-gamer", "fundacion")),
    ("diana", ROL_EDITOR, "coordinador_redes", False, ("unotv", "piso-15", "fundacion")),
    ("elias", ROL_EDITOR, "coordinador_redes", True, ("claro-sports",)),
    ("maira", ROL_EDITOR, "gerente_podcast", False, ("piso-15",)),
    ("lalo", ROL_EDITOR, "content_manager", True, ("unotv",)),
    ("angel", ROL_EDITOR, "content_manager", True, ("unotv",)),
    ("tezcu", ROL_EDITOR, "community_manager", True, ("claro-sports",)),
    ("luis", ROL_EDITOR, "community_manager", True, ("claro-sports",)),
    ("roger", ROL_EDITOR, "community_manager", True, ("claro-sports",)),
    # Daiana: NO es de ClaroSports (era un error). Es creativa de Fundacion; fuera de la
    # rota de cobertura. Esta fila es la CORRECCION explicita que motiva esta ola.
    ("daiana", ROL_EDITOR, "creativo_vertical", False, ("fundacion",)),
    ("mariana", ROL_EDITOR, "coordinador_operativo", False, ("claro-sports",)),
    ("ale", ROL_EDITOR, "fotografia_qa", False, ("claro-sports",)),
    ("jonathan", ROL_EDITOR, "creativo_vertical", True, ("nacion-gamer",)),
    ("jose", ROL_EDITOR, "redactor", True, ("unotv",)),
    ("yustine", ROL_EDITOR, "editorial_youtube", True, ("claro-sports", "unotv", "piso-15")),
    ("laloyt", ROL_EDITOR, "coordinador_youtube", False,
     ("claro-sports", "unotv", "piso-15", "nacion-gamer")),
)


# Cargos del catalogo VIEJO que la ola anterior usaba en `EQUIPO_AMX`. Si un usuario aun
# tiene uno de estos como cargo, la migracion correctiva lo sustituye por el del
# organigrama nuevo (sin pisar cargos que el admin haya editado a un valor del catalogo
# nuevo). Si su cargo ya esta en el catalogo nuevo (el admin lo cambio o ya corre con la
# nueva semilla), no se toca.
_CARGOS_VIEJOS_CATALOGO: frozenset[str] = frozenset({
    "director", "gerente", "coordinador", "content_manager", "community_manager",
    "redactor", "guionista", "editorial", "estrategia", "fotografia",
    "",  # legado sin clasificar
})


def sembrar_equipo() -> None:
    """Asegura los 16 usuarios del equipo AMX en la BD (idempotente).

    - Usuarios nuevos: se crean con `PASSWORD_INICIAL` y `debe_cambiar_password=True`,
      con su cargo, cobertura y marcas del organigrama.
    - Usuarios ya existentes: NO se toca la contrasena ni el rol; solo se sincronizan
      `cargo` y `cobertura` cuando el cargo actual es del catalogo VIEJO (un admin que
      lo haya cambiado a un cargo del NUEVO catalogo se respeta), y se REEMPLAZA el
      conjunto de marcas N:M para reflejar el organigrama vigente.
    - Caso especial Daiana (sacarla del calendario de ClaroSports): se sobreescribe
      INCONDICIONALMENTE su cargo/cobertura/marcas a (`creativo_vertical`, False,
      ["fundacion"]). Es la correccion critica que motiva esta ola y debe quedar
      garantizada tras el deploy, aunque alguien la haya editado mal a mano.

    Asi el seed se puede correr en cada arranque sin efectos secundarios para usuarios
    cuyo cargo ya este personalizado, y la BD queda al dia con el organigrama.
    """
    existentes = {u["usuario"]: u for u in listar_usuarios()}
    nuevos = 0
    actualizados = 0
    corregidos_daiana = 0
    for usuario, _rol, cargo, cobertura, marcas in EQUIPO_AMX:
        marcas_lista = list(marcas)
        if usuario in existentes:
            actual = existentes[usuario]
            # Correccion correctiva critica: Daiana SIEMPRE se sobreescribe (sale del
            # calendario, va a Fundacion). El admin no tiene autoridad para revertir
            # esta semilla porque su valor anterior era un error de captura.
            if usuario == "daiana":
                if (
                    actual.get("cargo") != cargo
                    or bool(actual.get("cobertura")) != cobertura
                    or sorted(actual.get("marcas") or []) != sorted(marcas_lista)
                ):
                    actualizar_perfil(
                        actual["id"], cargo=cargo, cobertura=cobertura, marcas=marcas_lista,
                    )
                    corregidos_daiana += 1
                continue

            cargo_actual = actual.get("cargo") or ""
            marcas_actuales = sorted(actual.get("marcas") or [])
            cambia_cargo = (
                cargo_actual != cargo
                and cargo_actual in _CARGOS_VIEJOS_CATALOGO
            )
            cambia_cobertura = bool(actual.get("cobertura")) != cobertura and cambia_cargo
            cambia_marcas = marcas_actuales != sorted(marcas_lista)
            # Aplica solo lo que toca; si el admin ya migro el cargo a uno del nuevo
            # catalogo, lo respetamos (no pisamos `cargo` ni `cobertura`).
            kwargs: dict[str, object] = {}
            if cambia_cargo:
                kwargs["cargo"] = cargo
            if cambia_cobertura:
                kwargs["cobertura"] = cobertura
            if cambia_marcas:
                kwargs["marcas"] = marcas_lista
            if kwargs:
                actualizar_perfil(actual["id"], **kwargs)  # type: ignore[arg-type]
                actualizados += 1
            continue
        creado = crear_usuario(
            usuario,
            PASSWORD_INICIAL,
            _rol,
            debe_cambiar_password=True,
            cargo=cargo,
            cobertura=cobertura,
            marcas=marcas_lista,
        )
        if creado is not None:
            nuevos += 1
    if nuevos or actualizados or corregidos_daiana:
        _logger.info(
            "Seed equipo AMX: %d usuarios creados, %d actualizados (cargo/cobertura/marcas), "
            "%d correctivos de Daiana aplicados.",
            nuevos,
            actualizados,
            corregidos_daiana,
        )
