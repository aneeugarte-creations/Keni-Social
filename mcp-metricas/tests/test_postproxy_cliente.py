"""Tests del cliente HTTP de Postproxy (`fuentes.postproxy`).

SIN red real: se parchea el seam único `_HACER_PETICION` (el ÚNICO punto que toca la red)
para devolver respuestas deterministas. Cubren el parseo defensivo, la traducción de
errores a mensajes en español y que la api_key vacía se rechaza antes de tocar la red.
"""

from __future__ import annotations

import httpx
import pytest

from keni_metricas.fuentes import postproxy as pp


@pytest.fixture
def fake_red(monkeypatch):
    """Reemplaza el seam de red por una función configurable que registra la llamada."""
    llamadas: list[dict] = []
    plan: dict = {"resultado": (200, [])}

    def _fake(metodo, ruta, api_key, *, params=None, json=None):
        llamadas.append(
            {"metodo": metodo, "ruta": ruta, "api_key": api_key, "params": params, "json": json}
        )
        res = plan["resultado"]
        if isinstance(res, Exception):
            raise res
        return res

    monkeypatch.setattr(pp, "_HACER_PETICION", _fake)
    return {"llamadas": llamadas, "plan": plan}


def test_api_key_vacia_no_toca_red(fake_red):
    ok, msg, datos = pp.listar_grupos("")
    assert ok is False
    assert "API key" in msg
    assert fake_red["llamadas"] == []  # nunca se llamó al seam de red


def test_listar_grupos_parsea_defensivo(fake_red):
    fake_red["plan"]["resultado"] = (
        200,
        [{"id": 5, "name": "Claro", "profiles_count": 3}, {"sin_id": True}],
    )
    ok, _msg, grupos = pp.listar_grupos("K")
    assert ok is True
    assert grupos == [{"id": "5", "name": "Claro", "profiles_count": 3}]


def test_listar_perfiles_parsea_y_normaliza(fake_red):
    fake_red["plan"]["resultado"] = (
        200,
        [
            {
                "id": "p1",
                "name": "@unotv",
                "platform": "instagram",
                "status": "active",
                "post_count": 12,
                "avatar_url": "https://a/x.png",
                "expires_at": "2026-12-01",
            }
        ],
    )
    ok, _msg, perfiles = pp.listar_perfiles("K", "grupo-1")
    assert ok is True
    p = perfiles[0]
    assert p["id"] == "p1"
    assert p["platform"] == "instagram"
    assert p["status"] == "active"
    assert p["post_count"] == 12
    # el seam recibió el query param correcto
    assert fake_red["llamadas"][0]["params"] == {"profile_group_id": "grupo-1"}


def test_crear_grupo_envia_body_correcto(fake_red):
    fake_red["plan"]["resultado"] = (201, {"id": "g9", "name": "Nuevo", "profiles_count": 0})
    ok, _msg, grupo = pp.crear_grupo("K", "Nuevo")
    assert ok is True
    assert grupo["id"] == "g9"
    assert fake_red["llamadas"][0]["json"] == {"profile_group": {"name": "Nuevo"}}


def test_initialize_connection_rechaza_plataforma_invalida(fake_red):
    ok, msg, url = pp.initialize_connection("K", "g1", "myspace", "https://r")
    assert ok is False
    assert "Plataforma" in msg
    assert url is None
    assert fake_red["llamadas"] == []  # validó antes de tocar la red


def test_initialize_connection_devuelve_url(fake_red):
    fake_red["plan"]["resultado"] = (200, {"url": "https://oauth/x", "success": True})
    ok, _msg, url = pp.initialize_connection("K", "g1", "instagram", "https://r")
    assert ok is True
    assert url == "https://oauth/x"


def test_error_401_traduce_a_espanol(fake_red):
    fake_red["plan"]["resultado"] = (401, None)
    ok, msg, _ = pp.listar_grupos("K")
    assert ok is False
    assert "rechazó la API key" in msg


def test_fallo_de_red_no_lanza(fake_red):
    fake_red["plan"]["resultado"] = httpx.ConnectError("boom")
    ok, msg, _ = pp.listar_grupos("K")
    assert ok is False
    assert "No se pudo contactar" in msg


def test_desconectar_perfil(fake_red):
    fake_red["plan"]["resultado"] = (204, None)
    ok, msg = pp.desconectar_perfil("K", "p1")
    assert ok is True
    assert fake_red["llamadas"][0]["ruta"] == "/profiles/p1"
    assert fake_red["llamadas"][0]["metodo"] == "DELETE"


def test_probar_ok(fake_red):
    fake_red["plan"]["resultado"] = (200, [])
    ok, msg = pp.probar("K")
    assert ok is True
    assert "funciona" in msg
