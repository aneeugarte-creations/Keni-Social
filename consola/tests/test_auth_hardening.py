"""Tests del ENDURECIMIENTO de auth tras la revisión de seguridad (#130).

Cubre los tres must-fix:
  1. Cambiar/resetear la contraseña invalida TODAS las sesiones del usuario (sesión
     robada/equipo prestado/cuenta reseteada por el admin). El cambio voluntario
     re-emite una sesión nueva para el dispositivo actual (no fuerza re-login).
  2. `debe_cambiar_password` se aplica en el SERVIDOR: con el flag activo solo se
     permiten ver/cambiar/salir; cualquier otra /api -> 403.
  3. Tope de longitud (anti-DoS scrypt) en contraseña y nombre de usuario.

Todo OFFLINE; reusa el aislamiento de `entorno`.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
_ADMIN_TOKEN = {**_ORIGIN, "Authorization": f"Bearer {TOKEN_PRUEBA}"}

CLAVE = "clave-de-prueba"
CLAVE_NUEVA = "clave-nueva-test"


def _cli() -> TestClient:
    """TestClient SIN credencial por defecto (cada test la aporta como necesita)."""
    return TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False))


def _login(c: TestClient, usuario: str, password: str):
    return c.post("/api/auth/login", json={"usuario": usuario, "password": password}, headers=_ORIGIN)


# --------------------------------------------------------------------------- #
# 1) Invalidación de sesiones al cambiar/resetear contraseña                  #
# --------------------------------------------------------------------------- #


def test_cambiar_password_invalida_otras_sesiones_y_reemite_la_actual(entorno):
    auth.crear_usuario("ana", CLAVE, "editor")
    ca, cb = _cli(), _cli()
    assert _login(ca, "ana", CLAVE).status_code == 200
    assert _login(cb, "ana", CLAVE).status_code == 200  # dos sesiones vivas

    r = ca.post(
        "/api/auth/cambiar-password",
        json={"password_actual": CLAVE, "password_nueva": CLAVE_NUEVA},
        headers=_ORIGIN,
    )
    assert r.status_code == 204

    # La OTRA sesión queda invalidada; la del dispositivo que cambió sigue viva (re-emitida).
    assert cb.get("/api/auth/me").status_code == 401
    assert ca.get("/api/auth/me").status_code == 200


def test_reset_de_admin_expulsa_la_sesion_del_objetivo(entorno):
    auth.crear_usuario("jefa", CLAVE, "admin", superadmin=True)
    auth.crear_usuario("leo", CLAVE, "editor")
    ce = _cli()
    assert _login(ce, "leo", CLAVE).status_code == 200
    leo_id = auth.autenticar("leo", CLAVE)["id"]

    # El admin REAL (sesion) resetea la contraseña de leo (#150: el token ya no es admin).
    cadmin = _cli()
    assert _login(cadmin, "jefa", CLAVE).status_code == 200
    r = cadmin.patch(f"/api/usuarios/{leo_id}", json={"password": CLAVE_NUEVA}, headers=_ORIGIN)
    assert r.status_code == 200

    # La sesión que leo tenía abierta deja de valer.
    assert ce.get("/api/auth/me").status_code == 401


# --------------------------------------------------------------------------- #
# 2) Enforcement server-side de debe_cambiar_password                         #
# --------------------------------------------------------------------------- #


def test_debe_cambiar_password_bloquea_otras_rutas_en_el_servidor(entorno):
    auth.crear_usuario("nueva", CLAVE, "admin", debe_cambiar_password=True, superadmin=True)
    c = _cli()
    assert _login(c, "nueva", CLAVE).status_code == 200

    # Con el flag activo, una ruta normal /api -> 403 (no la deja el middleware).
    bloqueada = c.get("/api/usuarios")
    assert bloqueada.status_code == 403
    assert "cambiar tu contrase" in bloqueada.json()["error"].lower()

    # Pero SÍ puede ver su sesión y cambiar la contraseña (rutas permitidas).
    assert c.get("/api/auth/me").status_code == 200
    cambio = c.post(
        "/api/auth/cambiar-password",
        json={"password_actual": CLAVE, "password_nueva": CLAVE_NUEVA},
        headers=_ORIGIN,
    )
    assert cambio.status_code == 204

    # Tras cambiarla, ya puede usar el resto.
    assert c.get("/api/usuarios").status_code == 200


def test_token_de_mantenimiento_no_esta_sujeto_a_debe_cambiar(entorno):
    # El gate `debe_cambiar_password` es de un USUARIO de sesion; el token de mantenimiento
    # no tiene usuario, asi que no le aplica. Probamos con una ruta /api normal (no admin):
    # el token la pasa aunque exista una cuenta con el flag activo (no hay "admin fantasma",
    # #150: el token NO toca /api/usuarios, eso ya es 403 — ver test_auth.py).
    auth.crear_usuario("nueva", CLAVE, "admin", debe_cambiar_password=True)
    assert _cli().get("/api/estado", headers=_ADMIN_TOKEN).status_code == 200


# --------------------------------------------------------------------------- #
# 3) Tope de longitud (anti-DoS scrypt)                                       #
# --------------------------------------------------------------------------- #


def test_login_rechaza_password_gigante_sin_hashear(entorno):
    auth.crear_usuario("ana", CLAVE, "editor")
    enorme = "x" * (auth.LONGITUD_MAX_PASSWORD + 1)
    assert _login(_cli(), "ana", enorme).status_code == 401


def test_crear_usuario_rechaza_password_y_nombre_gigantes(entorno):
    # #150: la gestion de usuarios exige un superadmin REAL (el token ya no es admin), asi que
    # creamos un superadmin y entramos por sesion para probar la validacion de tamano.
    auth.crear_usuario("jefa", CLAVE, "admin", superadmin=True)
    c = _cli()
    assert _login(c, "jefa", CLAVE).status_code == 200
    larga = "x" * (auth.LONGITUD_MAX_PASSWORD + 1)
    r1 = c.post("/api/usuarios", json={"usuario": "bob", "password": larga, "rol": "editor"}, headers=_ORIGIN)
    assert r1.status_code == 400

    nombre = "n" * (auth.LONGITUD_MAX_USUARIO + 1)
    r2 = c.post("/api/usuarios", json={"usuario": nombre, "password": CLAVE, "rol": "editor"}, headers=_ORIGIN)
    assert r2.status_code == 400


def test_cambiar_password_rechaza_actual_gigante(entorno):
    auth.crear_usuario("ana", CLAVE, "editor")
    c = _cli()
    assert _login(c, "ana", CLAVE).status_code == 200
    enorme = "x" * (auth.LONGITUD_MAX_PASSWORD + 1)
    r = c.post(
        "/api/auth/cambiar-password",
        json={"password_actual": enorme, "password_nueva": CLAVE_NUEVA},
        headers=_ORIGIN,
    )
    assert r.status_code == 400
