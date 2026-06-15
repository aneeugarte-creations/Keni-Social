"""Tests del proxy de CUENTA del back (`/api/sistema/cuenta/*`). Panel ADMIN.

Cubre el cerrojo de rol (solo admin; editor/token -> 403), la DEGRADACION cuando el control
no esta configurado (sin bearer -> {disponible:false}) y el REENVIO al control (parcheando
`_llamar_control`, sin red real ni `claude`). Usa el fixture `entorno` (Postgres) para las
sesiones, como el resto de tests de `/api/sistema`.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth
from keni_consola.api import sistema as api_sistema

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
CLAVE = "clave-de-prueba"


def _cli() -> TestClient:
    return TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA))


def _cli_como(rol: str) -> TestClient:
    auth.crear_usuario("u", CLAVE, rol)
    c = _cli()
    assert c.post(
        "/api/auth/login", json={"usuario": "u", "password": CLAVE}, headers=_ORIGIN
    ).status_code == 200
    return c


def _cli_token() -> TestClient:
    c = _cli()
    c.headers.update({"Authorization": f"Bearer {TOKEN_PRUEBA}"})
    return c


# --- Permisos: solo admin -------------------------------------------------- #


def test_editor_no_ve_cuenta_403(entorno):
    assert _cli_como("editor").get("/api/sistema/cuenta").status_code == 403


def test_token_mantenimiento_no_es_admin_403(entorno):
    c = _cli_token()
    assert c.get("/api/sistema/cuenta").status_code == 403
    assert c.post("/api/sistema/cuenta/logout", headers=_ORIGIN).status_code == 403


# --- Degradacion: control NO configurado ----------------------------------- #


def test_admin_cuenta_no_configurada(entorno, monkeypatch):
    monkeypatch.setattr(api_sistema.cuenta.config, "control_bearer", lambda: None)
    r = _cli_como("admin").get("/api/sistema/cuenta")
    assert r.status_code == 200
    assert r.json() == {"disponible": False}


# --- Reenvio al control (parcheado) ---------------------------------------- #


def test_admin_cuenta_proxia(entorno, monkeypatch):
    monkeypatch.setattr(api_sistema.cuenta.config, "control_bearer", lambda: "tok")
    monkeypatch.setattr(
        api_sistema.cuenta,
        "_llamar_control",
        lambda metodo, ruta, json=None: (200, {"auth": {"logueado": True}, "uso": {"disponible": True}}),
    )
    r = _cli_como("admin").get("/api/sistema/cuenta")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["disponible"] is True
    assert cuerpo["auth"]["logueado"] is True


def test_admin_login_iniciar_proxia(entorno, monkeypatch):
    monkeypatch.setattr(api_sistema.cuenta.config, "control_bearer", lambda: "tok")
    capturado: dict = {}

    def _fake(metodo, ruta, json=None):
        capturado["ruta"] = ruta
        capturado["json"] = json
        return 200, {"sesion": "s1", "url": "https://claude.ai/oauth?x=1"}

    monkeypatch.setattr(api_sistema.cuenta, "_llamar_control", _fake)
    r = _cli_como("admin").post(
        "/api/sistema/cuenta/login/iniciar", json={"console": True}, headers=_ORIGIN
    )
    assert r.status_code == 200
    assert r.json()["url"].startswith("https://")
    assert capturado["ruta"] == "/control/cuenta/login/iniciar"
    assert capturado["json"] == {"console": True}
