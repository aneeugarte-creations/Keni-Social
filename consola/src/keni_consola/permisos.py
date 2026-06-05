"""Permisos por ROL de la Consola Keni: helper unico de "¿es admin?" (#153).

CONTEXTO (#153, deriva de #130 multiusuario / #145 acotado por permisos)
========================================================================
El servicio multiusuario hosted tiene atribucion de autor (#130 Fase 1) pero el
ESTADO y los SECRETOS globales (clave del proveedor de imagen en `secretos.toml`,
tokens de redes en el `config.toml` de metricas) viven en UN solo fichero que
cualquier usuario autenticado podia leer y mutar. El primer cerrojo achacable es
exigir rol ADMIN para esas areas sensibles y globales.

Este modulo centraliza la pregunta "¿esta peticion la hace un admin?" que antes
estaba DUPLICADA inline en `api/usuarios.py` y `api/rota.py` (mismo cuerpo). Es la
FUENTE UNICA de la decision de rol admin para `/api/usuarios`, `/api/conexiones` y
`/api/rota`.

CONTRATO ESTRICTO (#150 + #153): el TOKEN de mantenimiento NO es admin
======================================================================
Alineado con #150 (CRITICO: el token de mantenimiento NO es un backdoor de admin),
este helper es ESTRICTO:

  - Si hay una SESION de un usuario REAL (`request.state.usuario`), True SOLO si su rol
    es `admin`; un `editor` -> False.
  - Si se entro SOLO por el TOKEN de mantenimiento (`request.state.auth_por_token`, sin
    usuario de sesion), NO es admin -> False. El token pasa la barrera de `/api` (es una
    credencial de mantenimiento), pero NO otorga poder admin sobre usuarios/secretos.
  - Sin credencial reconocida (no deberia llegar aqui: el middleware ya devolvio 401),
    False por defecto.

Consecuencia: el token de mantenimiento recibe 403 en `/api/usuarios/*` y en
`/api/conexiones/*`; solo una SESION admin real gestiona usuarios y secretos. La UNICA
excepcion acotada es el BOOTSTRAP del primer admin con la BD vacia, que `api/usuarios`
trata aparte (no aqui).

NO inventa una via de auth nueva: solo LEE el estado que `SeguridadConsola` ya dejo
en `request.state`. El gate de sesion + CSRF lo sigue aplicando el middleware.

ALCANCE (lo que SI y lo que NO cubre #153)
==========================================
Hoy el modelo de roles es binario (`admin`/`editor`) y SIN dimension de tenant ni de
marca/proyecto en la cuenta: por eso el cerrojo achacable es "solo admin" sobre el
estado/secreto global, no un acotamiento por tenant. El AISLAMIENTO de secretos POR
TENANT (un almacen por cliente en vez de un fichero global) es un cambio de arquitectura
mayor y queda DIFERIDO: ver `docs/adr/0003-aislamiento-secretos-por-tenant.md`.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .estados import ROL_ADMIN

# Mensaje generico de rechazo por falta de rol admin (en espanol, forma `{"error": ...}`).
# Cada area puede pasar el suyo a `rechazo_solo_admin`; este es el por defecto.
MSG_SOLO_ADMIN = "Solo un administrador puede acceder a esta sección."


def es_admin(request: Request) -> bool:
    """True SOLO si la peticion la hace una SESION de un usuario real con rol admin.

    ESTRICTO (#150 + #153): el token de mantenimiento NO es admin. Lee SOLO el estado que
    dejo el middleware (`request.state.usuario`); no abre ninguna via de auth nueva. Una
    peticion autenticada UNICAMENTE por el token (`request.state.auth_por_token`, sin
    usuario de sesion) NO pasa: el token no es un backdoor de admin sobre usuarios/secretos
    (#150). El bootstrap del primer admin con la BD vacia se trata aparte (`api/usuarios`).
    """
    usuario = getattr(request.state, "usuario", None)
    if not isinstance(usuario, dict):
        return False
    return usuario.get("rol") == ROL_ADMIN


def rechazo_solo_admin(mensaje: str = MSG_SOLO_ADMIN) -> Response:
    """Respuesta 403 estandar (`{"error": ...}`) para un acceso que exige rol admin."""
    return JSONResponse({"error": mensaje}, status_code=403)


def usuario_actual(request: Request) -> dict[str, Any] | None:
    """Usuario de la sesion (forma publica), o None si se entro por el token interino."""
    usuario = getattr(request.state, "usuario", None)
    return usuario if isinstance(usuario, dict) else None


# --------------------------------------------------------------------------- #
# Marca como FOCO POR DEFECTO (NO una restriccion): capacitar, no limitar       #
# --------------------------------------------------------------------------- #
#
# CONTRATO (revertido respecto al cerrojo duro del ADR 0003): el equipo es
# MULTIDISCIPLINAR; la marca NO acota lo que alguien puede ver o tocar. Cualquiera
# cubre/accede CUALQUIER marca. La marca es solo un FOCO POR DEFECTO: cuando un
# listado/metrica no pide marca explicita, se enfoca en la(s) marca(s) preferida(s)
# del usuario para reducir la mezcla de contexto. Ese foco es SIEMPRE sobreescribible
# pasando una `marca` explicita (cualquiera) y NUNCA bloquea (sin 403/404/400 por marca).
#
# Por eso NO existe ya `rechazo_pieza`/`rechazo_marca`: no hay cerrojo por marca. Solo
# queda `marcas_preferentes` (antes `marcas_visibles`/`marcas_scope`), que da el FOCO
# por defecto (None = sin preferencia => todas las marcas).


def marcas_preferentes(request: Request) -> set[str] | None:
    """Marcas (ids canonicos) en las que la sesion se ENFOCA por defecto, o None si sin foco.

    None (sin foco => todas las marcas) cuando: es admin, se entro por token (sin usuario
    de sesion), o el usuario no tiene marcas asignadas. En otro caso, el conjunto de ids
    canonicos de sus marcas (relacion N:M del organigrama AMX).

    NO es una restriccion: solo es el FOCO POR DEFECTO de listados/metricas cuando no se
    pide marca explicita. Pasar una `marca` explicita (cualquiera) sobreescribe este foco.

    La sesion del middleware no arrastra las marcas (la cookie no carga la tabla N:M),
    asi que se consultan al vuelo por id de usuario, igual que hace `GET /api/auth/me`.
    """
    usuario = usuario_actual(request)
    if usuario is None:
        return None
    if usuario.get("rol") == ROL_ADMIN:
        return None
    from .auth import obtener_usuario_por_id  # lazy: evita ciclo de import con auth

    refrescado = obtener_usuario_por_id(usuario["id"]) or {}
    marcas = refrescado.get("marcas") or []
    return set(marcas) if marcas else None
