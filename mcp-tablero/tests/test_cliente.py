"""Tests del `ClienteConsola` SIN red real (respx intercepta httpx).

Cubren el contrato de la unica capa que toca la red: autenticacion por cabeceras,
url-encoding de los filtros (via `params=` de httpx), traduccion de errores HTTP a
`ErrorConsola` en espanol (`error` o `mensaje` del cuerpo), y los reintentos de
transporte SOLO en GET (idempotente; un POST reintentado podria duplicar la mutacion).
"""

from __future__ import annotations

import httpx
import pytest
import respx

from keni_tablero.cliente import ClienteConsola, ErrorConsola
from keni_tablero.config import Config

BASE = "http://consola.test"


@pytest.fixture
def cliente(monkeypatch) -> ClienteConsola:
    # Sin esperas reales entre reintentos (el backoff es parte del contrato, no del test).
    monkeypatch.setattr("keni_tablero.cliente.time.sleep", lambda _s: None)
    return ClienteConsola(Config(url=BASE, token="tok-123"))


# --- autenticacion y encoding ------------------------------------------------ #


@respx.mock
def test_manda_token_en_ambas_cabeceras(cliente):
    ruta = respx.get(f"{BASE}/api/contenido").respond(json={"contenidos": []})
    cliente.listar_contenido()
    peticion = ruta.calls.last.request
    assert peticion.headers["Authorization"] == "Bearer tok-123"
    assert peticion.headers["X-Keni-Token"] == "tok-123"


@respx.mock
def test_listar_urlencodea_los_filtros(cliente):
    """Filtros con espacios/acentos/&: antes la query se armaba con f-strings y salia
    una URL invalida; ahora va por `params=` de httpx (encoding correcto)."""
    ruta = respx.get(f"{BASE}/api/contenido").respond(json={"contenidos": []})
    cliente.listar_contenido({"marca": "claro sports & más", "flujo": "evento", "clase": ""})
    url = ruta.calls.last.request.url
    assert url.params["marca"] == "claro sports & más"
    assert url.params["flujo"] == "evento"
    assert "clase" not in url.params  # los filtros vacios no viajan
    # Lo que protege esta regresion: los caracteres peligrosos van PERCENT-ENCODED en la
    # query cruda, no literales (un '&' literal partiria la query; un acento crudo da URL
    # invalida). El espacio httpx lo codifica como '+' (equivalente valido a %20), asi que
    # NO lo fijamos: comprobamos el '&' y el acento, que son los que rompian con f-strings.
    cruda = str(url)
    assert "%26" in cruda  # el '&' del valor viaja escapado, no parte la query
    assert "m%C3%A1s" in cruda  # el acento viaja percent-encoded


@respx.mock
def test_listar_sin_filtros_no_manda_query(cliente):
    ruta = respx.get(f"{BASE}/api/contenido").respond(json={"contenidos": []})
    cliente.listar_contenido()
    assert not ruta.calls.last.request.url.query


# --- traduccion de errores ----------------------------------------------------- #


@respx.mock
def test_error_usa_mensaje_de_la_api_clave_error(cliente):
    respx.post(f"{BASE}/api/contenido").respond(400, json={"error": "Falta el titulo."})
    with pytest.raises(ErrorConsola, match="Falta el titulo."):
        cliente.crear_contenido({})


@respx.mock
def test_error_usa_clave_mensaje_si_no_hay_error(cliente):
    """Algunos endpoints responden `{"mensaje": ...}`: tambien se aprovecha (antes solo
    se leia `error` y el detalle de la API se perdia)."""
    respx.post(f"{BASE}/api/contenido").respond(409, json={"mensaje": "Ya existe."})
    with pytest.raises(ErrorConsola, match="Ya existe."):
        cliente.crear_contenido({"titulo": "x"})


@respx.mock
def test_error_sin_cuerpo_json_cae_al_generico(cliente):
    respx.post(f"{BASE}/api/contenido").respond(500, text="boom")
    with pytest.raises(ErrorConsola, match="HTTP 500"):
        cliente.crear_contenido({"titulo": "x"})


@respx.mock
def test_401_y_403_tienen_mensaje_propio(cliente):
    respx.get(f"{BASE}/api/contenido").respond(401)
    with pytest.raises(ErrorConsola, match="KENI_CONSOLA_TOKEN"):
        cliente.listar_contenido()
    respx.get(f"{BASE}/api/contenido").respond(403)
    with pytest.raises(ErrorConsola, match="403"):
        cliente.listar_contenido()


@respx.mock
def test_respuesta_no_json_es_error_claro(cliente):
    respx.get(f"{BASE}/api/contenido").respond(200, text="<html>")
    with pytest.raises(ErrorConsola, match="no-JSON"):
        cliente.listar_contenido()


# --- reintentos: solo GET ------------------------------------------------------ #


@respx.mock
def test_get_reintenta_ante_fallo_de_transporte(cliente):
    ruta = respx.get(f"{BASE}/api/contenido")
    ruta.side_effect = [httpx.ConnectError("caida"), httpx.Response(200, json={"contenidos": []})]
    assert cliente.listar_contenido() == {"contenidos": []}
    assert ruta.call_count == 2


@respx.mock
def test_get_agota_reintentos_y_da_error_en_espanol(cliente):
    ruta = respx.get(f"{BASE}/api/contenido")
    ruta.side_effect = httpx.ConnectError("caida")
    with pytest.raises(ErrorConsola, match="No se pudo conectar"):
        cliente.listar_contenido()
    assert ruta.call_count == 3  # _INTENTOS_GET


@respx.mock
def test_post_no_reintenta(cliente):
    """Una mutacion NUNCA se reintenta a ciegas (podria duplicar el contenido)."""
    ruta = respx.post(f"{BASE}/api/contenido")
    ruta.side_effect = httpx.ConnectError("caida")
    with pytest.raises(ErrorConsola, match="No se pudo conectar"):
        cliente.crear_contenido({"titulo": "x"})
    assert ruta.call_count == 1


@respx.mock
def test_timeout_da_mensaje_propio(cliente):
    ruta = respx.post(f"{BASE}/api/contenido")
    ruta.side_effect = httpx.ReadTimeout("lento")
    with pytest.raises(ErrorConsola, match="no respondio a tiempo"):
        cliente.crear_contenido({"titulo": "x"})


# --- cliente persistente -------------------------------------------------------- #


def test_reusa_un_httpx_client_por_instancia(monkeypatch):
    """UN `httpx.Client` por instancia (keep-alive), no uno nuevo por peticion."""
    transporte = httpx.MockTransport(lambda req: httpx.Response(200, json={"contenidos": []}))
    cli = ClienteConsola(Config(url=BASE), cliente=httpx.Client(transport=transporte))
    primero = cli._cli
    cli.listar_contenido()
    cli.listar_contenido()
    assert cli._cli is primero


@respx.mock
def test_rutas_de_mutacion_componen_url_y_cuerpo(cliente):
    ruta = respx.patch(f"{BASE}/api/contenido/c1/plataformas/p1").respond(
        json={"plataforma": {"id": "p1", "estado": "aprobado"}}
    )
    out = cliente.actualizar_plataforma("c1", "p1", {"estado": "aprobado"})
    assert out["plataforma"]["estado"] == "aprobado"
    import json as _json

    assert _json.loads(ruta.calls.last.request.content) == {"estado": "aprobado"}
