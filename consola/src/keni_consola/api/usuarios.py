"""API Usuarios: gestion de cuentas. SOLO superadmin (un admin normal NO entra).

Endpoints (todos bajo `/api/usuarios`, CONTRATO con el frontend):

  - GET    /api/usuarios            -> {usuarios: [{id, usuario, rol, creado,
                                      ultimo_acceso, cargo, cobertura, puede_coordinar,
                                      nombre, manager_id, marcas}]}
  - POST   /api/usuarios            {usuario, password, rol, nombre?} -> 201 {id, usuario,
                                      rol}; 409 si el nombre de cuenta ya existe.
  - PATCH  /api/usuarios/{id}       {rol?, password?, cargo?, cobertura?, puede_coordinar?,
                                      nombre?, manager_id?, marcas?} -> 200.
  - DELETE /api/usuarios/{id}       -> 204.

Tokens del MCP (SELF-SERVICE, NO superadmin: cualquier sesión real gestiona los SUYOS):
  - GET    /api/usuarios/tokens-mcp            -> {tokens: [{etiqueta, creado, ultimo_uso,
                                                  expira, revocado}]} (sin el valor).
  - POST   /api/usuarios/tokens-mcp            {etiqueta, expira_horas?} -> 201 {token, etiqueta}
                                                  (el valor del token, UNA vez).
  - DELETE /api/usuarios/tokens-mcp/{token_id} -> 204 (revoca por el valor del token).

PATCH: ademas de rol/password, el admin puede actualizar
`cargo` (allowlist `CARGOS_USUARIO`), `cobertura` (bool) y `marcas` (lista de ids canonicos
del catalogo de `keni_shared.marcas`). Las marcas se REEMPLAZAN al conjunto enviado (lista
vacia = desasignar todas). Cada valor invalido devuelve 400 con el mensaje accionable.

GUARDAS de integridad (no quedarse sin acceso de admin):
  - No borrar al ULTIMO admin.
  - No borrarte a TI MISMO.
  - No dejar 0 admins via PATCH (degradar al ultimo admin a editor).

Autorizacion (#150): exige una SESION de un usuario REAL con el flag `superadmin`. El
middleware deja ese usuario en `request.state.usuario`. Un admin normal (sin flag) NO entra,
y el TOKEN de mantenimiento (`request.state.auth_por_token`) tampoco: 403. La UNICA excepcion
es el BOOTSTRAP DE RECUPERACION: crear el PRIMER admin (que nace superadmin) cuando la BD no
tiene NINGUN usuario (POST con rol admin por token). Arranque acotado, registrado como
mantenimiento.
"""

from __future__ import annotations

import logging

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from keni_shared import marcas as marcas_catalogo

from .. import ajustes, ajustes_catalogo, auth, config, permisos, seguridad
from .._http_json import leer_json
from ..estados import CARGOS_USUARIO, ROL_ADMIN, ROLES_USUARIO
from ..observabilidad import NOMBRE_LOGGER

_logger = logging.getLogger(NOMBRE_LOGGER)

_MSG_SOLO_ADMIN = "Solo un superadministrador puede gestionar usuarios."

# Los tokens del MCP son SELF-SERVICE (cada cuenta gestiona los suyos), no gestión de usuarios:
# exigen una SESIÓN real (no el token de mantenimiento, que no tiene usuario al que atribuir).
_MSG_TOKEN_MCP_SESION = "Necesitas una sesión iniciada para gestionar tus tokens del MCP."

# Hard-block de MFA: una persona a la que se le EXIGE segundo factor (`mfa_requerido`) y aun
# no inscribio passkey no puede gestionar usuarios (crear/editar/borrar) hasta enrolar una
# llave. El login ya la fuerza a inscribirse antes de operar; este es el cierre de defensa en
# la API (sesion/cookie robada). Codigo estable para que el frontend lleve al enrolamiento.
_MSG_MFA_INSCRIPCION = (
    "Antes de gestionar usuarios, inscribe una llave de acceso (passkey)."
)
_CODIGO_MFA_INSCRIPCION = "mfa_inscripcion_requerida"

# Longitud maxima del nombre HUMANO (organigrama). No es la identidad de la cuenta (esa es
# `usuario`), solo lo que se pinta en las tarjetas; un limite holgado evita textos absurdos.
_LONGITUD_MAX_NOMBRE = 120


def _crearia_ciclo(usuario_id: str, manager_id: str) -> bool:
    """True si poner `manager_id` como superior de `usuario_id` cerraria un ciclo.

    Sube por la cadena de superiores desde el candidato (`manager_id`): si en el camino
    aparece `usuario_id`, el enlace cerraria un bucle (A->B->...->A) y el organigrama
    dejaria de ser un arbol. La cota por numero de usuarios evita un bucle infinito si la
    BD ya tuviera un ciclo previo (no deberia, pero somos defensivos).
    """
    visitados: set[str] = set()
    actual: str = manager_id
    while actual:
        if actual == usuario_id:
            return True
        if actual in visitados:
            break  # ciclo preexistente ajeno: cortamos sin afirmar el del enlace nuevo
        visitados.add(actual)
        superior = auth.obtener_usuario_por_id(actual)
        if superior is None:
            break
        actual = superior.get("manager_id") or ""
    return False


def _es_superadmin(request: Request) -> bool:
    """True SOLO si la peticion la hace una sesion real con el flag `superadmin`.

    Gestionar usuarios es competencia EXCLUSIVA del superadmin (un admin normal NO entra).
    Delega en `permisos.es_superadmin`, ESTRICTO (#150): el token de mantenimiento (sin
    usuario de sesion) NO cuenta. El arranque del PRIMER superadmin por token se trata aparte
    (la excepcion acotada de `crear`), no aqui.
    """
    return permisos.es_superadmin(request)


def _es_token_mantenimiento(request: Request) -> bool:
    """True si la peticion se autentico SOLO por el token de mantenimiento (sin usuario)."""
    return bool(getattr(request.state, "auth_por_token", False))


def _mfa_inscripcion_pendiente(request: Request) -> bool:
    """True si a la sesion se le EXIGE passkey y aun no la tiene (hard-block de gestion).

    Se le exige por cualquiera de las politicas (global, admin o per-usuario; fuente unica
    `seguridad.mfa_requerido_para`, gateada por que haya clave de firma: red ANTI-LOCKOUT). El
    login ya fuerza el enrolamiento antes de operar; esto cierra la API si llega una sesion en ese
    estado (cookie robada / gracia a medias).
    """
    usuario = getattr(request.state, "usuario", None)
    if usuario is None:
        return False
    refrescado = auth.obtener_usuario_por_id(usuario["id"]) or {}
    return seguridad.mfa_requerido_para(refrescado) and not bool(refrescado.get("mfa_activo"))


def _rechazo_mfa_pendiente() -> Response:
    return JSONResponse(
        {"error": _MSG_MFA_INSCRIPCION, "codigo": _CODIGO_MFA_INSCRIPCION},
        status_code=403,
    )


def _usuario_actual_id(request: Request) -> str | None:
    """Id del usuario de la sesion (None si se entro por token de bootstrap)."""
    usuario = getattr(request.state, "usuario", None)
    return usuario["id"] if usuario else None


def _rechazo_no_admin() -> Response:
    return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)


async def listar(request: Request) -> Response:
    """GET /api/usuarios: lista de cuentas (sin salt/hash).

    Cada fila incluye `cargo`/`cobertura`/`marcas` para la pagina de Usuarios (organigrama
    del cliente). `marcas` siempre es una lista (vacia si el usuario no tiene marcas asignadas).
    """
    if not _es_superadmin(request):
        return _rechazo_no_admin()
    usuarios = [
        {
            "id": u["id"],
            "usuario": u["usuario"],
            "rol": u["rol"],
            "creado": u["creado"],
            "ultimo_acceso": u["ultimo_acceso"],
            "cargo": u.get("cargo", "") or "",
            "cobertura": bool(u.get("cobertura")),
            "puede_coordinar": bool(u.get("puede_coordinar")),
            "nombre": u.get("nombre", "") or "",
            "manager_id": u.get("manager_id", "") or "",
            "superadmin": bool(u.get("superadmin")),
            "mfa_requerido": bool(u.get("mfa_requerido")),
            "mfa_activo": bool(u.get("mfa_activo")),
            "marcas": list(u.get("marcas") or []),
        }
        for u in auth.listar_usuarios()
    ]
    return JSONResponse({"usuarios": usuarios})


async def crear(request: Request) -> Response:
    """POST /api/usuarios: alta de cuenta. 409 si el nombre ya existe.

    Autorizacion (#150): la regla normal es rol admin (sesion real). EXCEPCION acotada de
    recuperacion: si la peticion entro por el TOKEN de mantenimiento Y la BD NO tiene
    NINGUN usuario, se permite crear el PRIMER admin (bootstrap). Asi un despliegue recien
    arrancado puede crear su admin inicial con el token, pero el token NO da poder admin
    sobre una BD que YA tiene usuarios (ahi exige una sesion admin real, como el resto).
    """
    bootstrap_por_token = False
    if not _es_superadmin(request):
        # Unica via sin sesion admin: bootstrap del primer admin por token (BD vacia).
        if _es_token_mantenimiento(request) and not auth.hay_usuarios():
            bootstrap_por_token = True
        else:
            return _rechazo_no_admin()
    # Hard-block MFA: un admin sin passkey (en gracia) no puede dar de alta cuentas. El
    # bootstrap por token va por su propio carril (BD vacia, sin sesion) y no aplica.
    if not bootstrap_por_token and _mfa_inscripcion_pendiente(request):
        return _rechazo_mfa_pendiente()
    datos = await leer_json(request)
    usuario = datos.get("usuario")
    password = datos.get("password")
    rol = datos.get("rol")
    nombre = datos.get("nombre")
    superadmin = datos.get("superadmin")
    mfa_requerido = datos.get("mfa_requerido")
    if superadmin is not None and not isinstance(superadmin, bool):
        return JSONResponse({"error": "El campo 'superadmin' debe ser true o false."}, status_code=400)
    if mfa_requerido is not None and not isinstance(mfa_requerido, bool):
        return JSONResponse({"error": "El campo 'mfa_requerido' debe ser true o false."}, status_code=400)

    if not isinstance(usuario, str) or not usuario.strip():
        return JSONResponse({"error": "El usuario necesita un nombre."}, status_code=400)
    usuario = usuario.strip()
    # `nombre` (humano, organigrama) es opcional al crear: el admin puede dejarlo y la UI
    # cae al `usuario`. Si llega, debe ser texto y no pasarse de largo.
    if nombre is not None:
        if not isinstance(nombre, str):
            return JSONResponse({"error": "El nombre debe ser texto."}, status_code=400)
        nombre = nombre.strip()
        if len(nombre) > _LONGITUD_MAX_NOMBRE:
            return JSONResponse(
                {"error": f"El nombre no puede superar {_LONGITUD_MAX_NOMBRE} caracteres."},
                status_code=400,
            )
    else:
        nombre = ""
    if len(usuario) > auth.LONGITUD_MAX_USUARIO:
        return JSONResponse(
            {"error": f"El nombre de usuario no puede superar {auth.LONGITUD_MAX_USUARIO} caracteres."},
            status_code=400,
        )
    motivo = auth.motivo_rechazo_password(password, usuario, config.password_min())
    if motivo is not None:
        return JSONResponse({"error": motivo}, status_code=400)
    if not auth.rol_valido(rol):
        validos = " o ".join(f'"{r}"' for r in ROLES_USUARIO)
        return JSONResponse({"error": f"Rol inválido. Usa {validos}."}, status_code=400)

    # Bootstrap por token: SOLO sirve para crear el primer ADMIN (recuperar el acceso),
    # no para crear editores. Crear un editor con la BD vacia dejaria la consola sin admin.
    if bootstrap_por_token and rol != ROL_ADMIN:
        return JSONResponse(
            {"error": "El token de mantenimiento solo puede crear el primer administrador."},
            status_code=403,
        )

    # El primer admin por token nace SUPERADMIN (debe poder gestionar usuarios). En el alta
    # normal, los flags `superadmin`/`mfa_requerido` los decide el superadmin que crea.
    crea_superadmin = True if bootstrap_por_token else bool(superadmin)
    # HERENCIA del predeterminado: si no se indica `mfa_requerido` explícito, la cuenta nueva lo
    # HEREDA según su rol. Un ADMIN (o superadmin) nace exigido si la política de admins está
    # activa (`config.mfa_obligatorio_admin`, def ON); un EDITOR hereda el «passkey para todo el
    # equipo» vigente (`config.mfa_habilitado`). Así las altas quedan cubiertas sin re-aplicar la
    # acción masiva; el enforcement real lo decide luego la columna (se puede eximir). Explícito manda.
    es_admin_nuevo = crea_superadmin or rol == ROL_ADMIN
    mfa_req = (
        bool(mfa_requerido)
        if mfa_requerido is not None
        else (config.mfa_obligatorio_admin() if es_admin_nuevo else config.mfa_habilitado())
    )
    creado = auth.crear_usuario(
        usuario, password, rol, nombre=nombre,
        superadmin=crea_superadmin, mfa_requerido=mfa_req,
    )
    if creado is None:
        return JSONResponse({"error": "Ya existe un usuario con ese nombre."}, status_code=409)
    if bootstrap_por_token:
        # Atribuible a MANTENIMIENTO (token, sin usuario): nunca un "admin fantasma" (#150).
        _logger.warning(
            "Mantenimiento (token): primer admin creado por bootstrap de recuperacion. "
            "usuario=%s (la BD no tenia usuarios).",
            creado["usuario"],
        )
    return JSONResponse(
        {"id": creado["id"], "usuario": creado["usuario"], "rol": creado["rol"]},
        status_code=201,
    )


async def actualizar(request: Request) -> Response:
    """PATCH /api/usuarios/{id}: cambia usuario/rol/contrasena/cargo/cobertura/puede_coordinar/marcas.

    Cuerpo (todo opcional, manda solo lo que cambia):
      - `usuario`          nombre de cuenta (login): texto no vacio, <= LONGITUD_MAX_USUARIO;
                           409 si otra cuenta ya lo usa. Renombrar NO invalida la sesion activa
                           (las sesiones se atan al id, no al login).
      - `rol`              admin|editor (allowlist `ROLES_USUARIO`).
      - `password`         contrasena nueva (reset por admin; obliga al cambio al proximo login).
      - `cargo`            allowlist `CARGOS_USUARIO`; "" para desclasificar.
      - `cobertura`        bool: True/False (entra o no en la rota de turnos).
      - `puede_coordinar`  bool: True/False (candidato a coordinador por celda; ola "coord").
      - `marcas`           lista de ids canonicos del catalogo (`keni_shared.marcas`); reemplaza
                           el conjunto del usuario. `[]` desasigna todas.

    Guardas:
      - No degradar al ULTIMO admin a editor (dejaria 0 admins).
      - Nombre de cuenta vacio/largo -> 400; duplicado -> 409.
      - Cargos invalidos -> 400 con la allowlist.
      - Marcas invalidas -> 400 con la lista canonica.
    """
    if not _es_superadmin(request):
        return _rechazo_no_admin()
    if _mfa_inscripcion_pendiente(request):
        return _rechazo_mfa_pendiente()
    usuario_id = request.path_params["usuario_id"]
    objetivo = auth.obtener_usuario_por_id(usuario_id)
    if objetivo is None:
        return JSONResponse({"error": "El usuario no existe."}, status_code=404)

    datos = await leer_json(request)
    nuevo_usuario = datos.get("usuario")
    nuevo_rol = datos.get("rol")
    nueva_password = datos.get("password")
    nuevo_cargo = datos.get("cargo")
    nueva_cobertura = datos.get("cobertura")
    nuevo_puede_coordinar = datos.get("puede_coordinar")
    nuevo_nombre = datos.get("nombre")
    nuevo_manager_id = datos.get("manager_id")
    nuevas_marcas = datos.get("marcas")
    # `mfa_reset` (recuperacion de cuenta): si `true`, el admin APAGA el segundo factor de la
    # cuenta (borra todas las passkeys + recovery + flag). Es el equivalente al reset de
    # contrasena para cuando alguien pierde sus dispositivos. Mismo guard admin que el PATCH.
    reset_mfa = datos.get("mfa_reset")
    # `superadmin` (gestion de usuarios) y `mfa_requerido` (exigir segundo factor): los decide
    # el superadmin. Booleanos opcionales; `None` deja el campo intacto.
    nuevo_superadmin = datos.get("superadmin")
    nuevo_mfa_requerido = datos.get("mfa_requerido")
    if (
        nuevo_usuario is None
        and nuevo_rol is None
        and nueva_password is None
        and nuevo_cargo is None
        and nueva_cobertura is None
        and nuevo_puede_coordinar is None
        and nuevo_nombre is None
        and nuevo_manager_id is None
        and nuevas_marcas is None
        and reset_mfa is None
        and nuevo_superadmin is None
        and nuevo_mfa_requerido is None
    ):
        return JSONResponse(
            {
                "error": (
                    "Indica un campo a modificar (usuario, rol, contraseña, cargo, cobertura, "
                    "puede_coordinar, nombre, manager_id, marcas, superadmin, mfa_requerido "
                    "o mfa_reset)."
                )
            },
            status_code=400,
        )

    # Nombre de cuenta (login): texto no vacio y dentro del limite. La unicidad la decide la
    # BD al aplicar (UNIQUE -> 409 mas abajo); aqui solo forma y longitud.
    if nuevo_usuario is not None:
        if not isinstance(nuevo_usuario, str):
            return JSONResponse({"error": "El usuario debe ser texto."}, status_code=400)
        nuevo_usuario = nuevo_usuario.strip()
        if not nuevo_usuario:
            return JSONResponse(
                {"error": "El nombre de usuario no puede estar vacío."}, status_code=400
            )
        if len(nuevo_usuario) > auth.LONGITUD_MAX_USUARIO:
            return JSONResponse(
                {
                    "error": (
                        f"El nombre de usuario no puede superar "
                        f"{auth.LONGITUD_MAX_USUARIO} caracteres."
                    )
                },
                status_code=400,
            )

    if reset_mfa is not None and not isinstance(reset_mfa, bool):
        return JSONResponse(
            {"error": "El campo 'mfa_reset' debe ser true o false."}, status_code=400
        )

    if nuevo_superadmin is not None and not isinstance(nuevo_superadmin, bool):
        return JSONResponse(
            {"error": "El campo 'superadmin' debe ser true o false."}, status_code=400
        )
    if nuevo_mfa_requerido is not None and not isinstance(nuevo_mfa_requerido, bool):
        return JSONResponse(
            {"error": "El campo 'mfa_requerido' debe ser true o false."}, status_code=400
        )
    # Guarda: quitar el superadmin al ULTIMO superadmin dejaria la consola sin quien gestione
    # usuarios (nadie podria volver a entrar a /usuarios). Igual que la guarda del ultimo admin.
    if (
        nuevo_superadmin is False
        and objetivo.get("superadmin")
        and auth.contar_superadmins() <= 1
    ):
        return JSONResponse(
            {"error": "No puedes quitar el superadmin al último superadministrador."},
            status_code=409,
        )

    if nuevo_rol is not None:
        if not auth.rol_valido(nuevo_rol):
            validos = " o ".join(f'"{r}"' for r in ROLES_USUARIO)
            return JSONResponse({"error": f"Rol inválido. Usa {validos}."}, status_code=400)
        # Guarda: degradar al ultimo admin dejaria la consola sin administradores.
        if (
            objetivo["rol"] == ROL_ADMIN
            and nuevo_rol != ROL_ADMIN
            and auth.contar_admins() <= 1
        ):
            return JSONResponse(
                {"error": "No puedes degradar al último administrador."}, status_code=409
            )

    if nueva_password is not None:
        motivo = auth.motivo_rechazo_password(
            nueva_password, nuevo_usuario or objetivo["usuario"], config.password_min()
        )
        if motivo is not None:
            return JSONResponse({"error": motivo}, status_code=400)

    if nuevo_cargo is not None:
        if not isinstance(nuevo_cargo, str):
            return JSONResponse({"error": "Cargo inválido."}, status_code=400)
        if nuevo_cargo and nuevo_cargo not in CARGOS_USUARIO:
            return JSONResponse(
                {"error": f"Cargo desconocido: {nuevo_cargo!r}."},
                status_code=400,
            )

    if nueva_cobertura is not None and not isinstance(nueva_cobertura, bool):
        return JSONResponse(
            {"error": "El campo 'cobertura' debe ser true o false."}, status_code=400
        )

    if nuevo_puede_coordinar is not None and not isinstance(nuevo_puede_coordinar, bool):
        return JSONResponse(
            {"error": "El campo 'puede_coordinar' debe ser true o false."},
            status_code=400,
        )

    if nuevo_nombre is not None:
        if not isinstance(nuevo_nombre, str):
            return JSONResponse({"error": "El nombre debe ser texto."}, status_code=400)
        nuevo_nombre = nuevo_nombre.strip()
        if len(nuevo_nombre) > _LONGITUD_MAX_NOMBRE:
            return JSONResponse(
                {"error": f"El nombre no puede superar {_LONGITUD_MAX_NOMBRE} caracteres."},
                status_code=400,
            )

    # `manager_id` define el organigrama: "" = sin superior (raiz, p.ej. el director). Si
    # llega un id, debe apuntar a un usuario REAL, distinto de uno mismo y sin cerrar ciclos
    # (el grafo de reporte tiene que seguir siendo un arbol). Para desligar, manda "".
    if nuevo_manager_id is not None:
        if not isinstance(nuevo_manager_id, str):
            return JSONResponse(
                {"error": "El campo 'manager_id' debe ser el id de un usuario o cadena vacía."},
                status_code=400,
            )
        elif nuevo_manager_id == "":
            pass  # desligar: el usuario pasa a ser raiz del organigrama
        elif nuevo_manager_id == usuario_id:
            return JSONResponse(
                {"error": "Una persona no puede reportarse a sí misma."}, status_code=400
            )
        elif auth.obtener_usuario_por_id(nuevo_manager_id) is None:
            return JSONResponse(
                {"error": "El superior indicado no existe."}, status_code=400
            )
        elif _crearia_ciclo(usuario_id, nuevo_manager_id):
            return JSONResponse(
                {
                    "error": (
                        "Ese cambio crearía un ciclo en el organigrama "
                        "(el superior depende, directa o indirectamente, de esta persona)."
                    )
                },
                status_code=400,
            )

    if nuevas_marcas is not None:
        if not isinstance(nuevas_marcas, list) or not all(
            isinstance(m, str) for m in nuevas_marcas
        ):
            return JSONResponse(
                {"error": "El campo 'marcas' debe ser una lista de identificadores."},
                status_code=400,
            )
        validas = set(marcas_catalogo.ids())
        invalidas = [m for m in nuevas_marcas if m not in validas]
        if invalidas:
            return JSONResponse(
                {
                    "error": (
                        f"Marca(s) desconocida(s): {', '.join(invalidas)}. "
                        f"Usa una de: {', '.join(sorted(validas))}."
                    )
                },
                status_code=400,
            )

    # Promover a admin MARCA la exigencia de passkey (predeterminado de admins), salvo que el
    # mismo PATCH la fije explícitamente: así un admin nuevo no queda sin segundo factor por la
    # puerta de atrás. Para EXIMIR a un admin, manda `mfa_requerido=false` (en este PATCH o luego).
    if (
        nuevo_rol == ROL_ADMIN
        and objetivo["rol"] != ROL_ADMIN
        and nuevo_mfa_requerido is None
        and config.mfa_obligatorio_admin()
    ):
        nuevo_mfa_requerido = True

    if nuevo_usuario is not None and nuevo_usuario != objetivo["usuario"]:
        cambiado = auth.cambiar_usuario(usuario_id, nuevo_usuario)
        if cambiado is None:
            return JSONResponse(
                {"error": "Ya existe un usuario con ese nombre."}, status_code=409
            )
    if nuevo_rol is not None:
        auth.cambiar_rol(usuario_id, nuevo_rol)
    if nueva_password is not None:
        # Reset por el admin: la cuenta debera cambiarla en su proximo acceso.
        auth.establecer_password(usuario_id, nueva_password, debe_cambiar_password=True)
    if reset_mfa:
        # Recuperacion de cuenta: el admin apaga el segundo factor (perdida de dispositivo).
        auth.desactivar_mfa(usuario_id)
        _logger.warning(
            "Admin reseteo el MFA de la cuenta %s (recuperacion de segundo factor).",
            objetivo["usuario"],
        )
    if (
        nuevo_cargo is not None
        or nueva_cobertura is not None
        or nuevo_puede_coordinar is not None
        or nuevo_nombre is not None
        or nuevo_manager_id is not None
        or nuevas_marcas is not None
        or nuevo_superadmin is not None
        or nuevo_mfa_requerido is not None
    ):
        auth.actualizar_perfil(
            usuario_id,
            cargo=nuevo_cargo if nuevo_cargo is not None else None,
            cobertura=nueva_cobertura if nueva_cobertura is not None else None,
            puede_coordinar=(
                nuevo_puede_coordinar if nuevo_puede_coordinar is not None else None
            ),
            nombre=nuevo_nombre if nuevo_nombre is not None else None,
            manager_id=nuevo_manager_id if nuevo_manager_id is not None else None,
            superadmin=nuevo_superadmin if nuevo_superadmin is not None else None,
            mfa_requerido=nuevo_mfa_requerido if nuevo_mfa_requerido is not None else None,
            marcas=list(nuevas_marcas) if nuevas_marcas is not None else None,
        )

    actualizado = auth.obtener_usuario_por_id(usuario_id)
    return JSONResponse(
        {
            "id": actualizado["id"],
            "usuario": actualizado["usuario"],
            "rol": actualizado["rol"],
            "cargo": actualizado.get("cargo", "") or "",
            "cobertura": bool(actualizado.get("cobertura")),
            "puede_coordinar": bool(actualizado.get("puede_coordinar")),
            "nombre": actualizado.get("nombre", "") or "",
            "manager_id": actualizado.get("manager_id", "") or "",
            "superadmin": bool(actualizado.get("superadmin")),
            "mfa_requerido": bool(actualizado.get("mfa_requerido")),
            "mfa_activo": bool(actualizado.get("mfa_activo")),
            "marcas": list(actualizado.get("marcas") or []),
        }
    )


async def borrar(request: Request) -> Response:
    """DELETE /api/usuarios/{id}: baja de cuenta (204).

    Guardas: no borrarte a ti mismo, ni borrar al ultimo admin.
    """
    if not _es_superadmin(request):
        return _rechazo_no_admin()
    if _mfa_inscripcion_pendiente(request):
        return _rechazo_mfa_pendiente()
    usuario_id = request.path_params["usuario_id"]
    objetivo = auth.obtener_usuario_por_id(usuario_id)
    if objetivo is None:
        return JSONResponse({"error": "El usuario no existe."}, status_code=404)

    if usuario_id == _usuario_actual_id(request):
        return JSONResponse({"error": "No puedes borrar tu propia cuenta."}, status_code=409)
    if objetivo["rol"] == ROL_ADMIN and auth.contar_admins() <= 1:
        return JSONResponse(
            {"error": "No puedes borrar al último administrador."}, status_code=409
        )

    auth.borrar_usuario(usuario_id)
    return Response(status_code=204)


# --------------------------------------------------------------------------- #
# Llaves de acceso (passkeys) de OTRA persona, gestionadas por el superadmin    #
# --------------------------------------------------------------------------- #
#
# El propio usuario gestiona SUS llaves en "Mi cuenta" (`/api/auth/mfa/credenciales*`). Aquí el
# SUPERADMIN ve y borra las de CUALQUIER cuenta: rescate cuando alguien pierde un dispositivo o no
# puede usar su passkey en un equipo concreto (p.ej. un PC sin permiso de llavero). NO hay "crear
# una passkey por otra persona": una passkey se genera EN el dispositivo del propio usuario (su
# clave privada nunca sale de ahí), así que el superadmin solo puede LISTAR, BORRAR una llave
# concreta o resetear todas (`mfa_reset` en el PATCH). Recuperar el acceso = borrar la llave que
# estorba (o todas) y, si hace falta, eximir a la persona (`mfa_requerido=false`).


async def passkeys_de_usuario(request: Request) -> Response:
    """GET /api/usuarios/{id}/passkeys: las llaves de acceso (passkeys) de una persona, SIN secretos.

    Solo superadmin. Devuelve `{credenciales: [{id, nombre, creada, ultimo_uso}]}` (nunca la
    `public_key`): la lista que el panel de Usuarios muestra para borrar una llave concreta.
    """
    if not _es_superadmin(request):
        return _rechazo_no_admin()
    usuario_id = request.path_params["usuario_id"]
    if auth.obtener_usuario_por_id(usuario_id) is None:
        return JSONResponse({"error": "El usuario no existe."}, status_code=404)
    credenciales = [
        {
            "id": c["id"],
            "nombre": c["nombre"],
            "creada": c["creada"],
            "ultimo_uso": c["ultimo_uso"],
        }
        for c in auth.listar_credenciales_mfa(usuario_id)
    ]
    return JSONResponse({"credenciales": credenciales})


async def borrar_passkey_de_usuario(request: Request) -> Response:
    """DELETE /api/usuarios/{id}/passkeys/{credencial_id}: borra UNA llave de acceso de la persona (204).

    Solo superadmin. Si era la ÚLTIMA, `borrar_credencial_mfa` apaga `mfa_activo`. 404 si esa llave
    no existe o no es de esa persona. Es la versión por-llave del reset total (`mfa_reset`).
    """
    if not _es_superadmin(request):
        return _rechazo_no_admin()
    if _mfa_inscripcion_pendiente(request):
        return _rechazo_mfa_pendiente()
    usuario_id = request.path_params["usuario_id"]
    if auth.obtener_usuario_por_id(usuario_id) is None:
        return JSONResponse({"error": "El usuario no existe."}, status_code=404)
    credencial_id = request.path_params.get("credencial_id", "")
    if not auth.borrar_credencial_mfa(usuario_id, credencial_id):
        return JSONResponse({"error": "Esa llave de acceso no existe."}, status_code=404)
    return Response(status_code=204)


# --------------------------------------------------------------------------- #
# Configuración GLOBAL de seguridad/acceso (superadmin)                        #
# --------------------------------------------------------------------------- #
#
# Política del equipo, no de una persona: vive en el panel de Usuarios (superadmin), con
# contrato propio (NO el `/api/ajustes` de admin). Reutiliza la maquinaria de ajustes —catálogo
# declarativo tipado (`ajustes_catalogo`) + store editable (`ajustes`), precedencia
# STORE > ENV > DEFECTO de `config._crudo`—: togglear aquí escribe el store y los accesores
# (`config.mfa_habilitado`/`mfa_obligatorio_admin`/`sesion_horas`/`sesion_max_horas`/
# `password_min`) lo recogen sin más wiring. Acotado a estas claves curadas (jamás otras del
# catálogo de la máquina). El enforcement de MFA ya lo aplica `seguridad.mfa_requerido_para`.
_AJUSTES_SEGURIDAD: tuple[ajustes_catalogo.Ajuste, ...] = (
    # «Passkey obligatorio para todo el equipo» NO es un override de runtime (el enforcement es
    # per-usuario; ver `seguridad.mfa_requerido_para`). Es el PREDETERMINADO global: el frontend lo
    # togglea como ACCIÓN MASIVA (marca/desmarca `mfa_requerido` en las cuentas existentes) y,
    # persistido aquí, lo HEREDAN las cuentas NUEVAS al crearse (ver `crear`). Editable per-usuario.
    ajustes_catalogo.Ajuste(
        clave=config.ENV_MFA,
        tipo="bool",
        etiqueta="Passkey obligatorio para todo el equipo",
        ayuda="Predeterminado del equipo: marca a las cuentas existentes y se HEREDA en las "
        "nuevas. Luego puedes eximir o exigir persona a persona desde su ficha.",
        grupo="seguridad",
        defecto=False,
    ),
    ajustes_catalogo.Ajuste(
        clave=config.ENV_MFA_ADMIN,
        tipo="bool",
        etiqueta="Passkey obligatorio para administradores",
        ayuda="Predeterminado de las cuentas admin (publican en canales de marca): un admin nuevo "
        "nace exigido y al promover a alguien a admin se le marca. Puedes eximir a un admin "
        "concreto desde su ficha si no puede usar passkey en su equipo.",
        grupo="seguridad",
        defecto=True,
    ),
    ajustes_catalogo.Ajuste(
        clave=config.ENV_SESION_HORAS,
        tipo="int",
        etiqueta="Duración de la sesión (horas)",
        ayuda="Ventana de inactividad: la sesión se renueva con cada uso y caduca tras estas "
        "horas sin actividad.",
        grupo="seguridad",
        defecto=config.SESION_HORAS_DEF,
        minimo=1,
    ),
    ajustes_catalogo.Ajuste(
        clave=config.ENV_SESION_MAX_HORAS,
        tipo="int",
        etiqueta="Vida máxima de la sesión (horas)",
        ayuda="Tope absoluto desde que se creó la sesión: pasado este límite se cierra aunque "
        "se siga usando.",
        grupo="seguridad",
        defecto=config.SESION_MAX_HORAS_DEF,
        minimo=1,
    ),
    ajustes_catalogo.Ajuste(
        clave=config.ENV_PASSWORD_MIN,
        tipo="int",
        etiqueta="Longitud mínima de contraseña",
        ayuda="Mínimo de caracteres para una contraseña nueva o reseteada. Suelo de 12 (NIST "
        "800-63B); súbela para endurecer la política.",
        grupo="seguridad",
        defecto=config.PASSWORD_MIN_DEF,
        minimo=config.PASSWORD_MIN_DEF,
        maximo=128,
    ),
)
_AJUSTES_SEGURIDAD_POR_CLAVE = {a.clave: a for a in _AJUSTES_SEGURIDAD}


async def configuracion(request: Request) -> Response:
    """GET /api/usuarios/configuracion: ajustes globales de seguridad (valor efectivo + fuente).

    Solo superadmin. Devuelve `{ajustes: [...]}` con la forma del catálogo (`ajustes_catalogo.a_dict`).
    """
    if not _es_superadmin(request):
        return _rechazo_no_admin()
    return JSONResponse(
        {"ajustes": [ajustes_catalogo.a_dict(a) for a in _AJUSTES_SEGURIDAD]}
    )


async def actualizar_configuracion(request: Request) -> Response:
    """PATCH /api/usuarios/configuracion: escribe `{clave, valor}` o resetea `{clave, reset}`.

    Solo superadmin y SOLO claves de `_AJUSTES_SEGURIDAD` (400 si no). Valida con el catálogo y
    persiste en el store editable; los accesores de `config` recogen el cambio (STORE > ENV >
    DEFECTO). `reset` borra la clave del store (vuelve a env/defecto). Devuelve el ajuste actualizado.
    """
    if not _es_superadmin(request):
        return _rechazo_no_admin()
    datos = await leer_json(request)
    clave = datos.get("clave")
    if not isinstance(clave, str) or clave not in _AJUSTES_SEGURIDAD_POR_CLAVE:
        return JSONResponse({"error": "Ajuste de seguridad desconocido."}, status_code=400)
    ajuste = _AJUSTES_SEGURIDAD_POR_CLAVE[clave]

    if datos.get("reset") is True:
        try:
            ajustes.borrar(clave)
        except OSError as e:
            return JSONResponse(
                {"error": f"No se pudo restablecer el ajuste: {e}"}, status_code=400
            )
        return JSONResponse({"ajuste": ajustes_catalogo.a_dict(ajuste)})

    if "valor" not in datos:
        return JSONResponse(
            {"error": "Indica el 'valor' a guardar o usa 'reset' para restablecer."},
            status_code=400,
        )
    a_guardar, error = ajustes_catalogo.validar_valor(ajuste, datos.get("valor"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    try:
        ajustes.guardar(clave, a_guardar)
    except OSError as e:
        return JSONResponse({"error": f"No se pudo guardar el ajuste: {e}"}, status_code=400)
    return JSONResponse({"ajuste": ajustes_catalogo.a_dict(ajuste)})


# --------------------------------------------------------------------------- #
# Tokens del MCP operativo (self-service de la cuenta en sesión)               #
# --------------------------------------------------------------------------- #
#
# Cada cuenta emite/lista/revoca SUS PROPIOS tokens del MCP por identidad (`tokens_mcp`): un
# secreto atado al usuario que un cliente MCP (Claude Code) presenta como bearer y que el guard
# de `/mcp` resuelve a esta identidad, sin cabeceras. NO es gestión de usuarios (no exige
# superadmin), pero sí una SESIÓN real: el token de mantenimiento no tiene usuario al que atribuir.


def _rechazo_token_mcp_sesion() -> Response:
    return JSONResponse({"error": _MSG_TOKEN_MCP_SESION}, status_code=403)


async def listar_tokens_mcp(request: Request) -> Response:
    """GET /api/usuarios/tokens-mcp: tokens MCP de la cuenta en sesión, SIN el secreto.

    Devuelve `{tokens: [{etiqueta, creado, ultimo_uso, expira, revocado}]}`. El valor del token
    NO se devuelve aquí (solo se entrega una vez, al crearlo).
    """
    usuario_id = _usuario_actual_id(request)
    if usuario_id is None:
        return _rechazo_token_mcp_sesion()
    return JSONResponse({"tokens": auth.listar_tokens_mcp(usuario_id)})


async def crear_token_mcp(request: Request) -> Response:
    """POST /api/usuarios/tokens-mcp {etiqueta, expira_horas?}: emite un token (201).

    Devuelve `{token, etiqueta}` con el VALOR del token UNA sola vez (no se vuelve a mostrar).
    `etiqueta` es obligatoria; `expira_horas` (opcional) son las horas hasta caducar (sin ella,
    sin caducidad).
    """
    usuario_id = _usuario_actual_id(request)
    if usuario_id is None:
        return _rechazo_token_mcp_sesion()
    datos = await leer_json(request)
    etiqueta = datos.get("etiqueta")
    if not isinstance(etiqueta, str) or not etiqueta.strip():
        return JSONResponse({"error": "El token necesita una etiqueta."}, status_code=400)
    etiqueta = etiqueta.strip()
    if len(etiqueta) > _LONGITUD_MAX_NOMBRE:
        return JSONResponse(
            {"error": f"La etiqueta no puede superar {_LONGITUD_MAX_NOMBRE} caracteres."},
            status_code=400,
        )
    expira_horas = datos.get("expira_horas")
    if expira_horas is not None and (
        isinstance(expira_horas, bool)
        or not isinstance(expira_horas, (int, float))
        or expira_horas <= 0
    ):
        return JSONResponse(
            {"error": "El campo 'expira_horas' debe ser un número de horas positivo."},
            status_code=400,
        )
    token = auth.crear_token_mcp(usuario_id, etiqueta, expira=expira_horas)
    return JSONResponse({"token": token, "etiqueta": etiqueta}, status_code=201)


async def revocar_token_mcp(request: Request) -> Response:
    """DELETE /api/usuarios/tokens-mcp/{token_id}: revoca un token MCP por su valor (204).

    404 si no existe ningún token con ese valor. Marca el token `revocado` (no lo borra): el
    guard de `/mcp` deja de aceptarlo de inmediato.
    """
    usuario_id = _usuario_actual_id(request)
    if usuario_id is None:
        return _rechazo_token_mcp_sesion()
    token = request.path_params.get("token_id", "")
    if not auth.revocar_token_mcp(token):
        return JSONResponse({"error": "Ese token no existe."}, status_code=404)
    return Response(status_code=204)


RUTAS = [
    Route("/api/usuarios", listar, methods=["GET"]),
    Route("/api/usuarios", crear, methods=["POST"]),
    # Rutas LITERALES antes que la paramétrica `{usuario_id}` (Starlette matchea en orden).
    Route("/api/usuarios/configuracion", configuracion, methods=["GET"]),
    Route("/api/usuarios/configuracion", actualizar_configuracion, methods=["PATCH"]),
    # Tokens del MCP (self-service): literal `tokens-mcp` antes que la paramétrica `{usuario_id}`.
    Route("/api/usuarios/tokens-mcp", listar_tokens_mcp, methods=["GET"]),
    Route("/api/usuarios/tokens-mcp", crear_token_mcp, methods=["POST"]),
    Route("/api/usuarios/tokens-mcp/{token_id}", revocar_token_mcp, methods=["DELETE"]),
    # Llaves de acceso de OTRA persona (superadmin): listar / borrar una concreta. Van ANTES de
    # las paramétricas de 2 segmentos (no colisionan, pero las agrupamos junto a /configuracion).
    Route("/api/usuarios/{usuario_id}/passkeys", passkeys_de_usuario, methods=["GET"]),
    Route(
        "/api/usuarios/{usuario_id}/passkeys/{credencial_id}",
        borrar_passkey_de_usuario,
        methods=["DELETE"],
    ),
    Route("/api/usuarios/{usuario_id}", actualizar, methods=["PATCH"]),
    Route("/api/usuarios/{usuario_id}", borrar, methods=["DELETE"]),
]
