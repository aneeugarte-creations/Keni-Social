from __future__ import annotations

from datetime import UTC, date, datetime

import httpx
import respx

from keni_metricas.fuentes.meta import BASE as META_BASE
from keni_metricas.fuentes.meta import AdaptadorMeta
from keni_metricas.fuentes.tiktok import AdaptadorTikTok
from keni_metricas.fuentes.x import AdaptadorX
from keni_metricas.fuentes.youtube import AdaptadorYouTube
from keni_metricas.schema import Plataforma

DESDE = date(2026, 5, 16)
HASTA = date(2026, 5, 22)
TS_EN_RANGO = int(datetime(2026, 5, 20, 12, 0, tzinfo=UTC).timestamp())


@respx.mock
def test_x_pagina_dos_paginas():
    pm = lambda imp, lk: {  # noqa: E731
        "impression_count": imp,
        "like_count": lk,
        "reply_count": 0,
        "retweet_count": 0,
        "quote_count": 0,
    }
    def pagina(tid, imp, lk, next_token=None):
        meta = {"next_token": next_token} if next_token else {}
        return httpx.Response(200, json={"data": [{"id": tid, "public_metrics": pm(imp, lk)}], "meta": meta})

    respx.get("https://api.twitter.com/2/users/U/tweets").mock(
        side_effect=[pagina("1", 100, 5, "abc"), pagina("2", 200, 10)]
    )
    m = AdaptadorX({"bearer_token": "t"}).metricas("U", DESDE, HASTA)
    assert m is not None
    assert m.visualizaciones == 300  # suma de las dos páginas
    assert m.interacciones == 15


@respx.mock
def test_tiktok_pagina_dos_paginas():
    def vid(i, vc, lk):
        return {
            "id": i, "view_count": vc, "like_count": lk,
            "comment_count": 0, "share_count": 0, "create_time": TS_EN_RANGO,
        }

    respx.post("https://open.tiktokapis.com/v2/video/list/").mock(
        side_effect=[
            httpx.Response(200, json={"data": {"videos": [vid("1", 100, 10)], "has_more": True, "cursor": 123}}),
            httpx.Response(200, json={"data": {"videos": [vid("2", 200, 20)], "has_more": False}}),
        ]
    )
    m = AdaptadorTikTok({"access_token": "t"}).metricas("h", DESDE, HASTA)
    assert m is not None
    assert m.visualizaciones == 300
    assert m.interacciones == 30


@respx.mock
def test_tiktok_corta_si_cursor_no_avanza():
    """has_more=True pero cursor None: corta el bucle (no re-pagina la misma página)."""
    def vid(i, vc):
        return {
            "id": i, "view_count": vc, "like_count": 0,
            "comment_count": 0, "share_count": 0, "create_time": TS_EN_RANGO,
        }

    respx.post("https://open.tiktokapis.com/v2/video/list/").mock(
        side_effect=[
            httpx.Response(200, json={"data": {"videos": [vid("1", 100)], "has_more": True}}),  # sin cursor
            httpx.Response(200, json={"data": {"videos": [vid("1", 100)], "has_more": False}}),  # no debe pedirse
        ]
    )
    m = AdaptadorTikTok({"access_token": "t"}).metricas("h", DESDE, HASTA)
    assert m is not None
    assert m.visualizaciones == 100  # una sola página: sin cursor no se repagina ni duplica


@respx.mock
def test_meta_piezas_pagina_via_paging_next():
    def post(pid, vis, eng, dia):
        return {
            "id": pid,
            "message": pid,
            "permalink_url": f"https://fb/{pid}",
            "created_time": f"2026-05-{dia}T00:00:00+0000",
            "insights": {
                "data": [
                    {"name": "post_impressions", "values": [{"value": vis}]},
                    {"name": "post_engaged_users", "values": [{"value": eng}]},
                ]
            },
        }

    siguiente = f"{META_BASE}/PAGE/posts?after=X"
    respx.get(f"{META_BASE}/PAGE/posts").mock(
        side_effect=[
            httpx.Response(200, json={"data": [post("p1", 1000, 50, "20")], "paging": {"next": siguiente}}),
            httpx.Response(200, json={"data": [post("p2", 2000, 40, "21")]}),
        ]
    )
    piezas = AdaptadorMeta({"access_token": "tok"}, Plataforma.facebook).piezas("PAGE", DESDE, HASTA, 5)
    assert {p.id for p in piezas} == {"p1", "p2"}  # juntó las dos páginas


@respx.mock
def test_youtube_refresh_en_401():
    respx.get("https://youtubeanalytics.googleapis.com/v2/reports").mock(
        side_effect=[
            httpx.Response(401, json={"error": "expired"}),
            httpx.Response(200, json={"rows": [[1000, 50, 30, 20]]}),
        ]
    )
    respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(200, json={"access_token": "nuevo"})
    )
    ad = AdaptadorYouTube({"access_token": "viejo", "client_id": "c", "client_secret": "s", "refresh_token": "r"})
    m = ad.metricas("CH", DESDE, HASTA)
    assert m is not None
    assert m.visualizaciones == 1000
    assert ad._token == "nuevo"  # se refrescó tras el 401


@respx.mock
def test_youtube_sin_refresh_creds_no_reintenta():
    respx.get("https://youtubeanalytics.googleapis.com/v2/reports").mock(
        return_value=httpx.Response(401, json={"error": "expired"})
    )
    ad = AdaptadorYouTube({"access_token": "viejo"})  # sin client_id/secret/refresh_token
    assert ad.metricas("CH", DESDE, HASTA) is None  # degrada, no rompe
