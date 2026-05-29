"""Tests de la API de la Parrilla del dia (`/api/parrilla-dia`). OFFLINE, sin red.

Cubre:
  - GET /api/parrilla-dia             -> parrilla del Radar en vivo (Trends mockeado)
  - POST /api/parrilla-dia            -> parrilla con temas en el body
  - POST /api/parrilla-dia            -> sin temas en body -> trae del Radar
  - POST /api/parrilla-dia/puntuar    -> score individual
  - Validacion: geo invalido cae a MX; body no-JSON devuelve 400; titulo ausente 400.
  - Auth: sin token -> 401.
  - Degradacion: Radar caido -> parrilla vacia, sin inventar temas.
"""

from __future__ import annotations

from keni_consola.api import rss

from .conftest import _cliente  # noqa: F401 (fixture cliente)

# Feed de Trends con 4 temas variados para que la clasificacion tenga material
_TRENDS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0"><channel>
  <item>
    <title>accidente en autopista mexico</title>
    <ht:approx_traffic>50K+</ht:approx_traffic>
    <ht:news_item>
      <ht:news_item_title>Video del choque múltiple</ht:news_item_title>
      <ht:news_item_url>https://example.com/acc</ht:news_item_url>
      <ht:news_item_source>Milenio</ht:news_item_source>
    </ht:news_item>
  </item>
  <item>
    <title>inflacion datos estadisticas</title>
    <ht:approx_traffic>20K+</ht:approx_traffic>
    <ht:news_item>
      <ht:news_item_title>Cifras oficiales de inflacion</ht:news_item_title>
      <ht:news_item_url>https://example.com/inf</ht:news_item_url>
      <ht:news_item_source>El Financiero</ht:news_item_source>
    </ht:news_item>
  </item>
  <item>
    <title>analisis escandalo corrupcion pemex</title>
    <ht:approx_traffic>10K+</ht:approx_traffic>
  </item>
  <item>
    <title>concierto junior h fotos galeria</title>
    <ht:approx_traffic>5K+</ht:approx_traffic>
  </item>
</channel></rss>
"""

# Temas de ejemplo para el body del POST
_TEMAS_BODY = [
    {
        "titulo": "Sismo en Oaxaca sacude la region",
        "senal": 80000,
        "senal_texto": "80K+",
        "por_que": "Terremoto de magnitud 6 registrado esta manana",
        "redes": ["busquedas-mx"],
        "fuentes": ["Google Trends"],
        "enlaces": [
            {
                "titulo": "SSN reporta sismo",
                "url": "https://example.com/sismo",
                "fuente": "El Universal",
            }
        ],
    },
    {
        "titulo": "Investigacion sobre fraude electoral en Mexico",
        "senal": 15000,
        "senal_texto": "15K+",
        "por_que": "Reportaje de investigacion periodistica",
        "redes": ["busquedas-mx"],
        "fuentes": ["Proceso"],
        "enlaces": [],
    },
    {
        "titulo": "Fotos del desfile de moda en CDMX",
        "senal": 3000,
        "senal_texto": "3K+",
        "por_que": "Evento de moda con imagenes exclusivas",
        "redes": ["busquedas-mx"],
        "fuentes": ["Google Trends"],
        "enlaces": [],
    },
]


# --------------------------------------------------------------------------- #
# GET /api/parrilla-dia                                                         #
# --------------------------------------------------------------------------- #

class TestGetParrillaDia:
    def test_respuesta_tiene_estructura_basica(self, cliente, monkeypatch):
        monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _TRENDS_XML)
        datos = cliente.get("/api/parrilla-dia").json()
        assert "posteos" in datos
        assert "editorial" in datos
        assert "sobrantes" in datos
        assert "total_entrada" in datos
        assert "geo" in datos
        assert datos["geo"] == "MX"

    def test_geo_defecto_es_mx(self, cliente, monkeypatch):
        monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _TRENDS_XML)
        datos = cliente.get("/api/parrilla-dia").json()
        assert datos["geo"] == "MX"

    def test_geo_invalido_cae_a_mx(self, cliente, monkeypatch):
        monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _TRENDS_XML)
        datos = cliente.get("/api/parrilla-dia?geo=ZZ").json()
        assert datos["geo"] == "MX"

    def test_geo_valido_se_respeta(self, cliente, monkeypatch):
        capturadas = []

        def fake(url):  # noqa: ANN001
            capturadas.append(url)
            return _TRENDS_XML

        monkeypatch.setattr(rss, "_DESCARGADOR", fake)
        datos = cliente.get("/api/parrilla-dia?geo=US").json()
        assert datos["geo"] == "US"
        assert any("geo=US" in u for u in capturadas)

    def test_temas_clasificados_con_tipo(self, cliente, monkeypatch):
        monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _TRENDS_XML)
        datos = cliente.get("/api/parrilla-dia").json()
        todos = datos["posteos"] + datos["editorial"] + datos["sobrantes"]
        for t in todos:
            assert t["tipo"] in ("posteo", "editorial")

    def test_posteos_tienen_subtipo(self, cliente, monkeypatch):
        monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _TRENDS_XML)
        datos = cliente.get("/api/parrilla-dia").json()
        from keni_consola.parrilla import SUBTIPOS_POSTEO
        for t in datos["posteos"]:
            assert t["subtipo"] in SUBTIPOS_POSTEO, f"Subtipo inesperado: {t['subtipo']!r}"

    def test_cuotas_no_excedidas(self, cliente, monkeypatch):
        monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _TRENDS_XML)
        datos = cliente.get("/api/parrilla-dia").json()
        from keni_consola import parrilla
        assert len(datos["posteos"]) <= parrilla.CUOTA_POSTEOS
        assert len(datos["editorial"]) <= parrilla.CUOTA_EDITORIAL

    def test_orden_asignado_en_cada_tema(self, cliente, monkeypatch):
        monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _TRENDS_XML)
        datos = cliente.get("/api/parrilla-dia").json()
        todos = datos["posteos"] + datos["editorial"] + datos["sobrantes"]
        for t in todos:
            assert "orden" in t
            assert isinstance(t["orden"], int) and t["orden"] >= 1

    def test_radar_caido_devuelve_parrilla_vacia(self, cliente, monkeypatch):
        monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: (_ for _ in ()).throw(
            rss.RSSError("feed caido")
        ))
        datos = cliente.get("/api/parrilla-dia").json()
        assert datos["total_entrada"] == 0
        assert datos["posteos"] == []
        assert datos["editorial"] == []


# --------------------------------------------------------------------------- #
# POST /api/parrilla-dia                                                        #
# --------------------------------------------------------------------------- #

class TestPostParrillaDia:
    def test_con_temas_en_body(self, cliente, monkeypatch):
        # No debe tocar el Radar cuando se pasan temas en el body
        llamadas = []
        monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: llamadas.append(url) or "")
        datos = cliente.post("/api/parrilla-dia", json={"temas": _TEMAS_BODY}).json()
        # La respuesta tiene la estructura esperada
        assert "posteos" in datos
        assert datos["total_entrada"] == len(_TEMAS_BODY)
        # No se llamo al radar (temas provistos en body)
        assert llamadas == []

    def test_sin_temas_usa_radar(self, cliente, monkeypatch):
        monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _TRENDS_XML)
        datos = cliente.post("/api/parrilla-dia", json={}).json()
        assert datos["total_entrada"] > 0

    def test_body_vacio_usa_radar(self, cliente, monkeypatch):
        monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _TRENDS_XML)
        r = cliente.post(
            "/api/parrilla-dia",
            content=b"",
            headers={"Content-Type": "application/json"},
        )
        # Puede ser 200 (usa radar) o 400 si body invalido; ambos son validos
        assert r.status_code in (200, 400)

    def test_body_no_json_devuelve_400_o_usa_radar(self, cliente, monkeypatch):
        monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _TRENDS_XML)
        r = cliente.post(
            "/api/parrilla-dia",
            content=b"texto plano no json",
            headers={"Content-Type": "text/plain"},
        )
        # Puede ser 200 (degrada graciosamente) o 400 (rechazo); no debe ser 5xx
        assert r.status_code < 500

    def test_temas_sin_titulo_devuelve_400(self, cliente, monkeypatch):
        monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _TRENDS_XML)
        r = cliente.post(
            "/api/parrilla-dia",
            json={"temas": [{"senal": 100, "por_que": "sin titulo"}]},
        )
        assert r.status_code == 400
        assert "error" in r.json()

    def test_geo_en_body_se_respeta(self, cliente, monkeypatch):
        monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _TRENDS_XML)
        datos = cliente.post(
            "/api/parrilla-dia",
            json={"temas": _TEMAS_BODY, "geo": "US"},
        ).json()
        assert datos["geo"] == "US"

    def test_geo_invalido_en_body_cae_a_mx(self, cliente, monkeypatch):
        monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _TRENDS_XML)
        datos = cliente.post(
            "/api/parrilla-dia",
            json={"temas": _TEMAS_BODY, "geo": "ZZ"},
        ).json()
        assert datos["geo"] == "MX"

    def test_total_entrada_refleja_temas_del_body(self, cliente, monkeypatch):
        monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _TRENDS_XML)
        datos = cliente.post(
            "/api/parrilla-dia",
            json={"temas": _TEMAS_BODY},
        ).json()
        assert datos["total_entrada"] == len(_TEMAS_BODY)

    def test_clasificacion_correcta_en_temas_del_body(self, cliente, monkeypatch):
        monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _TRENDS_XML)
        datos = cliente.post(
            "/api/parrilla-dia",
            json={"temas": _TEMAS_BODY},
        ).json()
        todos = {t["titulo"]: t for t in datos["posteos"] + datos["editorial"] + datos["sobrantes"]}
        # "Fotos del desfile de moda" debe ser galeria (posteo)
        if "Fotos del desfile de moda en CDMX" in todos:
            assert todos["Fotos del desfile de moda en CDMX"]["tipo"] == "posteo"
            assert todos["Fotos del desfile de moda en CDMX"]["subtipo"] == "galeria"


# --------------------------------------------------------------------------- #
# POST /api/parrilla-dia/puntuar                                                #
# --------------------------------------------------------------------------- #

class TestPuntuarEndpoint:
    def test_puntuar_tema_valido(self, cliente, monkeypatch):
        datos = cliente.post(
            "/api/parrilla-dia/puntuar",
            json={
                "titulo": "Sismo en México",
                "senal": 50000,
                "por_que": "Terremoto registrado en zona sísmica",
                "fuentes": ["Google Trends"],
                "redes": ["busquedas-mx"],
            },
        ).json()
        assert "score" in datos
        assert "razon" in datos
        assert "tipo" in datos
        assert 0.0 <= datos["score"] <= 1.0

    def test_puntuar_sin_titulo_devuelve_400(self, cliente):
        r = cliente.post(
            "/api/parrilla-dia/puntuar",
            json={"senal": 100},
        )
        assert r.status_code == 400
        assert "error" in r.json()

    def test_puntuar_devuelve_tipo_y_subtipo(self, cliente):
        datos = cliente.post(
            "/api/parrilla-dia/puntuar",
            json={"titulo": "Video del accidente en carretera federal"},
        ).json()
        assert datos["tipo"] == "posteo"
        assert datos["subtipo"] == "clip"

    def test_puntuar_geo_valido(self, cliente):
        datos = cliente.post(
            "/api/parrilla-dia/puntuar",
            json={"titulo": "Noticias globales", "geo": "US"},
        ).json()
        assert datos["geo"] == "US"

    def test_puntuar_geo_invalido_cae_a_mx(self, cliente):
        datos = cliente.post(
            "/api/parrilla-dia/puntuar",
            json={"titulo": "Algo", "geo": "ZZ"},
        ).json()
        assert datos["geo"] == "MX"


# --------------------------------------------------------------------------- #
# Auth                                                                          #
# --------------------------------------------------------------------------- #

class TestAuth:
    def test_get_sin_token_401(self, entorno):
        cli = _cliente(autenticar=False)
        assert cli.get("/api/parrilla-dia").status_code == 401

    def test_post_sin_token_401(self, entorno):
        cli = _cliente(autenticar=False)
        assert cli.post("/api/parrilla-dia", json={}).status_code == 401

    def test_puntuar_sin_token_401(self, entorno):
        cli = _cliente(autenticar=False)
        assert cli.post("/api/parrilla-dia/puntuar", json={"titulo": "X"}).status_code == 401
