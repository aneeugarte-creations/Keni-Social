"""Endpoints de conexión a Postproxy (`/api/conexiones/postproxy*`).

Mismas reglas que Metricool: SOLO ADMIN (un editor recibe 403), la api_key es un
SECRETO GLOBAL que NUNCA se devuelve (solo pista `····last4`), y los puntos de red van
mockeados (los tests NUNCA tocan la red ni el disco real: `entorno` aísla el config en
tmp). La sesión admin se obtiene por login (cookie), igual que en los demás tests.
"""

from __future__ import annotations

import os
import tomllib

import pytest
from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth
from keni_consola.api import conexiones

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
CLAVE = "contraseña-larga-de-prueba-pp"
_API_KEY = "pp-SECRETO-9999"


def _cli() -> TestClient:
    return TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA))


def _cli_como(rol: str) -> TestClient:
    auth.crear_usuario("u", CLAVE, rol)
    c = _cli()
    r = c.post("/api/auth/login", json={"usuario": "u", "password": CLAVE}, headers=_ORIGIN)
    assert r.status_code == 200
    return c


def _admin() -> TestClient:
    return _cli_como("admin")


# --------------------------------------------------------------------------- #
# Permisos: editor -> 403 en todo                                             #
# --------------------------------------------------------------------------- #
_ENDPOINTS = [
    ("GET", "/api/conexiones/postproxy", None),
    ("PUT", "/api/conexiones/postproxy", {"api_key": _API_KEY}),
    ("DELETE", "/api/conexiones/postproxy", None),
    ("POST", "/api/conexiones/postproxy/probar", None),
    ("PUT", "/api/conexiones/postproxy/claro_sports/grupo", {"profile_group_id": "1"}),
    ("PUT", "/api/conexiones/postproxy/claro_sports/canal", {"canal": "postproxy"}),
    ("POST", "/api/conexiones/postproxy/claro_sports/conectar",
     {"platform": "instagram", "redirect_url": "https://r"}),
    ("DELETE", "/api/conexiones/postproxy/perfil/p1", None),
]


def test_editor_403_en_todos_los_endpoints(entorno):
    c = _cli_como("editor")
    for metodo, ruta, cuerpo in _ENDPOINTS:
        headers = {} if metodo == "GET" else dict(_ORIGIN)
        r = c.request(metodo, ruta, json=cuerpo, headers=headers)
        assert r.status_code == 403, f"{metodo} {ruta} debería ser 403 para editor"
        assert _API_KEY not in r.text


# --------------------------------------------------------------------------- #
# Estado / guardar / borrar (la api_key nunca sale)                           #
# --------------------------------------------------------------------------- #
def test_estado_inicial_sin_configurar(entorno):
    c = _admin()
    cuerpo = c.get("/api/conexiones/postproxy").json()
    assert cuerpo["configurado"] is False
    assert cuerpo["pista"] is None
    # Una entrada por marca del catálogo, todas sin grupo y canal default "metricool".
    assert any(m["marca"] == "claro_sports" for m in cuerpo["marcas"])
    assert all(m["profile_group_id"] is None for m in cuerpo["marcas"])
    assert all(m["canal"] == "metricool" for m in cuerpo["marcas"])


def test_guardar_api_key_y_pista(entorno):
    c = _admin()
    r = c.put("/api/conexiones/postproxy", json={"api_key": _API_KEY}, headers=_ORIGIN)
    assert r.status_code == 200
    assert r.json()["configurado"] is True
    assert _API_KEY not in r.text
    estado = c.get("/api/conexiones/postproxy").json()
    assert estado["configurado"] is True
    assert estado["pista"] == "····9999"
    assert _API_KEY not in c.get("/api/conexiones/postproxy").text
    # Persiste en el config de métricas (en disco, pero el secreto no se eco por la API).
    datos = tomllib.loads(open(os.environ["KENI_METRICAS_CONFIG"], encoding="utf-8").read())
    assert datos["postproxy"]["api_key"] == _API_KEY


def test_guardar_api_key_vacia_400(entorno):
    c = _admin()
    r = c.put("/api/conexiones/postproxy", json={"api_key": "  "}, headers=_ORIGIN)
    assert r.status_code == 400


def test_borrar_api_key(entorno):
    c = _admin()
    c.put("/api/conexiones/postproxy", json={"api_key": _API_KEY}, headers=_ORIGIN)
    r = c.delete("/api/conexiones/postproxy", headers=_ORIGIN)
    assert r.status_code == 200
    assert c.get("/api/conexiones/postproxy").json()["configurado"] is False


# --------------------------------------------------------------------------- #
# Probar: usa la api_key GUARDADA, con el probador mockeado                    #
# --------------------------------------------------------------------------- #
def test_probar_sin_api_key(entorno):
    c = _admin()
    r = c.post("/api/conexiones/postproxy/probar", headers=_ORIGIN)
    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_probar_con_api_key_mockeado(entorno, monkeypatch):
    c = _admin()
    c.put("/api/conexiones/postproxy", json={"api_key": _API_KEY}, headers=_ORIGIN)
    vistos = {}

    def _fake(api_key):
        vistos["api_key"] = api_key
        return True, "La API key de Postproxy funciona."

    monkeypatch.setattr(conexiones, "_PROBADOR_PP", _fake)
    r = c.post("/api/conexiones/postproxy/probar", headers=_ORIGIN)
    assert r.json() == {"ok": True, "mensaje": "La API key de Postproxy funciona."}
    assert vistos["api_key"] == _API_KEY  # usó la guardada


# --------------------------------------------------------------------------- #
# Grupo por marca: guardar uno dado, o CREARLO en Postproxy (mockeado)        #
# --------------------------------------------------------------------------- #
def test_grupo_guarda_id_dado(entorno):
    c = _admin()
    r = c.put(
        "/api/conexiones/postproxy/claro_sports/grupo",
        json={"profile_group_id": "42"},
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    assert r.json()["profile_group_id"] == "42"
    estado = {m["marca"]: m for m in c.get("/api/conexiones/postproxy").json()["marcas"]}
    assert estado["claro_sports"]["profile_group_id"] == "42"


def test_grupo_sin_id_lo_crea(entorno, monkeypatch):
    c = _admin()
    c.put("/api/conexiones/postproxy", json={"api_key": _API_KEY}, headers=_ORIGIN)
    creados = {}

    def _fake(api_key, nombre):
        creados["nombre"] = nombre
        return True, "Grupo creado.", {"id": "g100", "name": nombre, "profiles_count": 0}

    monkeypatch.setattr(conexiones, "_PP_CREAR_GRUPO", _fake)
    r = c.put("/api/conexiones/postproxy/claro_sports/grupo", json={}, headers=_ORIGIN)
    assert r.status_code == 200
    assert r.json()["profile_group_id"] == "g100"
    assert creados["nombre"] == "Claro Sports"  # etiqueta de la marca


def test_grupo_marca_desconocida_400(entorno):
    c = _admin()
    r = c.put(
        "/api/conexiones/postproxy/no_existe/grupo",
        json={"profile_group_id": "1"},
        headers=_ORIGIN,
    )
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Conectar una red (initialize_connection mockeado)                           #
# --------------------------------------------------------------------------- #
def test_conectar_plataforma_invalida_400(entorno):
    c = _admin()
    c.put("/api/conexiones/postproxy", json={"api_key": _API_KEY}, headers=_ORIGIN)
    r = c.post(
        "/api/conexiones/postproxy/claro_sports/conectar",
        json={"platform": "myspace", "redirect_url": "https://r"},
        headers=_ORIGIN,
    )
    assert r.status_code == 400


def test_conectar_crea_grupo_si_falta_y_devuelve_url(entorno, monkeypatch):
    c = _admin()
    c.put("/api/conexiones/postproxy", json={"api_key": _API_KEY}, headers=_ORIGIN)

    def _crear(api_key, nombre):
        return True, "Grupo creado.", {"id": "g7", "name": nombre, "profiles_count": 0}

    iniciados = {}

    def _iniciar(api_key, group_id, platform, redirect_url):
        iniciados.update(group_id=group_id, platform=platform)
        return True, "Conexión iniciada.", "https://oauth/x"

    monkeypatch.setattr(conexiones, "_PP_CREAR_GRUPO", _crear)
    monkeypatch.setattr(conexiones, "_PP_INICIAR_CONEXION", _iniciar)
    r = c.post(
        "/api/conexiones/postproxy/claro_sports/conectar",
        json={"platform": "instagram", "redirect_url": "https://r"},
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    assert r.json() == {"url": "https://oauth/x"}
    assert iniciados == {"group_id": "g7", "platform": "instagram"}


def test_conectar_sin_api_key_400(entorno):
    c = _admin()
    r = c.post(
        "/api/conexiones/postproxy/claro_sports/conectar",
        json={"platform": "instagram", "redirect_url": "https://r"},
        headers=_ORIGIN,
    )
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Desconectar un perfil (mockeado)                                            #
# --------------------------------------------------------------------------- #
def test_desconectar_perfil(entorno, monkeypatch):
    c = _admin()
    c.put("/api/conexiones/postproxy", json={"api_key": _API_KEY}, headers=_ORIGIN)

    def _fake(api_key, perfil_id):
        assert perfil_id == "p1"
        return True, "Perfil desconectado."

    monkeypatch.setattr(conexiones, "_PP_DESCONECTAR", _fake)
    r = c.request("DELETE", "/api/conexiones/postproxy/perfil/p1", headers=_ORIGIN)
    assert r.status_code == 200
    assert r.json()["mensaje"] == "Perfil desconectado."


# --------------------------------------------------------------------------- #
# Canal de publicación por marca (selector metricool | postproxy)             #
# --------------------------------------------------------------------------- #
def test_canal_guarda_postproxy_y_se_refleja_en_estado(entorno):
    c = _admin()
    r = c.put(
        "/api/conexiones/postproxy/claro_sports/canal",
        json={"canal": "postproxy"},
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    assert r.json()["canal"] == "postproxy"
    estado = {m["marca"]: m for m in c.get("/api/conexiones/postproxy").json()["marcas"]}
    assert estado["claro_sports"]["canal"] == "postproxy"
    # Las demás marcas siguen en el default "metricool".
    assert estado["unotv"]["canal"] == "metricool"


def test_canal_volver_a_metricool(entorno):
    c = _admin()
    c.put("/api/conexiones/postproxy/claro_sports/canal", json={"canal": "postproxy"}, headers=_ORIGIN)
    r = c.put(
        "/api/conexiones/postproxy/claro_sports/canal", json={"canal": "metricool"}, headers=_ORIGIN
    )
    assert r.status_code == 200
    estado = {m["marca"]: m for m in c.get("/api/conexiones/postproxy").json()["marcas"]}
    assert estado["claro_sports"]["canal"] == "metricool"


def test_canal_invalido_400(entorno):
    c = _admin()
    r = c.put(
        "/api/conexiones/postproxy/claro_sports/canal", json={"canal": "buffer"}, headers=_ORIGIN
    )
    assert r.status_code == 400


def test_canal_marca_desconocida_400(entorno):
    c = _admin()
    r = c.put(
        "/api/conexiones/postproxy/no_existe/canal", json={"canal": "postproxy"}, headers=_ORIGIN
    )
    assert r.status_code == 400


def test_canal_no_pisa_el_grupo(entorno):
    """Guardar el canal NO borra el profile_group_id ya guardado (campos ortogonales)."""
    c = _admin()
    c.put(
        "/api/conexiones/postproxy/claro_sports/grupo",
        json={"profile_group_id": "42"},
        headers=_ORIGIN,
    )
    c.put("/api/conexiones/postproxy/claro_sports/canal", json={"canal": "postproxy"}, headers=_ORIGIN)
    estado = {m["marca"]: m for m in c.get("/api/conexiones/postproxy").json()["marcas"]}
    assert estado["claro_sports"]["profile_group_id"] == "42"
    assert estado["claro_sports"]["canal"] == "postproxy"
