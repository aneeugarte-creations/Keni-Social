"""Tests del cliente GA4 (`keni_metricas.ga4`). OFFLINE: httpx mockeado con respx.

Cubre la URL de autorización (scope + state + offline), el refresh + lectura de
propiedades (Admin API) y pageviews por URL (Data API), y que `probar` degrada con
honestidad ante un error HTTP en vez de lanzar.
"""

from __future__ import annotations

from datetime import date

import httpx
import respx

from keni_metricas import ga4


def test_url_autorizacion_incluye_scope_state_y_offline():
    url = ga4.url_autorizacion("cid", "https://x/cb", "st")
    assert url.startswith(ga4.AUTH_URL)
    assert "client_id=cid" in url
    assert "state=st" in url
    assert "access_type=offline" in url
    assert "prompt=consent" in url
    assert "analytics.readonly" in url


@respx.mock
def test_intercambiar_codigo_devuelve_tokens():
    respx.post(ga4.TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"refresh_token": "RT", "access_token": "AT"})
    )
    tokens = ga4.intercambiar_codigo("cid", "sec", "code", "https://x/cb")
    assert tokens["refresh_token"] == "RT"


@respx.mock
def test_cliente_propiedades_y_reporte():
    respx.post(ga4.TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "AT"}))
    respx.get(f"{ga4.ADMIN_API}/accountSummaries").mock(
        return_value=httpx.Response(
            200,
            json={
                "accountSummaries": [
                    {
                        "displayName": "AMX",
                        "propertySummaries": [
                            {"property": "properties/123", "displayName": "UnoTV"}
                        ],
                    }
                ]
            },
        )
    )
    respx.post(f"{ga4.DATA_API}/properties/123:runReport").mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [
                    {
                        "dimensionValues": [{"value": "/nota/x"}, {"value": "Título"}],
                        "metricValues": [{"value": "10"}, {"value": "4"}],
                    }
                ]
            },
        )
    )
    cliente = ga4.ClienteGA4("cid", "sec", "rt")
    assert cliente.propiedades() == [
        {"property_id": "123", "nombre": "UnoTV", "cuenta": "AMX"}
    ]
    filas = cliente.reporte_paginas("123", date(2026, 1, 1), date(2026, 1, 7))
    assert filas == [{"ruta": "/nota/x", "titulo": "Título", "vistas": 10, "usuarios": 4}]


@respx.mock
def test_probar_degrada_sin_lanzar():
    respx.post(ga4.TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "AT"}))
    respx.post(f"{ga4.DATA_API}/properties/9:runReport").mock(
        return_value=httpx.Response(403, text="permiso denegado")
    )
    cliente = ga4.ClienteGA4("cid", "sec", "rt")
    res = cliente.probar("9", date(2026, 1, 1), date(2026, 1, 7))
    assert res["ok"] is False
    assert "403" in res["detalle"]
