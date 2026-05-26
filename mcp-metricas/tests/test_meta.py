from __future__ import annotations

from datetime import date

import httpx
import respx

from keni_metricas.fuentes.meta import BASE, AdaptadorMeta
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
    respx.get(f"{BASE}/PAGE/insights").mock(
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
    respx.get(f"{BASE}/PAGE/insights").mock(
        return_value=httpx.Response(403, json={"error": {"message": "sin permiso"}})
    )
    ad = AdaptadorMeta({"access_token": "tok"}, Plataforma.facebook)
    assert ad.metricas("PAGE", DESDE, HASTA) is None  # no rompe, degrada


@respx.mock
def test_system_user_no_llama_token_exchange_en_401():
    """Token de System User no caduca: ante un 401 NO se intenta fb_exchange_token."""
    # Aunque haya app_id/app_secret, el tipo system_user manda: refresh = no-op.
    ruta_insights = respx.get(f"{BASE}/PAGE/insights").mock(
        return_value=httpx.Response(401, json={"error": {"message": "token"}})
    )
    ruta_exchange = respx.get(f"{BASE}/oauth/access_token").mock(
        return_value=httpx.Response(200, json={"access_token": "nuevo"})
    )
    ad = AdaptadorMeta(
        {"access_token": "tok", "tipo_token": "system_user", "app_id": "a", "app_secret": "s"},
        Plataforma.facebook,
    )
    assert ad.metricas("PAGE", DESDE, HASTA) is None  # degrada, no rompe
    assert ruta_insights.called
    assert not ruta_exchange.called  # nunca se llamó al endpoint de intercambio
    assert ad._token == "tok"  # el token no cambió


def test_system_user_refrescar_es_noop():
    ad = AdaptadorMeta(
        {"access_token": "tok", "tipo_token": "system_user", "app_id": "a", "app_secret": "s"},
        Plataforma.facebook,
    )
    assert ad._es_system_user is True
    assert ad._refrescar() is False  # no-op: no caduca, nada que renovar


def test_token_normal_no_es_system_user():
    ad = AdaptadorMeta({"access_token": "tok"}, Plataforma.facebook)
    assert ad._es_system_user is False  # comportamiento por defecto sin cambios
