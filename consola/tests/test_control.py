"""Tests del listener de CONTROL del daemons (`control.py`). OFFLINE, sin Postgres.

El control es un Starlette autonomo: lo probamos con TestClient sobre `crear_app_control()`,
parcheando `cuenta_claude` (no se ejecuta `claude`) y el bearer. Cubre la BARRERA (bearer) y
el reenvio a las funciones de dominio.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import control


def _cli(monkeypatch, *, bearer: str | None = "tok") -> TestClient:
    monkeypatch.setattr(control.config, "control_bearer", lambda: bearer)
    return TestClient(control.crear_app_control())


def _auth(bearer: str = "tok") -> dict:
    return {"Authorization": f"Bearer {bearer}"}


def test_healthz_sin_bearer():
    c = TestClient(control.crear_app_control())
    assert c.get("/control/healthz").json() == {"ok": True}


def test_estado_sin_bearer_401(monkeypatch):
    c = _cli(monkeypatch)
    assert c.get("/control/cuenta/estado").status_code == 401


def test_estado_bearer_malo_401(monkeypatch):
    c = _cli(monkeypatch)
    assert c.get("/control/cuenta/estado", headers=_auth("otro")).status_code == 401


def test_estado_ok(monkeypatch):
    monkeypatch.setattr(control.cuenta_claude, "estado", lambda: {"logueado": True, "metodo": "claudeai"})
    monkeypatch.setattr(control.cuenta_claude, "uso", lambda: {"disponible": True, "medidores": []})
    c = _cli(monkeypatch)
    r = c.get("/control/cuenta/estado", headers=_auth())
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["auth"]["metodo"] == "claudeai"
    assert cuerpo["uso"]["disponible"] is True


def test_login_iniciar_devuelve_url(monkeypatch):
    monkeypatch.setattr(
        control.cuenta_claude,
        "iniciar_login",
        lambda **kw: {"sesion": "s1", "url": "https://claude.ai/oauth?x=1"},
    )
    c = _cli(monkeypatch)
    r = c.post("/control/cuenta/login/iniciar", headers=_auth(), json={})
    assert r.status_code == 200
    assert r.json()["url"].startswith("https://")


def test_login_iniciar_sin_url_502(monkeypatch):
    monkeypatch.setattr(control.cuenta_claude, "iniciar_login", lambda **kw: {"error": "sin url"})
    c = _cli(monkeypatch)
    r = c.post("/control/cuenta/login/iniciar", headers=_auth(), json={})
    assert r.status_code == 502


def test_login_codigo_valida_campos(monkeypatch):
    c = _cli(monkeypatch)
    # Falta el codigo -> 400 sin tocar dominio.
    r = c.post("/control/cuenta/login/codigo", headers=_auth(), json={"sesion": "s1"})
    assert r.status_code == 400


def test_login_codigo_ok(monkeypatch):
    monkeypatch.setattr(control.cuenta_claude, "enviar_codigo", lambda sid, cod: {"ok": True, "mensaje": "ok"})
    c = _cli(monkeypatch)
    r = c.post("/control/cuenta/login/codigo", headers=_auth(), json={"sesion": "s1", "codigo": "abc"})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_logout_ok(monkeypatch):
    monkeypatch.setattr(control.cuenta_claude, "logout", lambda: {"ok": True, "mensaje": "cerrada"})
    c = _cli(monkeypatch)
    r = c.post("/control/cuenta/logout", headers=_auth())
    assert r.status_code == 200
    assert r.json()["ok"] is True
