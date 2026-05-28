"""API Usuarios: gestion de cuentas por el admin (#130). SOLO rol admin.

Endpoints (todos bajo `/api/usuarios`, CONTRATO con el frontend):

  - GET    /api/usuarios            -> {usuarios: [{id, usuario, rol, creado, ultimo_acceso}]}
  - POST   /api/usuarios            {usuario, password, rol} -> 201 {id, usuario, rol};
                                      409 si el nombre ya existe.
  - PATCH  /api/usuarios/{id}       {rol?, password?} -> 200 (cambia rol / resetea pass).
  - DELETE /api/usuarios/{id}       -> 204.

GUARDAS de integridad (no quedarse sin acceso de admin):
  - No borrar al ULTIMO admin.
  - No borrarte a TI MISMO.
  - No dejar 0 admins via PATCH (degradar al ultimo admin a editor).

Autorizacion (#150): exige una SESION de un usuario REAL con rol admin. El middleware
deja ese usuario en `request.state.usuario`. El TOKEN de mantenimiento
(`request.state.auth_por_token`) YA NO cuenta como admin: por si solo no puede listar,
modificar ni borrar usuarios -> 403. La UNICA excepcion es el BOOTSTRAP DE RECUPERACION:
crear el PRIMER admin cuando la BD no tiene NINGUN usuario (POST con rol admin). Es un
arranque acotado, no poder admin general, y queda registrado como mantenimiento.
"""

from __future__ import annotations

import logging

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import auth
from .._http_json import leer_json
from ..estados import ROL_ADMIN, ROLES_USUARIO
from ..observabilidad import NOMBRE_LOGGER

_logger = logging.getLogger(NOMBRE_LOGGER)

_MSG_SOLO_ADMIN = "Solo un administrador puede gestionar usuarios."


def _es_admin(request: Request) -> bool:
    """True SOLO si la peticion la hace un usuario real con rol admin (#150).

    El token de mantenimiento NO es admin: una peticion autenticada unicamente por el
    token (`request.state.auth_por_token`) NO pasa esta comprobacion. El unico camino con
    poder admin es una sesion de un usuario real con rol admin. El arranque del PRIMER
    admin por token se trata aparte (la excepcion acotada de `crear`), no aqui.
    """
    usuario = getattr(request.state, "usuario", None)
    return bool(usuario) and usuario.get("rol") == ROL_ADMIN


def _es_token_mantenimiento(request: Request) -> bool:
    """True si la peticion se autentico SOLO por el token de mantenimiento (sin usuario)."""
    return bool(getattr(request.state, "auth_por_token", False))


def _usuario_actual_id(request: Request) -> str | None:
    """Id del usuario de la sesion (None si se entro por token de bootstrap)."""
    usuario = getattr(request.state, "usuario", None)
    return usuario["id"] if usuario else None


def _rechazo_no_admin() -> Response:
    return JSONResponse({"error": _MSG_SOLO_ADMIN}, status_code=403)


async def listar(request: Request) -> Response:
    """GET /api/usuarios: lista de cuentas (sin salt/hash)."""
    if not _es_admin(request):
        return _rechazo_no_admin()
    usuarios = [
        {
            "id": u["id"],
            "usuario": u["usuario"],
            "rol": u["rol"],
            "creado": u["creado"],
            "ultimo_acceso": u["ultimo_acceso"],
        }
        for u in auth.listar_usuarios()
    ]
    return JSONResponse({"usuarios": usuarios})


async def crear(request: Request) -> Response:
    """POST /api/usuarios: alta de cuenta. 409 si el nombre ya existe.

    Autorizacion (#150): la regla normal es rol admin (sesion real). EXCEPCION acotada de
    recuperacion: si la peticion entro por el TOKEN de mantenimiento Y la BD NO tiene
    NINGUN usuario, se permite crear el PRIMER admin (bootstrap). Asi un despliegue recien
    arrancado puede sembrar su admin inicial con el token, pero el token NO da poder admin
    sobre una BD que YA tiene usuarios (ahi exige una sesion admin real, como el resto).
    """
    bootstrap_por_token = False
    if not _es_admin(request):
        # Unica via sin sesion admin: bootstrap del primer admin por token (BD vacia).
        if _es_token_mantenimiento(request) and not auth.hay_usuarios():
            bootstrap_por_token = True
        else:
            return _rechazo_no_admin()
    datos = await leer_json(request)
    usuario = datos.get("usuario")
    password = datos.get("password")
    rol = datos.get("rol")

    if not isinstance(usuario, str) or not usuario.strip():
        return JSONResponse({"error": "El usuario necesita un nombre."}, status_code=400)
    usuario = usuario.strip()
    if len(usuario) > auth.LONGITUD_MAX_USUARIO:
        return JSONResponse(
            {"error": f"El nombre de usuario no puede superar {auth.LONGITUD_MAX_USUARIO} caracteres."},
            status_code=400,
        )
    if not auth.password_aceptable(password):
        return JSONResponse(
            {"error": f"La contraseña debe tener al menos {auth.LONGITUD_MIN_PASSWORD} caracteres."},
            status_code=400,
        )
    if not auth.rol_valido(rol):
        validos = " o ".join(f'"{r}"' for r in ROLES_USUARIO)
        return JSONResponse({"error": f"Rol inválido. Usa {validos}."}, status_code=400)

    # Bootstrap por token: SOLO sirve para sembrar el primer ADMIN (recuperar el acceso),
    # no para crear editores. Crear un editor con la BD vacia dejaria la consola sin admin.
    if bootstrap_por_token and rol != ROL_ADMIN:
        return JSONResponse(
            {"error": "El token de mantenimiento solo puede crear el primer administrador."},
            status_code=403,
        )

    creado = auth.crear_usuario(usuario, password, rol)
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
    """PATCH /api/usuarios/{id}: cambia rol y/o resetea contrasena.

    Guarda: no degradar al ULTIMO admin a editor (dejaria 0 admins).
    """
    if not _es_admin(request):
        return _rechazo_no_admin()
    usuario_id = request.path_params["usuario_id"]
    objetivo = auth.obtener_usuario_por_id(usuario_id)
    if objetivo is None:
        return JSONResponse({"error": "El usuario no existe."}, status_code=404)

    datos = await leer_json(request)
    nuevo_rol = datos.get("rol")
    nueva_password = datos.get("password")
    if nuevo_rol is None and nueva_password is None:
        return JSONResponse(
            {"error": "Indica un rol nuevo o una contraseña nueva."}, status_code=400
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

    if nueva_password is not None and not auth.password_aceptable(nueva_password):
        return JSONResponse(
            {"error": f"La contraseña debe tener al menos {auth.LONGITUD_MIN_PASSWORD} caracteres."},
            status_code=400,
        )

    if nuevo_rol is not None:
        auth.cambiar_rol(usuario_id, nuevo_rol)
    if nueva_password is not None:
        # Reset por el admin: la cuenta debera cambiarla en su proximo acceso.
        auth.establecer_password(usuario_id, nueva_password, debe_cambiar_password=True)

    actualizado = auth.obtener_usuario_por_id(usuario_id)
    return JSONResponse(
        {
            "id": actualizado["id"],
            "usuario": actualizado["usuario"],
            "rol": actualizado["rol"],
        }
    )


async def borrar(request: Request) -> Response:
    """DELETE /api/usuarios/{id}: baja de cuenta (204).

    Guardas: no borrarte a ti mismo, ni borrar al ultimo admin.
    """
    if not _es_admin(request):
        return _rechazo_no_admin()
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
