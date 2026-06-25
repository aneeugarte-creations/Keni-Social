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


def test_seguidores_filtra_por_red(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_serie_seguidores=_serie_seguidores)
    r = cliente.get("/api/metricas/seguidores?rango=mes&marca=claro_sports&red=facebook")
    assert r.status_code == 200
    data = r.json()
    # El neto y el stock por día quedan proyectados a la red pedida.
    assert data["neto"] == 5
    assert data["neto_por_red"] == {"facebook": 5}
    assert data["puntos"][0]["total"] == 600
    assert data["puntos"][0]["por_red"] == {"facebook": 600}


def test_seguidores_red_invalida_devuelve_400(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_serie_seguidores=_serie_seguidores)
    r = cliente.get("/api/metricas/seguidores?rango=mes&red=threads")
    assert r.status_code == 400
    assert "error" in r.json()


# --------------------------------------------------------------------------- #
# /api/metricas/serie-alcance                                                  #
# --------------------------------------------------------------------------- #


def _serie_alcance(rango="mes", marca=None):
    return {
        "cuenta": marca,
        "rango": rango,
        "etiqueta_rango": "ignored",  # el endpoint lo recalcula
        "periodo": {"desde": "2026-05-01", "hasta": "2026-05-31"},
        "fuente": "muestra",
        "puntos": [
            {"fecha": "2026-05-20", "total": 12000, "por_red": {"instagram": 12000}},
            {"fecha": "2026-05-21", "total": 9000, "por_red": {"instagram": 9000}},
        ],
    }


def test_serie_alcance_200_y_shape(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_serie_alcance=_serie_alcance)
    r = cliente.get("/api/metricas/serie-alcance?rango=mes&marca=claro_sports")
    assert r.status_code == 200
    data = r.json()
    assert data["cuenta"] == "claro_sports"
    assert data["puntos"][0]["por_red"]["instagram"] == 12000
    assert data["etiqueta_rango"] and data["etiqueta_rango"] != "ignored"
    assert data["generado_en"]


def test_serie_alcance_degrada_con_honestidad_si_vacio(cliente, monkeypatch):
    def vacio(rango="mes", marca=None):
        s = _serie_alcance(rango, marca)
        s["puntos"] = []
        return s

    _mock_servicio(monkeypatch, construir_serie_alcance=vacio)
    r = cliente.get("/api/metricas/serie-alcance?rango=semana")
    assert r.status_code == 200
    assert r.json()["puntos"] == []


def test_serie_alcance_filtra_por_red(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_serie_alcance=_serie_alcance)
    r = cliente.get("/api/metricas/serie-alcance?rango=mes&red=instagram")
    assert r.status_code == 200
    data = r.json()
    assert data["puntos"][0]["por_red"] == {"instagram": 12000}
    assert data["puntos"][0]["total"] == 12000


def test_serie_alcance_red_invalida_devuelve_400(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_serie_alcance=_serie_alcance)
    r = cliente.get("/api/metricas/serie-alcance?rango=mes&red=threads")
    assert r.status_code == 400
    assert "error" in r.json()


# --------------------------------------------------------------------------- #
# /api/metricas/demografia                                                     #
# --------------------------------------------------------------------------- #


def _demografia(marca, red):
    return {
        "red": red,
        "distribuciones": {
            "gender": [{"clave": "F", "valor": 50.0}, {"clave": "M", "valor": 47.5}],
            "postsTypes": [{"clave": "reel", "valor": 12}],
        },
    }


def test_demografia_200_shape(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_demografia=_demografia)
    r = cliente.get("/api/metricas/demografia?marca=claro_sports&red=instagram")
    assert r.status_code == 200
    data = r.json()
    assert data["red"] == "instagram"
    assert data["distribuciones"]["gender"][0] == {"clave": "F", "valor": 50.0}
    assert data["distribuciones"]["postsTypes"][0]["valor"] == 12


def test_demografia_red_invalida_400(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_demografia=_demografia)
    r = cliente.get("/api/metricas/demografia?marca=claro_sports&red=threads")
    assert r.status_code == 400
    assert "error" in r.json()


def test_demografia_sin_red_400(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_demografia=_demografia)
    r = cliente.get("/api/metricas/demografia?marca=claro_sports")
    assert r.status_code == 400
    assert "error" in r.json()


# --------------------------------------------------------------------------- #
# /api/programacion/mejor-hora                                                 #
# --------------------------------------------------------------------------- #


def test_mejor_hora_200_devuelve_hora(cliente, monkeypatch):
    _mock_servicio(monkeypatch, mejor_hora=lambda marca, red: "20:00")
    r = cliente.get("/api/programacion/mejor-hora?marca=claro_sports&red=instagram")
    assert r.status_code == 200
    assert r.json() == {"hora": "20:00"}


def test_mejor_hora_null_si_sin_datos(cliente, monkeypatch):
    _mock_servicio(monkeypatch, mejor_hora=lambda marca, red: None)
    r = cliente.get("/api/programacion/mejor-hora?marca=claro_sports&red=instagram")
    assert r.status_code == 200
    assert r.json() == {"hora": None}


def test_mejor_hora_red_invalida_400(cliente, monkeypatch):
    _mock_servicio(monkeypatch, mejor_hora=lambda marca, red: "20:00")
    r = cliente.get("/api/programacion/mejor-hora?marca=claro_sports&red=threads")
    assert r.status_code == 400
    assert "error" in r.json()


def test_mejor_hora_sin_red_400(cliente, monkeypatch):
    _mock_servicio(monkeypatch, mejor_hora=lambda marca, red: "20:00")
    r = cliente.get("/api/programacion/mejor-hora?marca=claro_sports")
    assert r.status_code == 400
    assert "error" in r.json()


# --------------------------------------------------------------------------- #
# /api/metricas/audiencia (altas/bajas de seguidores)                          #
# --------------------------------------------------------------------------- #


def _audiencia(rango="mes", marca=None):
    return {
        "por_red": [
            {"red": "facebook", "altas": 50, "bajas": 10, "neto": 40},
            {"red": "instagram", "altas": None, "bajas": None, "neto": 75},
        ]
    }


def test_audiencia_200_shape(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_flujo_audiencia=_audiencia)
    r = cliente.get("/api/metricas/audiencia?rango=mes&marca=claro_sports")
    assert r.status_code == 200
    data = r.json()
    fb = next(x for x in data["por_red"] if x["red"] == "facebook")
    assert fb == {"red": "facebook", "altas": 50, "bajas": 10, "neto": 40}
    ig = next(x for x in data["por_red"] if x["red"] == "instagram")
    assert ig["altas"] is None and ig["neto"] == 75
    assert data["etiqueta_rango"] and data["etiqueta_rango"] != "ignored"
    assert data["generado_en"]


def test_audiencia_filtra_por_red(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_flujo_audiencia=_audiencia)
    r = cliente.get("/api/metricas/audiencia?rango=mes&red=facebook")
    assert r.status_code == 200
    assert [x["red"] for x in r.json()["por_red"]] == ["facebook"]


def test_audiencia_red_invalida_400(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_flujo_audiencia=_audiencia)
    r = cliente.get("/api/metricas/audiencia?rango=mes&red=threads")
    assert r.status_code == 400
    assert "error" in r.json()


def test_audiencia_degrada_vacio(cliente, monkeypatch):
    _mock_servicio(
        monkeypatch,
        construir_flujo_audiencia=lambda rango="mes", marca=None: {"por_red": []},
    )
    r = cliente.get("/api/metricas/audiencia?rango=semana")
    assert r.status_code == 200
    assert r.json()["por_red"] == []


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


def test_desglose_filtra_por_red(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_desglose_interacciones=_desglose)
    r = cliente.get("/api/metricas/desglose?rango=mes&red=facebook")
    assert r.status_code == 200
    data = r.json()
    assert all(c["red"] == "facebook" for c in data["celdas"])
    # Totales re-sumados sobre la red (la única celda de la muestra es facebook).
    assert data["totales"]["interacciones"] == 135
    assert data["totales"]["likes"] == 100
    assert data["totales"]["engagement_pct"] == 6.75


def test_desglose_red_sin_celdas_queda_vacio(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_desglose_interacciones=_desglose)
    r = cliente.get("/api/metricas/desglose?rango=mes&red=instagram")
    assert r.status_code == 200
    data = r.json()
    assert data["celdas"] == []
    assert data["totales"]["interacciones"] == 0
    assert data["totales"]["engagement_pct"] == 0.0


def test_desglose_red_invalida_devuelve_400(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_desglose_interacciones=_desglose)
    r = cliente.get("/api/metricas/desglose?rango=mes&red=threads")
    assert r.status_code == 400
    assert "error" in r.json()


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


def test_crosstab_filtra_por_red(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_crosstab=_crosstab)
    r = cliente.get("/api/metricas/crosstab?rango=mes&red=instagram")
    assert r.status_code == 200
    data = r.json()
    assert all(c["red"] == "instagram" for c in data["celdas"])
    assert len(data["celdas"]) == 1


def test_crosstab_red_invalida_devuelve_400(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_crosstab=_crosstab)
    r = cliente.get("/api/metricas/crosstab?rango=mes&red=threads")
    assert r.status_code == 400
    assert "error" in r.json()


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


def test_correlacion_filtra_por_red(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_correlacion_seguidores=_correlacion)
    r = cliente.get("/api/metricas/correlacion?rango=mes&red=instagram")
    assert r.status_code == 200
    data = r.json()
    assert all(it["red"] == "instagram" for it in data["items"])
    assert len(data["items"]) == 1
    assert data["nota"]  # la nota de caveat se conserva


def test_correlacion_red_invalida_devuelve_400(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_correlacion_seguidores=_correlacion)
    r = cliente.get("/api/metricas/correlacion?rango=mes&red=threads")
    assert r.status_code == 400
    assert "error" in r.json()


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


def test_ads_filtra_por_red(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_ads=_ads)
    # Ambas campañas de la muestra son de facebook: el filtro las conserva...
    r = cliente.get("/api/metricas/ads?rango=mes&red=facebook")
    assert r.status_code == 200
    data = r.json()
    assert len(data["ads"]) == 2 and data["total"]["campanias"] == 2
    # ...y deja vacía una red sin campañas (totales re-sumados a 0).
    r2 = cliente.get("/api/metricas/ads?rango=mes&red=instagram")
    data2 = r2.json()
    assert data2["ads"] == [] and data2["total"]["campanias"] == 0
    assert data2["total"]["visualizaciones"] == 0


def test_ads_red_invalida_devuelve_400(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_ads=_ads)
    r = cliente.get("/api/metricas/ads?rango=mes&red=threads")
    assert r.status_code == 400
    assert "error" in r.json()


# --------------------------------------------------------------------------- #
# /api/metricas/ads/{provider_campaign_id}/desglose (drill-down)              #
# --------------------------------------------------------------------------- #


def _ads_desglose(rango="mes", marca=None, provider_campaign_id=""):
    return {
        "provider_campaign_id": provider_campaign_id,
        "adgroups": [
            {"provider_adgroup_id": "ag_1", "nombre": "Grupo A", "impresiones": 5000,
             "clics": 100, "gasto": 40.0, "ctr": 2.0, "cuenta": marca},
        ],
        "ads": [
            {"ad_id": "ad_1", "nombre": "Anuncio 1", "tipo": "SINGLE_IMAGE",
             "impresiones": 3000, "clics": 60, "gasto": 25.0, "cuenta": marca},
        ],
    }


def test_ads_desglose_200_shape(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_ads_desglose=_ads_desglose)
    r = cliente.get("/api/metricas/ads/camp_1/desglose?rango=mes&marca=claro_sports")
    assert r.status_code == 200
    data = r.json()
    assert data["provider_campaign_id"] == "camp_1"
    assert data["adgroups"][0]["provider_adgroup_id"] == "ag_1"
    assert data["ads"][0]["ad_id"] == "ad_1"
    assert data["etiqueta_rango"] and data["etiqueta_rango"] != "ignored"
    assert data["generado_en"]


def test_ads_desglose_vacio_si_sin_campania(cliente, monkeypatch):
    _mock_servicio(
        monkeypatch,
        construir_ads_desglose=lambda rango="mes", marca=None, provider_campaign_id="": {
            "provider_campaign_id": provider_campaign_id, "adgroups": [], "ads": []
        },
    )
    r = cliente.get("/api/metricas/ads/desconocida/desglose")
    assert r.status_code == 200
    data = r.json()
    assert data["adgroups"] == [] and data["ads"] == []


# --------------------------------------------------------------------------- #
# /api/metricas/ingesta (canales con la sincronización estancada)             #
# --------------------------------------------------------------------------- #


def _listado_estancado(rango="mes", marca=None):
    base = {"titulo": "x", "url": "", "engagement_pct": 1.0, "interacciones": 1,
            "visualizaciones": 100, "cuenta": "claro_sports"}
    piezas = [
        # FB foto al día (última = pieza más fresca de la marca) -> no alerta.
        {**base, "id": "f1", "red": "facebook", "formato": "foto", "publicado": "2026-06-08"},
        # IG reel al día -> no alerta.
        {**base, "id": "i1", "red": "instagram", "formato": "reel", "publicado": "2026-06-07"},
    ]
    # FB reel ESTANCADO de verdad: publicaba CADA 2 DÍAS y se cortó el 15-may; 24d de silencio,
    # muy por encima de su ritmo normal. Cadencia fiable -> debe alertar.
    for i, d in enumerate(
        ["2026-05-05", "2026-05-07", "2026-05-09", "2026-05-11", "2026-05-13", "2026-05-15"]
    ):
        piezas.append({**base, "id": f"r{i}", "red": "facebook", "formato": "reel", "publicado": d})
    # TikTok foto: el equipo apenas lo usa (2 piezas/mes); su última quedó vieja PERO es baja
    # cadencia, no un atasco -> NO debe alertar (falso positivo que arreglamos).
    piezas.append({**base, "id": "t1", "red": "tiktok", "formato": "foto", "publicado": "2026-05-10"})
    piezas.append({**base, "id": "t2", "red": "tiktok", "formato": "foto", "publicado": "2026-05-20"})
    # FB sin formato clasificado (residuo de Metricool): no es un canal atribuible -> ignorado.
    piezas.append({**base, "id": "u1", "red": "facebook", "formato": None, "publicado": "2026-05-12"})
    piezas.append({**base, "id": "u2", "red": "facebook", "formato": None, "publicado": "2026-05-18"})
    return piezas


def test_ingesta_detecta_canal_estancado(cliente, monkeypatch):
    _mock_servicio(monkeypatch, construir_listado_piezas=_listado_estancado)
    r = cliente.get("/api/metricas/ingesta?rango=mes&marca=claro_sports")
    assert r.status_code == 200, r.text
    alertas = r.json()["alertas"]
    # Solo FB/reel: cadencia de 2 días rota desde el 15-may (24d de rezago, ≥3× su ritmo). Lo
    # demás va al día, es baja cadencia (TikTok foto) o sin formato (residuo): no son atascos.
    assert len(alertas) == 1
    a = alertas[0]
    assert a["red"] == "facebook" and a["formato"] == "reel"
    assert a["marca"] == "Claro Sports"
    assert a["ultima_pieza"] == "2026-05-15" and a["rezago_dias"] >= 7


def test_ingesta_no_alerta_baja_cadencia_ni_sin_formato(cliente, monkeypatch):
    """Un canal que el equipo apenas usa (pocas piezas, ritmo
    lento) o el residuo sin formato clasificado SIEMPRE quedan por detrás de una marca que
    publica a diario; no es un atasco de ingesta y no debe disparar la alerta."""
    def _baja_cadencia(rango="mes", marca=None):
        base = {"titulo": "x", "url": "", "engagement_pct": 1.0, "interacciones": 1,
                "visualizaciones": 100, "cuenta": "claro_sports"}
        return [
            {**base, "id": "a", "red": "facebook", "formato": "foto", "publicado": "2026-06-08"},
            # TikTok foto: 2 piezas en el mes, la última vieja -> baja cadencia, no atasco.
            {**base, "id": "b", "red": "tiktok", "formato": "foto", "publicado": "2026-05-10"},
            {**base, "id": "c", "red": "tiktok", "formato": "foto", "publicado": "2026-05-20"},
            # FB sin formato (Metricool no clasificó): no es un canal atribuible.
            {**base, "id": "d", "red": "facebook", "formato": None, "publicado": "2026-05-12"},
            {**base, "id": "e", "red": "facebook", "formato": None, "publicado": "2026-05-18"},
        ]
    _mock_servicio(monkeypatch, construir_listado_piezas=_baja_cadencia)
    r = cliente.get("/api/metricas/ingesta?rango=mes&marca=claro_sports")
    assert r.status_code == 200 and r.json()["alertas"] == []


def test_ingesta_sin_estancados_lista_vacia(cliente, monkeypatch):
    def _al_dia(rango="mes", marca=None):
        return [{"id": "1", "red": "facebook", "formato": "foto", "publicado": "2026-06-08",
                 "cuenta": "claro_sports", "titulo": "x", "url": "", "engagement_pct": 1.0,
                 "interacciones": 1, "visualizaciones": 100}]
    _mock_servicio(monkeypatch, construir_listado_piezas=_al_dia)
    r = cliente.get("/api/metricas/ingesta?rango=mes&marca=claro_sports")
    assert r.status_code == 200 and r.json()["alertas"] == []
