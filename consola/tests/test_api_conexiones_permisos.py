"""Permisos por rol en /api/conexiones (#153): SOLO ADMIN.

La clave del proveedor de imagen (`secretos.toml`) y las credenciales de Metricool
(`config.toml` de metricas) son SECRETOS GLOBALES y compartidos. Antes cualquier
usuario autenticado podia leerlos/mutarlos; ahora TODOS los endpoints de conexiones
(lectura Y mutacion) exigen rol admin:

  - un EDITOR (sesion) recibe 403 en cada endpoint (GET/PUT/POST/DELETE),
  - SOLO un ADMIN (sesion) puede; el TOKEN de mantenimiento NO es admin (#150) y
    tambien recibe 403 en conexiones (no es un backdoor a los secretos globales).

Mismo aislamiento OFFLINE que el resto: `entorno` aisla `secretos.toml` y el config
de metricas en tmp; nunca se toca la red ni el disco real. La sesion se obtiene por
login (cookie), igual que en test_auth.py.
"""

from __future__ import annotations

import os
import tomllib

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth

from .conftest import TOKEN_PRUEBA

# Origin del propio host del TestClient (pasa el chequeo CSRF en mutaciones).
_ORIGIN = {"Origin": "http://testserver"}
CLAVE = "clave-de-prueba"
_CLAVE_IMG = "sk-test-PISTA1234"
_TOKEN_RED = "tok-red-SECRETO-9999"


def _app():
    """App con el token interino de prueba (sin lanzadores reales)."""
    return app_modulo.crear_app(token=TOKEN_PRUEBA)


def _cli() -> TestClient:
    """TestClient SIN credencial por defecto (cada test la aporta como necesita)."""
    return TestClient(_app())


def _login(c: TestClient, usuario: str, password: str):
    """Hace login y deja la cookie de sesion en el cliente; devuelve la respuesta."""
    return c.post(
        "/api/auth/login", json={"usuario": usuario, "password": password}, headers=_ORIGIN
    )


def _cli_como(rol: str) -> TestClient:
    """TestClient autenticado por SESION con un usuario del rol dado (admin/editor)."""
    auth.crear_usuario("u", CLAVE, rol)
    c = _cli()
    r = _login(c, "u", CLAVE)
    assert r.status_code == 200
    return c


def _cli_token() -> TestClient:
    """TestClient que entra SOLO por el TOKEN de mantenimiento (sin usuario de sesion).

    ESTRICTO (#150): el token NO es admin, asi que en `/api/conexiones/*` recibe 403.
    """
    c = _cli()
    c.headers.update({"Authorization": f"Bearer {TOKEN_PRUEBA}"})
    return c


# Endpoints (metodo, ruta, json) que tocan secretos globales: TODOS solo-admin.
_LECTURAS = [
    ("GET", "/api/conexiones/imagen", None),
    ("GET", "/api/conexiones/metricool", None),
]
_MUTACIONES = [
    ("PUT", "/api/conexiones/imagen", {"api_key": _CLAVE_IMG}),
    ("DELETE", "/api/conexiones/imagen", None),
    ("PUT", "/api/conexiones/imagen/modelo", {"modelo": "openai/gpt-5-image"}),
    ("POST", "/api/conexiones/imagen/probar", None),
    (
        "PUT",
        "/api/conexiones/metricool/claro_sports",
        {"user_token": _TOKEN_RED, "user_id": "1", "blog_id": "1"},
    ),
    ("DELETE", "/api/conexiones/metricool/claro_sports", None),
    ("POST", "/api/conexiones/metricool/claro_sports/probar", None),
    (
        "POST",
        "/api/conexiones/metricool/perfiles",
        {"user_token": _TOKEN_RED, "user_id": "1"},
    ),
]


def _pedir(c: TestClient, metodo: str, ruta: str, cuerpo):
    """Lanza una peticion `metodo ruta` (con Origin propio en mutaciones)."""
    headers = {} if metodo == "GET" else dict(_ORIGIN)
    return c.request(metodo, ruta, json=cuerpo, headers=headers)


# --------------------------------------------------------------------------- #
# Editor (sesion) -> 403 en TODO conexiones (lectura y mutacion)              #
# --------------------------------------------------------------------------- #


def test_editor_no_lee_conexiones_403(entorno):
    c = _cli_como("editor")
    for metodo, ruta, cuerpo in _LECTURAS:
        r = _pedir(c, metodo, ruta, cuerpo)
        assert r.status_code == 403, f"{metodo} {ruta} deberia ser 403 para editor"
        assert "administrador" in r.json()["error"].lower()


def test_editor_no_muta_conexiones_403(entorno):
    c = _cli_como("editor")
    for metodo, ruta, cuerpo in _MUTACIONES:
        r = _pedir(c, metodo, ruta, cuerpo)
        assert r.status_code == 403, f"{metodo} {ruta} deberia ser 403 para editor"


def test_editor_no_filtra_secreto_de_imagen(entorno):
    """Un admin (sesion) guarda una clave; un editor NO puede leer ni la pista del estado."""
    auth.crear_usuario("admin", CLAVE, "admin")
    admin = _cli()
    assert _login(admin, "admin", CLAVE).status_code == 200
    admin.put("/api/conexiones/imagen", json={"api_key": _CLAVE_IMG}, headers=_ORIGIN)
    editor = _cli_como("editor")
    r = editor.get("/api/conexiones/imagen")
    assert r.status_code == 403
    # La clave (ni su pista) nunca aparece en el cuerpo del rechazo.
    assert _CLAVE_IMG not in r.text
    assert _CLAVE_IMG[-4:] not in r.text


def test_editor_no_escribe_secreto_global(entorno):
    """El PUT de un editor NO debe llegar a tocar el secreto global (sigue sin clave)."""
    editor = _cli_como("editor")
    r = editor.put("/api/conexiones/imagen", json={"api_key": _CLAVE_IMG}, headers=_ORIGIN)
    assert r.status_code == 403
    # Un admin (sesion) comprueba que NADA se guardo: sigue sin configurar.
    auth.crear_usuario("admin", CLAVE, "admin")
    admin = _cli()
    assert _login(admin, "admin", CLAVE).status_code == 200
    assert admin.get("/api/conexiones/imagen").json()["configurado"] is False


# --------------------------------------------------------------------------- #
# Admin (sesion) -> SI puede; token de mantenimiento -> NO (403, #150)        #
# --------------------------------------------------------------------------- #


def test_admin_lee_y_guarda_conexiones(entorno):
    c = _cli_como("admin")
    assert c.get("/api/conexiones/imagen").status_code == 200
    r = c.put("/api/conexiones/imagen", json={"api_key": _CLAVE_IMG}, headers=_ORIGIN)
    assert r.status_code == 200
    assert c.get("/api/conexiones/imagen").json()["configurado"] is True
    # El token NO se devuelve nunca.
    assert _CLAVE_IMG not in r.text


def test_admin_guarda_credencial_metricool(entorno):
    c = _cli_como("admin")
    r = c.put(
        "/api/conexiones/metricool/claro_sports",
        json={"user_token": _TOKEN_RED, "user_id": "1", "blog_id": "9"},
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    marcas = {m["marca"]: m for m in c.get("/api/conexiones/metricool").json()["marcas"]}
    assert marcas["claro_sports"]["conectado"] is True
    # Persiste en el config de metricas (el token real no se devuelve por la API).
    datos = tomllib.loads(open(os.environ["KENI_METRICAS_CONFIG"], encoding="utf-8").read())
    assert datos["metricool"]["marcas"]["claro_sports"]["user_token"] == _TOKEN_RED
    assert _TOKEN_RED not in r.text


def test_token_mantenimiento_no_gestiona_conexiones_403(entorno):
    """ESTRICTO (#150): el TOKEN de mantenimiento NO es admin -> 403 en conexiones.

    Pasa la barrera de `/api` (es una credencial de mantenimiento), pero NO da acceso a los
    secretos globales: solo una SESION admin real los gestiona. Ni lectura ni mutacion.
    """
    c = _cli_token()
    assert c.get("/api/conexiones/imagen").status_code == 403
    assert c.get("/api/conexiones/metricool").status_code == 403
    r = c.put(
        "/api/conexiones/metricool/claro_sports",
        json={"user_token": _TOKEN_RED, "user_id": "1", "blog_id": "1"},
        headers=_ORIGIN,
    )
    assert r.status_code == 403
    # El secreto nunca aparece en el cuerpo del rechazo.
    assert _TOKEN_RED not in r.text
