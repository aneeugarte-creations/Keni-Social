"""Auth multiusuario de la Consola Keni: usuarios, roles, sesiones, bootstrap.

Sobre la barrera de TOKEN unico previa se monta un modelo MULTIUSUARIO con login
user/pass y roles (`admin`/`editor`). El middleware `SeguridadConsola` (ver
`seguridad.py`) acepta UNA sesion valida (cookie) O el token de bootstrap, de modo que
los clientes y tests que ya usan el token siguen funcionando.

ORGANIZACION (paquete) — este `__init__` es solo la FACHADA que reexporta el contrato.
El trabajo vive en submodulos pequenos y testeables:

  - `hashing`   -> scrypt + salt, verificacion en tiempo constante, politica de longitud.
  - `usuarios`  -> CRUD de cuentas, login con anti fuerza bruta, cambio de contrasena.
  - `sesiones`  -> sesiones server-side con ventana deslizante y la cookie de sesion.
  - `bootstrap` -> alta idempotente del primer admin.
  - `_comun`    -> utilidades de tiempo y duracion de sesion (interno).

Los consumidores (`seguridad.py`, `api/auth.py`, `api/usuarios.py`, `app.py`) siguen
importando `from . import auth` y usando `auth.X`: el contrato publico no cambia.
"""

from __future__ import annotations

from ._comun import horas_sesion
from .bootstrap import (
    ADMIN_POR_DEFECTO,
    ENV_ADMIN_PASS,
    ENV_ADMIN_USER,
    bootstrap_admin,
    hay_usuarios,
)
from .hashing import (
    LONGITUD_MAX_PASSWORD,
    LONGITUD_MAX_USUARIO,
    LONGITUD_MIN_PASSWORD,
    PASSWORDS_PROHIBIDAS,
    hashear_password,
    motivo_rechazo_password,
    necesita_rehash,
    password_aceptable,
    rol_valido,
    verificar_password,
)
from .mfa import (
    NOMBRE_RP_DEFECTO,
    MfaNoDisponible,
    b64url_a_bytes,
    bytes_a_b64url,
    cifrador,
    credential_id_de_respuesta,
    opciones_login,
    opciones_registro,
    verificar_login,
    verificar_registro,
)
from .sesiones import COOKIE_SESION, borrar_sesion, crear_sesion, sesion_valida
from .tokens_mcp import (
    crear_token_mcp,
    listar_tokens_mcp,
    revocar_token_mcp,
    revocar_token_mcp_de_usuario,
    token_mcp_valido,
)
from .usuarios import (
    BLOQUEO_MINUTOS,
    MAX_INTENTOS_FALLIDOS,
    ZONA_HORARIA_DEFECTO,
    actualizar_perfil,
    actualizar_sign_count_mfa,
    autenticar,
    borrar_credencial_mfa,
    borrar_usuario,
    cambiar_rol,
    cambiar_usuario,
    contar_admins,
    contar_superadmins,
    credencial_mfa_global,
    credencial_mfa_por_credential_id,
    crear_usuario,
    desactivar_mfa,
    establecer_password,
    estado_mfa,
    guardar_credencial_mfa,
    listar_credenciales_mfa,
    listar_usuarios,
    obtener_usuario_por_id,
    reemplazar_marcas_de_usuario,
    renombrar_credencial_mfa,
    verificar_password_actual,
)

__all__ = [
    # Hashing / politica de contrasena
    "hashear_password",
    "verificar_password",
    "password_aceptable",
    "motivo_rechazo_password",
    "necesita_rehash",
    "PASSWORDS_PROHIBIDAS",
    "rol_valido",
    "LONGITUD_MIN_PASSWORD",
    "LONGITUD_MAX_PASSWORD",
    "LONGITUD_MAX_USUARIO",
    # Cuentas / login
    "crear_usuario",
    "listar_usuarios",
    "obtener_usuario_por_id",
    "contar_admins",
    "contar_superadmins",
    "cambiar_rol",
    "cambiar_usuario",
    "establecer_password",
    "borrar_usuario",
    "actualizar_perfil",
    "reemplazar_marcas_de_usuario",
    "autenticar",
    "verificar_password_actual",
    "MAX_INTENTOS_FALLIDOS",
    "BLOQUEO_MINUTOS",
    "ZONA_HORARIA_DEFECTO",
    # MFA PASSKEYS / WebAuthn (segundo factor)
    "MfaNoDisponible",
    "NOMBRE_RP_DEFECTO",
    "cifrador",
    "bytes_a_b64url",
    "b64url_a_bytes",
    "opciones_registro",
    "verificar_registro",
    "opciones_login",
    "verificar_login",
    "credential_id_de_respuesta",
    "estado_mfa",
    "listar_credenciales_mfa",
    "credencial_mfa_global",
    "credencial_mfa_por_credential_id",
    "guardar_credencial_mfa",
    "actualizar_sign_count_mfa",
    "borrar_credencial_mfa",
    "renombrar_credencial_mfa",
    "desactivar_mfa",
    # Sesiones
    "COOKIE_SESION",
    "crear_sesion",
    "sesion_valida",
    "borrar_sesion",
    "horas_sesion",
    # Tokens del MCP operativo por identidad
    "crear_token_mcp",
    "revocar_token_mcp_de_usuario",
    "token_mcp_valido",
    "revocar_token_mcp",
    "listar_tokens_mcp",
    # Bootstrap
    "hay_usuarios",
    "bootstrap_admin",
    "ENV_ADMIN_USER",
    "ENV_ADMIN_PASS",
    "ADMIN_POR_DEFECTO",
]
