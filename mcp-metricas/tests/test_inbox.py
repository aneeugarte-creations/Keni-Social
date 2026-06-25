"""Tests del inbox de LECTURA de `FuenteMetricool` (DMs + comentarios de Metricool).

SIN red real: toda llamada HTTP va mockeada con respx. Cubren:
  - parseo de conversaciones (DMs) y comentarios a la forma de schema (Conversacion/Comentario);
  - filtrado por `authorizations` (una red sin buzón habilitado se omite);
  - degradación por red (un fallo de una red no rompe las demás);
  - troceo por día de los comentarios (un request por día) + dedupe entre días;
  - omisión de redes no conectadas en Metricool antes de consultar el buzón.
"""

from __future__ import annotations

import httpx
import respx

from keni_metricas.fuentes.metricool import (
    BASE,
    ENDPOINT_INBOX_AUTH,
    ENDPOINT_INBOX_COMENTARIOS,
    ENDPOINT_INBOX_CONVERSACIONES,
    FuenteMetricool,
)
from keni_metricas.schema import Plataforma

MARCAS = {
    "claro_sports": {
        "user_token": "TOK",
        "user_id": "999",
        "blog_id": "1234567",
        "nombre": "Claro Sports",
        "plataformas": [Plataforma.facebook, Plataforma.instagram],
    }
}


def _fuente(cliente: httpx.Client) -> FuenteMetricool:
    return FuenteMetricool(marcas=MARCAS, cliente=cliente)


def _perfil(blog_id: str = "1234567", **redes) -> dict:
    base = {
        "id": int(blog_id),
        "twitter": None,
        "facebook": None,
        "instagram": None,
        "tiktok": None,
        "youtube": None,
    }
    base.update(redes)
    return base


def _mock_perfiles(*perfiles: dict) -> None:
    respx.get(f"{BASE}/admin/simpleProfiles").mock(
        return_value=httpx.Response(200, json=list(perfiles))
    )


def _mock_auth(*habilitados: str) -> None:
    """Mockea authorizations: solo los providers de `habilitados` tienen el buzón abierto."""

    def responder(request: httpx.Request) -> httpx.Response:
        provider = request.url.params.get("provider")
        if provider in habilitados:
            return httpx.Response(
                200, json={"data": {"missingScopes": [], "allowAccessToMessages": True}}
            )
        return httpx.Response(
            200, json={"data": {"missingScopes": ["pages_messaging"], "allowAccessToMessages": False}}
        )

    respx.get(f"{BASE}{ENDPOINT_INBOX_AUTH}").mock(side_effect=responder)


def _conv(id_: str, status: str = "PENDING", texto: str = "hola") -> dict:
    """Una conversación con la forma real de `/v2/inbox/conversations`."""
    return {
        "id": id_,
        "status": status,
        "creationDate": "2026-06-20T10:00:00",
        "lastUpdateTime": "2026-06-20T11:00:00",
        "participants": [{"id": "u1", "name": "Ana", "imageProfileUrl": "http://img/a.jpg"}],
        "messages": [
            {
                "id": "m1",
                "from": "u1",
                "to": "page",
                "text": texto,
                "publicationDateTime": "2026-06-20T10:00:00",
                "attachments": [{"url": "x"}],
            }
        ],
    }


def _com(id_: str, status: str = "PENDING") -> dict:
    """Un hilo de comentario con la forma real de `/v2/inbox/post-comments`."""
    return {
        "id": "thread_" + id_,
        "status": status,
        "creationDate": "2026-06-20T10:00:00",
        "participants": [{"id": "u2", "name": "Luis"}],
        "root": {
            "id": id_,
            "creationDate": "2026-06-20T10:05:00",
            "owner": "Luis",
            "text": "qué golazo",
            "properties": {"permalink": "https://fb.com/c/" + id_},
            "element": {
                "id": "post1",
                "owner": "page",
                "link": "https://fb.com/post1",
                "text": "Resumen del partido",
                "mediaUrls": ["https://img/p1.jpg"],
                "commentCount": 3,
            },
            "comments": [
                {
                    "id": "r1",
                    "owner": "page",
                    "text": "¡gracias!",
                    "creationDate": "2026-06-20T10:10:00",
                    "status": "READ",
                }
            ],
        },
    }


@respx.mock
def test_conversaciones_parsea_y_agrupa_por_red() -> None:
    _mock_perfiles(_perfil(facebook="cs_fb", instagram="cs_ig"))
    _mock_auth("FACEBOOK", "INSTAGRAM")

    def responder(request: httpx.Request) -> httpx.Response:
        provider = request.url.params.get("provider")
        data = [_conv("c_fb")] if provider == "FACEBOOK" else [_conv("c_ig")]
        return httpx.Response(200, json={"data": data})

    respx.get(f"{BASE}{ENDPOINT_INBOX_CONVERSACIONES}").mock(side_effect=responder)

    convs = _fuente(httpx.Client()).conversaciones("claro_sports")

    redes = {c.red for c in convs}
    assert redes == {"facebook", "instagram"}
    fb = next(c for c in convs if c.red == "facebook")
    assert fb.id == "c_fb"
    assert fb.pendiente is True
    assert fb.participantes[0].nombre == "Ana"
    assert fb.participantes[0].avatar == "http://img/a.jpg"
    assert fb.mensajes[0].texto == "hola"
    assert fb.mensajes[0].autor_id == "u1"
    assert fb.mensajes[0].adjuntos == 1  # se cuentan, no se exponen las URLs
    assert fb.creado is not None and fb.actualizado is not None


@respx.mock
def test_conversaciones_omite_red_sin_autorizacion() -> None:
    _mock_perfiles(_perfil(facebook="cs_fb", instagram="cs_ig"))
    _mock_auth("FACEBOOK")  # IG sin scopes -> se omite

    respx.get(f"{BASE}{ENDPOINT_INBOX_CONVERSACIONES}").mock(
        side_effect=lambda r: httpx.Response(200, json={"data": [_conv("c1")]})
    )

    convs = _fuente(httpx.Client()).conversaciones("claro_sports")
    assert {c.red for c in convs} == {"facebook"}


@respx.mock
def test_conversaciones_degrada_por_red_que_falla() -> None:
    _mock_perfiles(_perfil(facebook="cs_fb", instagram="cs_ig"))
    _mock_auth("FACEBOOK", "INSTAGRAM")

    def responder(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("provider") == "FACEBOOK":
            return httpx.Response(500)
        return httpx.Response(200, json={"data": [_conv("c_ig")]})

    respx.get(f"{BASE}{ENDPOINT_INBOX_CONVERSACIONES}").mock(side_effect=responder)

    convs = _fuente(httpx.Client()).conversaciones("claro_sports")
    assert {c.red for c in convs} == {"instagram"}  # FB cayó, IG sigue


@respx.mock
def test_comentarios_trocea_por_dia_y_dedupe() -> None:
    _mock_perfiles(_perfil(facebook="cs_fb"))  # solo FB conectada
    _mock_auth("FACEBOOK")

    ruta = respx.get(f"{BASE}{ENDPOINT_INBOX_COMENTARIOS}").mock(
        side_effect=lambda r: httpx.Response(200, json={"data": [_com("k1")]})
    )

    coms = _fuente(httpx.Client()).comentarios("claro_sports", dias=3)

    assert ruta.call_count == 3  # un request por día de la ventana
    assert len(coms) == 1  # el mismo comentario en los 3 días se deduplica
    c = coms[0]
    assert c.red == "facebook"
    assert c.id == "k1"
    assert c.texto == "qué golazo"
    assert c.permalink == "https://fb.com/c/k1"
    assert c.post_id == "post1"
    assert c.post_texto == "Resumen del partido"
    assert c.post_enlace == "https://fb.com/post1"
    assert c.post_media == ["https://img/p1.jpg"]
    assert c.autor is not None and c.autor.nombre == "Luis"
    assert len(c.respuestas) == 1
    assert c.respuestas[0].texto == "¡gracias!"
    assert c.respuestas[0].pendiente is False


@respx.mock
def test_comentarios_un_dia_que_falla_no_rompe_la_red() -> None:
    _mock_perfiles(_perfil(facebook="cs_fb"))
    _mock_auth("FACEBOOK")

    llamadas = {"n": 0}

    def responder(request: httpx.Request) -> httpx.Response:
        llamadas["n"] += 1
        if llamadas["n"] == 1:  # el primer día falla
            return httpx.Response(500)
        return httpx.Response(200, json={"data": [_com("k1")]})

    respx.get(f"{BASE}{ENDPOINT_INBOX_COMENTARIOS}").mock(side_effect=responder)

    coms = _fuente(httpx.Client()).comentarios("claro_sports", dias=3)
    assert len(coms) == 1  # los días que respondieron aportan; el que falló se omitió


@respx.mock
def test_comentarios_omite_red_no_conectada() -> None:
    _mock_perfiles(_perfil(facebook="cs_fb"))  # IG NO conectada (pese a estar en plataformas)
    _mock_auth("FACEBOOK", "INSTAGRAM")  # aunque IG estuviera autorizada, no está conectada

    rutas: list[str] = []

    def responder(request: httpx.Request) -> httpx.Response:
        rutas.append(request.url.params.get("provider"))
        return httpx.Response(200, json={"data": [_com("k1")]})

    respx.get(f"{BASE}{ENDPOINT_INBOX_COMENTARIOS}").mock(side_effect=responder)

    coms = _fuente(httpx.Client()).comentarios("claro_sports", dias=1)
    assert {c.red for c in coms} == {"facebook"}
    assert set(rutas) == {"FACEBOOK"}  # IG (no conectada) nunca se consultó
