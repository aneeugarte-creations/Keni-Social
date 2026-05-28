"""Permisos por rol en /api/conexiones (#153): SOLO ADMIN.

La clave del proveedor de imagen (`secretos.toml`) y los tokens de redes
(`config.toml` de metricas) son SECRETOS GLOBALES y compartidos. Antes cualquier
usuario autenticado podia leerlos/mutarlos; ahora TODOS los endpoints de conexiones
(lectura Y mutacion) exigen rol admin:

  - un EDITOR (sesion) recibe 403 en cada endpoint (GET/PUT/POST/DELETE),
  - un ADMIN (sesion) y el acceso por TOKEN interino de mantenimiento SI pueden.

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
    """TestClient que entra por el TOKEN interino (mantenimiento = plenos permisos)."""
    c = _cli()
    c.headers.update({"Authorization": f"Bearer {TOKEN_PRUEBA}"})
    return c


# Endpoints (metodo, ruta, json) que tocan secretos globales: TODOS solo-admin.
_LECTURAS = [
    ("GET", "/api/conexiones/imagen", None),
    ("GET", "/api/conexiones/redes", None),
]
_MUTACIONES = [
    ("PUT", "/api/conexiones/imagen", {"api_key": _CLAVE_IMG}),
    ("DELETE", "/api/conexiones/imagen", None),
    ("PUT", "/api/conexiones/imagen/modelo", {"modelo": "openai/gpt-5-image"}),
    ("POST", "/api/conexiones/imagen/probar", None),
    ("PUT", "/api/conexiones/redes/meta", {"token": _TOKEN_RED}),
    ("DELETE", "/api/conexiones/redes/meta", None),
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
    """Un admin guarda una clave; un editor NO debe poder leer ni la pista del estado."""
    admin = _cli_token()
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
    # El admin (token) comprueba que NADA se guardo: sigue sin configurar.
    admin = _cli_token()
    assert admin.get("/api/conexiones/imagen").json()["configurado"] is False


# --------------------------------------------------------------------------- #
# Admin (sesion) -> SI puede; token interino tambien                          #
# --------------------------------------------------------------------------- #


def test_admin_lee_y_guarda_conexiones(entorno):
    c = _cli_como("admin")
    assert c.get("/api/conexiones/imagen").status_code == 200
    r = c.put("/api/conexiones/imagen", json={"api_key": _CLAVE_IMG}, headers=_ORIGIN)
    assert r.status_code == 200
    assert c.get("/api/conexiones/imagen").json()["configurado"] is True
    # El token NO se devuelve nunca.
    assert _CLAVE_IMG not in r.text


def test_admin_guarda_token_de_red(entorno):
    c = _cli_como("admin")
    r = c.put("/api/conexiones/redes/meta", json={"token": _TOKEN_RED}, headers=_ORIGIN)
    assert r.status_code == 200
    redes = {x["plataforma"]: x for x in c.get("/api/conexiones/redes").json()["redes"]}
    assert redes["meta"]["conectado"] is True
    # Persiste en el config de metricas (el token real no se devuelve por la API).
    datos = tomllib.loads(open(os.environ["KENI_METRICAS_CONFIG"], encoding="utf-8").read())
    assert datos["credenciales"]["meta"]["access_token"] == _TOKEN_RED


def test_token_interino_mantiene_acceso(entorno):
    """El acceso por TOKEN interino (despliegue/mantenimiento) sigue pudiendo gestionar."""
    c = _cli_token()
    assert c.get("/api/conexiones/imagen").status_code == 200
    r = c.put("/api/conexiones/redes/youtube", json={"token": _TOKEN_RED}, headers=_ORIGIN)
    assert r.status_code == 200
