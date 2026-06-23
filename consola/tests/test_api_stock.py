"""API /api/stock: claves GLOBALES de bancos de fotos + fuentes habilitadas por marca.

SOLO ADMIN (secretos compartidos), mismo criterio que /api/conexiones. `entorno` aisla
`secretos.toml` y el store de ajustes en tmp; la prueba de conexión parchea el descargador
de `api.rss` (OFFLINE, sin red). La sesión se obtiene por login (cookie), como en test_auth.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import agencias, app as app_modulo
from keni_consola import auth, secretos, stock_fotos

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
    assert c.get("/api/stock/proveedores").status_code == 403
    r = c.put(
        "/api/stock/clave",
        json={"proveedor": "pexels", "api_key": _KEY},
        headers=_ORIGIN,
    )
    assert r.status_code == 403
    assert _KEY not in r.text


def test_admin_guarda_clave_global_y_no_filtra(entorno):
    c = _cli_como("admin")
    r = c.put(
        "/api/stock/clave",
        json={"proveedor": "pexels", "api_key": _KEY},
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    assert _KEY not in r.text
    estado = c.get("/api/stock/proveedores").json()
    pexels = next(p for p in estado["proveedores"] if p["proveedor"] == "pexels")
    assert pexels["configurado"] is True
    assert pexels["disponible"] is True
    assert pexels["pista"] == "····" + _KEY[-4:]
    assert _KEY not in c.get("/api/stock/proveedores").text


def test_clave_global_vale_para_cualquier_marca(entorno):
    c = _cli_como("admin")
    c.put("/api/stock/clave", json={"proveedor": "pexels", "api_key": _KEY}, headers=_ORIGIN)
    # La misma clave global hace a Pexels disponible en la vista por marca, sin reconfigurar.
    fuentes = c.get(f"/api/stock/fuentes?marca={_MARCA}").json()["fuentes"]
    pexels = next(f for f in fuentes if f["proveedor"] == "pexels")
    assert pexels["disponible"] is True


def test_admin_borra_clave_global(entorno):
    c = _cli_como("admin")
    c.put("/api/stock/clave", json={"proveedor": "pexels", "api_key": _KEY}, headers=_ORIGIN)
    assert c.request("DELETE", "/api/stock/clave/pexels", headers=_ORIGIN).status_code == 200
    estado = c.get("/api/stock/proveedores").json()
    pexels = next(p for p in estado["proveedores"] if p["proveedor"] == "pexels")
    assert pexels["configurado"] is False
    assert pexels["disponible"] is False


def test_admin_guarda_fuentes_activas_por_marca(entorno):
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


def test_fuentes_marca_desconocida_400(entorno):
    c = _cli_como("admin")
    assert c.get("/api/stock/fuentes?marca=no-existe").status_code == 400
    assert c.get("/api/stock/fuentes").status_code == 400  # marca obligatoria


def test_probar_clave_global_offline(entorno, monkeypatch):
    monkeypatch.setattr(stock_fotos.rss, "validar_url", lambda url: (url, None))
    monkeypatch.setattr(
        stock_fotos.rss,
        "_DESCARGADOR",
        lambda url: '{"photos": [{"src": {"original": "https://p/o.jpg"}, "photographer": "A"}]}',
    )
    c = _cli_como("admin")
    c.put("/api/stock/clave", json={"proveedor": "pexels", "api_key": _KEY}, headers=_ORIGIN)
    r = c.post("/api/stock/probar", json={"proveedor": "pexels"}, headers=_ORIGIN)
    assert r.json()["ok"] is True


def test_probar_sin_clave(entorno):
    c = _cli_como("admin")
    r = c.post("/api/stock/probar", json={"proveedor": "pexels"}, headers=_ORIGIN)
    assert r.json()["ok"] is False


# --------------------------------------------------------------------------- #
# Credenciales de AGENCIAS (AFP / Reuters)                                    #
# --------------------------------------------------------------------------- #

_CRED_AFP = "prueba-afp-1111"


def test_editor_no_accede_a_agencias_403(entorno):
    c = _cli_como("editor")
    assert c.get("/api/stock/agencias").status_code == 403
    r = c.put(
        "/api/stock/agencias/afp",
        json={"valores": {"client_secret": _CRED_AFP}},
        headers=_ORIGIN,
    )
    assert r.status_code == 403
    assert _CRED_AFP not in r.text


def test_admin_lista_agencias_con_campos(entorno):
    c = _cli_como("admin")
    cuerpo = c.get("/api/stock/agencias").json()
    ids = {a["agencia"] for a in cuerpo["agencias"]}
    assert ids == {"afp", "reuters"}
    afp = next(a for a in cuerpo["agencias"] if a["agencia"] == "afp")
    assert afp["nombre"] == "AFP"
    assert afp["configurado"] is False
    claves = {cmp["clave"] for cmp in afp["campos"]}
    assert claves == {"client_id", "client_secret", "base_url"}
    # base_url NO es secreto: devuelve el valor efectivo (def)
    base = next(cmp for cmp in afp["campos"] if cmp["clave"] == "base_url")
    assert base["secreto"] is False
    assert base["valor"]
    # los secretos NO traen valor, solo presencia + pista
    cid = next(cmp for cmp in afp["campos"] if cmp["clave"] == "client_id")
    assert cid["secreto"] is True
    assert "valor" not in cid
    assert cid["configurado"] is False


def test_admin_guarda_credenciales_afp_y_no_filtra(entorno):
    c = _cli_como("admin")
    r = c.put(
        "/api/stock/agencias/afp",
        json={"valores": {"client_id": "id-xyz", "client_secret": _CRED_AFP}},
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    assert _CRED_AFP not in r.text
    cuerpo = r.json()
    assert cuerpo["configurado"] is True
    assert cuerpo["disponible"] is True
    secreto = next(cmp for cmp in cuerpo["campos"] if cmp["clave"] == "client_secret")
    assert secreto["configurado"] is True
    assert secreto["pista"] == "····" + _CRED_AFP[-4:]
    # el GET tampoco filtra el secreto
    assert _CRED_AFP not in c.get("/api/stock/agencias").text


def test_put_secret_vacio_no_borra(entorno):
    c = _cli_como("admin")
    c.put(
        "/api/stock/agencias/afp",
        json={"valores": {"client_id": "id-xyz", "client_secret": _CRED_AFP}},
        headers=_ORIGIN,
    )
    # reguardar con el secret vacío NO debe borrar el ya guardado
    c.put(
        "/api/stock/agencias/afp",
        json={"valores": {"client_secret": "", "base_url": "https://nuevo.afp.example"}},
        headers=_ORIGIN,
    )
    assert secretos.obtener_credencial_agencia("afp", "client_secret") == _CRED_AFP
    assert secretos.obtener_credencial_agencia("afp", "base_url") == "https://nuevo.afp.example"


def test_put_campo_no_valido_400(entorno):
    c = _cli_como("admin")
    r = c.put(
        "/api/stock/agencias/afp",
        json={"valores": {"api_key": "no-aplica-a-afp"}},
        headers=_ORIGIN,
    )
    assert r.status_code == 400


def test_put_agencia_desconocida_400(entorno):
    c = _cli_como("admin")
    r = c.put(
        "/api/stock/agencias/inventada",
        json={"valores": {"x": "y"}},
        headers=_ORIGIN,
    )
    assert r.status_code == 400


def test_delete_limpia_credenciales(entorno):
    c = _cli_como("admin")
    c.put(
        "/api/stock/agencias/reuters",
        json={"valores": {"api_key": "key-reuters"}},
        headers=_ORIGIN,
    )
    r = c.request("DELETE", "/api/stock/agencias/reuters", headers=_ORIGIN)
    assert r.status_code == 200
    assert r.json()["configurado"] is False
    assert secretos.obtener_credencial_agencia("reuters", "api_key") is None


def test_probar_afp_ok_con_token_mock(entorno, monkeypatch):
    monkeypatch.setattr(agencias, "obtener_token_afp", lambda: "tok-123")
    c = _cli_como("admin")
    c.put(
        "/api/stock/agencias/afp",
        json={"valores": {"client_id": "id-xyz", "client_secret": _CRED_AFP}},
        headers=_ORIGIN,
    )
    r = c.post("/api/stock/agencias/afp/probar", headers=_ORIGIN)
    assert r.json()["ok"] is True


def test_probar_afp_sin_credenciales(entorno):
    c = _cli_como("admin")
    r = c.post("/api/stock/agencias/afp/probar", headers=_ORIGIN)
    cuerpo = r.json()
    assert cuerpo["ok"] is False


def test_probar_reuters_presencia(entorno):
    c = _cli_como("admin")
    # sin credenciales: ok falso
    assert c.post("/api/stock/agencias/reuters/probar", headers=_ORIGIN).json()["ok"] is False
    c.put(
        "/api/stock/agencias/reuters",
        json={"valores": {"api_key": "key-reuters"}},
        headers=_ORIGIN,
    )
    # con credenciales: ok verdadero (presencia; sin validación en vivo)
    assert c.post("/api/stock/agencias/reuters/probar", headers=_ORIGIN).json()["ok"] is True
