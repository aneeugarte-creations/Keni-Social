"""Tests de seguridad de la Consola: auth por token + proteccion CSRF (issue #134).

Cubre la barrera minima (NO multiusuario, eso es #130):
  - `/api` SIN token -> 401; CON token (cabecera o cookie) -> OK.
  - Mutaciones (POST/PUT/PATCH/DELETE) con `Origin`/`Referer` AJENO -> 403 (CSRF).
  - El SPA y sus estaticos se sirven SIN token (hay que poder cargar la pagina) y el
    index siembra la cookie + inyecta `window.__KENI_TOKEN__`.
  - El token se resuelve de `KENI_CONSOLA_TOKEN`; si no esta, se genera uno (logueado).

Todo OFFLINE: ningun lanzador real, ninguna red. Reusa el aislamiento de `entorno`.
"""

from __future__ import annotations

import logging

import pytest
from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import seguridad
from keni_consola.observabilidad import NOMBRE_LOGGER

from .conftest import TOKEN_PRUEBA

# Host esperado por defecto del TestClient de Starlette (base_url = http://testserver).
_HOST = "testserver"


def _app(token: str = TOKEN_PRUEBA):
    """App con un token de sesion conocido (sin lanzadores reales)."""
    return app_modulo.crear_app(token=token)


def _cli_sin_auth(token: str = TOKEN_PRUEBA) -> TestClient:
    """TestClient que NO manda el token por defecto (para probar el rechazo)."""
    return TestClient(_app(token))


def _cli_con_auth(token: str = TOKEN_PRUEBA) -> TestClient:
    """TestClient que manda `Authorization: Bearer <token>` por defecto."""
    return TestClient(_app(token), headers={"Authorization": f"Bearer {token}"})


# --------------------------------------------------------------------------- #
# 1) Token de sesion exigido para /api                                         #
# --------------------------------------------------------------------------- #


def test_api_sin_token_da_401(entorno):
    """Una peticion a /api SIN token es rechazada con 401 JSON en espanol."""
    c = _cli_sin_auth()
    r = c.get("/api/estado")
    assert r.status_code == 401
    assert "error" in r.json()
    assert "token" in r.json()["error"].lower()


def test_api_con_token_bearer_ok(entorno):
    """Con `Authorization: Bearer <token>` correcto, /api responde 200."""
    c = _cli_con_auth()
    r = c.get("/api/estado")
    assert r.status_code == 200


def test_api_con_token_cabecera_x_keni_ok(entorno):
    """El token tambien se admite por la cabecera `X-Keni-Token`."""
    c = _cli_sin_auth()
    r = c.get("/api/estado", headers={"X-Keni-Token": TOKEN_PRUEBA})
    assert r.status_code == 200


def test_api_con_token_cookie_ok(entorno):
    """El token tambien se admite por la cookie `keni_consola_token` (GET/img/descargas)."""
    c = _cli_sin_auth()
    c.cookies.set(seguridad.COOKIE_TOKEN, TOKEN_PRUEBA)
    r = c.get("/api/estado")
    assert r.status_code == 200


def test_api_con_token_incorrecto_da_401(entorno):
    """Un token que no coincide es rechazado (401), aunque venga bien formado."""
    c = _cli_sin_auth()
    r = c.get("/api/estado", headers={"Authorization": "Bearer token-equivocado"})
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# 2) Proteccion CSRF en mutaciones (Origin/Referer)                            #
# --------------------------------------------------------------------------- #


def test_mutacion_con_origin_ajeno_rechazada(entorno):
    """POST con token valido pero `Origin` de otro sitio -> 403 (CSRF)."""
    c = _cli_con_auth()
    r = c.post(
        "/api/config/esfuerzo",
        json={"esfuerzo": "high"},
        headers={"Origin": "https://sitio-malicioso.example"},
    )
    assert r.status_code == 403
    assert "csrf" in r.json()["error"].lower() or "origen" in r.json()["error"].lower()


def test_mutacion_con_referer_ajeno_rechazada(entorno):
    """POST con `Referer` de otro sitio (sin Origin) -> 403 (CSRF)."""
    c = _cli_con_auth()
    r = c.post(
        "/api/config/esfuerzo",
        json={"esfuerzo": "high"},
        headers={"Referer": "https://otro.example/pagina"},
    )
    assert r.status_code == 403


def test_mutacion_con_origin_mismo_host_ok(entorno):
    """POST con `Origin` del mismo host (como el SPA propio) pasa el chequeo CSRF."""
    c = _cli_con_auth()
    r = c.post(
        "/api/config/esfuerzo",
        json={"esfuerzo": "high"},
        headers={"Origin": f"http://{_HOST}"},
    )
    # 200 (guardado) — lo importante es que NO es 403 (no fue rechazado por CSRF).
    assert r.status_code != 403
    assert r.status_code == 200


def test_mutacion_sin_origin_ni_referer_ok(entorno):
    """Un cliente sin navegador (sin Origin/Referer) que ya tiene el token puede mutar.

    El modelo de amenaza de CSRF es el NAVEGADOR de un tercero (que SIEMPRE manda
    Origin en cross-site con cuerpo); un cliente legitimo con el token no lo es.
    """
    c = _cli_con_auth()
    r = c.post("/api/config/esfuerzo", json={"esfuerzo": "high"})
    assert r.status_code != 403


def test_get_con_origin_ajeno_no_se_bloquea_por_csrf(entorno):
    """El chequeo CSRF solo aplica a MUTACIONES: un GET con Origin ajeno no es 403.

    (Un GET ajeno igual no puede LEER la respuesta cross-site sin CORS, que no damos.)
    """
    c = _cli_con_auth()
    r = c.get("/api/estado", headers={"Origin": "https://sitio-ajeno.example"})
    assert r.status_code == 200


# --------------------------------------------------------------------------- #
# 3) El SPA / estaticos NO exigen token (hay que poder cargar la pagina)       #
# --------------------------------------------------------------------------- #


def test_spa_se_sirve_sin_token(entorno):
    """La raiz (SPA / placeholder) se sirve SIN token: 200 HTML."""
    c = _cli_sin_auth()
    r = c.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_index_siembra_cookie_e_inyecta_token(entorno):
    """El index del SPA siembra la cookie del token e inyecta `window.__KENI_TOKEN__`."""
    c = _cli_sin_auth()
    r = c.get("/")
    assert r.status_code == 200
    # Cookie sembrada con el token.
    assert seguridad.COOKIE_TOKEN in r.headers.get("set-cookie", "")
    # Token inyectado en el HTML para que el SPA lo mande por cabecera.
    assert "__KENI_TOKEN__" in r.text
    assert TOKEN_PRUEBA in r.text


def test_ruta_no_api_se_sirve_sin_token(entorno):
    """Una ruta de enrutado en cliente (no /api) cae al SPA sin exigir token."""
    c = _cli_sin_auth()
    r = c.get("/tareas")
    assert r.status_code == 200


def test_cookie_token_sin_secure_por_defecto(entorno, monkeypatch):
    """Por defecto (local HTTP) la cookie del token NO lleva `Secure`."""
    monkeypatch.delenv(seguridad.ENV_COOKIE_SECURE, raising=False)
    monkeypatch.delenv(seguridad.ENV_HTTPS, raising=False)
    c = _cli_sin_auth()
    r = c.get("/")
    set_cookie = r.headers.get("set-cookie", "").lower()
    assert seguridad.COOKIE_TOKEN.lower() in set_cookie
    assert "secure" not in set_cookie


def test_cookie_token_con_secure_por_env(entorno, monkeypatch):
    """`KENI_CONSOLA_COOKIE_SECURE=1` marca la cookie del token como `Secure`."""
    monkeypatch.setenv(seguridad.ENV_COOKIE_SECURE, "1")
    c = _cli_sin_auth()
    r = c.get("/")
    set_cookie = r.headers.get("set-cookie", "").lower()
    assert seguridad.COOKIE_TOKEN.lower() in set_cookie
    assert "secure" in set_cookie


def test_cookie_token_secure_derivado_de_https(entorno, monkeypatch):
    """Sin flag explicito, `KENI_CONSOLA_HTTPS=1` tambien activa `Secure`."""
    monkeypatch.delenv(seguridad.ENV_COOKIE_SECURE, raising=False)
    monkeypatch.setenv(seguridad.ENV_HTTPS, "1")
    c = _cli_sin_auth()
    r = c.get("/")
    assert "secure" in r.headers.get("set-cookie", "").lower()


# --------------------------------------------------------------------------- #
# 4) Resolucion del token (env var o generado)                                 #
# --------------------------------------------------------------------------- #


def test_token_desde_env_var(entorno, monkeypatch):
    """`KENI_CONSOLA_TOKEN` fija el token; `resolver_token` no genera uno nuevo."""
    monkeypatch.setenv("KENI_CONSOLA_TOKEN", "mi-token-fijo")
    token, generado = seguridad.resolver_token()
    assert token == "mi-token-fijo"
    assert generado is False


def test_token_generado_si_no_hay_env(entorno, monkeypatch):
    """Sin env var, `resolver_token` genera uno aleatorio no vacio."""
    monkeypatch.delenv("KENI_CONSOLA_TOKEN", raising=False)
    token, generado = seguridad.resolver_token()
    assert generado is True
    assert isinstance(token, str) and len(token) >= 16


def test_crear_app_genera_y_loguea_token(entorno, monkeypatch, caplog):
    """Si no se inyecta token ni hay env var, `crear_app` genera uno y lo muestra en el log."""
    monkeypatch.delenv("KENI_CONSOLA_TOKEN", raising=False)
    # `configurar_logging()` (lo llaman otros tests/arranque) deja el logger del paquete
    # con `propagate=False`; caplog captura via el root, asi que forzamos propagacion
    # durante la captura (y la restauramos despues). Solo es relevante en tests.
    logger_pkg = logging.getLogger(NOMBRE_LOGGER)
    propagacion_previa = logger_pkg.propagate
    logger_pkg.propagate = True
    try:
        with caplog.at_level(logging.WARNING, logger=NOMBRE_LOGGER):
            app = app_modulo.crear_app()
    finally:
        logger_pkg.propagate = propagacion_previa
    # El token quedo en el estado de la app y aparecio en un WARNING del paquete.
    token = app.state.token_consola
    assert token
    mensajes = "\n".join(r.getMessage() for r in caplog.records if r.name == NOMBRE_LOGGER)
    assert token in mensajes


def test_app_usa_token_de_env(entorno, monkeypatch):
    """Sin token inyectado pero CON env var, la app usa el de la env var."""
    monkeypatch.setenv("KENI_CONSOLA_TOKEN", "token-de-entorno-xyz")
    c = TestClient(app_modulo.crear_app())
    # Con el token de la env var en cabecera -> OK; sin el -> 401.
    assert c.get("/api/estado", headers={"Authorization": "Bearer token-de-entorno-xyz"}).status_code == 200
    assert c.get("/api/estado").status_code == 401


# --------------------------------------------------------------------------- #
# 5) Helpers de host/origen (unit)                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "url,esperado",
    [
        ("http://127.0.0.1:8765", "127.0.0.1:8765"),
        ("http://127.0.0.1:8765/ruta?x=1", "127.0.0.1:8765"),
        ("https://EVIL.example", "evil.example"),
        ("no-es-url", None),
        ("", None),
    ],
)
def test_host_de_url(url, esperado):
    assert seguridad._host_de_url(url) == esperado


# --------------------------------------------------------------------------- #
# 6) cookie_secure(): flag explicito > derivado de HTTPS > default False       #
# --------------------------------------------------------------------------- #


def test_cookie_secure_default_false(monkeypatch):
    monkeypatch.delenv(seguridad.ENV_COOKIE_SECURE, raising=False)
    monkeypatch.delenv(seguridad.ENV_HTTPS, raising=False)
    assert seguridad.cookie_secure() is False


@pytest.mark.parametrize("valor", ["1", "true", "yes", "si", "on"])
def test_cookie_secure_activada_por_flag(monkeypatch, valor):
    monkeypatch.setenv(seguridad.ENV_COOKIE_SECURE, valor)
    assert seguridad.cookie_secure() is True


def test_cookie_secure_derivada_de_https(monkeypatch):
    """Sin flag explicito, se deriva de `KENI_CONSOLA_HTTPS`."""
    monkeypatch.delenv(seguridad.ENV_COOKIE_SECURE, raising=False)
    monkeypatch.setenv(seguridad.ENV_HTTPS, "1")
    assert seguridad.cookie_secure() is True


def test_cookie_secure_flag_explicito_manda_sobre_https(monkeypatch):
    """El flag explicito gana: `COOKIE_SECURE=0` apaga aunque `HTTPS=1`."""
    monkeypatch.setenv(seguridad.ENV_COOKIE_SECURE, "0")
    monkeypatch.setenv(seguridad.ENV_HTTPS, "1")
    assert seguridad.cookie_secure() is False
