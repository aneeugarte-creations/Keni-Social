"""Permisos por ROL de la Consola Keni: helper unico de "¿es admin?" (#153).

CONTEXTO (#153, deriva de #130 multiusuario / #145 acotado por permisos)
========================================================================
El servicio multiusuario hosted tiene atribucion de autor (#130 Fase 1) pero el
ESTADO y los SECRETOS globales (clave del proveedor de imagen en `secretos.toml`,
tokens de redes en el `config.toml` de metricas) viven en UN solo fichero que
cualquier usuario autenticado podia leer y mutar. El primer cerrojo achacable es
exigir rol ADMIN para esas areas sensibles y globales.

Este modulo centraliza la pregunta "¿esta peticion la hace un admin?" que antes
estaba DUPLICADA inline en `api/usuarios.py` y `api/rota.py` (mismo cuerpo). Mismo
contrato exacto que esas copias:

  - Si se entro por el TOKEN interino de mantenimiento (`request.state.auth_por_token`),
    cuenta como acceso de mantenimiento con plenos permisos -> True (no rompe el modo
    local ni el token de despliegue, que no llevan usuario asociado).
  - Si hay una SESION de usuario (`request.state.usuario`), True solo si su rol es
    `admin`; un `editor` -> False.
  - Sin credencial reconocida (no deberia llegar aqui: el middleware ya devolvio 401),
    False por defecto.

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
    """True si la peticion la hace un admin o entro por el token de mantenimiento.

    Lee SOLO el estado que dejo el middleware (`request.state.auth_por_token` y
    `request.state.usuario`); no abre ninguna via de auth nueva. El token interino
    (mantenimiento / despliegue, sin usuario) cuenta como plenos permisos.
    """
    if getattr(request.state, "auth_por_token", False):
        return True
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
