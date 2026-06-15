"""Dashboard "Marcas" (`GET /api/marcas`): vista consolidada por marca.

SOLO ADMIN (#153): un editor recibe 403. Se MOCKEAN los probadores de conexión y el
cliente de Postproxy + la fachada de métricas, así el test ejercita la AGREGACIÓN del
endpoint (no la red ni la fuente real). Propiedad clave: el endpoint NUNCA casca y
DEGRADA a null/desconectado si un proveedor falla; nunca inventa ceros.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth
from keni_consola.api import conexiones, marcas
from keni_metricas import servicio as metricas_servicio
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
    """Mockea conexiones + métricas para una respuesta determinista."""
    # api_key presente (para que el dashboard intente listar perfiles).
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

    def _serie(rango="mes", marca=None):
        return {
            "puntos": [
                {"fecha": "2026-05-01", "total": 1000, "por_red": {"instagram": 1000}},
                {"fecha": "2026-05-31", "total": 1200, "por_red": {"instagram": 1200}},
            ]
        }

    def _reporte(rango="mes", marca=None):
        return {
            "total": {"publicaciones": 30},
            "cuentas": [
                {"resumen": {"periodo": {"desde": "2026-05-01", "hasta": "2026-05-31"}}}
            ],
        }

    monkeypatch.setattr(metricas_servicio, "construir_serie_seguidores", _serie)
    monkeypatch.setattr(metricas_servicio, "construir_reporte", _reporte)
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
    assert set(cuerpo["totales"]) == {
        "marcas", "redes_conectadas", "cuentas", "seguidores", "posts_totales", "posts_dia"
    }
    por_marca = {m["marca"]: m for m in cuerpo["marcas"]}
    cs = por_marca["claro_sports"]
    assert cs["metricool"] == {"conectado": True}
    assert cs["postproxy"] == {"conectado": True, "profile_group_id": "g1"}
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
    # Métricas cableadas: seguidores = último total; posts/día = 30/31 días.
    assert cs["metricas"]["seguidores"] == 1200
    assert cs["metricas"]["posts_totales"] == 30
    assert cs["metricas"]["posts_dia"] == round(30 / 31, 2)
    # google_business NO aparece.
    assert all(r["plataforma"] != "google_business" for m in cuerpo["marcas"] for r in m["redes"])


def test_marca_sin_grupo_redes_desconectadas(entorno, mocks):
    c = _cli_como("admin")
    cuerpo = c.get("/api/marcas").json()
    unotv = next(m for m in cuerpo["marcas"] if m["marca"] == "unotv")
    assert unotv["postproxy"]["conectado"] is False
    assert all(r["conectado"] is False for r in unotv["redes"])


def test_metricas_degradan_a_null_si_fallan(entorno, monkeypatch):
    """Si la fachada de métricas LANZA, las métricas van a null (no a 0) y no casca."""
    monkeypatch.setattr(conexiones, "_postproxy_api_key", lambda cfg: "")
    monkeypatch.setattr(conexiones, "_config_existente", lambda: {})
    monkeypatch.setattr(
        conexiones, "estado_postproxy",
        lambda: {"configurado": False, "pista": None, "marcas": [
            {"marca": "claro_sports", "etiqueta": "Claro Sports", "profile_group_id": None}]},
    )
    monkeypatch.setattr(conexiones, "estado_marcas_metricool", lambda: [])

    def _boom(*a, **k):
        raise RuntimeError("metricool caído")

    monkeypatch.setattr(metricas_servicio, "construir_serie_seguidores", _boom)
    monkeypatch.setattr(metricas_servicio, "construir_reporte", _boom)

    c = _cli_como("admin")
    r = c.get("/api/marcas")
    assert r.status_code == 200
    cuerpo = r.json()
    cs = next(m for m in cuerpo["marcas"] if m["marca"] == "claro_sports")
    assert cs["metricas"] == {"seguidores": None, "posts_totales": None, "posts_dia": None}
    assert cuerpo["totales"]["seguidores"] is None
    assert cuerpo["totales"]["posts_dia"] is None
