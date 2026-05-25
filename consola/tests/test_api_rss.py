"""Tests de la API RSS (/api/rss/*). OFFLINE: NUNCA se toca la red.

Cubre:
  - fuentes CRUD + validacion de URL (esquema) + guard SSRF (IPs privadas/loopback...),
  - parser tolerante RSS 2.0 y Atom con fixtures XML (funcion pura, sin red),
  - lectura de items mockeando el descargador inyectable `_DESCARGADOR`,
  - un feed que falla se OMITE con su error sin romper los demas.

El guard SSRF se prueba con IPs LITERALES (no requieren DNS, asi el test es offline y
determinista). Para una fuente "buena" se usa una IP publica literal, tambien sin DNS.
"""

from __future__ import annotations

import pytest

from keni_consola.api import rss

# IP publica literal: pasa el guard SSRF sin tocar DNS. example.com no se resuelve aqui.
_URL_OK = "https://93.184.216.34/feed.xml"


# --------------------------------------------------------------------------- #
# validar_url + guard SSRF (funcion pura, IPs literales => sin DNS)            #
# --------------------------------------------------------------------------- #


def test_validar_url_ok_ip_publica():
    url, error = rss.validar_url(_URL_OK)
    assert error is None
    assert url == _URL_OK


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/feed.xml",
        "file:///etc/passwd",
        "gopher://example.com/",
        "javascript:alert(1)",
    ],
)
def test_validar_url_esquema_no_http(url):
    _, error = rss.validar_url(url)
    assert error is not None
    assert "http" in error.lower()


def test_validar_url_vacia():
    _, error = rss.validar_url("")
    assert error is not None
    _, error = rss.validar_url(None)
    assert error is not None


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",  # loopback
        "127.5.5.5",  # 127.0.0.0/8
        "10.0.0.1",  # 10/8
        "10.255.255.255",
        "172.16.0.1",  # 172.16/12
        "172.31.255.255",
        "192.168.1.1",  # 192.168/16
        "169.254.0.1",  # 169.254/16 link-local
        "0.0.0.0",  # unspecified
        "[::1]",  # loopback IPv6
        "[fc00::1]",  # IPv6 ULA (privada)
        "[fe80::1]",  # IPv6 link-local
    ],
)
def test_validar_url_ssrf_bloquea_privadas(host):
    _, error = rss.validar_url(f"http://{host}/feed.xml")
    assert error is not None, f"deberia bloquear {host}"


def test_validar_url_localhost_se_resuelve_y_bloquea():
    # 'localhost' resuelve a 127.0.0.1/::1 => el guard lo bloquea (esto SI usa el
    # resolvedor del sistema, pero 'localhost' es local y no hace red externa).
    _, error = rss.validar_url("http://localhost/feed.xml")
    assert error is not None


# --------------------------------------------------------------------------- #
# Fuentes CRUD (API)                                                          #
# --------------------------------------------------------------------------- #


def test_crear_fuente_y_listar(cliente):
    r = cliente.post(
        "/api/rss/fuentes", json={"nombre": "Diario", "url": _URL_OK, "marca": "unotv"}
    )
    assert r.status_code == 200
    f = r.json()["fuente"]
    assert f["id"]
    assert f["nombre"] == "Diario"
    assert f["url"] == _URL_OK
    assert f["marca_nombre"] == "UnoTV"
    assert len(cliente.get("/api/rss/fuentes").json()["fuentes"]) == 1


def test_crear_fuente_nombre_obligatorio_400(cliente):
    assert (
        cliente.post("/api/rss/fuentes", json={"url": _URL_OK}).status_code == 400
    )
    assert (
        cliente.post("/api/rss/fuentes", json={"nombre": " ", "url": _URL_OK}).status_code == 400
    )


def test_crear_fuente_url_invalida_400(cliente):
    r = cliente.post("/api/rss/fuentes", json={"nombre": "X", "url": "ftp://x/y"})
    assert r.status_code == 400


def test_crear_fuente_ssrf_400(cliente):
    r = cliente.post(
        "/api/rss/fuentes", json={"nombre": "X", "url": "http://127.0.0.1/feed.xml"}
    )
    assert r.status_code == 400
    assert "permitida" in r.json()["error"].lower()


def test_crear_fuente_marca_invalida_400(cliente):
    r = cliente.post(
        "/api/rss/fuentes", json={"nombre": "X", "url": _URL_OK, "marca": "marca_falsa"}
    )
    assert r.status_code == 400


def test_borrar_fuente(cliente):
    fid = cliente.post(
        "/api/rss/fuentes", json={"nombre": "X", "url": _URL_OK}
    ).json()["fuente"]["id"]
    assert cliente.delete(f"/api/rss/fuentes/{fid}").status_code == 200
    assert cliente.delete(f"/api/rss/fuentes/{fid}").status_code == 404


# --------------------------------------------------------------------------- #
# Parser RSS 2.0 y Atom (funcion pura, sin red)                               #
# --------------------------------------------------------------------------- #

_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Mi Feed</title>
    <item>
      <title>Noticia 1</title>
      <link>https://example.com/1</link>
      <description><![CDATA[<p>Resumen <b>uno</b> con <a href="x">enlace</a>.</p>]]></description>
      <pubDate>Mon, 19 May 2026 10:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Noticia 2</title>
      <link>https://example.com/2</link>
      <description>Texto plano dos</description>
    </item>
  </channel>
</rss>
"""

_ATOM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Mi Feed Atom</title>
  <entry>
    <title>Entrada A</title>
    <link rel="alternate" href="https://example.com/a"/>
    <summary>Resumen &lt;b&gt;A&lt;/b&gt;</summary>
    <updated>2026-05-19T10:00:00Z</updated>
  </entry>
  <entry>
    <title>Entrada B</title>
    <link href="https://example.com/b"/>
    <content type="html">&lt;p&gt;Cuerpo B&lt;/p&gt;</content>
    <published>2026-05-18T10:00:00Z</published>
  </entry>
</feed>
"""


def test_parsear_rss():
    items = rss.parsear_feed(_RSS_XML)
    assert len(items) == 2
    assert items[0]["titulo"] == "Noticia 1"
    assert items[0]["enlace"] == "https://example.com/1"
    assert items[0]["fecha"] == "Mon, 19 May 2026 10:00:00 GMT"
    # HTML eliminado del resumen
    assert "<" not in items[0]["resumen"]
    assert "Resumen uno con enlace" in items[0]["resumen"]
    assert items[1]["resumen"] == "Texto plano dos"


def test_parsear_atom():
    items = rss.parsear_feed(_ATOM_XML)
    assert len(items) == 2
    assert items[0]["titulo"] == "Entrada A"
    assert items[0]["enlace"] == "https://example.com/a"
    assert items[0]["fecha"] == "2026-05-19T10:00:00Z"
    assert "<" not in items[0]["resumen"]
    assert "A" in items[0]["resumen"]
    # entrada B usa <content> y link sin rel
    assert items[1]["enlace"] == "https://example.com/b"
    assert "Cuerpo B" in items[1]["resumen"]


def test_parsear_xml_invalido_lanza():
    with pytest.raises(rss.RSSError):
        rss.parsear_feed("esto no es xml <<<")


def test_parsear_limita_items(monkeypatch):
    monkeypatch.setattr(rss, "_MAX_ITEMS", 1)
    items = rss.parsear_feed(_RSS_XML)
    assert len(items) == 1


def test_resumen_se_recorta(monkeypatch):
    monkeypatch.setattr(rss, "_RESUMEN_MAX", 10)
    xml = _RSS_XML.replace("Texto plano dos", "x" * 50)
    items = rss.parsear_feed(xml)
    # el segundo item tiene el resumen largo recortado con elipsis
    largo = [i for i in items if i["titulo"] == "Noticia 2"][0]
    assert largo["resumen"].endswith("…")
    assert len(largo["resumen"]) <= 11


# --------------------------------------------------------------------------- #
# GET /api/rss/items: mockea el descargador inyectable (NUNCA red real)        #
# --------------------------------------------------------------------------- #


def _fuente(cliente, nombre, url=_URL_OK, marca=""):
    cuerpo = {"nombre": nombre, "url": url}
    if marca:
        cuerpo["marca"] = marca
    return cliente.post("/api/rss/fuentes", json=cuerpo).json()["fuente"]


def test_items_de_una_fuente(cliente, monkeypatch):
    f = _fuente(cliente, "Diario")
    monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _RSS_XML)
    r = cliente.get(f"/api/rss/items?fuente={f['id']}")
    assert r.status_code == 200
    datos = r.json()
    assert datos["errores"] == []
    assert len(datos["items"]) == 2
    assert datos["items"][0]["fuente_id"] == f["id"]
    assert datos["items"][0]["fuente_nombre"] == "Diario"


def test_items_todas_las_fuentes(cliente, monkeypatch):
    _fuente(cliente, "RSS")
    _fuente(cliente, "Atom")

    def fake(url):  # noqa: ANN001
        return _RSS_XML  # ambas fuentes devuelven contenido

    monkeypatch.setattr(rss, "_DESCARGADOR", fake)
    datos = cliente.get("/api/rss/items").json()
    assert datos["errores"] == []
    assert len(datos["items"]) == 4  # 2 fuentes x 2 items


def test_items_fuente_inexistente_404(cliente):
    assert cliente.get("/api/rss/items?fuente=noexiste").status_code == 404


def test_items_feed_que_falla_se_omite(cliente, monkeypatch):
    bueno = _fuente(cliente, "Bueno")
    malo = _fuente(cliente, "Malo")

    def fake(url):  # noqa: ANN001
        raise rss.RSSError("El feed tardó demasiado y se canceló.")

    # Solo el "malo" falla; el bueno devuelve XML valido.
    def selectivo(url):  # noqa: ANN001
        # No podemos distinguir por url (ambas comparten _URL_OK), asi que probamos
        # el caso global: TODAS fallan => items vacios, dos errores anotados.
        return fake(url)

    monkeypatch.setattr(rss, "_DESCARGADOR", selectivo)
    datos = cliente.get("/api/rss/items").json()
    assert datos["items"] == []
    nombres = {e["fuente_nombre"] for e in datos["errores"]}
    assert nombres == {"Bueno", "Malo"}
    assert all("error" in e for e in datos["errores"])
    # ids presentes (referencia a las fuentes que fallaron)
    assert {bueno["id"], malo["id"]} == {e["fuente_id"] for e in datos["errores"]}


def test_items_un_feed_falla_otros_siguen(cliente, monkeypatch):
    # Dos fuentes con URLs distintas (IPs publicas literales) para distinguir cual falla.
    cliente.post("/api/rss/fuentes", json={"nombre": "OK", "url": "https://93.184.216.34/a.xml"})
    cliente.post("/api/rss/fuentes", json={"nombre": "Roto", "url": "https://93.184.216.35/b.xml"})

    def fake(url):  # noqa: ANN001
        if url.endswith("b.xml"):
            raise rss.RSSError("No se pudo contactar con el feed.")
        return _ATOM_XML

    monkeypatch.setattr(rss, "_DESCARGADOR", fake)
    datos = cliente.get("/api/rss/items").json()
    assert len(datos["items"]) == 2  # solo la fuente OK aporto items
    assert len(datos["errores"]) == 1
    assert datos["errores"][0]["fuente_nombre"] == "Roto"


def test_items_excepcion_inesperada_se_omite(cliente, monkeypatch):
    _fuente(cliente, "Raro")

    def revienta(url):  # noqa: ANN001
        raise ValueError("kaboom interno")  # no es RSSError

    monkeypatch.setattr(rss, "_DESCARGADOR", revienta)
    datos = cliente.get("/api/rss/items").json()
    assert datos["items"] == []
    assert len(datos["errores"]) == 1
    # mensaje generico en espanol, sin el traceback crudo
    assert datos["errores"][0]["error"] == "No se pudo leer el feed."
