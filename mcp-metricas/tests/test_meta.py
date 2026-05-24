from __future__ import annotations

from datetime import date

import httpx
import respx

from keni_metricas.fuentes.meta import AdaptadorMeta
from keni_metricas.schema import Plataforma

DESDE = date(2026, 5, 16)
HASTA = date(2026, 5, 22)


def test_disponible_segun_token():
    assert AdaptadorMeta({"access_token": "x"}, Plataforma.facebook).disponible()
    assert not AdaptadorMeta({}, Plataforma.facebook).disponible()


def test_sin_token_no_llama_red():
    ad = AdaptadorMeta({}, Plataforma.facebook)
    assert ad.metricas("PAGE", DESDE, HASTA) is None
    assert ad.piezas("PAGE", DESDE, HASTA, 3) == []


@respx.mock
def test_metricas_facebook_parsea_insights():
    respx.get("https://graph.facebook.com/v21.0/PAGE/insights").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"name": "page_impressions", "values": [{"value": 1000}, {"value": 500}]},
                    {"name": "page_impressions_unique", "values": [{"value": 900}]},
                    {"name": "page_post_engagements", "values": [{"value": 30}, {"value": 15}]},
                ]
            },
        )
    )
    ad = AdaptadorMeta({"access_token": "tok"}, Plataforma.facebook)
    m = ad.metricas("PAGE", DESDE, HASTA)
    assert m is not None
    assert m.visualizaciones == 1500  # suma de los valores diarios
    assert m.alcance == 900
    assert m.interacciones == 45
    assert m.engagement_pct == 3.0  # 45/1500*100


@respx.mock
def test_metricas_degrada_en_error():
    respx.get("https://graph.facebook.com/v21.0/PAGE/insights").mock(
        return_value=httpx.Response(403, json={"error": {"message": "sin permiso"}})
    )
    ad = AdaptadorMeta({"access_token": "tok"}, Plataforma.facebook)
    assert ad.metricas("PAGE", DESDE, HASTA) is None  # no rompe, degrada
