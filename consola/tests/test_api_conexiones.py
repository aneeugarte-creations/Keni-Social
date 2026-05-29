"""Tests de la API Conexiones (/api/conexiones). OFFLINE: NUNCA se toca la red.

Cubre la clave de imagen IA (estado/guardar/probar-mockeado/borrar, incl. "no
configurada") y los tokens de redes (estado/set/remove sobre un config.toml de
metricas temporal). En "probar" se parchea `_PROBADOR`: jamas se llama a OpenRouter.
La clave nunca debe aparecer en ninguna respuesta de la API.

AUTORIZACION (#153, ESTRICTO por #150): los endpoints de conexiones son SOLO ADMIN y el
TOKEN de mantenimiento NO es admin (#150). Por eso estos tests funcionales usan un
`cliente` que es una SESION admin REAL (no el token): la `fixture cliente` de aqui
SOBREESCRIBE la de conftest. El gate por rol (editor/token -> 403) se prueba aparte en
`test_api_conexiones_permisos.py`.
"""

from __future__ import annotations

import os
import tomllib
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth
from keni_consola.api import conexiones

from .conftest import TOKEN_PRUEBA

_CLAVE = "sk-test-PISTA1234"
_ORIGIN = {"Origin": "http://testserver"}
_CLAVE_SESION = "clave-de-prueba"


@pytest.fixture
def cliente(entorno):
    """TestClient autenticado por SESION con un ADMIN real (no el token de mantenimiento).

    Conexiones es SOLO ADMIN (#153) y el token NO es admin (#150); estos tests funcionales
    necesitan a quien SI puede gestionarlas: un admin con sesion. Sobreescribe el `cliente`
    de conftest (que entra por el token) solo para este modulo.
    """
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    auth.crear_usuario("admin", _CLAVE_SESION, "admin")
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"usuario": "admin", "password": _CLAVE_SESION}, headers=_ORIGIN)
    assert r.status_code == 200, r.text
    # Origin propio por defecto: las mutaciones (PUT/DELETE/POST) pasan el chequeo CSRF.
    c.headers.update(_ORIGIN)
    return c


# --------------------------------------------------------------------------- #
# Imagen IA                                                                   #
# --------------------------------------------------------------------------- #


def test_imagen_estado_sin_clave(cliente):
    from keni_consola import media

    r = cliente.get("/api/conexiones/imagen")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo == {
        "proveedor": "openrouter",
        "modelo": "openai/gpt-5-image-mini",
        "modelos": media.modelos_disponibles(),
        "configurado": False,
        "pista": "",
    }
    # el primer modelo de la lista curada es el por defecto (economico, con personas)
    assert cuerpo["modelos"][0]["id"] == "openai/gpt-5-image-mini"


def test_imagen_guardar_y_estado(cliente):
    r = cliente.put("/api/conexiones/imagen", json={"api_key": _CLAVE})
    assert r.status_code == 200
    assert r.json()["configurado"] is True
    # el PUT NO devuelve la clave
    assert _CLAVE not in r.text

    estado = cliente.get("/api/conexiones/imagen").json()
    assert estado["configurado"] is True
    assert estado["modelo"] == "openai/gpt-5-image-mini"
    assert estado["pista"] == "····" + _CLAVE[-4:]
    # el estado NUNCA expone la clave entera
    assert _CLAVE not in cliente.get("/api/conexiones/imagen").text


def test_imagen_guardar_sin_clave_400(cliente):
    r = cliente.put("/api/conexiones/imagen", json={})
    assert r.status_code == 400
    r2 = cliente.put("/api/conexiones/imagen", json={"api_key": "   "})
    assert r2.status_code == 400


def test_imagen_borrar(cliente):
    cliente.put("/api/conexiones/imagen", json={"api_key": _CLAVE})
    r = cliente.delete("/api/conexiones/imagen")
    assert r.status_code == 200
    assert cliente.get("/api/conexiones/imagen").json()["configurado"] is False


def test_imagen_probar_no_configurada(cliente):
    r = cliente.post("/api/conexiones/imagen/probar")
    assert r.status_code == 200
    assert r.json() == {"ok": False, "mensaje": "No hay clave configurada."}


def test_imagen_probar_ok_mockeado(cliente, monkeypatch):
    """Con clave guardada + probador MOCK (sin red) => {ok:true}."""
    cliente.put("/api/conexiones/imagen", json={"api_key": _CLAVE})

    llamado = {}

    def _mock(clave):
        llamado["clave"] = clave
        return True, "La clave funciona."

    monkeypatch.setattr(conexiones, "_PROBADOR", _mock)
    r = cliente.post("/api/conexiones/imagen/probar")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "mensaje": "La clave funciona."}
    # el probador recibio la clave guardada, pero esta no sale al cliente
    assert llamado["clave"] == _CLAVE
    assert _CLAVE not in r.text


def test_imagen_probar_rechazada_mockeado(cliente, monkeypatch):
    cliente.put("/api/conexiones/imagen", json={"api_key": _CLAVE})
    monkeypatch.setattr(
        conexiones, "_PROBADOR", lambda _c: (False, "La clave fue rechazada por el proveedor.")
    )
    r = cliente.post("/api/conexiones/imagen/probar")
    assert r.json()["ok"] is False
    assert "rechazada" in r.json()["mensaje"]


def test_imagen_clave_activa_generacion_en_media(cliente, monkeypatch):
    """Guardar la clave por la UI debe activar la generacion en media (sin env)."""
    from keni_consola import media

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert media.proveedor_configurado() is False
    cliente.put("/api/conexiones/imagen", json={"api_key": _CLAVE})
    assert media.proveedor_configurado() is True


# --------------------------------------------------------------------------- #
# Imagen IA: selector de modelo                                               #
# --------------------------------------------------------------------------- #


def test_imagen_estado_trae_lista_de_modelos(cliente):
    """El GET incluye `modelos` (lista curada {id, etiqueta}) para poblar el dropdown."""
    cuerpo = cliente.get("/api/conexiones/imagen").json()
    modelos = cuerpo["modelos"]
    assert isinstance(modelos, list) and modelos
    # cada entrada tiene id + etiqueta
    assert all(set(m) == {"id", "etiqueta"} for m in modelos)
    ids = [m["id"] for m in modelos]
    assert "openai/gpt-5-image-mini" in ids
    assert "google/gemini-2.5-flash-image" in ids


def test_imagen_modelo_guardar_valido_y_persiste(cliente):
    """PUT /imagen/modelo con un id valido lo guarda y el GET lo refleja como `modelo`."""
    r = cliente.put(
        "/api/conexiones/imagen/modelo", json={"modelo": "google/gemini-2.5-flash-image"}
    )
    assert r.status_code == 200
    assert r.json() == {"modelo": "google/gemini-2.5-flash-image"}
    # el estado refleja el modelo guardado (gana al por defecto)
    estado = cliente.get("/api/conexiones/imagen").json()
    assert estado["modelo"] == "google/gemini-2.5-flash-image"


def test_imagen_modelo_invalido_400(cliente):
    """Un id fuera de la lista curada => 400 con mensaje en espanol; no cambia nada."""
    r = cliente.put("/api/conexiones/imagen/modelo", json={"modelo": "inventado/foo"})
    assert r.status_code == 400
    assert "modelo" in r.json()["error"].lower()
    # el modelo en uso sigue siendo el por defecto
    assert cliente.get("/api/conexiones/imagen").json()["modelo"] == "openai/gpt-5-image-mini"


def test_imagen_modelo_vacio_400(cliente):
    r = cliente.put("/api/conexiones/imagen/modelo", json={"modelo": "  "})
    assert r.status_code == 400
    r2 = cliente.put("/api/conexiones/imagen/modelo", json={})
    assert r2.status_code == 400


def test_imagen_modelo_no_borra_la_clave(cliente):
    """Guardar el modelo NO debe tocar la clave ya configurada (se preserva)."""
    cliente.put("/api/conexiones/imagen", json={"api_key": _CLAVE})
    cliente.put("/api/conexiones/imagen/modelo", json={"modelo": "openai/gpt-5-image"})
    estado = cliente.get("/api/conexiones/imagen").json()
    assert estado["configurado"] is True
    assert estado["modelo"] == "openai/gpt-5-image"
    assert estado["pista"] == "····" + _CLAVE[-4:]


# --------------------------------------------------------------------------- #
# Redes sociales                                                              #
# --------------------------------------------------------------------------- #

_PLACEHOLDER = "PENDIENTE_PON_TU_TOKEN_AQUI"
_TOKEN_RED = "tok-red-SECRETO-9999"


def _ruta_metricas() -> str:
    return os.environ["KENI_METRICAS_CONFIG"]


def test_redes_estado_inicial_todo_desconectado(cliente):
    r = cliente.get("/api/conexiones/redes")
    assert r.status_code == 200
    redes = {x["plataforma"]: x for x in r.json()["redes"]}
    assert set(redes) == {"meta", "youtube", "x", "tiktok"}
    assert redes["meta"]["nombre"] == "Meta (Facebook/Instagram)"
    assert all(x["conectado"] is False for x in redes.values())


def test_redes_set_conecta_y_persiste(cliente):
    r = cliente.put("/api/conexiones/redes/meta", json={"token": _TOKEN_RED})
    assert r.status_code == 200
    assert r.json()["conectado"] is True
    # el token NO se devuelve
    assert _TOKEN_RED not in r.text
    # estado refleja conectado, sin exponer el token
    redes = {x["plataforma"]: x for x in cliente.get("/api/conexiones/redes").json()["redes"]}
    assert redes["meta"]["conectado"] is True
    assert _TOKEN_RED not in cliente.get("/api/conexiones/redes").text
    # persiste en el config.toml de metricas en el campo correcto
    datos = tomllib.loads(open(_ruta_metricas(), encoding="utf-8").read())
    assert datos["credenciales"]["meta"]["access_token"] == _TOKEN_RED


def test_redes_set_token_vacio_400(cliente):
    r = cliente.put("/api/conexiones/redes/meta", json={"token": "  "})
    assert r.status_code == 400


def test_redes_plataforma_desconocida_400(cliente):
    r = cliente.put("/api/conexiones/redes/inventada", json={"token": "x"})
    assert r.status_code == 400
    r2 = cliente.delete("/api/conexiones/redes/inventada")
    assert r2.status_code == 400


def test_redes_borrar_desconecta(cliente):
    cliente.put("/api/conexiones/redes/youtube", json={"token": _TOKEN_RED})
    r = cliente.delete("/api/conexiones/redes/youtube")
    assert r.status_code == 200
    redes = {x["plataforma"]: x for x in cliente.get("/api/conexiones/redes").json()["redes"]}
    assert redes["youtube"]["conectado"] is False
    # tras borrar, el campo queda en el placeholder (no se devuelve el real)
    datos = tomllib.loads(open(_ruta_metricas(), encoding="utf-8").read())
    assert datos["credenciales"]["youtube"]["access_token"] == _PLACEHOLDER


def test_redes_set_preserva_otros_bloques(cliente):
    cliente.put("/api/conexiones/redes/meta", json={"token": "meta-token"})
    cliente.put("/api/conexiones/redes/x", json={"token": "x-token"})
    datos = tomllib.loads(open(_ruta_metricas(), encoding="utf-8").read())
    # ambos bloques coexisten, en su campo de token propio
    assert datos["credenciales"]["meta"]["access_token"] == "meta-token"
    assert datos["credenciales"]["x"]["bearer_token"] == "x-token"


def test_redes_x_usa_bearer_token(cliente):
    cliente.put("/api/conexiones/redes/x", json={"token": _TOKEN_RED})
    datos = tomllib.loads(open(_ruta_metricas(), encoding="utf-8").read())
    # X usa bearer_token (derivado de CAMPO_TOKEN), no access_token
    assert datos["credenciales"]["x"]["bearer_token"] == _TOKEN_RED
    assert "access_token" not in datos["credenciales"]["x"]


def test_redes_config_0600(cliente):
    cliente.put("/api/conexiones/redes/meta", json={"token": _TOKEN_RED})
    assert (os.stat(_ruta_metricas()).st_mode & 0o777) == 0o600


# --------------------------------------------------------------------------- #
# Metricool por marca                                                         #
# --------------------------------------------------------------------------- #

_TOKEN_MC = "mc-user-token-SECRETO-7777"


def _una_marca_metricool() -> str:
    """Un id_metricas real del catalogo (clave de [metricool.marcas.<id>])."""
    from keni_shared import marcas

    return marcas.opciones_metricas()[0][0]


def test_metricool_estado_inicial_todo_desconectado(cliente):
    r = cliente.get("/api/conexiones/metricool")
    assert r.status_code == 200
    marcas = r.json()["marcas"]
    assert marcas, "deberia listar las marcas del catalogo"
    assert all(m["conectado"] is False for m in marcas)
    # cada entrada trae marca + etiqueta; sin token jamas
    assert all({"marca", "etiqueta", "conectado"} <= set(m) for m in marcas)
    # sin conectar no se exponen ni user_id ni blog_id
    assert all("user_id_pista" not in m for m in marcas)


def test_metricool_guardar_persiste_y_conecta(cliente):
    marca = _una_marca_metricool()
    r = cliente.put(
        f"/api/conexiones/metricool/{marca}",
        json={"user_token": _TOKEN_MC, "user_id": "999", "blog_id": "12345"},
    )
    assert r.status_code == 200
    assert r.json()["conectado"] is True
    # el token NO se devuelve
    assert _TOKEN_MC not in r.text

    # el estado refleja conectado, con pista de user_id + blog_id, SIN token
    marcas = {m["marca"]: m for m in cliente.get("/api/conexiones/metricool").json()["marcas"]}
    assert marcas[marca]["conectado"] is True
    assert marcas[marca]["user_id_pista"] == "999"
    assert marcas[marca]["blog_id"] == "12345"
    assert _TOKEN_MC not in cliente.get("/api/conexiones/metricool").text

    # persiste en [metricool.marcas.<marca>] con los tres campos
    datos = tomllib.loads(open(_ruta_metricas(), encoding="utf-8").read())
    entrada = datos["metricool"]["marcas"][marca]
    assert entrada["user_token"] == _TOKEN_MC
    assert entrada["user_id"] == "999"
    assert entrada["blog_id"] == "12345"


def test_metricool_guardar_campos_faltantes_400(cliente):
    marca = _una_marca_metricool()
    r = cliente.put(f"/api/conexiones/metricool/{marca}", json={"user_token": "t", "user_id": "1"})
    assert r.status_code == 400  # falta blog_id
    r2 = cliente.put(
        f"/api/conexiones/metricool/{marca}",
        json={"user_token": "  ", "user_id": "1", "blog_id": "1"},
    )
    assert r2.status_code == 400  # token vacio


def test_metricool_marca_desconocida_400(cliente):
    r = cliente.put(
        "/api/conexiones/metricool/inventada",
        json={"user_token": "t", "user_id": "1", "blog_id": "1"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "Marca desconocida."
    assert cliente.delete("/api/conexiones/metricool/inventada").status_code == 400
    assert cliente.post("/api/conexiones/metricool/inventada/probar").status_code == 400


def test_metricool_borrar_quita_la_marca(cliente):
    marca = _una_marca_metricool()
    cliente.put(
        f"/api/conexiones/metricool/{marca}",
        json={"user_token": _TOKEN_MC, "user_id": "999", "blog_id": "12345"},
    )
    r = cliente.delete(f"/api/conexiones/metricool/{marca}")
    assert r.status_code == 200
    marcas = {m["marca"]: m for m in cliente.get("/api/conexiones/metricool").json()["marcas"]}
    assert marcas[marca]["conectado"] is False
    # ya no figura en el config
    datos = tomllib.loads(open(_ruta_metricas(), encoding="utf-8").read())
    assert marca not in datos.get("metricool", {}).get("marcas", {})


def test_metricool_guardar_preserva_otras_marcas(cliente):
    from keni_shared import marcas as catalogo

    opciones = catalogo.opciones_metricas()
    if len(opciones) < 2:  # pragma: no cover -- catalogo siempre trae >1 marca
        return
    m1, m2 = opciones[0][0], opciones[1][0]
    cliente.put(
        f"/api/conexiones/metricool/{m1}",
        json={"user_token": "t1", "user_id": "1", "blog_id": "b1"},
    )
    cliente.put(
        f"/api/conexiones/metricool/{m2}",
        json={"user_token": "t2", "user_id": "2", "blog_id": "b2"},
    )
    datos = tomllib.loads(open(_ruta_metricas(), encoding="utf-8").read())
    marcas = datos["metricool"]["marcas"]
    assert marcas[m1]["user_token"] == "t1"
    assert marcas[m2]["user_token"] == "t2"


def test_metricool_config_0600(cliente):
    marca = _una_marca_metricool()
    cliente.put(
        f"/api/conexiones/metricool/{marca}",
        json={"user_token": _TOKEN_MC, "user_id": "1", "blog_id": "1"},
    )
    assert (os.stat(_ruta_metricas()).st_mode & 0o777) == 0o600


def test_metricool_probar_sin_credenciales(cliente):
    marca = _una_marca_metricool()
    r = cliente.post(f"/api/conexiones/metricool/{marca}/probar")
    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_metricool_probar_ok_mockeado(cliente, monkeypatch):
    """Con credenciales guardadas + probador MOCK (sin red) => {ok:true}."""
    marca = _una_marca_metricool()
    cliente.put(
        f"/api/conexiones/metricool/{marca}",
        json={"user_token": _TOKEN_MC, "user_id": "999", "blog_id": "12345"},
    )
    recibido = {}

    def _mock(token, user_id, blog_id):
        recibido["token"] = token
        recibido["user_id"] = user_id
        recibido["blog_id"] = blog_id
        return True, "La credencial funciona."

    monkeypatch.setattr(conexiones, "_PROBADOR_MC", _mock)
    r = cliente.post(f"/api/conexiones/metricool/{marca}/probar")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "detalle": "La credencial funciona."}
    # el probador recibio el token guardado, pero este no sale al cliente
    assert recibido["token"] == _TOKEN_MC
    assert recibido["user_id"] == "999"
    assert _TOKEN_MC not in r.text


def test_metricool_probar_rechazada_mockeada(cliente, monkeypatch):
    marca = _una_marca_metricool()
    cliente.put(
        f"/api/conexiones/metricool/{marca}",
        json={"user_token": _TOKEN_MC, "user_id": "1", "blog_id": "1"},
    )
    monkeypatch.setattr(
        conexiones, "_PROBADOR_MC", lambda *_a: (False, "Metricool rechazó la credencial.")
    )
    r = cliente.post(f"/api/conexiones/metricool/{marca}/probar")
    assert r.json()["ok"] is False
    assert "rechaz" in r.json()["detalle"].lower()


# --------------------------------------------------------------------------- #
# Seguridad: follow_redirects=False en _probar_openrouter (#117)              #
# --------------------------------------------------------------------------- #


def test_probar_openrouter_no_sigue_redirects_a_otro_host():
    """_probar_openrouter pasa follow_redirects=False a httpx.get.

    Un redirect 302 a un host distinto NO debe reenviar el Bearer. Con
    follow_redirects=False httpx devuelve la respuesta 3xx directamente sin seguirla,
    por lo que el header Authorization nunca llega al host externo. Verificamos que el
    kwarg llega a httpx.get y que un 302 se trata como error.
    """
    from keni_consola.api.conexiones import _probar_openrouter

    mock_resp = MagicMock()
    mock_resp.status_code = 302

    with patch("httpx.get", return_value=mock_resp) as mock_get:
        ok, _ = _probar_openrouter("sk-or-test-1234")

    # follow_redirects=False debe estar en los kwargs de la llamada
    _, kwargs = mock_get.call_args
    assert kwargs.get("follow_redirects") is False, (
        "follow_redirects=False ausente: un redirect puede filtrar el Bearer"
    )
    # Un 302 NO se trata como clave válida
    assert ok is False


def test_probar_openrouter_no_reenvio_bearer_en_redirect():
    """Simula un redirect 302 a otro host y verifica que el Bearer no se reenvía.

    Con follow_redirects=False httpx NO llama al host de destino del redirect,
    así que la clave nunca llega a un servidor externo. El mock confirma que
    httpx.get se invocó UNA SOLA VEZ (solo la URL original, no la de redirect).
    """
    from keni_consola.api.conexiones import _probar_openrouter

    redirect_resp = MagicMock()
    redirect_resp.status_code = 302
    redirect_resp.headers = {"location": "https://evil.example.com/captura"}

    with patch("httpx.get", return_value=redirect_resp) as mock_get:
        ok, mensaje = _probar_openrouter("sk-or-secreto-5678")

    # httpx.get llamado SOLO UNA vez (no siguió el redirect)
    assert mock_get.call_count == 1
    url_llamada = mock_get.call_args[0][0]
    assert "openrouter.ai" in url_llamada
    assert "evil.example.com" not in url_llamada
    assert ok is False
