"""Tests del listener de CONTROL del daemons (`control.py`). OFFLINE, sin Postgres.

El control es un Starlette autonomo: lo probamos con TestClient sobre `crear_app_control()`,
parcheando `cuenta_claude` (no se ejecuta `claude`) y el bearer. Cubre la BARRERA (bearer) y
el reenvio a las funciones de dominio.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import control


def _cli(monkeypatch, *, bearer: str = "tok") -> TestClient:
    # El bearer efectivo (auto-persistido) se parchea a un valor fijo para los tests.
    monkeypatch.setattr(control.cuenta_claude, "bearer_efectivo", lambda: bearer)
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
    monkeypatch.setattr(control.cuenta_claude, "estado", lambda cuenta="a": {"logueado": True, "metodo": "claudeai"})
    monkeypatch.setattr(control.cuenta_claude, "uso", lambda cuenta="a": {"disponible": True, "medidores": []})
    c = _cli(monkeypatch)
    r = c.get("/control/cuenta/estado", headers=_auth())
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["auth"]["metodo"] == "claudeai"
    assert cuerpo["uso"]["disponible"] is True


def test_estado_propaga_cuenta_b(monkeypatch):
    # `?cuenta=b` se reenvia a estado()/uso() como selector; sin query, default 'a'.
    visto: dict = {}
    monkeypatch.setattr(control.cuenta_claude, "estado", lambda cuenta="a": visto.setdefault("estado", cuenta) or {})
    monkeypatch.setattr(control.cuenta_claude, "uso", lambda cuenta="a": visto.setdefault("uso", cuenta) or {})
    c = _cli(monkeypatch)
    assert c.get("/control/cuenta/estado?cuenta=b", headers=_auth()).status_code == 200
    assert visto == {"estado": "b", "uso": "b"}


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


def test_login_iniciar_propaga_cuenta_b(monkeypatch):
    # El selector `?cuenta=b` llega a iniciar_login para apuntar al config-dir de B.
    visto: dict = {}

    def _fake(**kw):
        visto.update(kw)
        return {"sesion": "s1", "url": "https://claude.ai/oauth?x=1"}

    monkeypatch.setattr(control.cuenta_claude, "iniciar_login", _fake)
    c = _cli(monkeypatch)
    r = c.post("/control/cuenta/login/iniciar?cuenta=b", headers=_auth(), json={"console": True})
    assert r.status_code == 200
    assert visto["cuenta"] == "b"
    assert visto["console"] is True


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
    monkeypatch.setattr(control.cuenta_claude, "logout", lambda cuenta="a": {"ok": True, "mensaje": "cerrada"})
    c = _cli(monkeypatch)
    r = c.post("/control/cuenta/logout", headers=_auth())
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_logout_propaga_cuenta_b(monkeypatch):
    visto: dict = {}
    monkeypatch.setattr(control.cuenta_claude, "logout", lambda cuenta="a": visto.setdefault("c", cuenta) or {"ok": True})
    c = _cli(monkeypatch)
    assert c.post("/control/cuenta/logout?cuenta=b", headers=_auth()).status_code == 200
    assert visto["c"] == "b"
