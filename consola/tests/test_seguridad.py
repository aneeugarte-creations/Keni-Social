"""Tests de seguridad de la Consola: auth por token + proteccion CSRF (#134 + #130).

Cubre:
  - `/api` SIN token -> 401; CON token (cabecera o cookie) -> OK.
  - Mutaciones (POST/PUT/PATCH/DELETE) con `Origin`/`Referer` AJENO -> 403 (CSRF).
  - El SPA y sus estaticos se sirven SIN token (hay que poder cargar la pagina) y el
    index siembra la cookie + inyecta `window.__KENI_TOKEN__`.
  - El token se resuelve de `KENI_CONSOLA_TOKEN`; si no esta, se genera uno (logueado).
  - CSRF detras de proxy (#130): la allowlist `KENI_CONSOLA_ORIGENES` deja pasar la
    mutacion del SPA con el `Origin` del host publico, sin abrir cross-site. Local intacto.
  - Token interino OPCIONAL (#130): con `crear_app(token=None)` la app se protege solo con
    sesion + CSRF (sin sesion -> 401; mutaciones con CSRF), sin debilitar nada.

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


def test_crear_app_genera_token_pero_no_loguea_su_valor(entorno, monkeypatch, caplog):
    """#150: sin env var, `crear_app` genera un token pero NUNCA loguea su VALOR.

    Antes (#134) el token generado se imprimia en el log (UX `?token=...`); era un vector
    de fuga (backdoor en logs/capturas). Ahora se avisa de que se genero, sin revelarlo.
    """
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
    # El token quedo en el estado de la app (se usa para autenticar)...
    token = app.state.token_consola
    assert token
    # ...pero su VALOR NO aparece en NINGUN mensaje de log (#150), ni `?token=`.
    mensajes = "\n".join(r.getMessage() for r in caplog.records if r.name == NOMBRE_LOGGER)
    assert token not in mensajes
    assert "?token=" not in mensajes
    # Si avisa (sin revelar el secreto) de que se genero un token de mantenimiento.
    assert "KENI_CONSOLA_TOKEN" in mensajes


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


@pytest.mark.parametrize(
    "declarado,peticion,permitidos,esperado",
    [
        # Coincide con el Host de la peticion (local): pasa, haya o no allowlist.
        ("127.0.0.1:8765", "127.0.0.1:8765", frozenset(), True),
        ("127.0.0.1:8765", "127.0.0.1:8765", frozenset({"social.kenitech.io"}), True),
        # No coincide con el Host pero SI con la allowlist (tras proxy): pasa.
        ("social.kenitech.io", "back-interno:8765", frozenset({"social.kenitech.io"}), True),
        # Ni Host ni allowlist: rechazado (cross-site).
        ("evil.example", "back-interno:8765", frozenset({"social.kenitech.io"}), False),
        # Origin presente pero ilegible (host None) -> rechazado (no se confunde con "sin Origin").
        (None, "127.0.0.1:8765", frozenset(), False),
    ],
)
def test_host_de_confianza(declarado, peticion, permitidos, esperado):
    assert seguridad._host_de_confianza(declarado, peticion, permitidos) is esperado


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


# --------------------------------------------------------------------------- #
# 7) CSRF detras de un reverse-proxy (Traefik): allowlist de hosts externos    #
# --------------------------------------------------------------------------- #
#
# Detras de Traefik el host publico es `social.kenitech.io` y el navegador manda ese
# `Origin`; el `Host` que ve el back puede no coincidir byte a byte. La allowlist
# `KENI_CONSOLA_ORIGENES` permite que la mutacion del SPA legitimo pase, manteniendo el
# rechazo cross-site. En local (sin allowlist) solo cuenta el `Host`: intacto.

_ORIGEN_EXTERNO = "https://social.kenitech.io"


def test_mutacion_desde_origen_externo_configurado_pasa(entorno, monkeypatch):
    """Con `KENI_CONSOLA_ORIGENES` = host publico, un `Origin` de ESE host pasa el CSRF.

    Simula el SPA tras Traefik: el navegador manda `Origin: https://social.kenitech.io`
    aunque el `Host` que llega al back sea distinto (testserver). Debe NO ser 403.
    """
    monkeypatch.setenv(seguridad.ENV_ORIGENES, _ORIGEN_EXTERNO)
    c = _cli_con_auth()
    r = c.post(
        "/api/config/esfuerzo",
        json={"esfuerzo": "high"},
        headers={"Origin": _ORIGEN_EXTERNO},
    )
    assert r.status_code != 403
    assert r.status_code == 200


def test_mutacion_cross_site_rechazada_aunque_haya_allowlist(entorno, monkeypatch):
    """Con la allowlist puesta, un `Origin` AJENO (no en la lista) sigue siendo 403."""
    monkeypatch.setenv(seguridad.ENV_ORIGENES, _ORIGEN_EXTERNO)
    c = _cli_con_auth()
    r = c.post(
        "/api/config/esfuerzo",
        json={"esfuerzo": "high"},
        headers={"Origin": "https://sitio-malicioso.example"},
    )
    assert r.status_code == 403
    assert "csrf" in r.json()["error"].lower() or "origen" in r.json()["error"].lower()


def test_mutacion_referer_externo_configurado_pasa(entorno, monkeypatch):
    """El `Referer` del host publico (sin Origin) tambien pasa con la allowlist."""
    monkeypatch.setenv(seguridad.ENV_ORIGENES, "social.kenitech.io")  # host pelado
    c = _cli_con_auth()
    r = c.post(
        "/api/config/esfuerzo",
        json={"esfuerzo": "high"},
        headers={"Referer": "https://social.kenitech.io/panel"},
    )
    assert r.status_code != 403


def test_origin_del_host_de_la_peticion_pasa_sin_allowlist(entorno, monkeypatch):
    """LOCAL INTACTO: sin allowlist, el `Origin` == `Host` de la peticion sigue pasando."""
    monkeypatch.delenv(seguridad.ENV_ORIGENES, raising=False)
    c = _cli_con_auth()
    r = c.post(
        "/api/config/esfuerzo",
        json={"esfuerzo": "high"},
        headers={"Origin": f"http://{_HOST}"},
    )
    assert r.status_code != 403
    assert r.status_code == 200


def test_origin_externo_sin_allowlist_se_rechaza(entorno, monkeypatch):
    """Sin allowlist, un `Origin` que NO es el `Host` de la peticion -> 403 (como antes)."""
    monkeypatch.delenv(seguridad.ENV_ORIGENES, raising=False)
    c = _cli_con_auth()
    r = c.post(
        "/api/config/esfuerzo",
        json={"esfuerzo": "high"},
        headers={"Origin": _ORIGEN_EXTERNO},
    )
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
# 8) Token interino OPCIONAL (#130): sesion + CSRF protegen por si solas       #
# --------------------------------------------------------------------------- #
#
# Tras la auth multiusuario, el token interino es un gate EXTRA, no la barrera. Con
# `crear_app(token=None)` NO hay token interino: la unica credencial valida es la sesion.
# La proteccion NO se debilita: sin sesion -> 401; las mutaciones siguen con CSRF.


def _app_sin_token():
    """App SIN token interino (solo sesion + CSRF). Bootstrap ON para tener un admin."""
    return app_modulo.crear_app(token=None, bootstrap=False)


def test_api_sin_token_interino_exige_sesion_da_401(entorno):
    """Sin token interino y SIN sesion, una peticion a /api es 401 (no se debilita)."""
    c = TestClient(_app_sin_token())
    r = c.get("/api/estado")
    assert r.status_code == 401
    assert "error" in r.json()


def test_api_sin_token_interino_el_token_de_antes_no_vale(entorno):
    """Sin token interino, presentar el viejo TOKEN_PRUEBA NO autentica (la via no existe)."""
    c = TestClient(_app_sin_token())
    r = c.get("/api/estado", headers={"Authorization": f"Bearer {TOKEN_PRUEBA}"})
    assert r.status_code == 401


def test_api_sin_token_interino_la_sesion_si_funciona(entorno):
    """Sin token interino, una SESION valida (login real) SI da acceso a /api."""
    from keni_consola import auth

    auth.crear_usuario("ana", "clave-de-prueba", "editor")
    c = TestClient(_app_sin_token())
    login = c.post(
        "/api/auth/login",
        json={"usuario": "ana", "password": "clave-de-prueba"},
        headers={"Origin": f"http://{_HOST}"},
    )
    assert login.status_code == 200
    assert c.get("/api/auth/me").status_code == 200
    assert c.get("/api/estado").status_code == 200


def test_sin_token_interino_mutacion_sigue_con_csrf(entorno):
    """Sin token interino, una mutacion con `Origin` ajeno (y sesion) sigue siendo 403."""
    from keni_consola import auth

    auth.crear_usuario("ana", "clave-de-prueba", "editor")
    c = TestClient(_app_sin_token())
    assert c.post(
        "/api/auth/login",
        json={"usuario": "ana", "password": "clave-de-prueba"},
        headers={"Origin": f"http://{_HOST}"},
    ).status_code == 200
    r = c.post(
        "/api/config/esfuerzo",
        json={"esfuerzo": "high"},
        headers={"Origin": "https://sitio-malicioso.example"},
    )
    assert r.status_code == 403


def test_sin_token_interino_no_siembra_cookie_de_token(entorno):
    """Sin token interino, el index del SPA NO siembra la cookie del token (no hay token)."""
    c = TestClient(_app_sin_token())
    r = c.get("/")
    assert r.status_code == 200
    assert seguridad.COOKIE_TOKEN not in r.headers.get("set-cookie", "")
    assert "__KENI_TOKEN__" not in r.text


def test_token_vacio_equivale_a_sin_token(entorno):
    """`crear_app(token="")` se trata como SIN token interino (el middleware normaliza)."""
    c = TestClient(app_modulo.crear_app(token="", bootstrap=False))
    assert c.get("/api/estado").status_code == 401
    # Una cadena vacia presentada como token tampoco autentica (no se compara con "").
    assert c.get("/api/estado", headers={"Authorization": "Bearer "}).status_code == 401
