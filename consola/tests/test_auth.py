"""Tests de auth multiusuario de la Consola: login/roles/usuarios (#130).

Cubre el CONTRATO de la API contra el que tambien se construye el frontend:
  - login OK/KO (mensaje generico, sin enumeracion), cookie de sesion HttpOnly/Strict.
  - /api/auth/me (con y sin sesion), logout (invalida server-side + borra cookie).
  - cambiar-password (forzado y voluntario; valida la actual y la fuerza minima).
  - CRUD de /api/usuarios SOLO admin (403 para editor), 409 de duplicado.
  - Guardas: ultimo admin (borrar/degradar), auto-borrado.
  - Hashing: nada en texto plano en la BD; expiracion de sesion.
  - Convivencia con el TOKEN de #134 (sigue valiendo para /api).

Todo OFFLINE; reusa el aislamiento de `entorno`. Las apps se crean con `bootstrap`
desactivado salvo donde se prueba el bootstrap; los usuarios se crean a mano o por la API.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth, db

from .conftest import TOKEN_PRUEBA, _cliente

# Origin del propio host del TestClient (pasa el chequeo CSRF en mutaciones).
_ORIGIN = {"Origin": "http://testserver"}

# Contrasenas de PRUEBA, evidentemente falsas (no son secretos): cumplen la politica
# (>=12 caracteres, no comunes, no = al usuario) sin mas. `CLAVE` es la valida por
# defecto; `CLAVE_NUEVA` se usa donde se compara antes/despues de un cambio o reset.
CLAVE = "clave-de-prueba"
CLAVE_NUEVA = "clave-nueva-test"


def _app(bootstrap=False):
    """App con token de prueba conocido (sin lanzadores reales)."""
    return app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=bootstrap)


def _cli(bootstrap=False) -> TestClient:
    """TestClient SIN credencial por defecto (cada test la aporta como necesita)."""
    return TestClient(_app(bootstrap=bootstrap))


def _login(c: TestClient, usuario: str, password: str):
    """Hace login y deja la cookie de sesion en el cliente; devuelve la respuesta."""
    return c.post(
        "/api/auth/login", json={"usuario": usuario, "password": password}, headers=_ORIGIN
    )


def _crear(usuario: str, password: str, rol: str = "editor", **kw):
    """Crea un usuario directo en la BD (forma de dominio), sin pasar por la API.

    En estos tests un "admin" es la cuenta privilegiada que gestiona usuarios: nace
    SUPERADMIN salvo que el test pida lo contrario (`superadmin=...`). Gestionar usuarios
    (`/api/usuarios`) exige el flag superadmin; un admin normal recibe 403.
    """
    kw.setdefault("superadmin", rol == "admin")
    return auth.crear_usuario(usuario, password, rol, **kw)


# --------------------------------------------------------------------------- #
# 1) Bootstrap del admin inicial                                              #
# --------------------------------------------------------------------------- #


def test_bootstrap_crea_admin_si_no_hay_usuarios(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CONSOLA_ADMIN_PASS", CLAVE)
    assert not auth.hay_usuarios()
    auth.bootstrap_admin()
    assert auth.contar_admins() == 1
    u = auth.autenticar("admin", CLAVE)
    assert u is not None and u["rol"] == "admin" and u["debe_cambiar_password"] is True


def test_bootstrap_es_idempotente(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CONSOLA_ADMIN_PASS", CLAVE)
    auth.bootstrap_admin()
    auth.bootstrap_admin()
    assert auth.contar_admins() == 1


def test_bootstrap_sin_pass_no_crea_admin_ni_loguea_contrasena(entorno, monkeypatch, caplog):
    """Hardening 2026-06: sin KENI_CONSOLA_ADMIN_PASS NO se crea admin y NUNCA se loguea
    una contrasena en el log. El aviso debe decir como arreglarlo (fijar la env o usar
    el token de mantenimiento con la BD vacia)."""
    import logging

    from keni_consola.observabilidad import NOMBRE_LOGGER

    monkeypatch.delenv("KENI_CONSOLA_ADMIN_PASS", raising=False)
    logger = logging.getLogger(NOMBRE_LOGGER)
    previa = logger.propagate
    logger.propagate = True
    try:
        with caplog.at_level(logging.WARNING, logger=NOMBRE_LOGGER):
            auth.bootstrap_admin()
    finally:
        logger.propagate = previa
    assert auth.contar_admins() == 0  # no se crea un admin con una pass inaccesible
    mensajes = "\n".join(r.getMessage() for r in caplog.records if r.name == NOMBRE_LOGGER)
    assert "contrasena=" not in mensajes  # JAMAS una contrasena en el log
    assert "KENI_CONSOLA_ADMIN_PASS" in mensajes  # instruccion de como fijarla


def test_bootstrap_respeta_admin_user_env(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CONSOLA_ADMIN_USER", "jefe")
    monkeypatch.setenv("KENI_CONSOLA_ADMIN_PASS", CLAVE)
    auth.bootstrap_admin()
    assert auth.autenticar("jefe", CLAVE) is not None


# --------------------------------------------------------------------------- #
# 2) Login OK / KO                                                            #
# --------------------------------------------------------------------------- #


def test_login_ok_devuelve_usuario_y_cookie(entorno):
    _crear("ana", CLAVE, "admin")
    c = _cli()
    r = _login(c, "ana", CLAVE)
    assert r.status_code == 200
    cuerpo = r.json()["usuario"]
    assert cuerpo["usuario"] == "ana" and cuerpo["rol"] == "admin"
    assert set(cuerpo) == {"id", "usuario", "rol", "debe_cambiar_password"}
    set_cookie = r.headers.get("set-cookie", "").lower()
    assert auth.COOKIE_SESION in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=strict" in set_cookie
    assert "path=/" in set_cookie


def test_login_cookie_sesion_sin_secure_por_defecto(entorno, monkeypatch):
    """Por defecto (local HTTP) la cookie de sesion NO lleva `Secure`."""
    monkeypatch.delenv("KENI_CONSOLA_COOKIE_SECURE", raising=False)
    monkeypatch.delenv("KENI_CONSOLA_HTTPS", raising=False)
    _crear("ana", CLAVE, "admin")
    c = _cli()
    r = _login(c, "ana", CLAVE)
    assert r.status_code == 200
    assert "secure" not in r.headers.get("set-cookie", "").lower()


def test_login_cookie_sesion_con_secure_por_env(entorno, monkeypatch):
    """`KENI_CONSOLA_COOKIE_SECURE=1` marca la cookie de sesion como `Secure`."""
    monkeypatch.setenv("KENI_CONSOLA_COOKIE_SECURE", "1")
    _crear("ana", CLAVE, "admin")
    c = _cli()
    r = _login(c, "ana", CLAVE)
    assert r.status_code == 200
    set_cookie = r.headers.get("set-cookie", "").lower()
    assert auth.COOKIE_SESION in set_cookie
    assert "secure" in set_cookie


def test_login_password_incorrecta_da_401_generico(entorno):
    _crear("ana", CLAVE, "admin")
    c = _cli()
    r = _login(c, "ana", "equivocada")
    assert r.status_code == 401
    assert r.json()["error"] == "Usuario o contraseña incorrectos."


def test_login_usuario_inexistente_mismo_mensaje_que_pass_mala(entorno):
    """Sin enumeracion: usuario inexistente devuelve el MISMO mensaje generico."""
    _crear("ana", CLAVE)
    c = _cli()
    r1 = _login(c, "ana", "equivocada")
    r2 = _login(c, "fantasma", "loquesea")
    assert r1.status_code == r2.status_code == 401
    assert r1.json() == r2.json()


def test_login_sin_campos_da_401_generico(entorno):
    c = _cli()
    r = c.post("/api/auth/login", json={}, headers=_ORIGIN)
    assert r.status_code == 401
    assert r.json()["error"] == "Usuario o contraseña incorrectos."


def test_login_es_publico_pero_exige_origin_propio(entorno):
    """`/api/auth/login` no exige credencial previa, pero un Origin ajeno -> 403 (CSRF)."""
    _crear("ana", CLAVE)
    c = _cli()
    r = c.post(
        "/api/auth/login",
        json={"usuario": "ana", "password": CLAVE},
        headers={"Origin": "https://malicioso.example"},
    )
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
# 3) /api/auth/me                                                             #
# --------------------------------------------------------------------------- #


def test_me_con_sesion_devuelve_usuario(entorno):
    _crear("ana", CLAVE, "editor")
    c = _cli()
    _login(c, "ana", CLAVE)
    r = c.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["usuario"]["usuario"] == "ana"


def test_me_sin_sesion_da_401(entorno):
    """Con el TOKEN (no sesion) /api/auth/me responde 401: no hay usuario asociado."""
    c = _cli()
    r = c.get("/api/auth/me", headers={"Authorization": f"Bearer {TOKEN_PRUEBA}"})
    assert r.status_code == 401


def test_me_sin_ninguna_credencial_da_401(entorno):
    c = _cli()
    r = c.get("/api/auth/me")
    assert r.status_code == 401


def test_me_incluye_creado_y_ultimo_acceso_para_mi_cuenta(entorno):
    """`me` expone `creado` y `ultimo_acceso` (los usa la pagina "Mi cuenta")."""
    _crear("ana", CLAVE, "editor")
    c = _cli()
    _login(c, "ana", CLAVE)
    cuerpo = c.get("/api/auth/me").json()["usuario"]
    assert {"creado", "ultimo_acceso"} <= set(cuerpo)
    # Tras el login el ultimo_acceso queda fijado (no vacio).
    assert cuerpo["ultimo_acceso"]


def test_me_incluye_es_admin_segun_rol(entorno):
    """`me` expone `es_admin` (bool plano): True solo para una sesión con rol admin.

    Lo usa el frontend del rediseño de la Prompts para gatear publicar/aprobar.
    """
    _crear("edi", CLAVE, "editor")
    _crear("root", CLAVE, "admin")
    c = _cli()
    _login(c, "edi", CLAVE)
    assert c.get("/api/auth/me").json()["usuario"]["es_admin"] is False
    c2 = _cli()
    _login(c2, "root", CLAVE)
    assert c2.get("/api/auth/me").json()["usuario"]["es_admin"] is True


def test_login_no_filtra_creado_ni_ultimo_acceso(entorno):
    """El login mantiene su forma minima de 4 campos (esos extras solo van por `me`)."""
    _crear("ana", CLAVE, "editor")
    c = _cli()
    cuerpo = _login(c, "ana", CLAVE).json()["usuario"]
    assert set(cuerpo) == {"id", "usuario", "rol", "debe_cambiar_password"}


# --------------------------------------------------------------------------- #
# 4) Logout                                                                   #
# --------------------------------------------------------------------------- #


def test_logout_invalida_sesion_y_borra_cookie(entorno):
    _crear("ana", CLAVE)
    c = _cli()
    _login(c, "ana", CLAVE)
    assert c.get("/api/auth/me").status_code == 200
    r = c.post("/api/auth/logout", headers=_ORIGIN)
    assert r.status_code == 204
    # La cookie se borra (Set-Cookie con expiracion en el pasado o vacia).
    assert auth.COOKIE_SESION in r.headers.get("set-cookie", "")
    # Server-side: la sesion ya no vale (forzamos la cookie vieja y debe fallar).
    assert c.get("/api/auth/me").status_code == 401


def test_logout_invalida_server_side_aunque_se_reuse_la_cookie(entorno):
    _crear("ana", CLAVE)
    c = _cli()
    _login(c, "ana", CLAVE)
    # Capturamos el token de sesion inicializado.
    token_sesion = c.cookies.get(auth.COOKIE_SESION)
    assert token_sesion
    c.post("/api/auth/logout", headers=_ORIGIN)
    # Un cliente nuevo que reusa la MISMA cookie ya no entra (sesion borrada en BD).
    c2 = _cli()
    c2.cookies.set(auth.COOKIE_SESION, token_sesion)
    assert c2.get("/api/auth/me").status_code == 401


# --------------------------------------------------------------------------- #
# 5) Cambiar contrasena (forzado y voluntario)                                #
# --------------------------------------------------------------------------- #


def test_cambiar_password_ok(entorno):
    _crear("ana", CLAVE, debe_cambiar_password=True)
    c = _cli()
    _login(c, "ana", CLAVE)
    r = c.post(
        "/api/auth/cambiar-password",
        json={"password_actual": CLAVE, "password_nueva": CLAVE_NUEVA},
        headers=_ORIGIN,
    )
    assert r.status_code == 204
    # La nueva contrasena vale y la vieja ya no.
    assert auth.autenticar("ana", CLAVE_NUEVA) is not None
    assert auth.autenticar("ana", CLAVE) is None


def test_cambiar_password_limpia_debe_cambiar(entorno):
    _crear("ana", CLAVE, debe_cambiar_password=True)
    c = _cli()
    _login(c, "ana", CLAVE)
    c.post(
        "/api/auth/cambiar-password",
        json={"password_actual": CLAVE, "password_nueva": CLAVE_NUEVA},
        headers=_ORIGIN,
    )
    u = auth.autenticar("ana", CLAVE_NUEVA)
    assert u["debe_cambiar_password"] is False


def test_cambiar_password_actual_incorrecta_da_400(entorno):
    _crear("ana", CLAVE)
    c = _cli()
    _login(c, "ana", CLAVE)
    r = c.post(
        "/api/auth/cambiar-password",
        json={"password_actual": "no-es-esa", "password_nueva": CLAVE_NUEVA},
        headers=_ORIGIN,
    )
    assert r.status_code == 400


def test_cambiar_password_nueva_debil_da_400(entorno):
    _crear("ana", CLAVE)
    c = _cli()
    _login(c, "ana", CLAVE)
    r = c.post(
        "/api/auth/cambiar-password",
        json={"password_actual": CLAVE, "password_nueva": "corta"},
        headers=_ORIGIN,
    )
    assert r.status_code == 400


def test_cambiar_password_sin_sesion_da_401(entorno):
    """Por TOKEN (sin sesion) no se puede cambiar pass: no hay cuenta asociada."""
    c = _cli()
    r = c.post(
        "/api/auth/cambiar-password",
        json={"password_actual": "x", "password_nueva": CLAVE_NUEVA},
        headers={**_ORIGIN, "Authorization": f"Bearer {TOKEN_PRUEBA}"},
    )
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# 5b) Politica de contrasena (NIST: longitud + bloqueo de comunes)            #
# --------------------------------------------------------------------------- #


def test_password_corta_se_rechaza(entorno):
    """Menos de 12 caracteres -> 400 (la politica subio de 8 a 12)."""
    _crear("jefa", CLAVE, "admin")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.post(
        "/api/usuarios",
        json={"usuario": "nuevo", "password": "corta-11car", "rol": "editor"},
        headers=_ORIGIN,
    )
    assert r.status_code == 400


def test_password_comun_se_rechaza(entorno):
    """Una contrasena comun de la lista de prohibidas (>=12 para llegar al filtro) -> 400.

    'administrador' tiene 13 caracteres (pasa el minimo de longitud) pero esta en la
    blocklist, asi que cae por ser predecible, no por corta.
    """
    _crear("jefa", CLAVE, "admin")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.post(
        "/api/usuarios",
        json={"usuario": "nuevo", "password": "administrador", "rol": "editor"},
        headers=_ORIGIN,
    )
    assert r.status_code == 400
    assert "común" in r.json()["error"]


def test_password_igual_al_usuario_se_rechaza(entorno):
    """La contrasena no puede coincidir con el nombre de usuario (aunque sea larga)."""
    _crear("jefa", CLAVE, "admin")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.post(
        "/api/usuarios",
        json={"usuario": "personagrande", "password": "personagrande", "rol": "editor"},
        headers=_ORIGIN,
    )
    assert r.status_code == 400


def test_password_fuerte_se_acepta(entorno):
    """Una contrasena >=12, no comun y distinta del usuario crea la cuenta (201)."""
    _crear("jefa", CLAVE, "admin")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.post(
        "/api/usuarios",
        json={"usuario": "nuevo", "password": "una-clave-larga-y-decente", "rol": "editor"},
        headers=_ORIGIN,
    )
    assert r.status_code == 201


# --------------------------------------------------------------------------- #
# 5c) Editar el nombre humano PROPIO (PATCH /api/auth/me)                      #
# --------------------------------------------------------------------------- #


def test_editar_mi_nombre(entorno):
    """La persona edita su propio `nombre`; `me` lo refleja y NO toca rol ni login."""
    _crear("ana", CLAVE, "editor")
    c = _cli()
    _login(c, "ana", CLAVE)
    r = c.patch("/api/auth/me", json={"nombre": "Ana Pérez"}, headers=_ORIGIN)
    assert r.status_code == 200
    assert r.json()["nombre"] == "Ana Pérez"
    me = c.get("/api/auth/me").json()["usuario"]
    assert me["nombre"] == "Ana Pérez"
    assert me["usuario"] == "ana"
    assert me["rol"] == "editor"


def test_editar_mi_nombre_sin_sesion_da_401(entorno):
    """Por TOKEN (sin sesion) no hay cuenta propia que editar -> 401."""
    c = _cli()
    r = c.patch(
        "/api/auth/me",
        json={"nombre": "X"},
        headers={**_ORIGIN, "Authorization": f"Bearer {TOKEN_PRUEBA}"},
    )
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# 6) Gestion de usuarios (SOLO admin)                                         #
# --------------------------------------------------------------------------- #


def test_listar_usuarios_como_admin(entorno):
    _crear("jefa", CLAVE, "admin")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.get("/api/usuarios")
    assert r.status_code == 200
    nombres = {u["usuario"] for u in r.json()["usuarios"]}
    assert "jefa" in nombres
    # NUNCA se exponen salt/hash. Tras "feat/roles-marcas" la fila incluye cargo/cobertura/marcas;
    # ola "coord" anade `puede_coordinar`; el organigrama anade `nombre` y `manager_id`.
    for u in r.json()["usuarios"]:
        assert set(u) == {
            "id", "usuario", "rol", "creado", "ultimo_acceso",
            "cargo", "cobertura", "puede_coordinar", "nombre", "manager_id", "marcas",
            "superadmin", "mfa_requerido", "mfa_activo",
        }


def test_editor_no_puede_listar_usuarios_403(entorno):
    _crear("ed", CLAVE, "editor")
    c = _cli()
    _login(c, "ed", CLAVE)
    r = c.get("/api/usuarios")
    assert r.status_code == 403


def test_admin_normal_no_gestiona_usuarios_403(entorno):
    """Un admin SIN el flag superadmin NO entra a /api/usuarios (gestion = solo superadmin)."""
    _crear("jefe", CLAVE, "admin", superadmin=False)
    c = _cli()
    _login(c, "jefe", CLAVE)
    assert c.get("/api/usuarios").status_code == 403
    r = c.post(
        "/api/usuarios",
        json={"usuario": "x", "password": CLAVE, "rol": "editor"},
        headers=_ORIGIN,
    )
    assert r.status_code == 403


def test_superadmin_concede_flags_a_otra_cuenta(entorno):
    """El superadmin marca a otra cuenta como superadmin y le exige MFA; el PATCH lo refleja
    y la cuenta promovida ya puede gestionar usuarios."""
    _crear("jefa", CLAVE, "admin")  # superadmin por defecto del helper
    objetivo = _crear("leo", CLAVE, "editor")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.patch(
        f"/api/usuarios/{objetivo['id']}",
        json={"superadmin": True, "mfa_requerido": True},
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    assert r.json()["superadmin"] is True and r.json()["mfa_requerido"] is True
    c2 = _cli()
    _login(c2, "leo", CLAVE)
    assert c2.get("/api/usuarios").status_code == 200


def test_no_se_puede_quitar_superadmin_al_ultimo(entorno):
    """Guarda anti-lockout: no se quita el flag al ULTIMO superadmin (nadie gestionaria usuarios)."""
    jefa = _crear("jefa", CLAVE, "admin")  # unico superadmin del entorno
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.patch(
        f"/api/usuarios/{jefa['id']}", json={"superadmin": False}, headers=_ORIGIN
    )
    assert r.status_code == 409


def test_me_incluye_es_superadmin(entorno):
    """`me` expone `es_superadmin` (bool plano): True solo con el flag, no por ser admin."""
    _crear("jefa", CLAVE, "admin")  # superadmin
    _crear("ed", CLAVE, "admin", superadmin=False)  # admin normal, sin gestion de usuarios
    c = _cli()
    _login(c, "jefa", CLAVE)
    assert c.get("/api/auth/me").json()["usuario"]["es_superadmin"] is True
    c2 = _cli()
    _login(c2, "ed", CLAVE)
    assert c2.get("/api/auth/me").json()["usuario"]["es_superadmin"] is False


def test_crear_usuario_como_admin_201(entorno):
    _crear("jefa", CLAVE, "admin")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.post(
        "/api/usuarios",
        json={"usuario": "nuevo", "password": CLAVE, "rol": "editor"},
        headers=_ORIGIN,
    )
    assert r.status_code == 201
    assert r.json()["usuario"] == "nuevo" and r.json()["rol"] == "editor"
    assert auth.autenticar("nuevo", CLAVE) is not None


def test_crear_usuario_duplicado_da_409(entorno):
    _crear("jefa", CLAVE, "admin")
    _crear("repe", CLAVE, "editor")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.post(
        "/api/usuarios",
        json={"usuario": "repe", "password": CLAVE, "rol": "editor"},
        headers=_ORIGIN,
    )
    assert r.status_code == 409


def test_crear_usuario_rol_invalido_da_400(entorno):
    _crear("jefa", CLAVE, "admin")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.post(
        "/api/usuarios",
        json={"usuario": "x", "password": CLAVE, "rol": "superusuario"},
        headers=_ORIGIN,
    )
    assert r.status_code == 400


def test_crear_usuario_pass_debil_da_400(entorno):
    _crear("jefa", CLAVE, "admin")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.post(
        "/api/usuarios",
        json={"usuario": "x", "password": "corta", "rol": "editor"},
        headers=_ORIGIN,
    )
    assert r.status_code == 400


def test_editor_no_puede_crear_usuario_403(entorno):
    _crear("ed", CLAVE, "editor")
    c = _cli()
    _login(c, "ed", CLAVE)
    r = c.post(
        "/api/usuarios",
        json={"usuario": "x", "password": CLAVE, "rol": "editor"},
        headers=_ORIGIN,
    )
    assert r.status_code == 403


def test_patch_cambia_rol(entorno):
    _crear("jefa", CLAVE, "admin")
    ed = _crear("ed", CLAVE, "editor")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.patch(f"/api/usuarios/{ed['id']}", json={"rol": "admin"}, headers=_ORIGIN)
    assert r.status_code == 200 and r.json()["rol"] == "admin"
    assert auth.contar_admins() == 2


def test_patch_cambia_nombre_de_cuenta(entorno):
    """El admin renombra el login; la cuenta inicia sesion con el nombre nuevo (mismo id)."""
    _crear("jefa", CLAVE, "admin")
    ed = _crear("ed", CLAVE, "editor")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.patch(f"/api/usuarios/{ed['id']}", json={"usuario": "edu"}, headers=_ORIGIN)
    assert r.status_code == 200 and r.json()["usuario"] == "edu"
    # El nombre viejo ya no autentica; el nuevo si, y conserva el id.
    assert auth.autenticar("ed", CLAVE) is None
    nuevo = auth.autenticar("edu", CLAVE)
    assert nuevo is not None and nuevo["id"] == ed["id"]


def test_patch_nombre_de_cuenta_duplicado_da_409(entorno):
    """Renombrar al login de OTRA cuenta existente choca con el UNIQUE -> 409."""
    _crear("jefa", CLAVE, "admin")
    _crear("otra", CLAVE, "editor")
    ed = _crear("ed", CLAVE, "editor")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.patch(f"/api/usuarios/{ed['id']}", json={"usuario": "otra"}, headers=_ORIGIN)
    assert r.status_code == 409
    # No se cambio: "ed" sigue autenticando.
    assert auth.autenticar("ed", CLAVE) is not None


def test_patch_nombre_de_cuenta_vacio_da_400(entorno):
    _crear("jefa", CLAVE, "admin")
    ed = _crear("ed", CLAVE, "editor")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.patch(f"/api/usuarios/{ed['id']}", json={"usuario": "   "}, headers=_ORIGIN)
    assert r.status_code == 400


def test_patch_resetea_password_y_fuerza_cambio(entorno):
    _crear("jefa", CLAVE, "admin")
    ed = _crear("ed", CLAVE, "editor")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.patch(
        f"/api/usuarios/{ed['id']}", json={"password": CLAVE_NUEVA}, headers=_ORIGIN
    )
    assert r.status_code == 200
    u = auth.autenticar("ed", CLAVE_NUEVA)
    assert u is not None and u["debe_cambiar_password"] is True


def test_patch_usuario_inexistente_404(entorno):
    _crear("jefa", CLAVE, "admin")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.patch("/api/usuarios/noexiste", json={"rol": "admin"}, headers=_ORIGIN)
    assert r.status_code == 404


def test_patch_cambia_cargo_y_cobertura(entorno):
    """El admin puede ajustar cargo/cobertura sin tocar rol ni contrasena."""
    _crear("jefa", CLAVE, "admin")
    ed = _crear("ed", CLAVE, "editor")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.patch(
        f"/api/usuarios/{ed['id']}",
        json={"cargo": "community_manager", "cobertura": True},
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["cargo"] == "community_manager"
    assert cuerpo["cobertura"] is True
    assert cuerpo["marcas"] == []
    # Persistido:
    actualizado = auth.obtener_usuario_por_id(ed["id"])
    assert actualizado["cargo"] == "community_manager"
    assert actualizado["cobertura"] is True


def test_patch_cambia_puede_coordinar(entorno):
    """El admin puede marcar/desmarcar `puede_coordinar` sin tocar otros campos."""
    _crear("jefa", CLAVE, "admin")
    ed = _crear("ed", CLAVE, "editor")
    c = _cli()
    _login(c, "jefa", CLAVE)
    # Default = False.
    asegurado_pre = auth.obtener_usuario_por_id(ed["id"])
    assert asegurado_pre["puede_coordinar"] is False
    # Activar.
    r = c.patch(
        f"/api/usuarios/{ed['id']}",
        json={"puede_coordinar": True},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["puede_coordinar"] is True
    actualizado = auth.obtener_usuario_por_id(ed["id"])
    assert actualizado["puede_coordinar"] is True
    # Desactivar.
    r = c.patch(
        f"/api/usuarios/{ed['id']}",
        json={"puede_coordinar": False},
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    assert r.json()["puede_coordinar"] is False


def test_patch_puede_coordinar_tipo_invalido_400(entorno):
    """`puede_coordinar` no-bool -> 400 con mensaje accionable."""
    _crear("jefa", CLAVE, "admin")
    ed = _crear("ed", CLAVE, "editor")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.patch(
        f"/api/usuarios/{ed['id']}",
        json={"puede_coordinar": "si"},
        headers=_ORIGIN,
    )
    assert r.status_code == 400
    assert "puede_coordinar" in r.json()["error"]


def test_crear_usuario_default_puede_coordinar_false(entorno):
    """Un usuario creado por la API NO arranca como coordinador (default False)."""
    _crear("jefa", CLAVE, "admin")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.post(
        "/api/usuarios",
        json={"usuario": "nuevo", "password": CLAVE, "rol": "editor"},
        headers=_ORIGIN,
    )
    assert r.status_code == 201
    creado = auth.obtener_usuario_por_id(r.json()["id"])
    assert creado["puede_coordinar"] is False


def test_patch_cargo_invalido_400(entorno):
    """Cargo fuera del catalogo -> 400 con mensaje accionable."""
    _crear("jefa", CLAVE, "admin")
    ed = _crear("ed", CLAVE, "editor")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.patch(
        f"/api/usuarios/{ed['id']}",
        json={"cargo": "lo-que-sea"},
        headers=_ORIGIN,
    )
    assert r.status_code == 400
    assert "Cargo" in r.json()["error"]


def test_patch_asigna_marcas_reemplaza_conjunto(entorno):
    """PATCH con marcas REEMPLAZA el conjunto N:M (idempotente, deduplica)."""
    _crear("jefa", CLAVE, "admin")
    ed = _crear("ed", CLAVE, "editor")
    c = _cli()
    _login(c, "jefa", CLAVE)
    # 1) Asignar 2 marcas.
    r = c.patch(
        f"/api/usuarios/{ed['id']}",
        json={"marcas": ["claro-sports", "unotv"]},
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    assert sorted(r.json()["marcas"]) == ["claro-sports", "unotv"]
    # 2) Reducir a 1 marca: la otra debe desaparecer.
    r = c.patch(
        f"/api/usuarios/{ed['id']}",
        json={"marcas": ["claro-sports"]},
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    assert r.json()["marcas"] == ["claro-sports"]
    # 3) Vaciar lista: ninguna marca.
    r = c.patch(
        f"/api/usuarios/{ed['id']}",
        json={"marcas": []},
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    assert r.json()["marcas"] == []


def test_patch_marcas_invalidas_400(entorno):
    """Si alguna marca no esta en el catalogo canonico -> 400 con la lista valida."""
    _crear("jefa", CLAVE, "admin")
    ed = _crear("ed", CLAVE, "editor")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.patch(
        f"/api/usuarios/{ed['id']}",
        json={"marcas": ["unotv", "marca-inventada"]},
        headers=_ORIGIN,
    )
    assert r.status_code == 400
    assert "marca-inventada" in r.json()["error"]


def test_patch_marcas_tipo_invalido_400(entorno):
    """`marcas` debe ser lista de strings; un valor no-lista o no-string -> 400."""
    _crear("jefa", CLAVE, "admin")
    ed = _crear("ed", CLAVE, "editor")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.patch(
        f"/api/usuarios/{ed['id']}",
        json={"marcas": "claro-sports"},
        headers=_ORIGIN,
    )
    assert r.status_code == 400
    r = c.patch(
        f"/api/usuarios/{ed['id']}",
        json={"marcas": [1, 2]},
        headers=_ORIGIN,
    )
    assert r.status_code == 400


def test_patch_marcas_no_pisa_rol_ni_password(entorno):
    """PATCH con marcas no toca rol/contrasena ni invalida la sesion."""
    _crear("jefa", CLAVE, "admin")
    ed = _crear("ed", CLAVE, "editor")
    c = _cli()
    _login(c, "jefa", CLAVE)
    c.patch(
        f"/api/usuarios/{ed['id']}",
        json={"marcas": ["fundacion"]},
        headers=_ORIGIN,
    )
    # `ed` sigue siendo editor y la contrasena no se ha tocado.
    actualizado = auth.obtener_usuario_por_id(ed["id"])
    assert actualizado["rol"] == "editor"
    assert auth.autenticar("ed", CLAVE) is not None


def test_get_usuarios_incluye_marcas(entorno):
    """GET /api/usuarios incluye `marcas` (lista) en cada fila."""
    _crear("jefa", CLAVE, "admin")
    ed = _crear(
        "ed", CLAVE, "editor",
        cargo="community_manager", cobertura=True, marcas=["claro-sports"],
    )
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.get("/api/usuarios", headers=_ORIGIN)
    assert r.status_code == 200
    por_id = {u["id"]: u for u in r.json()["usuarios"]}
    assert por_id[ed["id"]]["marcas"] == ["claro-sports"]
    assert por_id[ed["id"]]["cargo"] == "community_manager"
    assert por_id[ed["id"]]["cobertura"] is True


def test_patch_sin_cambios_400(entorno):
    """PATCH sin ningun campo -> 400 con mensaje accionable."""
    _crear("jefa", CLAVE, "admin")
    ed = _crear("ed", CLAVE, "editor")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.patch(f"/api/usuarios/{ed['id']}", json={}, headers=_ORIGIN)
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# 6b) Organigrama: nombre + manager_id (linea de reporte)                      #
# --------------------------------------------------------------------------- #


def test_patch_cambia_nombre(entorno):
    """El admin puede fijar el nombre HUMANO (organigrama) sin tocar otros campos."""
    _crear("jefa", CLAVE, "admin")
    ed = _crear("ed", CLAVE, "editor")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.patch(f"/api/usuarios/{ed['id']}", json={"nombre": "  Edu Ríos  "}, headers=_ORIGIN)
    assert r.status_code == 200, r.text
    assert r.json()["nombre"] == "Edu Ríos"  # se recorta (strip)
    assert auth.obtener_usuario_por_id(ed["id"])["nombre"] == "Edu Ríos"


def test_patch_nombre_tipo_invalido_400(entorno):
    """`nombre` no-texto -> 400."""
    _crear("jefa", CLAVE, "admin")
    ed = _crear("ed", CLAVE, "editor")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.patch(f"/api/usuarios/{ed['id']}", json={"nombre": 123}, headers=_ORIGIN)
    assert r.status_code == 400


def test_patch_asigna_manager(entorno):
    """El admin define la linea de reporte: `manager_id` apunta a un superior existente."""
    _crear("jefa", CLAVE, "admin")
    dir_ = _crear("dir", CLAVE, "editor")
    ed = _crear("ed", CLAVE, "editor")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.patch(f"/api/usuarios/{ed['id']}", json={"manager_id": dir_["id"]}, headers=_ORIGIN)
    assert r.status_code == 200, r.text
    assert r.json()["manager_id"] == dir_["id"]
    assert auth.obtener_usuario_por_id(ed["id"])["manager_id"] == dir_["id"]
    # Desligar (volver a raiz) con cadena vacia.
    r = c.patch(f"/api/usuarios/{ed['id']}", json={"manager_id": ""}, headers=_ORIGIN)
    assert r.status_code == 200
    assert r.json()["manager_id"] == ""


def test_patch_manager_a_si_mismo_400(entorno):
    """Una persona no puede reportarse a si misma."""
    _crear("jefa", CLAVE, "admin")
    ed = _crear("ed", CLAVE, "editor")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.patch(f"/api/usuarios/{ed['id']}", json={"manager_id": ed["id"]}, headers=_ORIGIN)
    assert r.status_code == 400


def test_patch_manager_inexistente_400(entorno):
    """Un superior que no existe -> 400."""
    _crear("jefa", CLAVE, "admin")
    ed = _crear("ed", CLAVE, "editor")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.patch(f"/api/usuarios/{ed['id']}", json={"manager_id": "no-existe"}, headers=_ORIGIN)
    assert r.status_code == 400


def test_patch_manager_ciclo_400(entorno):
    """No se permite cerrar un ciclo en el organigrama (A->B->A)."""
    _crear("jefa", CLAVE, "admin")
    a = _crear("a", CLAVE, "editor")
    b = _crear("b", CLAVE, "editor")
    c = _cli()
    _login(c, "jefa", CLAVE)
    # b reporta a a.
    assert c.patch(
        f"/api/usuarios/{b['id']}", json={"manager_id": a["id"]}, headers=_ORIGIN
    ).status_code == 200
    # Ahora intentar que a reporte a b cerraria el ciclo -> 400.
    r = c.patch(f"/api/usuarios/{a['id']}", json={"manager_id": b["id"]}, headers=_ORIGIN)
    assert r.status_code == 400


def test_crear_usuario_api_con_nombre(entorno):
    """POST /api/usuarios acepta `nombre` opcional y lo persiste."""
    _crear("jefa", CLAVE, "admin")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.post(
        "/api/usuarios",
        json={"usuario": "nuevo", "password": CLAVE, "rol": "editor", "nombre": "Nuevo Nombre"},
        headers=_ORIGIN,
    )
    assert r.status_code == 201, r.text
    por_nombre = {u["usuario"]: u for u in auth.listar_usuarios()}
    assert por_nombre["nuevo"]["nombre"] == "Nuevo Nombre"


def test_catalogo_cargos_incluye_los_nuevos(entorno):
    """Sanidad: el catalogo `CARGOS_USUARIO` cubre los cargos del organigrama del cliente."""
    from keni_consola.estados import CARGOS_USUARIO
    for cargo in (
        "coordinador_redes",
        "coordinador_youtube",
        "gerente_podcast",
        "creativo_vertical",
        "editorial_youtube",
        "coordinador_invitados",
        "coordinador_operativo",
        "fotografia_revision",
        "editor_video",
        "disenador",
    ):
        assert cargo in CARGOS_USUARIO


def test_listar_usuarios_repo_persiste_marcas(entorno):
    """Persistencia N:M: lo que se crea con `crear_usuario(marcas=...)` sale en `listar_usuarios`."""
    auth.crear_usuario(
        "mary", CLAVE, "editor",
        cargo="community_manager", cobertura=True, marcas=["claro-sports", "unotv"],
    )
    por_nombre = {u["usuario"]: u for u in auth.listar_usuarios()}
    assert sorted(por_nombre["mary"]["marcas"]) == ["claro-sports", "unotv"]


def test_delete_usuario(entorno):
    _crear("jefa", CLAVE, "admin")
    ed = _crear("ed", CLAVE, "editor")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.delete(f"/api/usuarios/{ed['id']}", headers=_ORIGIN)
    assert r.status_code == 204
    assert auth.obtener_usuario_por_id(ed["id"]) is None


def test_editor_no_puede_borrar_usuario_403(entorno):
    _crear("jefa", CLAVE, "admin")
    otro = _crear("otro", CLAVE, "editor")
    _crear("ed", CLAVE, "editor")
    c = _cli()
    _login(c, "ed", CLAVE)
    r = c.delete(f"/api/usuarios/{otro['id']}", headers=_ORIGIN)
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
# 7) Guardas de integridad de admins                                          #
# --------------------------------------------------------------------------- #


def test_no_borrar_ultimo_admin(entorno):
    jefa = _crear("jefa", CLAVE, "admin")
    otro_admin = _crear("admin2", CLAVE, "admin")
    c = _cli()
    _login(c, "jefa", CLAVE)
    # Borramos el otro admin -> queda jefa como unico admin.
    assert c.delete(f"/api/usuarios/{otro_admin['id']}", headers=_ORIGIN).status_code == 204
    # Ahora intentar borrar al ultimo admin (jefa misma) falla por DOS guardas; basta 409.
    assert c.delete(f"/api/usuarios/{jefa['id']}", headers=_ORIGIN).status_code == 409
    assert auth.contar_admins() == 1


def test_no_borrarte_a_ti_mismo(entorno):
    jefa = _crear("jefa", CLAVE, "admin")
    _crear("admin2", CLAVE, "admin")  # hay otro admin, no es guarda de ultimo
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.delete(f"/api/usuarios/{jefa['id']}", headers=_ORIGIN)
    assert r.status_code == 409
    assert auth.obtener_usuario_por_id(jefa["id"]) is not None


def test_no_degradar_ultimo_admin_via_patch(entorno):
    jefa = _crear("jefa", CLAVE, "admin")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.patch(f"/api/usuarios/{jefa['id']}", json={"rol": "editor"}, headers=_ORIGIN)
    assert r.status_code == 409
    assert auth.contar_admins() == 1


def test_degradar_admin_si_queda_otro_admin_ok(entorno):
    _crear("jefa", CLAVE, "admin")
    otro = _crear("admin2", CLAVE, "admin")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.patch(f"/api/usuarios/{otro['id']}", json={"rol": "editor"}, headers=_ORIGIN)
    assert r.status_code == 200 and auth.contar_admins() == 1


# --------------------------------------------------------------------------- #
# 8) Hashing: nada en texto plano                                             #
# --------------------------------------------------------------------------- #


def test_password_no_se_guarda_en_texto_plano(entorno):
    _crear("ana", CLAVE, "editor")
    con = db.conectar()
    try:
        fila = con.execute(
            "SELECT salt, hash FROM usuarios WHERE usuario = ?", ("ana",)
        ).fetchone()
    finally:
        con.close()
    # Ni el salt ni el hash contienen la contrasena en claro.
    assert CLAVE not in fila["salt"]
    assert CLAVE not in fila["hash"]
    # El campo `hash` es VERSIONADO y auto-descriptivo: `scrypt$<n>$<r>$<p>$<digest hex>`.
    assert fila["hash"].startswith("scrypt$")
    assert len(fila["hash"].split("$")[-1]) == 128  # digest = 64 bytes en hex
    assert auth.verificar_password(CLAVE, fila["salt"], fila["hash"])
    assert not auth.verificar_password("otra", fila["salt"], fila["hash"])


def _hash_legado(password: str, salt: bytes) -> str:
    """Digest scrypt LEGADO (128 hex, N=2**14, SIN prefijo de version) como lo guardaban las
    cuentas antes de versionar el campo `hash`."""
    import hashlib

    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1, dklen=64,
        maxmem=256 * 1024 * 1024,
    ).hex()


def test_verifica_hash_legado_y_necesita_rehash():
    """Un hash LEGADO (128 hex, sin prefijo) sigue verificando; `necesita_rehash` lo marca, y
    un hash nuevo (coste objetivo, versionado) NO lo necesita."""
    salt = bytes.fromhex("00112233445566778899aabbccddeeff")
    legado = _hash_legado(CLAVE, salt)
    assert "$" not in legado and len(legado) == 128
    assert auth.verificar_password(CLAVE, salt.hex(), legado)
    assert not auth.verificar_password("otra", salt.hex(), legado)
    assert auth.necesita_rehash(legado) is True
    _, h_nuevo = auth.hashear_password(CLAVE)
    assert auth.necesita_rehash(h_nuevo) is False


def test_login_rehashea_password_legado(entorno):
    """REHASH-ON-LOGIN: una cuenta con hash legado (N=2**14) ve su hash RE-DERIVADO al formato
    versionado actual tras un login correcto, sin pedir cambio de contrasena."""
    u = _crear("ana", CLAVE, "editor")
    salt = bytes.fromhex("ffeeddccbbaa99887766554433221100")
    con = db.conectar()
    try:
        con.execute(
            "UPDATE usuarios SET salt = ?, hash = ? WHERE id = ?",
            (salt.hex(), _hash_legado(CLAVE, salt), u["id"]),
        )
        con.commit()
    finally:
        con.close()
    assert auth.autenticar("ana", CLAVE) is not None  # verifica contra el legado
    con = db.conectar()
    try:
        fila = con.execute(
            "SELECT salt, hash FROM usuarios WHERE id = ?", (u["id"],)
        ).fetchone()
    finally:
        con.close()
    assert fila["hash"].startswith("scrypt$")  # re-derivado al formato versionado
    assert auth.necesita_rehash(fila["hash"]) is False
    assert auth.verificar_password(CLAVE, fila["salt"], fila["hash"])


def test_dos_usuarios_misma_pass_distinto_hash(entorno):
    """Salt por usuario: la misma contrasena produce hashes distintos."""
    _crear("a", CLAVE, "editor")
    _crear("b", CLAVE, "editor")
    con = db.conectar()
    try:
        ha = con.execute("SELECT hash, salt FROM usuarios WHERE usuario='a'").fetchone()
        hb = con.execute("SELECT hash, salt FROM usuarios WHERE usuario='b'").fetchone()
    finally:
        con.close()
    assert ha["salt"] != hb["salt"]
    assert ha["hash"] != hb["hash"]


# --------------------------------------------------------------------------- #
# 9) Sesiones: expiracion                                                     #
# --------------------------------------------------------------------------- #


def test_sesion_expirada_no_vale_y_se_limpia(entorno):
    u = _crear("ana", CLAVE, "editor")
    token = auth.crear_sesion(u["id"])
    assert auth.sesion_valida(token) is not None
    # Forzamos la expiracion en el pasado directamente en la BD.
    con = db.conectar()
    try:
        con.execute(
            "UPDATE sesiones SET expira = ? WHERE token = ?",
            ("2000-01-01T00:00:00+00:00", token),
        )
        con.commit()
    finally:
        con.close()
    assert auth.sesion_valida(token) is None
    # Y la sesion caducada se borro de la BD.
    con = db.conectar()
    try:
        fila = con.execute("SELECT 1 FROM sesiones WHERE token = ?", (token,)).fetchone()
    finally:
        con.close()
    assert fila is None


def test_sesion_renueva_expiracion_con_uso(entorno):
    from datetime import UTC, datetime, timedelta

    u = _crear("ana", CLAVE, "editor")
    token = auth.crear_sesion(u["id"])
    # Adelantamos la expiracion a 2030 para ver que el uso la RECALCULA a ~ahora+12h.
    con = db.conectar()
    try:
        con.execute(
            "UPDATE sesiones SET expira = ? WHERE token = ?",
            ("2030-01-01T00:00:00+00:00", token),
        )
        con.commit()
    finally:
        con.close()
    assert auth.sesion_valida(token) is not None  # uso => renueva (ventana deslizante)
    con = db.conectar()
    try:
        despues = con.execute(
            "SELECT expira FROM sesiones WHERE token = ?", (token,)
        ).fetchone()["expira"]
    finally:
        con.close()
    # Ya NO es la fecha 2030 forzada: el uso la reescribio a ~ahora + horas_sesion().
    assert despues != "2030-01-01T00:00:00+00:00"
    # `expira` se guarda en el canon UTC-SIN-OFFSET (iso_utc): `despues` es naive. Comparamos
    # contra un `esperada` tambien naive-UTC (no aware), o restar naive-aware reventaria.
    esperada = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=auth.horas_sesion())
    obtenida = datetime.fromisoformat(despues)
    assert abs((obtenida - esperada).total_seconds()) < 60


def test_login_expirado_por_intentos_fallidos_bloquea(entorno):
    """Anti fuerza bruta: tras varios fallos, la cuenta queda bloqueada un rato."""
    _crear("ana", CLAVE, "editor")
    for _ in range(auth.MAX_INTENTOS_FALLIDOS):
        assert auth.autenticar("ana", "mala") is None
    # Aun con la contrasena CORRECTA, queda bloqueada justo despues.
    assert auth.autenticar("ana", CLAVE) is None


def test_login_limite_por_ip_devuelve_429(entorno, monkeypatch):
    """Limite POR IP (hardening 2026-06): tras N intentos FALLIDOS desde la misma IP, el
    login responde 429 ANTES de tocar credenciales (ni siquiera con la pass correcta).

    Complementa el lockout por cuenta (que solo, es un vector de DoS contra terceros).
    Ventana deslizante EN MEMORIA, por proceso (1 worker uvicorn en prod: ver api/auth).
    """
    from keni_consola.api import auth as api_auth

    monkeypatch.setenv("KENI_LOGIN_IP_MAX", "3")
    api_auth.reiniciar_limite_login_por_ip()
    _crear("ana", CLAVE, "editor")
    c = _cli()
    for _ in range(3):
        assert _login(c, "ana", "mala").status_code == 401
    # Cupo agotado: 429 incluso con credenciales CORRECTAS (la IP esta cortada).
    r = _login(c, "ana", CLAVE)
    assert r.status_code == 429
    assert "error" in r.json()


def test_login_limite_por_ip_no_cuenta_exitos(entorno, monkeypatch):
    """Los logins CORRECTOS no consumen cupo del limite por IP (uso normal intacto)."""
    from keni_consola.api import auth as api_auth

    monkeypatch.setenv("KENI_LOGIN_IP_MAX", "2")
    api_auth.reiniciar_limite_login_por_ip()
    _crear("ana", CLAVE, "editor", debe_cambiar_password=False)
    c = _cli()
    for _ in range(4):  # mas exitos que el maximo de fallos: nunca 429
        assert _login(c, "ana", CLAVE).status_code == 200


# --------------------------------------------------------------------------- #
# 10) Convivencia con el token de #134                                        #
# --------------------------------------------------------------------------- #


def test_token_de_bootstrap_sigue_valiendo_para_api(entorno):
    """El TOKEN de #134 sigue autorizando /api sin necesidad de sesion."""
    c = _cli()
    r = c.get("/api/estado", headers={"Authorization": f"Bearer {TOKEN_PRUEBA}"})
    assert r.status_code == 200


def test_token_bootstrap_crea_primer_admin_con_bd_vacia(entorno):
    """#150: con la BD VACIA, el token de mantenimiento SI puede crear el PRIMER admin.

    Es el unico camino admin que conserva el token: bootstrap de recuperacion. No es poder
    admin general (ver los tests de abajo): en cuanto hay usuarios, el token deja de poder.
    """
    c = _cli()
    assert not auth.hay_usuarios()
    h = {**_ORIGIN, "Authorization": f"Bearer {TOKEN_PRUEBA}"}
    r = c.post(
        "/api/usuarios",
        json={"usuario": "primero", "password": CLAVE, "rol": "admin"},
        headers=h,
    )
    assert r.status_code == 201
    assert r.json()["rol"] == "admin"
    assert auth.contar_admins() == 1


def test_token_bootstrap_solo_admin_no_editor(entorno):
    """#150: el bootstrap por token SOLO crea admin; un editor con BD vacia -> 403.

    Inicializar un editor con la BD vacia dejaria la consola sin admin (y sin recuperacion).
    """
    c = _cli()
    h = {**_ORIGIN, "Authorization": f"Bearer {TOKEN_PRUEBA}"}
    r = c.post(
        "/api/usuarios",
        json={"usuario": "ed", "password": CLAVE, "rol": "editor"},
        headers=h,
    )
    assert r.status_code == 403
    assert not auth.hay_usuarios()


def test_token_no_crea_usuarios_si_ya_hay(entorno):
    """#150: con usuarios YA en la BD, el token NO puede crear cuentas (no es admin) -> 403."""
    _crear("jefa", CLAVE, "admin")
    c = _cli()
    h = {**_ORIGIN, "Authorization": f"Bearer {TOKEN_PRUEBA}"}
    r = c.post(
        "/api/usuarios",
        json={"usuario": "colado", "password": CLAVE, "rol": "admin"},
        headers=h,
    )
    assert r.status_code == 403
    assert auth.autenticar("colado", CLAVE) is None


def test_token_no_lista_usuarios(entorno):
    """#150: GET /api/usuarios por el token (sin sesion admin real) -> 403 (no es admin)."""
    _crear("jefa", CLAVE, "admin")
    c = _cli()
    r = c.get("/api/usuarios", headers={"Authorization": f"Bearer {TOKEN_PRUEBA}"})
    assert r.status_code == 403


def test_token_no_modifica_usuarios(entorno):
    """#150: PATCH /api/usuarios/{id} por el token -> 403 (no puede tocar cuentas)."""
    _crear("jefa", CLAVE, "admin")
    ed = _crear("ed", CLAVE, "editor")
    c = _cli()
    h = {**_ORIGIN, "Authorization": f"Bearer {TOKEN_PRUEBA}"}
    r = c.patch(f"/api/usuarios/{ed['id']}", json={"rol": "admin"}, headers=h)
    assert r.status_code == 403
    # No cambio nada: sigue siendo editor.
    assert auth.obtener_usuario_por_id(ed["id"])["rol"] == "editor"


def test_token_no_borra_usuarios(entorno):
    """#150: DELETE /api/usuarios/{id} por el token -> 403 (no puede borrar cuentas)."""
    _crear("jefa", CLAVE, "admin")
    ed = _crear("ed", CLAVE, "editor")
    c = _cli()
    r = c.delete(
        f"/api/usuarios/{ed['id']}",
        headers={**_ORIGIN, "Authorization": f"Bearer {TOKEN_PRUEBA}"},
    )
    assert r.status_code == 403
    assert auth.obtener_usuario_por_id(ed["id"]) is not None


def test_admin_real_si_gestiona_usuarios(entorno):
    """#150: un admin REAL (sesion) SIGUE gestionando usuarios (no se rompe el flujo normal)."""
    _crear("jefa", CLAVE, "admin")
    c = _cli()
    _login(c, "jefa", CLAVE)
    assert c.get("/api/usuarios").status_code == 200
    r = c.post(
        "/api/usuarios",
        json={"usuario": "nuevo", "password": CLAVE, "rol": "editor"},
        headers=_ORIGIN,
    )
    assert r.status_code == 201


def test_sesion_autoriza_api_sin_token(entorno):
    """Una sesion valida autoriza /api aunque NO se mande el token de #134."""
    _crear("ana", CLAVE, "editor")
    c = _cli()
    _login(c, "ana", CLAVE)
    r = c.get("/api/estado")  # sin Authorization: solo la cookie de sesion
    assert r.status_code == 200


def test_api_sin_sesion_ni_token_da_401(entorno):
    c = _cli()
    assert c.get("/api/estado").status_code == 401


# --------------------------------------------------------------------------- #
# 11) Integridad de la tabla usuarios                                         #
# --------------------------------------------------------------------------- #


def test_usuario_unico_a_nivel_db(entorno):
    assert _crear("ana", CLAVE) is not None
    # Crear el mismo nombre otra vez devuelve None (UNIQUE), sin lanzar.
    assert _crear("ana", CLAVE_NUEVA) is None


def test_app_con_bootstrap_crea_admin(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CONSOLA_ADMIN_PASS", CLAVE)
    c = _cli(bootstrap=True)
    r = _login(c, "admin", CLAVE)
    assert r.status_code == 200 and r.json()["usuario"]["rol"] == "admin"


def test_cliente_conftest_no_arranca_bootstrap(entorno):
    """El `_cliente` de conftest no crea usuarios (via token); la tabla queda vacia."""
    _cliente()  # crea la app con bootstrap=False
    assert not auth.hay_usuarios()


def test_borrar_usuario_libera_sus_piezas_cogidas(entorno):
    """Dar de baja a un usuario LIBERA las piezas que tenía cogidas (vuelven a «Por coger»).

    Sin esto quedaban con `responsable_id` = un id fantasma: fuera de «Por coger» y de «Mis
    tareas» de cualquiera, e irreclamables (el claim exige responsable_id='').
    """
    from keni_consola import repos

    u = _crear("mariana", CLAVE, "editor")
    assert u is not None
    cont = repos.crear_publicacion(titulo="Gol del Mundial", marca="claro-sports")
    repos.reclamar_publicacion(
        cont["id"], responsable_id=u["id"], responsable_nombre="mariana"
    )
    assert repos.obtener_publicacion(cont["id"])["responsable_id"] == u["id"]

    assert auth.borrar_usuario(u["id"]) is True

    liberada = repos.obtener_publicacion(cont["id"])
    assert liberada is not None  # la pieza NO se borra; solo se suelta
    assert liberada["responsable_id"] == ""
    assert liberada["responsable_nombre"] == ""
