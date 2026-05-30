"""Tests del adapter `FuenteMetricol` (consumidor de la API REST de Metricool).

SIN red real: toda llamada HTTP va mockeada con respx. Cubren:
  - mapeo de una respuesta Metricool de ejemplo a la forma de `FuenteMetricas`
    (ResumenMetricas + Pieza), respetando el contrato;
  - degradación honesta a `muestra` cuando no hay token (vía `construir_fuente`);
  - que `FuenteMetricol` cumple el Protocol `FuenteMetricas`;
  - autenticación: header `X-Mc-Auth` + query params `userId`/`blogId`.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from keni_metricas.config import Config, MetricoolConfig, construir_fuente
from keni_metricas.fuentes.base import FuenteMetricas
from keni_metricas.fuentes.metricol import BASE, FuenteMetricol
from keni_metricas.fuentes.muestra import FuenteMuestra
from keni_metricas.schema import Plataforma, ResumenMetricas

RANGO = "semana"

MARCAS = {
    "claro_sports": {
        "user_token": "TOK",
        "user_id": "999",
        "blog_id": "1234567",
        "nombre": "Claro Sports",
        "plataformas": [Plataforma.instagram],
    }
}


def _fuente(cliente: httpx.Client) -> FuenteMetricol:
    return FuenteMetricol(marcas=MARCAS, cliente=cliente)


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


@respx.mock
def test_es_una_fuente_metricas():
    """FuenteMetricol cumple el contrato `FuenteMetricas` (mismo que muestra)."""
    with httpx.Client() as cli:
        f = _fuente(cli)
        assert isinstance(f, FuenteMetricas)
        assert f.nombre == "metricool"


@respx.mock
def test_resumen_mapea_respuesta_metricool():
    """Una respuesta de Metricool se mapea a ResumenMetricas (contrato intacto)."""
    # Instagram: vis=impressions, int=interactions, alc=reach (PLATAFORMAS_CON_ALCANCE).
    def responder(request: httpx.Request) -> httpx.Response:
        metric = request.url.params.get("metric")
        valores = {"impressions": 10000, "interactions": 300, "reach": 8000}
        return httpx.Response(200, json=_serie(valores.get(metric, 0)))

    ruta = respx.get(f"{BASE}/v2/analytics/timelines").mock(side_effect=responder)

    with httpx.Client() as cli:
        resumen = _fuente(cli).resumen("claro_sports", RANGO)

    assert ruta.called
    assert isinstance(resumen, ResumenMetricas)
    assert resumen.cuenta == "claro_sports"
    assert resumen.fuente == "metricool"
    assert resumen.visualizaciones == 10000
    assert resumen.interacciones == 300
    assert resumen.alcance == 8000  # Meta/IG sí mide alcance
    assert resumen.engagement_pct == pytest.approx(3.0)  # 300/10000 -> 3.0
    assert [m.plataforma for m in resumen.por_plataforma] == [Plataforma.instagram]
    assert resumen.cobertura is not None and resumen.cobertura.completa


@respx.mock
def test_resumen_envia_autenticacion_correcta():
    """X-Mc-Auth en header; userId/blogId en query (doc oficial de Metricool)."""
    capturadas: list[httpx.Request] = []

    def responder(request: httpx.Request) -> httpx.Response:
        capturadas.append(request)
        return httpx.Response(200, json=_serie(1))

    respx.get(f"{BASE}/v2/analytics/timelines").mock(side_effect=responder)
    with httpx.Client() as cli:
        _fuente(cli).resumen("claro_sports", RANGO)

    assert capturadas, "no se hizo ninguna llamada"
    req = capturadas[0]
    assert req.headers.get("X-Mc-Auth") == "TOK"
    assert req.url.params.get("userId") == "999"
    assert req.url.params.get("blogId") == "1234567"


@respx.mock
def test_plataforma_que_falla_se_omite_en_cobertura():
    """Si la API falla en una plataforma, se OMITE (no inventa ceros)."""
    respx.get(f"{BASE}/v2/analytics/timelines").mock(
        return_value=httpx.Response(500, json={"error": "boom"})
    )
    with httpx.Client() as cli:
        resumen = _fuente(cli).resumen("claro_sports", RANGO)

    assert resumen.por_plataforma == []
    assert resumen.cobertura is not None
    assert Plataforma.instagram in resumen.cobertura.omitidas


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
            },
            {
                "id": "p2",
                "publishedAt": "2026-05-21T12:00:00",
                "impressions": 2000,
                "interactions": 200,  # 10.0% -> debe ir primero
                "text": "Otra pieza",
                "url": "https://instagram.com/p/p2",
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
    assert isinstance(fuente, FuenteMetricol)
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
    assert isinstance(fuente, FuenteMetricol)
    assert fuente.cuentas() == []


def test_con_credenciales_por_marca_construye_metricol():
    """Con token + userId + blogId PROPIOS de la marca, devuelve FuenteMetricol."""
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
    assert isinstance(fuente, FuenteMetricol)
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
        return httpx.Response(200, json=_serie(1))

    respx.get(f"{BASE}/v2/analytics/timelines").mock(side_effect=responder)
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
        f = FuenteMetricol(marcas=marcas, cliente=cli)
        f.resumen("claro_sports", RANGO)
        f.resumen("unotv", RANGO)

    por_token = {r.headers.get("X-Mc-Auth"): r for r in capturadas}
    assert set(por_token) == {"TOK_CS", "TOK_UNO"}
    assert por_token["TOK_CS"].url.params.get("userId") == "111"
    assert por_token["TOK_CS"].url.params.get("blogId") == "blogCS"
    assert por_token["TOK_UNO"].url.params.get("userId") == "222"
    assert por_token["TOK_UNO"].url.params.get("blogId") == "blogUNO"


@respx.mock
def test_serie_diaria_suma_por_dia():
    """serie_diaria conserva los valores por día (vis+int) y los suma por fecha."""
    def responder(request: httpx.Request) -> httpx.Response:
        metric = request.url.params.get("metric")
        base = {"impressions": 1000, "interactions": 50}.get(metric, 0)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "metric": metric,
                        "values": [
                            {"dateTime": "2026-05-20T00:00:00", "value": base},
                            {"dateTime": "2026-05-21T00:00:00", "value": base * 2},
                        ],
                    }
                ]
            },
        )

    respx.get(f"{BASE}/v2/analytics/timelines").mock(side_effect=responder)
    with httpx.Client() as cli:
        puntos = _fuente(cli).serie_diaria("claro_sports", RANGO)

    assert [str(p.fecha) for p in puntos] == ["2026-05-20", "2026-05-21"]
    assert puntos[0].visualizaciones == 1000 and puntos[0].interacciones == 50
    assert puntos[1].visualizaciones == 2000 and puntos[1].interacciones == 100


@respx.mock
def test_serie_diaria_degrada_si_falla():
    """Si la API falla, la serie sale vacía (no inventa días)."""
    respx.get(f"{BASE}/v2/analytics/timelines").mock(
        return_value=httpx.Response(500, json={"error": "boom"})
    )
    with httpx.Client() as cli:
        puntos = _fuente(cli).serie_diaria("claro_sports", RANGO)
    assert puntos == []
