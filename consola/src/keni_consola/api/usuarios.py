"""API Usuarios: gestion de cuentas por el admin (#130). SOLO rol admin.

Endpoints (todos bajo `/api/usuarios`, CONTRATO con el frontend):

  - GET    /api/usuarios            -> {usuarios: [{id, usuario, rol, creado,
                                      ultimo_acceso, cargo, cobertura, puede_coordinar,
                                      nombre, manager_id, marcas}]}
  - POST   /api/usuarios            {usuario, password, rol, nombre?} -> 201 {id, usuario,
                                      rol}; 409 si el nombre de cuenta ya existe.
  - PATCH  /api/usuarios/{id}       {rol?, password?, cargo?, cobertura?, puede_coordinar?,
                                      nombre?, manager_id?, marcas?} -> 200.
  - DELETE /api/usuarios/{id}       -> 204.

PATCH: ademas de rol/password, el admin puede actualizar
`cargo` (allowlist `CARGOS_USUARIO`), `cobertura` (bool) y `marcas` (lista de ids canonicos
del catalogo de `keni_shared.marcas`). Las marcas se REEMPLAZAN al conjunto enviado (lista
vacia = desasignar todas). Cada valor invalido devuelve 400 con el mensaje accionable.

GUARDAS de integridad (no quedarse sin acceso de admin):
  - No borrar al ULTIMO admin.
  - No borrarte a TI MISMO.
  - No dejar 0 admins via PATCH (degradar al ultimo admin a editor).

Autorizacion (#150): exige una SESION de un usuario REAL con rol admin. El middleware
deja ese usuario en `request.state.usuario`. El TOKEN de mantenimiento
(`request.state.auth_por_token`) NO cuenta como admin: por si solo no puede listar,
modificar ni borrar usuarios -> 403. La UNICA excepcion es el BOOTSTRAP DE RECUPERACION:
crear el PRIMER admin cuando la BD no tiene NINGUN usuario (POST con rol admin). Es un
arranque acotado, no poder admin general, y queda registrado como mantenimiento.
"""

from __future__ import annotations

import logging

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from keni_shared import marcas as marcas_catalogo

from .. import auth, permisos, seguridad
from .._http_json import leer_json
from ..estados import CARGOS_USUARIO, ROL_ADMIN, ROLES_USUARIO
from ..observabilidad import NOMBRE_LOGGER

_logger = logging.getLogger(NOMBRE_LOGGER)

_MSG_SOLO_ADMIN = "Solo un administrador puede gestionar usuarios."

# Hard-block de MFA: un admin OBLIGADO a segundo factor que aun no inscribio passkey no
# puede gestionar usuarios (crear/editar/borrar) hasta enrolar una llave. El login lo deja
# entrar en GRACIA (para que pueda inscribirse) pero las acciones SENSIBLES se cierran: si
# un admin sin segundo factor fuera comprometido (sesion/cookie robada), no podria crear
# admins ni cambiar roles. Codigo estable para que el frontend lleve a "Mi cuenta".
_MSG_MFA_INSCRIPCION = (
    "Antes de gestionar usuarios, inscribe una llave de acceso (passkey) en Mi cuenta."
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


def _es_admin(request: Request) -> bool:
    """True SOLO si la peticion la hace un usuario real con rol admin (#150 + #153).

    Delega en el helper unico de rol (`keni_consola.permisos.es_admin`), FUENTE UNICA
    compartida con `/api/conexiones` y `/api/rota` (#153). Ese helper es ESTRICTO (#150):
    el token de mantenimiento (`request.state.auth_por_token`, sin usuario de sesion) NO
    cuenta como admin. El unico camino con poder admin es una sesion de un usuario real con
    rol admin. El arranque del PRIMER admin por token se trata aparte (la excepcion acotada
    de `crear`), no aqui.
    """
    return permisos.es_admin(request)


def _es_token_mantenimiento(request: Request) -> bool:
    """True si la peticion se autentico SOLO por el token de mantenimiento (sin usuario)."""
    return bool(getattr(request.state, "auth_por_token", False))


def _mfa_inscripcion_pendiente(request: Request) -> bool:
    """True si el admin de la sesion DEBE inscribir passkey antes de poder operar (hard block).

    Gateado IGUAL que el modo gracia del login (`api/auth._mfa_admin_aplica`): rol admin +
    MFA obligatorio de admin (`KENI_CONSOLA_MFA_ADMIN`, def ON) + hay clave de firma
    (`KENI_CONSOLA_MFA_KEY`) + la cuenta aun NO tiene passkey. Sin clave la maquinaria no
    puede correr la inscripcion, asi que NO se bloquea (red anti-lockout, identica a login).
    """
    usuario = getattr(request.state, "usuario", None)
    if usuario is None or usuario.get("rol") != ROL_ADMIN:
        return False
    if not (seguridad.mfa_obligatorio_admin() and seguridad.mfa_key_presente()):
        return False
    refrescado = auth.obtener_usuario_por_id(usuario["id"]) or {}
    return not bool(refrescado.get("mfa_activo"))


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
    if not _es_admin(request):
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
    if not _es_admin(request):
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
    motivo = auth.motivo_rechazo_password(password, usuario)
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

    creado = auth.crear_usuario(usuario, password, rol, nombre=nombre)
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
    if not _es_admin(request):
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
    ):
        return JSONResponse(
            {
                "error": (
                    "Indica un campo a modificar (usuario, rol, contraseña, cargo, cobertura, "
                    "puede_coordinar, nombre, manager_id, marcas o mfa_reset)."
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
            nueva_password, nuevo_usuario or objetivo["usuario"]
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
            "marcas": list(actualizado.get("marcas") or []),
        }
    )


async def borrar(request: Request) -> Response:
    """DELETE /api/usuarios/{id}: baja de cuenta (204).

    Guardas: no borrarte a ti mismo, ni borrar al ultimo admin.
    """
    if not _es_admin(request):
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


RUTAS = [
    Route("/api/usuarios", listar, methods=["GET"]),
    Route("/api/usuarios", crear, methods=["POST"]),
    Route("/api/usuarios/{usuario_id}", actualizar, methods=["PATCH"]),
    Route("/api/usuarios/{usuario_id}", borrar, methods=["DELETE"]),
]
