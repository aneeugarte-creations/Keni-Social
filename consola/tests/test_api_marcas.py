"""Dashboard "Marcas" (`GET /api/marcas`): estado de conexiones por marca × red.

SOLO ADMIN (#153): un editor recibe 403. Se MOCKEAN los probadores de conexión y el
cliente de Postproxy, así el test ejercita la AGREGACIÓN del endpoint (no la red real).
Propiedad clave: el endpoint NUNCA casca y DEGRADA a desconectado si un proveedor falla.
Las métricas de audiencia NO viven aquí (tienen su página en Analíticas).
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth
from keni_consola.api import conexiones
from keni_metricas.fuentes import postproxy as pp_cliente

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
CLAVE = "contraseña-larga-de-prueba-dash"


def _cli() -> TestClient:
    return TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA))


def _cli_como(rol: str) -> TestClient:
    auth.crear_usuario("u", CLAVE, rol)
    c = _cli()
    r = c.post("/api/auth/login", json={"usuario": "u", "password": CLAVE}, headers=_ORIGIN)
    assert r.status_code == 200
    return c


# --------------------------------------------------------------------------- #
# Mocks deterministas                                                         #
# --------------------------------------------------------------------------- #
@pytest.fixture
def mocks(monkeypatch):
    """Mockea el estado de conexiones + el cliente Postproxy para una respuesta fija."""
    monkeypatch.setattr(conexiones, "_postproxy_api_key", lambda cfg: "PP_KEY")
    monkeypatch.setattr(conexiones, "_config_existente", lambda: {})

    monkeypatch.setattr(
        conexiones,
        "estado_postproxy",
        lambda: {
            "configurado": True,
            "pista": "····9999",
            "marcas": [
                {"marca": "claro_sports", "etiqueta": "Claro Sports",
                 "profile_group_id": "g1", "canal": "postproxy"},
                {"marca": "unotv", "etiqueta": "UnoTV",
                 "profile_group_id": None, "canal": "metricool"},
            ],
        },
    )
    monkeypatch.setattr(
        conexiones,
        "estado_marcas_metricool",
        lambda: [{"marca": "claro_sports", "etiqueta": "Claro Sports", "conectado": True}],
    )

    def _perfiles(api_key, grupo):
        if grupo == "g1":
            return True, "ok", [
                {
                    "id": "p1",
                    "name": "@claro",
                    "platform": "instagram",
                    "status": "active",
                    "post_count": 50,
                }
            ]
        return False, "sin grupo", []

    monkeypatch.setattr(pp_cliente, "listar_perfiles", _perfiles)
    return monkeypatch


# --------------------------------------------------------------------------- #
# Permisos                                                                     #
# --------------------------------------------------------------------------- #
def test_editor_403(entorno):
    c = _cli_como("editor")
    r = c.get("/api/marcas")
    assert r.status_code == 403


def test_admin_forma_completa(entorno, mocks):
    c = _cli_como("admin")
    r = c.get("/api/marcas")
    assert r.status_code == 200
    cuerpo = r.json()
    assert "generado_en" in cuerpo
    # El panel es CONTROL DE CONEXIONES: totales de conexión, sin métricas de audiencia.
    assert set(cuerpo["totales"]) == {"marcas", "redes_conectadas", "cuentas"}
    por_marca = {m["marca"]: m for m in cuerpo["marcas"]}
    cs = por_marca["claro_sports"]
    assert cs["metricool"] == {"conectado": True}
    assert cs["postproxy"] == {"conectado": True, "profile_group_id": "g1"}
    # Las métricas NO viven en el panel (tienen su página en Analíticas).
    assert "metricas" not in cs
    # Canal de publicación por marca (selector metricool|postproxy).
    assert cs["canal_publicacion"] == "postproxy"
    assert por_marca["unotv"]["canal_publicacion"] == "metricool"
    # 10 redes (catálogo Postproxy sin google_business).
    assert len(cs["redes"]) == 10
    ig = next(r for r in cs["redes"] if r["plataforma"] == "instagram")
    assert ig["conectado"] is True
    assert ig["estado"] == "active"
    assert ig["perfil_id"] == "p1"
    assert ig["post_count"] == 50
    # Una red sin perfil queda desconectada con todo a null.
    fb = next(r for r in cs["redes"] if r["plataforma"] == "facebook")
    assert fb["conectado"] is False
    assert fb["estado"] is None
    # google_business NO aparece.
    assert all(r["plataforma"] != "google_business" for m in cuerpo["marcas"] for r in m["redes"])


def test_marca_sin_grupo_redes_desconectadas(entorno, mocks):
    c = _cli_como("admin")
    cuerpo = c.get("/api/marcas").json()
    unotv = next(m for m in cuerpo["marcas"] if m["marca"] == "unotv")
    assert unotv["postproxy"]["conectado"] is False
    assert all(r["conectado"] is False for r in unotv["redes"])


def test_postproxy_caido_no_casca(entorno, monkeypatch):
    """Si el cliente Postproxy LANZA, las redes van a desconectadas y el panel NO casca."""
    monkeypatch.setattr(conexiones, "_postproxy_api_key", lambda cfg: "PP_KEY")
    monkeypatch.setattr(conexiones, "_config_existente", lambda: {})
    monkeypatch.setattr(
        conexiones, "estado_postproxy",
        lambda: {"configurado": True, "pista": "····9999", "marcas": [
            {"marca": "claro_sports", "etiqueta": "Claro Sports",
             "profile_group_id": "g1", "canal": "metricool"}]},
    )
    monkeypatch.setattr(conexiones, "estado_marcas_metricool", lambda: [])

    def _boom(*a, **k):
        raise RuntimeError("postproxy caído")

    monkeypatch.setattr(pp_cliente, "listar_perfiles", _boom)

    c = _cli_como("admin")
    r = c.get("/api/marcas")
    assert r.status_code == 200
    cuerpo = r.json()
    cs = next(m for m in cuerpo["marcas"] if m["marca"] == "claro_sports")
    assert all(red["conectado"] is False for red in cs["redes"])
    assert cuerpo["totales"]["redes_conectadas"] == 0


# --------------------------------------------------------------------------- #
# Monitor de NÚMEROS (`GET /api/marcas/numeros`): conteos POSTPROXY por cuenta  #
# --------------------------------------------------------------------------- #
def test_numeros_editor_403(entorno):
    c = _cli_como("editor")
    assert c.get("/api/marcas/numeros").status_code == 403


def test_numeros_desde_postproxy(entorno, monkeypatch):
    """Una fila por cuenta conectada (seguidores/posts/posts-día de Postproxy) + sumatorio."""
    monkeypatch.setattr(conexiones, "_postproxy_api_key", lambda cfg: "PP_KEY")
    monkeypatch.setattr(conexiones, "_config_existente", lambda: {})
    monkeypatch.setattr(
        conexiones, "estado_postproxy",
        lambda: {"configurado": True, "pista": "····9999", "marcas": [
            {"marca": "claro_sports", "etiqueta": "Claro Sports",
             "profile_group_id": "g1", "canal": "postproxy"},
            {"marca": "unotv", "etiqueta": "UnoTV", "profile_group_id": None, "canal": "metricool"}]},
    )

    def _perfiles(api_key, grupo):
        if grupo == "g1":
            return True, "ok", [
                {"id": "p1", "name": "@claro", "platform": "instagram", "status": "active", "post_count": 99},
                {"id": "p2", "name": "Claro FB", "platform": "facebook", "status": "active", "post_count": 30},
            ]
        return False, "sin grupo", []

    def _stats(api_key, pid):
        if pid == "p1":
            return True, "ok", {"seguidores": 700, "posts_totales": 120, "posts_dia": 2.0}
        return True, "ok", {"seguidores": 300, "posts_totales": None, "posts_dia": None}

    monkeypatch.setattr(pp_cliente, "listar_perfiles", _perfiles)
    monkeypatch.setattr(pp_cliente, "stats_perfil", _stats)

    c = _cli_como("admin")
    r = c.get("/api/marcas/numeros")
    assert r.status_code == 200
    cuerpo = r.json()
    cs = next(m for m in cuerpo["marcas"] if m["marca"] == "claro_sports")
    # Una línea por cuenta, en orden fijo (facebook antes que instagram).
    assert [red["plataforma"] for red in cs["redes"]] == ["facebook", "instagram"]
    ig = next(red for red in cs["redes"] if red["plataforma"] == "instagram")
    assert ig["seguidores"] == 700
    assert ig["posts_totales"] == 120
    assert ig["posts_dia"] == 2.0
    fb = next(red for red in cs["redes"] if red["plataforma"] == "facebook")
    assert fb["seguidores"] == 300
    assert fb["posts_totales"] == 30  # respaldo: post_count del perfil (snapshot sin posts)
    assert fb["posts_dia"] is None
    # Sumatorio de la marca.
    assert cs["total"] == {"seguidores": 1000, "posts_totales": 150, "posts_dia": 2.0}
    # Marca sin grupo: sin cuentas.
    unotv = next(m for m in cuerpo["marcas"] if m["marca"] == "unotv")
    assert unotv["redes"] == []
    # Totales globales.
    assert cuerpo["totales"]["seguidores"] == 1000
    assert cuerpo["totales"]["posts_totales"] == 150


def test_numeros_sin_api_key_vacio(entorno, monkeypatch):
    """Sin api_key de Postproxy: ninguna cuenta, todo null, no casca."""
    monkeypatch.setattr(conexiones, "_postproxy_api_key", lambda cfg: "")
    monkeypatch.setattr(conexiones, "_config_existente", lambda: {})
    monkeypatch.setattr(
        conexiones, "estado_postproxy",
        lambda: {"configurado": False, "pista": None, "marcas": [
            {"marca": "claro_sports", "etiqueta": "Claro Sports", "profile_group_id": None}]},
    )

    c = _cli_como("admin")
    r = c.get("/api/marcas/numeros")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["totales"] == {"seguidores": None, "posts_totales": None, "posts_dia": None}
    assert all(m["redes"] == [] for m in cuerpo["marcas"])
