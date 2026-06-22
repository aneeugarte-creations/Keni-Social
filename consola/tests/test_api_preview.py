"""Tests OFFLINE del router de preview (assets del bundle + proxy SOLO-GET). Sin BD ni red.

`almacen_media.leer_crudo` y `httpx.AsyncClient` se parchean; el TestClient de Starlette
monta solo las RUTAS del router.
"""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from keni_consola import almacen_media
from keni_consola.api import preview


@pytest.fixture
def cliente():
    return TestClient(Starlette(routes=preview.RUTAS))


# --------------------------------------------------------------------------- #
# Assets del bundle (con fallback SPA a index.html)                            #
# --------------------------------------------------------------------------- #


def test_sirve_index_en_raiz(cliente, monkeypatch):
    monkeypatch.setattr(
        almacen_media, "leer_crudo",
        lambda clave: b"<html>ok" if clave == "previews/sug-x/index.html" else None,
    )
    r = cliente.get("/api/preview/x/")
    assert r.status_code == 200
    assert r.content == b"<html>ok"
    assert r.headers["content-type"].startswith("text/html")


def test_sirve_asset_anidado_con_content_type(cliente, monkeypatch):
    monkeypatch.setattr(
        almacen_media, "leer_crudo",
        lambda clave: b"//js" if clave == "previews/sug-x/assets/app.js" else None,
    )
    r = cliente.get("/api/preview/x/assets/app.js")
    assert r.status_code == 200
    assert r.content == b"//js"
    assert "javascript" in r.headers["content-type"]


def test_ruta_cliente_cae_a_index(cliente, monkeypatch):
    monkeypatch.setattr(
        almacen_media, "leer_crudo",
        lambda clave: b"<html>spa" if clave == "previews/sug-x/index.html" else None,
    )
    r = cliente.get("/api/preview/x/alguna/ruta/del/cliente")
    assert r.status_code == 200
    assert r.content == b"<html>spa"


def test_404_sin_preview(cliente, monkeypatch):
    monkeypatch.setattr(almacen_media, "leer_crudo", lambda _clave: None)
    assert cliente.get("/api/preview/x/").status_code == 404


# --------------------------------------------------------------------------- #
# Proxy de API: SOLO GET (lectura); las mutaciones caen en 405                 #
# --------------------------------------------------------------------------- #


class _RespFalsa:
    status_code = 200
    content = b'{"ok": true}'
    headers = {"content-type": "application/json"}


class _ClienteFalso:
    capturado: dict = {}

    def __init__(self, *a, **k): ...
    async def __aenter__(self):
        return self
    async def __aexit__(self, *a):
        return False
    async def get(self, url, params=None, headers=None):
        _ClienteFalso.capturado = {"url": url, "params": params, "headers": headers}
        return _RespFalsa()


def test_proxy_get_reenvia_a_la_api_real(cliente, monkeypatch):
    monkeypatch.setattr(preview.httpx, "AsyncClient", _ClienteFalso)
    r = cliente.get(
        "/api/preview/x/api/sugerencias", headers={"cookie": "keni_consola_token=t"}
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert _ClienteFalso.capturado["url"].endswith("/api/sugerencias")
    assert _ClienteFalso.capturado["headers"].get("cookie") == "keni_consola_token=t"


def test_mutaciones_bloqueadas_405(cliente):
    # El preview es de SOLO LECTURA: la ruta de API solo admite GET.
    assert cliente.post("/api/preview/x/api/sugerencias").status_code == 405
    assert cliente.put("/api/preview/x/api/sugerencias/1").status_code == 405
    assert cliente.delete("/api/preview/x/api/sugerencias/1").status_code == 405
