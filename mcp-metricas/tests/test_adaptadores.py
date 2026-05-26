from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx

from keni_metricas.fuentes.base import AdaptadorBase, engagement_pct
from keni_metricas.fuentes.meta import AdaptadorMeta
from keni_metricas.fuentes.tiktok import AdaptadorTikTok
from keni_metricas.fuentes.x import AdaptadorX
from keni_metricas.fuentes.youtube import AdaptadorYouTube
from keni_metricas.schema import Plataforma

DESDE = date(2026, 5, 16)
HASTA = date(2026, 5, 22)


@pytest.mark.parametrize(
    "adaptador",
    [
        AdaptadorMeta({}, Plataforma.facebook),
        AdaptadorMeta({}, Plataforma.instagram),
        AdaptadorYouTube({}),
        AdaptadorX({}),
        AdaptadorTikTok({}),
    ],
)
def test_sin_credenciales_degrada(adaptador):
    assert not adaptador.disponible()
    assert adaptador.metricas("h", DESDE, HASTA) is None
    assert adaptador.piezas("h", DESDE, HASTA, 3) == []


def test_disponible_con_credenciales():
    assert AdaptadorMeta({"access_token": "x"}, Plataforma.facebook).disponible()
    assert AdaptadorYouTube({"access_token": "x"}).disponible()
    assert AdaptadorX({"bearer_token": "x"}).disponible()
    assert AdaptadorTikTok({"access_token": "x"}).disponible()


# --- AdaptadorBase: helper de engagement (fórmula única, H4 / #97) -----------


@pytest.mark.parametrize(
    ("inter", "vis", "esperado"),
    [
        (45, 1500, 3.0),  # caso típico
        (0, 0, 0.0),  # sin visualizaciones: no divide por cero
        (10, 0, 0.0),  # interacciones pero 0 vis: 0.0, no error
        (1, 3, 33.3),  # redondeo a 1 decimal
        (2, 3, 66.7),  # redondeo a 1 decimal
    ],
)
def test_engagement_pct_formula_unica(inter, vis, esperado):
    assert engagement_pct(inter, vis) == esperado


# --- AdaptadorBase: comportamiento compartido (no cambia por plataforma) -----


def test_los_4_adaptadores_heredan_de_la_base():
    assert issubclass(AdaptadorMeta, AdaptadorBase)
    assert issubclass(AdaptadorYouTube, AdaptadorBase)
    assert issubclass(AdaptadorX, AdaptadorBase)
    assert issubclass(AdaptadorTikTok, AdaptadorBase)


def test_header_bearer_centralizado():
    # YouTube, X y TikTok comparten exactamente el mismo header Bearer.
    assert AdaptadorYouTube({"access_token": "tok"})._headers_bearer() == {
        "Authorization": "Bearer tok"
    }
    assert AdaptadorX({"bearer_token": "tok"})._headers_bearer() == {
        "Authorization": "Bearer tok"
    }
    assert AdaptadorTikTok({"access_token": "tok"})._headers_bearer() == {
        "Authorization": "Bearer tok"
    }


def test_x_lee_bearer_o_access_token():
    # X admite ambas claves; la base las resuelve vía `claves_token`.
    assert AdaptadorX({"bearer_token": "b"})._token == "b"
    assert AdaptadorX({"access_token": "a"})._token == "a"
    # bearer_token tiene prioridad si vienen las dos.
    assert AdaptadorX({"bearer_token": "b", "access_token": "a"})._token == "b"


def test_x_sin_refresh_es_noop():
    # X no sobreescribe `_refrescar`: usa el no-op de la base.
    assert AdaptadorX({"bearer_token": "b"})._refrescar() is False


@respx.mock
def test_intentar_degrada_en_error_no_propaga():
    # El wrapper try/except + log.warning de la base degrada a None / [] sin romper.
    respx.get("https://youtubeanalytics.googleapis.com/v2/reports").mock(
        return_value=httpx.Response(403, json={"error": "denegado"})
    )
    ad = AdaptadorYouTube({"access_token": "tok"})
    assert ad.metricas("CH", DESDE, HASTA) is None
    assert ad.piezas("CH", DESDE, HASTA, 3) == []
