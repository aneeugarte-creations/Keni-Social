"""API /api/stock: claves de bancos de fotos por marca + fuentes habilitadas por marca.

SOLO ADMIN (secretos compartidos), mismo criterio que /api/conexiones. `entorno` aisla
`secretos.toml` y el store de ajustes en tmp; la prueba de conexión parchea el descargador
de `api.rss` (OFFLINE, sin red). La sesión se obtiene por login (cookie), como en test_auth.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth, stock_fotos

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
CLAVE = "clave-de-prueba"
_KEY = "pexels-PISTA-7777"
_MARCA = "unotv"


def _cli() -> TestClient:
    return TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA))


def _cli_como(rol: str) -> TestClient:
    auth.crear_usuario("u", CLAVE, rol)
    c = _cli()
    assert c.post(
        "/api/auth/login", json={"usuario": "u", "password": CLAVE}, headers=_ORIGIN
    ).status_code == 200
    return c


def test_editor_no_accede_a_stock_403(entorno):
    c = _cli_como("editor")
    assert c.get("/api/stock/fuentes").status_code == 403
    r = c.put(
        f"/api/stock/clave/{_MARCA}",
        json={"proveedor": "pexels", "api_key": _KEY},
        headers=_ORIGIN,
    )
    assert r.status_code == 403
    assert _KEY not in r.text


def test_admin_guarda_clave_y_estado_no_filtra(entorno):
    c = _cli_como("admin")
    r = c.put(
        f"/api/stock/clave/{_MARCA}",
        json={"proveedor": "pexels", "api_key": _KEY},
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    assert _KEY not in r.text
    estado = c.get(f"/api/stock/fuentes?marca={_MARCA}").json()
    pexels = next(f for f in estado["fuentes"] if f["proveedor"] == "pexels")
    assert pexels["configurado"] is True
    assert pexels["disponible"] is True
    assert pexels["pista"] == "····" + _KEY[-4:]
    assert _KEY not in c.get(f"/api/stock/fuentes?marca={_MARCA}").text


def test_admin_borra_clave(entorno):
    c = _cli_como("admin")
    c.put(
        f"/api/stock/clave/{_MARCA}",
        json={"proveedor": "pexels", "api_key": _KEY},
        headers=_ORIGIN,
    )
    assert c.request("DELETE", f"/api/stock/clave/{_MARCA}/pexels", headers=_ORIGIN).status_code == 200
    estado = c.get(f"/api/stock/fuentes?marca={_MARCA}").json()
    pexels = next(f for f in estado["fuentes"] if f["proveedor"] == "pexels")
    assert pexels["configurado"] is False
    assert pexels["disponible"] is False


def test_admin_guarda_fuentes_activas(entorno):
    c = _cli_como("admin")
    r = c.put(
        f"/api/stock/fuentes/{_MARCA}",
        json={"activas": ["openverse", "wikimedia"]},
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    fuentes = {f["proveedor"]: f for f in r.json()["fuentes"]}
    assert fuentes["openverse"]["activa"] is True
    assert fuentes["nasa"]["activa"] is False  # no incluida -> deshabilitada


def test_fuentes_proveedor_invalido_ignora(entorno):
    c = _cli_como("admin")
    r = c.put(
        f"/api/stock/fuentes/{_MARCA}",
        json={"activas": ["openverse", "inventado"]},
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    fuentes = {f["proveedor"]: f for f in r.json()["fuentes"]}
    assert fuentes["openverse"]["activa"] is True
    assert "inventado" not in fuentes


def test_marca_desconocida_400(entorno):
    c = _cli_como("admin")
    assert c.get("/api/stock/fuentes?marca=no-existe").status_code == 400


def test_probar_clave_offline(entorno, monkeypatch):
    monkeypatch.setattr(stock_fotos.rss, "validar_url", lambda url: (url, None))
    monkeypatch.setattr(
        stock_fotos.rss,
        "_DESCARGADOR",
        lambda url: '{"photos": [{"src": {"original": "https://p/o.jpg"}, "photographer": "A"}]}',
    )
    c = _cli_como("admin")
    c.put(
        f"/api/stock/clave/{_MARCA}",
        json={"proveedor": "pexels", "api_key": _KEY},
        headers=_ORIGIN,
    )
    r = c.post(f"/api/stock/probar/{_MARCA}", json={"proveedor": "pexels"}, headers=_ORIGIN)
    assert r.json()["ok"] is True


def test_probar_sin_clave(entorno):
    c = _cli_como("admin")
    r = c.post(f"/api/stock/probar/{_MARCA}", json={"proveedor": "pexels"}, headers=_ORIGIN)
    assert r.json()["ok"] is False
