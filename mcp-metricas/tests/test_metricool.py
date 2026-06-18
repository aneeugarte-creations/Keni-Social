"""Tests del adapter `FuenteMetricool` (consumidor de la API REST de Metricool).

SIN red real: toda llamada HTTP va mockeada con respx. Cubren:
  - mapeo de una respuesta Metricool de ejemplo a la forma de `FuenteMetricas`
    (ResumenMetricas + Pieza), respetando el contrato;
  - degradación honesta a `muestra` cuando no hay token (vía `construir_fuente`);
  - que `FuenteMetricool` cumple el Protocol `FuenteMetricas`;
  - autenticación: header `X-Mc-Auth` + query params `userId`/`blogId`.
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx

from keni_metricas.config import Config, MetricoolConfig, construir_fuente
from keni_metricas.fuentes.base import FuenteMetricas
from keni_metricas.fuentes.metricool import BASE, FuenteMetricool, _fecha
from keni_metricas.fuentes.muestra import FuenteMuestra
from keni_metricas.schema import MotivoOmision, Plataforma, ResumenMetricas

# Rango ABSOLUTO (no relativo a hoy) para que las piezas mock con fecha 2026-05-xx caigan
# siempre dentro de [desde, hasta] y pasen el filtro de rango, de forma determinista.
RANGO = "mes:2026-05"

MARCAS = {
    "claro_sports": {
        "user_token": "TOK",
        "user_id": "999",
        "blog_id": "1234567",
        "nombre": "Claro Sports",
        "plataformas": [Plataforma.instagram],
    }
}


def _fuente(cliente: httpx.Client) -> FuenteMetricool:
    return FuenteMetricool(marcas=MARCAS, cliente=cliente)


def _serie(valor: float) -> dict:
    """Respuesta de /v2/analytics/timelines con un `aggregate` (forma del swagger)."""
    return {
        "data": [
            {
                "metric": "x",
                "values": [{"dateTime": "2026-05-20T00:00:00", "value": valor}],
                "aggregate": {"aggregation": "SUM", "value": valor},
            }
        ]
    }


def _perfil(blog_id: str = "1234567", **redes) -> dict:
    """Perfil de `/admin/simpleProfiles`: una red con valor truthy = conectada."""
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
    """Mockea `/admin/simpleProfiles` (lista de perfiles del usuario)."""
    respx.get(f"{BASE}/admin/simpleProfiles").mock(
        return_value=httpx.Response(200, json=list(perfiles))
    )


def _post_ig(id_: str, vis: int, inter: int, fecha: str = "2026-05-20T10:00:00") -> dict:
    """Un post de Instagram con la forma real de `/v2/analytics/posts/instagram`."""
    return {
        "postId": id_,
        "publishedAt": {"dateTime": fecha, "timezone": "UTC"},
        "views": vis,
        "interactions": inter,
        "url": f"https://instagram.com/p/{id_}",
    }


def _mock_posts(net: str, posts: list[dict]) -> None:
    """Mockea `/v2/analytics/posts/{net}` con una lista de posts."""
    respx.get(f"{BASE}/v2/analytics/posts/{net}").mock(
        return_value=httpx.Response(200, json={"data": posts})
    )


@respx.mock
def test_es_una_fuente_metricas():
    """FuenteMetricool cumple el contrato `FuenteMetricas` (mismo que muestra)."""
    with httpx.Client() as cli:
        f = _fuente(cli)
        assert isinstance(f, FuenteMetricas)
        assert f.nombre == "metricool"


@respx.mock
def test_resumen_agrega_los_posts_del_periodo_por_red():
    """resumen suma los POSTS del periodo por red (vis+inter) -> ResumenMetricas."""
    _mock_perfiles(_perfil(instagram="unotv_"))  # IG conectada
    _mock_posts("instagram", [_post_ig("p1", 6000, 200), _post_ig("p2", 4000, 100)])

    with httpx.Client() as cli:
        resumen = _fuente(cli).resumen("claro_sports", RANGO)

    assert isinstance(resumen, ResumenMetricas)
    assert resumen.cuenta == "claro_sports"
    assert resumen.fuente == "metricool"
    assert resumen.visualizaciones == 10000  # 6000 + 4000
    assert resumen.interacciones == 300  # 200 + 100
    # alcance no se deriva del post de forma uniforme -> None (honesto, no se inventa).
    assert resumen.alcance is None
    assert resumen.engagement_pct == pytest.approx(3.0)  # 300/10000 -> 3.0
    assert [m.plataforma for m in resumen.por_plataforma] == [Plataforma.instagram]
    assert resumen.cobertura is not None and resumen.cobertura.completa


@respx.mock
def test_resumen_incluye_reels_cuando_la_red_solo_publica_reels():
    """Una red (FB/IG) que SOLO publica reels (0 posts de feed) debe aportar sus métricas.

    Los reels viven en `/v2/analytics/reels/{network}`, aparte de `/posts`. Sin sumarlos, el
    agregado por red salía 0/0 -> la cobertura la marcaba "sin métricas" pese a tener
    actividad real (caso Piso 15: FB/IG todo reels). El resumen debe verlos, igual que el
    desglose/mejores_piezas.
    """
    _mock_perfiles(_perfil(instagram="piso15_"))  # IG conectada
    _mock_posts("instagram", [])  # sin posts de feed
    _mock_reels(
        "instagram",
        [
            {
                "reelId": "r1",
                "publishedAt": "2026-05-26T10:00:00",
                "content": "Reel del periodo",
                "views": 8000,
                "interactions": 400,
                "url": "https://instagram.com/reel/r1",
            }
        ],
    )

    with httpx.Client() as cli:
        resumen = _fuente(cli).resumen("claro_sports", RANGO)

    assert resumen.visualizaciones == 8000
    assert resumen.interacciones == 400
    assert [m.plataforma for m in resumen.por_plataforma] == [Plataforma.instagram]
    # Con actividad (vía reels) la red cuenta como cubierta -> la UI la pinta "con datos".
    assert resumen.cobertura is not None and resumen.cobertura.completa


@respx.mock
def test_resumen_envia_autenticacion_correcta():
    """X-Mc-Auth en header; userId/blogId en query (doc oficial de Metricool)."""
    _mock_perfiles(_perfil(instagram="x"))
    capturadas: list[httpx.Request] = []

    def responder(request: httpx.Request) -> httpx.Response:
        capturadas.append(request)
        return httpx.Response(200, json={"data": [_post_ig("p1", 100, 10)]})

    respx.get(f"{BASE}/v2/analytics/posts/instagram").mock(side_effect=responder)
    with httpx.Client() as cli:
        _fuente(cli).resumen("claro_sports", RANGO)

    assert capturadas, "no se hizo ninguna llamada a los posts"
    req = capturadas[0]
    assert req.headers.get("X-Mc-Auth") == "TOK"
    assert req.url.params.get("userId") == "999"
    assert req.url.params.get("blogId") == "1234567"


@respx.mock
def test_red_no_conectada_se_omite_con_motivo():
    """Una red que NO está conectada en Metricool (simpleProfiles) se omite con motivo."""
    _mock_perfiles(_perfil())  # ninguna red conectada (instagram=None)
    with httpx.Client() as cli:
        resumen = _fuente(cli).resumen("claro_sports", RANGO)

    assert resumen.por_plataforma == []
    assert resumen.cobertura is not None
    assert Plataforma.instagram in resumen.cobertura.omitidas
    assert resumen.cobertura.motivo["instagram"] == MotivoOmision.no_conectada


@respx.mock
def test_posts_que_fallan_se_omiten_en_cobertura():
    """Red conectada pero la API de posts falla -> se OMITE (no inventa ceros)."""
    _mock_perfiles(_perfil(instagram="x"))  # conectada...
    respx.get(f"{BASE}/v2/analytics/posts/instagram").mock(
        return_value=httpx.Response(403, json={"error": "boom"})  # ...pero la lectura falla
    )
    with httpx.Client() as cli:
        resumen = _fuente(cli).resumen("claro_sports", RANGO)

    assert resumen.por_plataforma == []
    assert resumen.cobertura is not None
    assert Plataforma.instagram in resumen.cobertura.omitidas
    assert resumen.cobertura.motivo["instagram"] == MotivoOmision.error_api


@respx.mock
def test_mejores_piezas_mapea_posts():
    """Posts de /v2/analytics/posts/{network} -> list[Pieza] ordenada por engagement."""
    posts = {
        "data": [
            {
                "id": "p1",
                "publishedAt": "2026-05-20T12:00:00",
                "impressions": 5000,
                "interactions": 250,  # 5.0%
                "text": "Gol agónico",
                "url": "https://instagram.com/p/p1",
                # Campos granulares (parseo defensivo por pieza).
                "likes": 200,
                "comments": 30,
                "shares": 15,
                "saves": 5,
                "mediaType": "REEL",
                "videoViews": 4200,
                "avgWatchTime": 12,
                "linkClicks": 8,
                "reach": 4500,  # alcance (usuarios únicos): solo Meta lo trae
            },
            {
                "id": "p2",
                "publishedAt": "2026-05-21T12:00:00",
                "impressions": 2000,
                "interactions": 200,  # 10.0% -> debe ir primero
                "text": "Otra pieza",
                "url": "https://instagram.com/p/p2",
                "type": "CAROUSEL_ALBUM",
            },
            # post sin visualizaciones: se descarta (no es "mejor pieza" útil)
            {"id": "p3", "impressions": 0, "interactions": 5, "text": "vacía"},
        ]
    }
    respx.get(f"{BASE}/v2/analytics/posts/instagram").mock(
        return_value=httpx.Response(200, json=posts)
    )
    with httpx.Client() as cli:
        piezas = _fuente(cli).mejores_piezas("claro_sports", RANGO, 5)

    assert [p.id for p in piezas] == ["p2", "p1"]  # ordenado por engagement desc
    assert piezas[0].plataforma == Plataforma.instagram
    assert piezas[0].engagement_pct == pytest.approx(10.0)
    assert piezas[0].url == "https://instagram.com/p/p2"
    # Granulares: p2 solo trajo formato (carrusel); el resto None (no se inventa).
    assert piezas[0].formato == "carrusel"
    assert piezas[0].likes is None and piezas[0].comentarios is None
    # Alcance: p2 no trajo reach -> None; p1 sí -> su valor (no se inventa un 0).
    assert piezas[0].alcance is None
    # p1 trajo el desglose completo y se parseó a los campos del contrato.
    p1 = next(p for p in piezas if p.id == "p1")
    assert p1.likes == 200
    assert p1.comentarios == 30
    assert p1.compartidos == 15
    assert p1.guardados == 5
    assert p1.formato == "reel"
    assert p1.video_views == 4200
    assert p1.tiempo_medio_vis_s == 12
    assert p1.clics_enlace == 8
    assert p1.alcance == 4500
    # cada pieza se sella con su marca (para estratificar top/peores por marca).
    assert all(p.cuenta == "claro_sports" for p in piezas)


def _mock_reels(net: str, reels: list[dict]) -> None:
    """Mockea `/v2/analytics/reels/{net}` con una lista de reels."""
    respx.get(f"{BASE}/v2/analytics/reels/{net}").mock(
        return_value=httpx.Response(200, json={"data": reels})
    )


@respx.mock
def test_mejores_piezas_incluye_reels_de_instagram():
    """Los Reels viven en `/v2/analytics/reels/{network}` (endpoint APARTE de /posts).

    Se parsean con su caption (`content`) — que SÍ trae los hashtags — y métricas.
    """
    _mock_posts("instagram", [])  # sin posts de feed
    _mock_reels(
        "instagram",
        [
            {
                "reelId": "r1",
                "type": "REELS_VIDEO",
                "publishedAt": "2026-05-26T10:00:00",
                "content": "🌎⚽ ¿Vienes a #México por el #Mundial? ... está escondido en #Chihuahua",
                "views": 10000,
                "interactions": 800,  # 8.0%
                "likes": 600,
                "comments": 50,
                "shares": 100,
                "saved": 50,
                "averageWatchTime": 9,
                "url": "https://instagram.com/reel/r1",
            }
        ],
    )
    with httpx.Client() as cli:
        piezas = _fuente(cli).mejores_piezas("claro_sports", RANGO, 5)

    assert len(piezas) == 1
    reel = piezas[0]
    assert reel.id == "r1"
    assert reel.plataforma == Plataforma.instagram
    assert reel.formato == "reel"
    assert reel.visualizaciones == 10000
    assert reel.engagement_pct == pytest.approx(8.0)
    # El caption del reel trae los hashtags (lo que /posts no daba para IG/FB).
    assert "#chihuahua" in reel.texto.lower()
    assert reel.likes == 600 and reel.comentarios == 50
    assert reel.url == "https://instagram.com/reel/r1"


@respx.mock
def test_reel_facebook_cuenta_interacciones_no_la_tasa():
    """En FB el reel trae `engagement` como TASA (%), no conteo; las interacciones son
    reacciones (`postVideoReactions`) + acciones sociales (`postVideoSocialActions`)."""
    _mock_posts("facebook", [])
    _mock_reels(
        "facebook",
        [
            {
                "reelId": "fbr1",
                "created": "2026-05-26T10:00:00",
                "description": "Reel FB de campaña #Chihuahua",
                "blueReelsPlayCount": 2530,
                "postImpressionsUnique": 2100,  # alcance único del reel FB
                "engagement": 0.8352,  # TASA en %, NO interacciones -> NO debe usarse
                "postVideoReactions": 16,
                "postVideoSocialActions": 6,
                "reelUrl": "https://facebook.com/reel/fbr1",
            }
        ],
    )
    marcas_fb = {"claro_sports": {**MARCAS["claro_sports"], "plataformas": [Plataforma.facebook]}}
    with httpx.Client() as cli:
        piezas = FuenteMetricool(marcas=marcas_fb, cliente=cli).mejores_piezas(
            "claro_sports", RANGO, 5
        )

    assert len(piezas) == 1
    reel = piezas[0]
    assert reel.plataforma == Plataforma.facebook
    assert reel.formato == "reel"
    assert reel.visualizaciones == 2530
    # alcance único del reel FB (postImpressionsUnique), distinto de las reproducciones.
    assert reel.alcance == 2100
    # interacciones = 16 reacciones + 6 acciones sociales = 22 (NO 0 por la tasa 0.83).
    assert reel.interacciones == 22
    # engagement recalculado sobre el conteo real (22/2530), redondeado a 1 decimal.
    assert reel.engagement_pct == pytest.approx(0.9)


@respx.mock
def test_reels_que_fallan_no_rompen_las_piezas():
    """Si el endpoint de reels falla, las piezas de /posts siguen saliendo (degrada a [])."""
    _mock_posts("instagram", [_post_ig("p1", 5000, 250)])
    respx.get(f"{BASE}/v2/analytics/reels/instagram").mock(
        return_value=httpx.Response(500, json={"error": "boom"})
    )
    with httpx.Client() as cli:
        piezas = _fuente(cli).mejores_piezas("claro_sports", RANGO, 5)
    assert [p.id for p in piezas] == ["p1"]  # el post sobrevive aunque el reel reviente


@respx.mock
def test_formato_feed_prefix_y_video_views_sin_colision():
    """Vocabulario REAL de Metricool: 'feed_carousel_album'/'feed_image' y que
    `video_views` NO copie las visualizaciones generales en posts de imagen."""
    posts = {
        "data": [
            {
                "id": "carrusel",
                "publishedAt": "2026-05-20T12:00:00",
                "impressions": 968213,
                "views": 968213,  # vistas GENERALES, no de vídeo
                "interactions": 55737,
                "mediaType": "feed_carousel_album",
            },
            {
                "id": "imagen",
                "publishedAt": "2026-05-21T12:00:00",
                "impressions": 297119,
                "views": 297119,
                "interactions": 3688,
                "mediaType": "feed_image",
            },
        ]
    }
    respx.get(f"{BASE}/v2/analytics/posts/instagram").mock(
        return_value=httpx.Response(200, json=posts)
    )
    with httpx.Client() as cli:
        piezas = _fuente(cli).mejores_piezas("claro_sports", RANGO, 5)

    por_id = {p.id: p for p in piezas}
    assert por_id["carrusel"].formato == "carrusel"  # prefijo feed_ resuelto
    assert por_id["imagen"].formato == "foto"
    # Sin alias "views" goloso: video_views None en imagen/carrusel (no copia impresiones).
    assert por_id["carrusel"].video_views is None
    assert por_id["imagen"].video_views is None


@respx.mock
def test_metricas_de_post_parsea_granulares():
    """metricas_de_post mapea los campos granulares del post al contrato."""
    posts = {
        "data": [
            {
                "id": "abc",
                "publishedAt": "2026-05-20T12:00:00",
                "impressions": 5000,
                "interactions": 250,
                "url": "https://instagram.com/p/abc",
                "likes": 180,
                "comments": 40,
                "shares": 20,
                "saves": 10,
                "mediaType": "VIDEO",
                "avgWatchTime": 22,
            }
        ]
    }
    respx.get(f"{BASE}/v2/analytics/posts/instagram").mock(
        return_value=httpx.Response(200, json=posts)
    )
    with httpx.Client() as cli:
        m = _fuente(cli).metricas_de_post("claro_sports", Plataforma.instagram, "abc")

    assert m is not None and m.encontrado
    assert m.likes == 180
    assert m.comentarios == 40
    assert m.compartidos == 20
    assert m.guardados == 10
    assert m.formato == "video"
    assert m.tiempo_medio_vis_s == 22
    # Seguidores atribuidos al post: Metricool no lo trajo -> None (no se inventa).
    assert m.seguidores_netos_atribuidos is None


@respx.mock
def test_interacciones_se_derivan_del_desglose_si_el_agregado_es_cero():
    """Metricool a veces da interactions=0 con el desglose poblado (típico en FB): se
    deriva interacciones = likes+comentarios+compartidos+guardados, y el engagement deja
    de ser un 0 falso. Aplica tanto a mejores_piezas (Pieza) como a metricas_de_post."""
    posts = {
        "data": [
            {
                "id": "fb1",
                "publishedAt": "2026-05-20T12:00:00",
                "impressions": 13400,
                "interactions": 0,  # agregado 0...
                "likes": 27,
                "comments": 1,
                "shares": 5,  # ...pero el desglose SÍ viene (27+1+5 = 33)
                "mediaType": "feed_image",
            }
        ]
    }
    respx.get(f"{BASE}/v2/analytics/posts/instagram").mock(
        return_value=httpx.Response(200, json=posts)
    )
    with httpx.Client() as cli:
        fuente = _fuente(cli)
        piezas = fuente.mejores_piezas("claro_sports", RANGO, 5)
        m = fuente.metricas_de_post("claro_sports", Plataforma.instagram, "fb1")

    assert piezas[0].interacciones == 33  # derivado del desglose, no el 0 agregado
    assert piezas[0].engagement_pct > 0  # ya no es un 0 falso (se redondea a 1 decimal)
    assert m is not None and m.interacciones == 33


@respx.mock
def test_interacciones_toma_el_maximo_si_el_agregado_es_diminuto():
    """Agregado roto-bajo (interactions=12) pero desglose enorme (likes=23599, típico en
    TikTok): se toma el MÁXIMO -> 23599, no el 12 que daría engagement falsamente nulo."""
    posts = {
        "data": [
            {
                "id": "tk1",
                "publishedAt": "2026-05-20T12:00:00",
                "views": 228984,
                "interactions": 12,  # agregado roto-bajo...
                "likes": 23599,  # ...pero el desglose es enorme
                "mediaType": "video",
            }
        ]
    }
    respx.get(f"{BASE}/v2/analytics/posts/instagram").mock(
        return_value=httpx.Response(200, json=posts)
    )
    with httpx.Client() as cli:
        piezas = _fuente(cli).mejores_piezas("claro_sports", RANGO, 5)

    assert piezas[0].interacciones == 23599  # max(12, 23599)
    assert piezas[0].engagement_pct > 0


def test_fecha_parsea_objeto_publishedAt_y_no_fabrica():
    """_fecha extrae el `dateTime` del OBJETO publishedAt de Metricool, acepta ISO/epoch,
    y devuelve None (sin fabricar) cuando no hay fecha reconocible."""
    # Metricool devuelve publishedAt como objeto {dateTime, timezone}.
    assert _fecha({"dateTime": "2026-05-20T07:27:58", "timezone": "Europe/Madrid"}) == date(2026, 5, 20)
    assert _fecha("2026-05-20T12:00:00") == date(2026, 5, 20)  # string ISO con hora
    assert _fecha("2026-05-20") == date(2026, 5, 20)  # string fecha
    assert isinstance(_fecha(1716163200), date)  # epoch segundos
    # Sin fecha reconocible -> None (NO se fabrica una fecha de hoy).
    assert _fecha(None) is None
    assert _fecha("") is None
    assert _fecha({}) is None
    assert _fecha({"timezone": "Europe/Madrid"}) is None  # objeto sin dateTime


@respx.mock
def test_piezas_sin_fecha_o_fuera_de_rango_se_descartan():
    """No se fabrica fecha (post sin publishedAt se descarta) y se filtra por la fecha
    REAL contra el rango (mes:2026-05); solo sobrevive la pieza con fecha real en rango."""
    posts = {
        "data": [
            {  # fecha real EN rango -> se queda
                "id": "ok",
                "publishedAt": {"dateTime": "2026-05-15T10:00:00", "timezone": "Europe/Madrid"},
                "impressions": 5000,
                "interactions": 100,
            },
            {  # SIN fecha -> se descarta (no se sella con hoy)
                "id": "sin_fecha",
                "impressions": 9999,
                "interactions": 200,
            },
            {  # fecha real FUERA de rango (enero) -> se descarta
                "id": "fuera",
                "publishedAt": {"dateTime": "2026-01-10T10:00:00", "timezone": "Europe/Madrid"},
                "impressions": 8888,
                "interactions": 300,
            },
        ]
    }
    respx.get(f"{BASE}/v2/analytics/posts/instagram").mock(
        return_value=httpx.Response(200, json=posts)
    )
    with httpx.Client() as cli:
        piezas = _fuente(cli).mejores_piezas("claro_sports", RANGO, 50)

    assert {p.id for p in piezas} == {"ok"}
    assert piezas[0].publicado == date(2026, 5, 15)


@respx.mock
def test_seguidores_van_con_subject_account_y_metrica_por_red():
    """La serie de followers se pide con subject=account y la métrica correcta por red.

    Instagram usa la métrica `followers`.
    """
    _mock_perfiles(_perfil(instagram="x"))
    _mock_posts("instagram", [_post_ig("p1", 100, 10)])
    capturadas: list[httpx.Request] = []

    def responder(request: httpx.Request) -> httpx.Response:
        capturadas.append(request)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "metric": "followers",
                        "values": [
                            {"dateTime": "2026-05-20T00:00:00", "value": 1000},
                            {"dateTime": "2026-05-26T00:00:00", "value": 1050},
                        ],
                    }
                ]
            },
        )

    respx.get(f"{BASE}/v2/analytics/timelines").mock(side_effect=responder)
    with httpx.Client() as cli:
        resumen = _fuente(cli).resumen("claro_sports", RANGO)

    assert resumen.seguidores_netos == 50  # 1050 - 1000
    assert capturadas, "no se llamó a timelines para followers"
    req = capturadas[0]
    assert req.url.params.get("subject") == "account"
    assert req.url.params.get("metric") == "followers"  # instagram


@respx.mock
def test_seguidores_netos_ultimo_menos_primero():
    """seguidores_netos = (último punto - primer punto) de la serie de followers."""
    # IG conectada + con posts -> entra en por_plataforma -> se le calculan seguidores.
    _mock_perfiles(_perfil(instagram="x"))
    _mock_posts("instagram", [_post_ig("p1", 100, 10)])

    def responder(request: httpx.Request) -> httpx.Response:
        # Comunidad (followers): 1000 al inicio del periodo, 1075 al final -> neto +75.
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "metric": "followers",
                        "values": [
                            {"dateTime": "2026-05-20T00:00:00", "value": 1000},
                            {"dateTime": "2026-05-23T00:00:00", "value": 1050},
                            {"dateTime": "2026-05-26T00:00:00", "value": 1075},
                        ],
                    }
                ]
            },
        )

    respx.get(f"{BASE}/v2/analytics/timelines").mock(side_effect=responder)
    with httpx.Client() as cli:
        resumen = _fuente(cli).resumen("claro_sports", RANGO)

    # Una sola plataforma (instagram) configurada en MARCAS -> neto = 1075 - 1000.
    assert resumen.seguidores_netos == 75


@respx.mock
def test_seguidores_netos_degrada_a_cero_sin_serie():
    """Sin serie de followers (o un solo punto) seguidores_netos = 0, no inventa."""
    _mock_perfiles(_perfil(instagram="x"))
    _mock_posts("instagram", [_post_ig("p1", 100, 10)])

    def responder(request: httpx.Request) -> httpx.Response:
        # Serie con un único punto: no hay variación medible -> 0.
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "metric": "followers",
                        "values": [{"dateTime": "2026-05-20T00:00:00", "value": 1000}],
                    }
                ]
            },
        )

    respx.get(f"{BASE}/v2/analytics/timelines").mock(side_effect=responder)
    with httpx.Client() as cli:
        resumen = _fuente(cli).resumen("claro_sports", RANGO)

    assert resumen.seguidores_netos == 0


@respx.mock
def test_cuentas_lista_marcas_configuradas():
    with httpx.Client() as cli:
        cuentas = _fuente(cli).cuentas()
    assert [c.id for c in cuentas] == ["claro_sports"]
    assert cuentas[0].nombre == "Claro Sports"
    assert cuentas[0].plataformas == [Plataforma.instagram]


# --- Sin credenciales: fuente vacía, NO datos de muestra --------------------


def test_sin_token_no_muestra_datos_falsos():
    """fuente='metricool' sin credenciales -> Metricool VACÍA (sin cuentas), no muestra."""
    cfg = Config(fuente="metricool", metricool=MetricoolConfig())  # sin marcas
    fuente = construir_fuente(cfg)
    assert isinstance(fuente, FuenteMetricool)
    assert not isinstance(fuente, FuenteMuestra)
    assert fuente.nombre == "metricool"
    assert fuente.cuentas() == []  # estado vacío honesto, sin inventar cifras


def test_marca_sin_credenciales_completas_queda_vacia():
    """Una marca sin token/user_id propios NI default => no configurada => fuente vacía."""
    cfg = Config(
        fuente="metricool",
        metricool=MetricoolConfig(marcas={"claro_sports": {"blog_id": "1234567"}}),
    )
    fuente = construir_fuente(cfg)
    assert isinstance(fuente, FuenteMetricool)
    assert fuente.cuentas() == []


def test_con_credenciales_por_marca_construye_metricool():
    """Con token + userId + blogId PROPIOS de la marca, devuelve FuenteMetricool."""
    cfg = Config(
        fuente="metricool",
        metricool=MetricoolConfig(
            marcas={
                "claro_sports": {
                    "user_token": "TOK",
                    "user_id": "999",
                    "blog_id": "1234567",
                }
            },
        ),
    )
    fuente = construir_fuente(cfg)
    assert isinstance(fuente, FuenteMetricool)
    assert fuente.nombre == "metricool"


def test_default_global_completa_marca_sin_token():
    """`[metricool] user_token/user_id` (default) completan una marca con solo blog_id."""
    mc = MetricoolConfig(
        user_token="GLOBAL",
        user_id="111",
        marcas={"claro_sports": {"blog_id": "1234567"}},
    )
    assert mc.configurada
    resueltas = mc.marcas_configuradas()
    assert resueltas["claro_sports"]["user_token"] == "GLOBAL"
    assert resueltas["claro_sports"]["user_id"] == "111"


def test_marca_propia_gana_al_default():
    """El token/user_id PROPIOS de la marca prevalecen sobre el default global."""
    mc = MetricoolConfig(
        user_token="GLOBAL",
        user_id="111",
        marcas={
            "claro_sports": {"user_token": "PROPIO", "user_id": "222", "blog_id": "1"},
        },
    )
    resueltas = mc.marcas_configuradas()
    assert resueltas["claro_sports"]["user_token"] == "PROPIO"
    assert resueltas["claro_sports"]["user_id"] == "222"


def test_solo_marcas_configuradas_pasan_a_la_fuente():
    """Marcas sin credenciales completas se OMITEN; solo las completas llegan."""
    mc = MetricoolConfig(
        marcas={
            "claro_sports": {"user_token": "T1", "user_id": "1", "blog_id": "b1"},
            "unotv": {"blog_id": "b2"},  # sin token ni default -> omitida
        }
    )
    configuradas = mc.marcas_configuradas()
    assert set(configuradas) == {"claro_sports"}


def test_metricool_config_configurada():
    assert not MetricoolConfig().configurada
    # token global pero sin marcas -> no hay nada que configurar
    assert not MetricoolConfig(user_token="t", user_id="1").configurada
    # marca con blog_id pero sin token ni default -> no configurada
    assert not MetricoolConfig(marcas={"m": {"blog_id": "1"}}).configurada
    # marca con sus tres credenciales propias -> configurada
    assert MetricoolConfig(
        marcas={"m": {"user_token": "t", "user_id": "1", "blog_id": "1"}}
    ).configurada


@respx.mock
def test_fuente_resuelve_credenciales_distintas_por_marca():
    """Dos marcas (cuentas Metricool distintas) -> headers/params PROPIOS cada una."""
    capturadas: list[httpx.Request] = []

    def responder(request: httpx.Request) -> httpx.Response:
        capturadas.append(request)
        return httpx.Response(200, json={"data": [_post_ig("p1", 100, 10)]})

    # Perfiles por blog_id (ambas con instagram conectada) + posts que capturan la auth.
    respx.get(f"{BASE}/admin/simpleProfiles").mock(
        return_value=httpx.Response(
            200,
            json=[{"id": "blogCS", "instagram": "cs"}, {"id": "blogUNO", "instagram": "uno"}],
        )
    )
    respx.get(f"{BASE}/v2/analytics/posts/instagram").mock(side_effect=responder)
    marcas = {
        "claro_sports": {
            "user_token": "TOK_CS",
            "user_id": "111",
            "blog_id": "blogCS",
            "plataformas": [Plataforma.instagram],
        },
        "unotv": {
            "user_token": "TOK_UNO",
            "user_id": "222",
            "blog_id": "blogUNO",
            "plataformas": [Plataforma.instagram],
        },
    }
    with httpx.Client() as cli:
        f = FuenteMetricool(marcas=marcas, cliente=cli)
        f.resumen("claro_sports", RANGO)
        f.resumen("unotv", RANGO)

    por_token = {r.headers.get("X-Mc-Auth"): r for r in capturadas}
    assert set(por_token) == {"TOK_CS", "TOK_UNO"}
    assert por_token["TOK_CS"].url.params.get("userId") == "111"
    assert por_token["TOK_CS"].url.params.get("blogId") == "blogCS"
    assert por_token["TOK_UNO"].url.params.get("userId") == "222"
    assert por_token["TOK_UNO"].url.params.get("blogId") == "blogUNO"


@respx.mock
def test_serie_diaria_suma_piezas_por_dia_de_publicacion():
    """serie_diaria agrupa las PIEZAS por su día de publicación (vis+int), desde posts."""
    _mock_perfiles(_perfil(instagram="x"))
    _mock_posts(
        "instagram",
        [
            _post_ig("p1", 1000, 50, "2026-05-20T10:00:00"),
            _post_ig("p3", 500, 20, "2026-05-20T15:00:00"),  # mismo día que p1 -> suma
            _post_ig("p2", 2000, 100, "2026-05-21T10:00:00"),
        ],
    )
    with httpx.Client() as cli:
        puntos = _fuente(cli).serie_diaria("claro_sports", RANGO)

    por_fecha = {str(p.fecha): p for p in puntos}
    assert set(por_fecha) == {"2026-05-20", "2026-05-21"}
    assert por_fecha["2026-05-20"].visualizaciones == 1500  # 1000 + 500
    assert por_fecha["2026-05-20"].interacciones == 70  # 50 + 20
    assert por_fecha["2026-05-21"].visualizaciones == 2000
    assert por_fecha["2026-05-21"].interacciones == 100


@respx.mock
def test_serie_diaria_degrada_si_falla():
    """Si la API de posts falla, la serie sale vacía (no inventa días)."""
    _mock_perfiles(_perfil(instagram="x"))
    respx.get(f"{BASE}/v2/analytics/posts/instagram").mock(
        return_value=httpx.Response(403, json={"error": "boom"})
    )
    with httpx.Client() as cli:
        puntos = _fuente(cli).serie_diaria("claro_sports", RANGO)
    assert puntos == []


@respx.mock
def test_campanias_ads_parsea_filtra_y_degrada_por_provider():
    """Lo INORGÁNICO: `/v2/advertising/campaigns` por provider. Solo campañas con entrega
    (IMPRESSIONS>0); el caption de un post impulsado se extrae del nombre; un provider sin
    Ads (TikTok, 403) se OMITE sin romper el resto."""

    def responder(request):
        if request.url.params.get("providers[]") == "tiktokads":
            return httpx.Response(403, json={"detail": "no ads provider"})
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "name": 'Publicación: "MÉXICO TAMBIÉN SE DESCUBRE"',
                        "currency": "MXN",
                        "start": {"dateTime": "2026-05-25T21:40:19"},
                        "stop": {"dateTime": "2026-06-08T21:40:19"},
                        "metrics": {"IMPRESSIONS": 118696.0, "SPENT": 993.62, "CLICKS": 3077.0},
                    },
                    {
                        "name": "ALCANCE CAMPAÑA CHIHUAHUA",
                        "currency": "MXN",
                        "metrics": {"IMPRESSIONS": 244093.0, "SPENT": 117.04, "CLICKS": 0.0},
                    },
                    {"name": "Sin entrega", "metrics": {"IMPRESSIONS": 0.0, "SPENT": 0.0}},
                ]
            },
        )

    respx.get(f"{BASE}/v2/advertising/campaigns").mock(side_effect=responder)
    with httpx.Client() as cli:
        ads = _fuente(cli).campanias_ads("claro_sports", RANGO)

    # 2 con entrega (la de 0 impresiones fuera); tiktokads (403) omitido sin romper.
    assert len(ads) == 2
    boost = next(a for a in ads if a.es_post_impulsado)
    assert boost.impresiones == 118696 and boost.gasto == 993.62 and boost.clics == 3077
    assert boost.caption == "MÉXICO TAMBIÉN SE DESCUBRE" and boost.red == "facebook"
    assert boost.inicio == "2026-05-25" and boost.fin == "2026-06-08"
    named = next(a for a in ads if not a.es_post_impulsado)
    assert named.nombre == "ALCANCE CAMPAÑA CHIHUAHUA" and named.impresiones == 244093
    assert named.caption == ""


@respx.mock
def test_campanias_ads_respeta_proveedores_por_marca():
    """`ads_proveedores` por marca acota los providers consultados (p.ej. sin licencia de
    TikTok Ads, ["facebookads"]): no se pide el provider sin licencia, ni 403 por barrido."""
    marcas = {"claro_sports": {**MARCAS["claro_sports"], "ads_proveedores": ["facebookads"]}}
    ruta = respx.get(f"{BASE}/v2/advertising/campaigns").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    with httpx.Client() as cli:
        FuenteMetricool(marcas=marcas, cliente=cli).campanias_ads("claro_sports", RANGO)

    providers = [c.request.url.params.get("providers[]") for c in ruta.calls]
    assert providers == ["facebookads"]  # tiktokads NI se consulta
