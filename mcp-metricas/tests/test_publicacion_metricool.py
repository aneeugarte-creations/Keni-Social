"""Tests del adaptador de PROGRAMACION via Metricool (`publicacion.metricool`).

SIN red real: toda llamada HTTP va mockeada con respx. Cubren la propiedad de
SEGURIDAD central (dry-run = CERO red) y que el camino real arma la peticion
correcta al scheduler de Metricool (POST /v2/scheduler/posts con X-Mc-Auth +
userId/blogId), incluido el mapeo x -> twitter y la programacion con fecha.
"""

from __future__ import annotations

from datetime import datetime

import httpx
import pytest
import respx
from pydantic import ValidationError

from keni_metricas.publicacion import (
    AdaptadorPublicacionMetricool,
    BorradorMetricool,
    MediaRef,
    ProgramacionNoConfigurada,
)
from keni_metricas.publicacion.metricool import BASE, ENDPOINT_PROGRAMAR
from keni_metricas.publicacion.modelos import TipoMedia
from keni_metricas.schema import Plataforma

CREDS = {"user_token": "TOK", "user_id": "999", "blog_id": "1234567"}
URL = f"{BASE}{ENDPOINT_PROGRAMAR}"


def _img(url: str = "https://e/x.jpg", desc: str | None = None) -> MediaRef:
    return MediaRef(tipo=TipoMedia.imagen, url=url, descripcion=desc)


# --- modelo: validacion ----------------------------------------------------
def test_borrador_exige_al_menos_una_red():
    with pytest.raises(ValidationError):
        BorradorMetricool(redes=[], texto="hola")


def test_borrador_rechaza_vacio():
    with pytest.raises(ValidationError):
        BorradorMetricool(redes=[Plataforma.facebook])


def test_instagram_exige_media():
    with pytest.raises(ValidationError):
        BorradorMetricool(redes=[Plataforma.instagram], texto="solo texto")


def test_facebook_admite_solo_texto():
    b = BorradorMetricool(redes=[Plataforma.facebook], texto="hola")
    assert b.texto_final() == "hola"


def test_hashtags_se_normalizan_y_anaden():
    b = BorradorMetricool(
        redes=[Plataforma.facebook],
        texto="cuerpo",
        hashtags=["#Deporte", "futbol", "futbol", " #futbol "],
    )
    assert b.texto_final() == "cuerpo\n\n#Deporte #futbol"


def test_dedup_de_redes_preserva_orden():
    b = BorradorMetricool(redes=[Plataforma.x, Plataforma.facebook, Plataforma.x], texto="hola")
    assert b.redes_metricool() == ["twitter", "facebook"]  # x -> twitter, sin duplicado


# --- dry-run: CERO red -----------------------------------------------------
@respx.mock
def test_dry_run_no_toca_la_red():
    ruta = respx.post(URL)
    ad = AdaptadorPublicacionMetricool(creds=CREDS)
    b = BorradorMetricool(redes=[Plataforma.facebook, Plataforma.instagram], texto="hola", media=[_img()])
    res = ad.programar(b, dry_run=True)
    assert res.dry_run is True
    assert not ruta.called  # no hubo NINGUNA peticion
    # La peticion armada lleva el contrato exacto.
    body = res.peticion.body
    assert body["text"] == "hola"
    assert body["providers"] == [{"network": "facebook"}, {"network": "instagram"}]
    assert body["media"] == ["https://e/x.jpg"]
    assert body["autoPublish"] is True
    assert res.peticion.params == {"userId": "999", "blogId": "1234567"}
    # El token NUNCA viaja en params ni en el body (solo en la cabecera, en el POST real).
    assert "user_token" not in body and "X-Mc-Auth" not in body


def test_dry_run_no_requiere_credenciales():
    ad = AdaptadorPublicacionMetricool(creds={})  # sin token
    b = BorradorMetricool(redes=[Plataforma.facebook], texto="hola")
    res = ad.programar(b, dry_run=True)
    assert res.dry_run is True


def test_programacion_con_fecha_y_timezone():
    ad = AdaptadorPublicacionMetricool(creds=CREDS)
    cuando = datetime(2026, 5, 30, 18, 0, 0)
    b = BorradorMetricool(redes=[Plataforma.x], texto="hola", publicar_en=cuando)
    body = ad.cuerpo_para(b)
    assert body["publicationDate"] == {
        "dateTime": "2026-05-30T18:00:00",
        "timezone": "America/Mexico_City",
    }


def test_publicar_en_none_usa_ahora_inyectado():
    ad = AdaptadorPublicacionMetricool(creds=CREDS)
    b = BorradorMetricool(redes=[Plataforma.facebook], texto="hola")
    body = ad.cuerpo_para(b, ahora=datetime(2026, 1, 2, 3, 4, 5))
    assert body["publicationDate"]["dateTime"] == "2026-01-02T03:04:05"


def test_alt_text_solo_si_hay_descripcion():
    ad = AdaptadorPublicacionMetricool(creds=CREDS)
    b = BorradorMetricool(redes=[Plataforma.instagram], texto="x", media=[_img(desc="un gato")])
    body = ad.cuerpo_para(b)
    assert body["mediaAltText"] == ["un gato"]
    assert body["saveExternalMediaFiles"] is True


# --- camino real: requiere credenciales ------------------------------------
def test_real_sin_credenciales_lanza_antes_de_red():
    ad = AdaptadorPublicacionMetricool(creds={})  # sin token
    b = BorradorMetricool(redes=[Plataforma.facebook], texto="hola")
    with pytest.raises(ProgramacionNoConfigurada):
        ad.programar(b, dry_run=False)


@respx.mock
def test_real_postea_al_scheduler_con_auth():
    capturado: dict = {}

    def responder(request: httpx.Request) -> httpx.Response:
        capturado["auth"] = request.headers.get("X-Mc-Auth")
        capturado["url"] = str(request.url)
        return httpx.Response(
            200,
            json={"data": {"id": 4242, "providers": [{"network": "facebook", "status": "PENDING"}]}},
        )

    ruta = respx.post(URL).mock(side_effect=responder)
    with httpx.Client() as cli:
        ad = AdaptadorPublicacionMetricool(creds=CREDS, cliente=cli)
        b = BorradorMetricool(redes=[Plataforma.facebook], texto="hola")
        res = ad.programar(b, dry_run=False, ahora=datetime(2026, 5, 30, 18, 0))
    assert ruta.called
    assert res.dry_run is False
    assert res.id_post == "4242"
    assert res.estados == {"facebook": "PENDING"}
    assert capturado["auth"] == "TOK"
    assert "userId=999" in capturado["url"] and "blogId=1234567" in capturado["url"]


@respx.mock
def test_real_parsea_respuesta_en_raiz():
    """Defensa: si la respuesta no trae 'data', se lee de la raiz."""
    respx.post(URL).mock(
        return_value=httpx.Response(200, json={"id": 7, "providers": [{"network": "twitter", "status": "PUBLISHED"}]})
    )
    with httpx.Client() as cli:
        ad = AdaptadorPublicacionMetricool(creds=CREDS, cliente=cli)
        b = BorradorMetricool(redes=[Plataforma.x], texto="hola")
        res = ad.programar(b, dry_run=False)
    assert res.id_post == "7"
    assert res.estados == {"twitter": "PUBLISHED"}
