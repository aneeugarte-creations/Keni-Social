"""Tests UNITARIOS de los adaptadores de agencias (Reuters/AFP, item F). OFFLINE, sin red.

Cubre la logica PURA: normalizadores tolerantes a la forma de cada API y la degradacion
honesta (estado/pendientes/traer_items) cuando NO hay credencial. El gating se prueba
monkeypatcheando los accesores de `config` (sin tocar el store de ajustes ni la red).
"""

from __future__ import annotations

from keni_consola import agencias, config
from keni_consola.dominio import ingesta


# --------------------------------------------------------------------------- #
# Normalizadores (PUROS, tolerantes a la forma)                                #
# --------------------------------------------------------------------------- #


def test_normalizar_reuters_lista_simple():
    datos = [
        {"headline": "Sismo en México", "uri": "https://r/1", "caption": "Resumen", "versionCreated": "2025-06-01"},
        {"title": "Otra nota", "url": "https://r/2"},
    ]
    items = agencias.normalizar_reuters(datos)
    assert [i["titulo"] for i in items] == ["Sismo en México", "Otra nota"]
    assert items[0]["enlace"] == "https://r/1"
    assert items[0]["fuente"] == "Reuters"
    assert items[0]["fecha"] == "2025-06-01"
    assert items[0]["clave"] == "https://r/1"


def test_normalizar_reuters_graphql_envuelto_en_edges_y_node():
    datos = {"data": {"search": {"edges": [{"node": {"headline": "T", "uri": "https://r/x"}}]}}}
    items = agencias.normalizar_reuters(datos)
    assert len(items) == 1
    assert items[0]["titulo"] == "T"
    assert items[0]["enlace"] == "https://r/x"


def test_normalizar_reuters_omite_sin_titulo_ni_enlace():
    items = agencias.normalizar_reuters([{"caption": "solo resumen"}])
    assert items == []


def test_normalizar_afp_response_docs_estilo_solr():
    datos = {"response": {"docs": [{"title": "Nota AFP", "href": "https://a/1", "summary": "S"}]}}
    items = agencias.normalizar_afp(datos)
    assert len(items) == 1
    assert items[0]["titulo"] == "Nota AFP"
    assert items[0]["enlace"] == "https://a/1"
    assert items[0]["fuente"] == "AFP"


def test_normalizar_afp_lista_directa():
    items = agencias.normalizar_afp([{"headline": "X", "url": "https://a/2"}])
    assert items == [
        {"titulo": "X", "resumen": "", "enlace": "https://a/2", "fecha": "", "fuente": "AFP", "clave": "https://a/2"}
    ]


def test_normalizar_recorta_y_limpia_resumen():
    datos = [{"title": "T", "uri": "https://r/1", "caption": "<b>Hola</b>  mundo"}]
    items = agencias.normalizar_reuters(datos)
    assert items[0]["resumen"] == "Hola mundo"  # HTML quitado + espacios colapsados


# --------------------------------------------------------------------------- #
# Degradacion honesta (gating por credencial)                                  #
# --------------------------------------------------------------------------- #


def test_estado_reuters_pendiente_sin_credencial(monkeypatch):
    monkeypatch.setattr(config, "reuters_configurado", lambda: False)
    estado = agencias.estado_fuente("reuters")
    assert estado["disponible"] is False
    assert "KENI_REUTERS_API_KEY" in estado["motivo"]


def test_estado_afp_disponible_con_credencial(monkeypatch):
    monkeypatch.setattr(config, "afp_configurado", lambda: True)
    estado = agencias.estado_fuente("afp")
    assert estado["disponible"] is True
    assert estado["motivo"] == ""


def test_traer_items_sin_credencial_devuelve_vacio_sin_red(monkeypatch):
    monkeypatch.setattr(config, "reuters_configurado", lambda: False)
    monkeypatch.setattr(config, "afp_configurado", lambda: False)
    assert agencias.traer_items("reuters") == []
    assert agencias.traer_items("afp") == []


def test_fuentes_pendientes_lista_las_no_configuradas(monkeypatch):
    monkeypatch.setattr(config, "reuters_configurado", lambda: False)
    monkeypatch.setattr(config, "afp_configurado", lambda: True)
    pend = agencias.fuentes_pendientes()
    redes = {p["red"] for p in pend}
    assert "reuters" in redes
    assert "afp" not in redes  # afp configurada => no pendiente


def test_traer_items_con_credencial_usa_descargador_inyectable(monkeypatch):
    # Con credencial, traer_items descarga via el _DESCARGADOR inyectable (sin red real).
    monkeypatch.setattr(config, "reuters_configurado", lambda: True)
    monkeypatch.setattr(config, "reuters_api_key", lambda: "k")
    monkeypatch.setattr(config, "reuters_base_url", lambda: "https://93.184.216.34")
    monkeypatch.setattr(
        agencias.rss, "_DESCARGADOR", lambda url: '{"items": [{"title": "N", "uri": "https://r/9"}]}'
    )
    items = agencias.traer_items("reuters")
    assert [i["titulo"] for i in items] == ["N"]


# --------------------------------------------------------------------------- #
# Builder de pool noticia_item_de_agencia (PURO, sin red) — Cambio 1 Fase 2    #
# --------------------------------------------------------------------------- #


def test_noticia_item_de_agencia_mapea_campos_y_fuente_estable():
    item = {
        "titulo": "Sismo en México",
        "resumen": "Resumen",
        "enlace": "https://reuters.com/a/1?utm_source=x",
        "fecha": "2025-06-01T10:00:00Z",
        "fuente": "Reuters",
        "clave": "https://reuters.com/a/1?utm_source=x",
    }
    fila = ingesta.noticia_item_de_agencia(item, agencia="reuters")
    assert fila is not None
    assert fila["fuente_id"] == "agencia-reuters"
    assert fila["fuente_nombre"] == "Reuters"
    assert fila["categoria"] == "agencias"
    assert fila["marca"] == ""  # agencias = señal global, sin marca
    assert fila["titulo"] == "Sismo en México"
    assert fila["resumen"] == "Resumen"
    assert fila["url"] == "https://reuters.com/a/1?utm_source=x"
    # clave = url canónica (sin utm_*): identidad estable cross-barrido.
    assert fila["url_canonica"] == "reuters.com/a/1"
    assert fila["clave"] == "reuters.com/a/1"
    assert fila["publicado_en"]  # fecha ISO parseada
    assert "senal" not in fila  # señal NORMAL (no curado), default 0 en el sink
    # Las agencias son fuentes POTENTES: pesan el doble en la corroboración del ranking.
    assert fila["fuente_peso"] == 2.0


def test_noticia_item_de_agencia_fuente_nombre_cae_a_agencia_upper():
    item = {"titulo": "X", "resumen": "", "enlace": "https://a/2", "fecha": "", "fuente": "", "clave": "https://a/2"}
    fila = ingesta.noticia_item_de_agencia(item, agencia="afp")
    assert fila is not None
    assert fila["fuente_id"] == "agencia-afp"
    assert fila["fuente_nombre"] == "AFP"


def test_noticia_item_de_agencia_clave_estable_por_titulo_sin_enlace():
    item = {"titulo": "Una nota sin enlace", "resumen": "", "enlace": "", "fecha": "", "fuente": "Reuters", "clave": "Una nota sin enlace"}
    fila = ingesta.noticia_item_de_agencia(item, agencia="reuters")
    assert fila is not None
    assert fila["url"] == ""
    assert fila["url_canonica"] == ""
    assert fila["clave"].startswith("t:")  # hash del título normalizado


def test_noticia_item_de_agencia_none_sin_identidad():
    # Sin enlace y sin título útil -> sin clave estable -> se omite (None).
    item = {"titulo": "", "resumen": "solo resumen", "enlace": "", "fecha": "", "fuente": "AFP", "clave": ""}
    assert ingesta.noticia_item_de_agencia(item, agencia="afp") is None
