"""Analíticas R2 de métricas: seguidores, desglose, crosstab, correlación.

Estos endpoints exponen 4 lecturas nuevas de `keni_metricas.servicio` por la API HTTP,
el contrato tipado (esquema_api) y las MCP tools. Para no depender de los datos de
muestra concretos (ni pegar a Metricool), se MOCKEAN las `servicio.construir_*` con
shapes deterministas; el camino que se prueba es consola (cache lazy-fill + endpoint +
serialización), no la fuente de métricas.
"""

from __future__ import annotations

import anyio
import pytest

from keni_consola import app as app_modulo
from keni_consola import auth, mcp_operativo
from keni_metricas import servicio

from .conftest import _cliente

OWNER = "duena-r2"
OWNER_PASS = "contraseña-larga-de-prueba-r2"


@pytest.fixture
def cliente(entorno):
    return _cliente()


def _crear_owner_admin() -> str:
    if auth.autenticar(OWNER, OWNER_PASS) is None:
        auth.crear_usuario(OWNER, OWNER_PASS, rol="admin", debe_cambiar_password=False)
    return OWNER


# --------------------------------------------------------------------------- #
# Shapes de muestra (deterministas) para mockear la fachada de métricas         #
# --------------------------------------------------------------------------- #


def _serie_seguidores(rango="mes", marca=None):
    return {
        "cuenta": marca,
        "rango": rango,
        "etiqueta_rango": "ignored",  # el endpoint lo recalcula
        "periodo": {"desde": "2026-05-01", "hasta": "2026-05-31"},
        "fuente": "muestra",
        "puntos": [
            {"fecha": "2026-05-01", "total": 1000, "por_red": {"facebook": 600, "instagram": 400}},
            {"fecha": "2026-05-02", "total": 1010, "por_red": {"facebook": 605, "instagram": 405}},
        ],
        "neto": 10,
        "neto_por_red": {"facebook": 5, "instagram": 5},
    }


def _serie_seguidores_vacia(rango="mes", marca=None):
    return {
        "cuenta": marca,
        "rango": rango,
        "etiqueta_rango": "ignored",
        "periodo": {"desde": "2026-05-01", "hasta": "2026-05-31"},
        "fuente": "muestra",
        "puntos": [],
        "neto": 0,
        "neto_por_red": {},
    }


def _desglose(rango="mes", marca=None):
    return {
        "rango": rango,
        "etiqueta_rango": "ignored",
        "periodo": {"desde": "2026-05-01", "hasta": "2026-05-31"},
        "fuente": "muestra",
        "celdas": [
            {
                "marca": "claro_sports", "red": "facebook",
                "likes": 100, "comentarios": 20, "compartidos": 10, "guardados": 5,
                "video_views": 500, "interacciones": 135, "visualizaciones": 2000,
                "engagement_pct": 6.75, "n_piezas": 4,
            }
        ],
        "totales": {
            "likes": 100, "comentarios": 20, "compartidos": 10, "guardados": 5,
            "video_views": 500, "interacciones": 135, "visualizaciones": 2000,
            "engagement_pct": 6.75, "n_piezas": 4,
        },
    }


def _crosstab(rango="mes", marca=None):
    return {
        "rango": rango,
        "etiqueta_rango": "ignored",
        "periodo": {"desde": "2026-05-01", "hasta": "2026-05-31"},
        "fuente": "muestra",
        "celdas": [
            {
                "marca": "claro_sports", "red": "instagram", "formato": "reel",
                "n_piezas": 3, "visualizaciones": 5000, "interacciones": 400,
                "engagement_pct": 8.0, "rendimiento_relativo_medio": 1.2,
            },
            {
                "marca": "claro_sports", "red": "facebook", "formato": None,
                "n_piezas": 1, "visualizaciones": 100, "interacciones": 5,
                "engagement_pct": 5.0, "rendimiento_relativo_medio": None,
            },
        ],
    }


def _correlacion(rango="mes", marca=None):
    return {
        "rango": rango,
        "etiqueta_rango": "ignored",
        "periodo": {"desde": "2026-05-01", "hasta": "2026-05-31"},
        "fuente": "muestra",
        "items": [
            {
                "marca": "claro_sports", "red": "instagram", "fecha": "2026-05-01",
                "seguidores_ganados": 50, "n_posts": 2, "seguidores_por_post": 25.0,
                "post_estrella": {
                    "id": "p1", "titulo": "Gol", "engagement_pct": 9.1,
                    "url": "https://example.com/p1",
                },
            },
            {
                "marca": "claro_sports", "red": "facebook", "fecha": "2026-05-02",
                "seguidores_ganados": 0, "n_posts": 0, "seguidores_por_post": None,
                "post_estrella": None,
            },
        ],
        "nota": "Correlación, no causalidad.",
    }


def _mock_servicio(monkeypatch, **fns):
    """Parchea las construir_* de la fachada (la cache las llama vía `servicio.*`)."""
    for nombre, fn in fns.items():
        monkeypatch.setattr(servicio, nombre, fn, raising=False)


# --------------------------------------------------------------------------- #
# /api/metricas/seguidores                                                     #
# --------------------------------------------------------------------------- #


def test_seguidores_200_y_shape(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_serie_seguidores=_serie_seguidores)
    r = cliente.get("/api/metricas/seguidores?rango=mes&marca=claro_sports")
    assert r.status_code == 200
    data = r.json()
    assert data["cuenta"] == "claro_sports"
    assert data["fuente"] == "muestra"
    assert data["neto"] == 10
    assert data["neto_por_red"] == {"facebook": 5, "instagram": 5}
    assert data["puntos"][0]["por_red"]["facebook"] == 600
    # El endpoint inyecta etiqueta_rango legible + generado_en (cache).
    assert data["etiqueta_rango"] and data["etiqueta_rango"] != "ignored"
    assert data["generado_en"]


def test_seguidores_degrada_con_honestidad_si_vacio(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_serie_seguidores=_serie_seguidores_vacia)
    r = cliente.get("/api/metricas/seguidores?rango=semana")
    assert r.status_code == 200
    data = r.json()
    assert data["puntos"] == []
    assert data["neto"] == 0
    assert data["neto_por_red"] == {}


# --------------------------------------------------------------------------- #
# /api/metricas/desglose                                                       #
# --------------------------------------------------------------------------- #


def test_desglose_200_y_shape(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_desglose_interacciones=_desglose)
    r = cliente.get("/api/metricas/desglose?rango=mes&marca=claro_sports")
    assert r.status_code == 200
    data = r.json()
    assert data["fuente"] == "muestra"
    celda = data["celdas"][0]
    assert celda["marca"] == "claro_sports" and celda["red"] == "facebook"
    assert celda["likes"] == 100 and celda["n_piezas"] == 4
    assert data["totales"]["interacciones"] == 135
    assert data["etiqueta_rango"] != "ignored"
    assert data["generado_en"]


def test_desglose_degrada_sin_celdas(cliente, monkeypatch):
    def vacio(rango="mes", marca=None):
        d = _desglose(rango, marca)
        d["celdas"] = []
        d["totales"] = {}
        return d

    _mock_servicio(monkeypatch, construir_desglose_interacciones=vacio)
    r = cliente.get("/api/metricas/desglose?rango=7d")
    assert r.status_code == 200
    assert r.json()["celdas"] == []


# --------------------------------------------------------------------------- #
# /api/metricas/crosstab                                                       #
# --------------------------------------------------------------------------- #


def test_crosstab_200_y_shape_con_nullables(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_crosstab=_crosstab)
    r = cliente.get("/api/metricas/crosstab?rango=mes&marca=claro_sports")
    assert r.status_code == 200
    data = r.json()
    assert data["fuente"] == "muestra"
    reel = data["celdas"][0]
    assert reel["formato"] == "reel" and reel["rendimiento_relativo_medio"] == 1.2
    # Celda con formato/rendimiento nulos (degradación honesta, no 0 inventado).
    nulo = data["celdas"][1]
    assert nulo["formato"] is None and nulo["rendimiento_relativo_medio"] is None
    assert data["generado_en"]


# --------------------------------------------------------------------------- #
# /api/metricas/correlacion                                                    #
# --------------------------------------------------------------------------- #


def test_correlacion_200_y_shape(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_correlacion_seguidores=_correlacion)
    r = cliente.get("/api/metricas/correlacion?rango=mes&marca=claro_sports")
    assert r.status_code == 200
    data = r.json()
    assert data["fuente"] == "muestra"
    assert data["nota"]
    estrella = data["items"][0]["post_estrella"]
    assert estrella["id"] == "p1" and estrella["url"] == "https://example.com/p1"
    # Item sin posts: ratio y post_estrella nulos (no se divide por cero ni se inventa).
    sin = data["items"][1]
    assert sin["seguidores_por_post"] is None and sin["post_estrella"] is None
    assert data["generado_en"]


def test_correlacion_degrada_sin_items(cliente, monkeypatch):
    def vacio(rango="mes", marca=None):
        d = _correlacion(rango, marca)
        d["items"] = []
        return d

    _mock_servicio(monkeypatch, construir_correlacion_seguidores=vacio)
    r = cliente.get("/api/metricas/correlacion?rango=30d")
    assert r.status_code == 200
    assert r.json()["items"] == []


# --------------------------------------------------------------------------- #
# Contrato tipado: modelos nuevos + PiezaMetrica ampliada en el esquema vivo    #
# --------------------------------------------------------------------------- #


def test_modelos_r2_estan_en_el_esquema():
    from keni_consola.esquema_api import esquema_json

    defs = esquema_json()["$defs"]
    esperados = {
        "PuntoSeguidores", "SerieSeguidores",
        "CeldaDesglose", "DesgloseInteracciones",
        "CeldaCrosstab", "Crosstab",
        "PostEstrella", "ItemCorrelacion", "CorrelacionSeguidores",
    }
    assert esperados <= set(defs)


def test_pieza_metrica_ampliada_con_desglose_granular():
    from keni_consola.esquema_api import esquema_json

    props = set(esquema_json()["$defs"]["PiezaMetrica"]["properties"])
    nuevos = {
        "likes", "comentarios", "compartidos", "guardados", "video_views",
        "tiempo_medio_vis_s", "clics_enlace", "formato", "cuenta", "rendimiento_relativo",
    }
    assert nuevos <= props


def test_modelos_r2_nullables_son_anyof_con_null():
    from keni_consola.esquema_api import esquema_json

    defs = esquema_json()["$defs"]
    # CeldaCrosstab.formato y rendimiento_relativo_medio admiten null.
    for campo in ("formato", "rendimiento_relativo_medio"):
        tipos = {m.get("type") for m in defs["CeldaCrosstab"]["properties"][campo]["anyOf"]}
        assert "null" in tipos
    # ItemCorrelacion.post_estrella y seguidores_por_post admiten null.
    assert "anyOf" in defs["ItemCorrelacion"]["properties"]["post_estrella"]
    # PiezaMetrica.likes admite null (no se inventa un 0).
    tipos_likes = {m.get("type") for m in defs["PiezaMetrica"]["properties"]["likes"]["anyOf"]}
    assert "null" in tipos_likes and "integer" in tipos_likes


# --------------------------------------------------------------------------- #
# MCP tool nueva invocable devuelve la estructura                              #
# --------------------------------------------------------------------------- #


def test_tools_r2_registradas(entorno):
    """El servidor MCP registra las 4 tools R2 de analíticas."""
    servidor = mcp_operativo.crear_servidor(OWNER)

    async def nombres():
        return {t.name for t in await servidor._mcp.list_tools()}

    tools = anyio.run(nombres)
    esperadas = {
        "keni_metricas_seguidores", "keni_metricas_desglose",
        "keni_metricas_crosstab", "keni_metricas_correlacion",
    }
    assert esperadas <= tools


def test_mcp_tool_seguidores_invocable_devuelve_estructura(entorno, monkeypatch):
    """`call_tool('keni_metricas_seguidores')` recorre tool -> /api -> servicio (mock).

    Camino completo en proceso (httpx ASGITransport): la tool es un cliente HTTP de la
    propia Consola, así que devuelve la estructura serializada del endpoint.
    """
    _mock_servicio(monkeypatch, construir_serie_seguidores=_serie_seguidores)
    _crear_owner_admin()
    api_app = app_modulo.crear_app(token="t", bootstrap=False)
    servidor = mcp_operativo.crear_servidor(OWNER)
    servidor.holder.cliente = mcp_operativo.ClienteConsola(api_app, OWNER)

    async def invocar():
        res = await servidor._mcp.call_tool(
            "keni_metricas_seguidores", {"rango": "mes", "marca": "claro_sports"}
        )
        await servidor.holder.cliente.aclose()
        return res

    res = anyio.run(invocar)
    # call_tool devuelve (bloques, dict-estructurado) en versiones recientes del SDK; en
    # cualquier forma, el payload con la estructura debe estar presente.
    payload = res[1] if isinstance(res, tuple) else res
    texto = repr(payload)
    assert "neto" in texto and "puntos" in texto


# --------------------------------------------------------------------------- #
# /api/metricas/ads (inorgánico: Meta/TikTok Ads)                              #
# --------------------------------------------------------------------------- #


def _ads(rango="mes", marca=None):
    return [
        {"nombre": "ALCANCE CAMPAÑA CHIHUAHUA", "red": "facebook", "impresiones": 244093,
         "gasto": 117.04, "clics": 50, "moneda": "MXN", "es_post_impulsado": False},
        {"nombre": 'Publicación: "MÉXICO TAMBIÉN SE DESCUBRE"', "red": "facebook",
         "impresiones": 118696, "gasto": 993.62, "clics": 3077, "moneda": "MXN",
         "es_post_impulsado": True},
    ]


def test_ads_200_shape_y_totales(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_ads=_ads)
    r = cliente.get("/api/metricas/ads?rango=mes&marca=claro_sports")
    assert r.status_code == 200
    data = r.json()
    assert len(data["ads"]) == 2
    # Totales = suma de impresiones/gasto/clics; nº de campañas; moneda de la 1ª no vacía.
    assert data["total"]["visualizaciones"] == 362789
    assert data["total"]["gasto"] == 1110.66
    assert data["total"]["clics"] == 3127
    assert data["total"]["campanias"] == 2
    assert data["total"]["moneda"] == "MXN"
    assert data["etiqueta_rango"] and data["etiqueta_rango"] != "ignored"
    assert data["generado_en"]


def test_ads_vacio_sin_inversion(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_ads=lambda rango="mes", marca=None: [])
    r = cliente.get("/api/metricas/ads?rango=7d")
    assert r.status_code == 200
    data = r.json()
    assert data["ads"] == [] and data["total"]["campanias"] == 0
    assert data["total"]["visualizaciones"] == 0
