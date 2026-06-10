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
from keni_consola.dominio import http_feed
from keni_consola.dominio.publicaciones import publicacion_a_dict

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


def test_listar_fuentes_filtra_por_marca(cliente):
    """`?marca=` devuelve las fuentes de ESA marca + las COMPARTIDAS (sin marca).

    Sin `marca` (admin "todas") devuelve todas. Las URLs son distintas porque el alta
    es idempotente por URL.
    """
    cliente.post(
        "/api/rss/fuentes",
        json={"nombre": "UnoTV", "url": "https://93.184.216.34/uno.xml", "marca": "unotv"},
    )
    cliente.post(
        "/api/rss/fuentes",
        json={
            "nombre": "Claro",
            "url": "https://93.184.216.34/claro.xml",
            "marca": "claro-sports",
        },
    )
    cliente.post(
        "/api/rss/fuentes",
        json={"nombre": "Compartida", "url": "https://93.184.216.34/comun.xml"},
    )

    # Admin (sin marca): ve todas.
    todas = cliente.get("/api/rss/fuentes").json()["fuentes"]
    assert {f["nombre"] for f in todas} == {"UnoTV", "Claro", "Compartida"}

    # Marca seleccionada: sus fuentes + las compartidas, NO las de otra marca.
    de_unotv = cliente.get("/api/rss/fuentes?marca=unotv").json()["fuentes"]
    assert {f["nombre"] for f in de_unotv} == {"UnoTV", "Compartida"}

    # Marca no permitida -> 400.
    assert cliente.get("/api/rss/fuentes?marca=marca_falsa").status_code == 400


def test_crear_fuente_con_categoria_y_editarla(cliente):
    """La categoría (manda la cadencia de sondeo del motor) se crea, expone y edita por la API."""
    r = cliente.post(
        "/api/rss/fuentes",
        json={"nombre": "Depor", "url": _URL_OK, "marca": "claro-sports", "categoria": "deportes"},
    )
    assert r.status_code == 200
    f = r.json()["fuente"]
    assert f["categoria"] == "deportes"

    r2 = cliente.put(f"/api/rss/fuentes/{f['id']}", json={"categoria": "breaking"})
    assert r2.status_code == 200
    assert r2.json()["fuente"]["categoria"] == "breaking"

    # Quitar la categoría ('' = cadencia por defecto) también es válido.
    r3 = cliente.put(f"/api/rss/fuentes/{f['id']}", json={"categoria": ""})
    assert r3.status_code == 200
    assert r3.json()["fuente"]["categoria"] == ""


def test_crear_fuente_categoria_invalida_400(cliente):
    r = cliente.post(
        "/api/rss/fuentes",
        json={"nombre": "X", "url": _URL_OK, "categoria": "no-existe"},
    )
    assert r.status_code == 400


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


def test_parsear_limita_items():
    # `parsear_feed` acepta `max_items` (def `_MAX_ITEMS`=30). El límite se PASA como argumento:
    # parchear el global `http_feed._MAX_ITEMS` no sirve porque el default del parámetro se
    # captura en la definición de la función, no se relee en cada llamada.
    items = rss.parsear_feed(_RSS_XML, max_items=1)
    assert len(items) == 1


def test_resumen_se_recorta(monkeypatch):
    monkeypatch.setattr(http_feed, "_RESUMEN_MAX", 10)
    xml = _RSS_XML.replace("Texto plano dos", "x" * 50)
    items = rss.parsear_feed(xml)
    # el segundo item tiene el resumen largo recortado con elipsis
    largo = [i for i in items if i["titulo"] == "Noticia 2"][0]
    assert largo["resumen"].endswith("…")
    assert len(largo["resumen"]) <= 11


# --------------------------------------------------------------------------- #
# Parser: imagen del item (media:content / media:thumbnail / enclosure)         #
# Funcion PURA (sin red): extrae la URL de la imagen del ARTICULO, "" si no la   #
# trae. NO usa el <image> del canal (logo del sitio).                           #
# --------------------------------------------------------------------------- #

# RSS 2.0 con namespace Media RSS (mrss): item con <media:content medium="image">.
_RSS_MEDIA_CONTENT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
  <channel>
    <image><url>https://example.com/LOGO-del-sitio.png</url></image>
    <item>
      <title>Con media:content</title>
      <link>https://example.com/mc</link>
      <media:content url="https://example.com/foto-mc.jpg" medium="image"/>
    </item>
  </channel>
</rss>
"""

# RSS 2.0 con <media:content type="image/*"> (sin medium, pero type de imagen).
_RSS_MEDIA_CONTENT_TYPE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
  <channel>
    <item>
      <title>media:content por type</title>
      <link>https://example.com/mct</link>
      <media:content url="https://example.com/foto-mct.jpg" type="image/jpeg"/>
    </item>
  </channel>
</rss>
"""

# RSS 2.0 con <media:thumbnail url=...>.
_RSS_MEDIA_THUMBNAIL_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
  <channel>
    <item>
      <title>Con media:thumbnail</title>
      <link>https://example.com/mt</link>
      <media:thumbnail url="https://example.com/thumb.jpg"/>
    </item>
  </channel>
</rss>
"""

# RSS 2.0 con <enclosure url=... type="image/jpeg">.
_RSS_ENCLOSURE_IMG_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Con enclosure imagen</title>
      <link>https://example.com/enc</link>
      <enclosure url="https://example.com/enc.jpg" type="image/jpeg"/>
    </item>
  </channel>
</rss>
"""

# RSS 2.0 con <enclosure> de AUDIO (no imagen): no debe extraerse.
_RSS_ENCLOSURE_AUDIO_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Con enclosure audio</title>
      <link>https://example.com/audio</link>
      <enclosure url="https://example.com/pod.mp3" type="audio/mpeg"/>
    </item>
  </channel>
</rss>
"""

# Media RSS dentro de <media:group> (la imagen cuelga anidada, no directa del item):
# `_imagen_item` recorre con `.iter()`, asi que la encuentra igualmente.
_RSS_MEDIA_GROUP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
  <channel>
    <item>
      <title>media dentro de group</title>
      <link>https://example.com/grp</link>
      <media:group>
        <media:content url="https://example.com/foto-grp.jpg" medium="image"/>
      </media:group>
    </item>
  </channel>
</rss>
"""

# Atom con <media:content medium="image"> (mrss sobre Atom): el helper SI lo cubre
# (mira el attr `url`, presente aqui).
_ATOM_MEDIA_CONTENT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/">
  <entry>
    <title>Atom con media:content</title>
    <link rel="alternate" href="https://example.com/am"/>
    <media:content url="https://example.com/foto-atom.jpg" medium="image"/>
  </entry>
</feed>
"""

# Atom con <link rel="enclosure" type="image/*" href=...>: el enclosure de Atom expone la
# URL en `href` (no `url`); `_imagen_item` lo soporta.
_ATOM_LINK_ENCLOSURE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Atom con link enclosure</title>
    <link rel="alternate" href="https://example.com/ale"/>
    <link rel="enclosure" type="image/jpeg" href="https://example.com/atom-enc.jpg"/>
  </entry>
</feed>
"""


def test_parsear_imagen_enclosure_rss():
    """<enclosure type=image/*> -> item['imagen'] es esa url."""
    items = rss.parsear_feed(_RSS_ENCLOSURE_IMG_XML)
    assert items[0]["imagen"] == "https://example.com/enc.jpg"


def test_parsear_imagen_media_content_por_medium():
    """<media:content medium='image'> -> se extrae; el <image> del canal NO se usa."""
    items = rss.parsear_feed(_RSS_MEDIA_CONTENT_XML)
    assert items[0]["imagen"] == "https://example.com/foto-mc.jpg"
    # El logo del canal (<image><url>) jamas debe colarse como imagen del item.
    assert "LOGO-del-sitio" not in items[0]["imagen"]


def test_parsear_imagen_media_content_por_type():
    """<media:content type='image/*'> (sin medium) -> tambien se extrae."""
    items = rss.parsear_feed(_RSS_MEDIA_CONTENT_TYPE_XML)
    assert items[0]["imagen"] == "https://example.com/foto-mct.jpg"


def test_parsear_imagen_media_thumbnail():
    """<media:thumbnail url=...> -> se extrae."""
    items = rss.parsear_feed(_RSS_MEDIA_THUMBNAIL_XML)
    assert items[0]["imagen"] == "https://example.com/thumb.jpg"


def test_parsear_imagen_media_group_anidada():
    """<media:content> dentro de <media:group> -> el .iter() la encuentra igual."""
    items = rss.parsear_feed(_RSS_MEDIA_GROUP_XML)
    assert items[0]["imagen"] == "https://example.com/foto-grp.jpg"


def test_parsear_imagen_enclosure_audio_no_es_imagen():
    """<enclosure type='audio/*'> -> NO es imagen: item['imagen'] == ''."""
    items = rss.parsear_feed(_RSS_ENCLOSURE_AUDIO_XML)
    assert items[0]["imagen"] == ""


def test_parsear_imagen_ausente_es_vacia():
    """Un item sin media/enclosure de imagen -> item['imagen'] == ''."""
    items = rss.parsear_feed(_RSS_XML)
    assert all(i["imagen"] == "" for i in items)
    # Y el campo SIEMPRE esta presente (clave estable del contrato del parser).
    assert all("imagen" in i for i in items)


def test_parsear_imagen_atom_media_content():
    """Atom + <media:content medium='image'> (attr url) -> se extrae."""
    items = rss.parsear_feed(_ATOM_MEDIA_CONTENT_XML)
    assert items[0]["imagen"] == "https://example.com/foto-atom.jpg"


def test_parsear_atom_link_enclosure_se_extrae():
    """Atom <link rel='enclosure' type='image/*' href=...> -> se extrae (usa `href`)."""
    items = rss.parsear_feed(_ATOM_LINK_ENCLOSURE_XML)
    assert items[0]["imagen"] == "https://example.com/atom-enc.jpg"


# --------------------------------------------------------------------------- #
# Helper: alta de una fuente RSS (reutilizado por los tests de CRUD de fuentes)#
# --------------------------------------------------------------------------- #


def _fuente(cliente, nombre, url=_URL_OK, marca=""):
    cuerpo = {"nombre": nombre, "url": url}
    if marca:
        cuerpo["marca"] = marca
    return cliente.post("/api/rss/fuentes", json=cuerpo).json()["fuente"]


# --------------------------------------------------------------------------- #
# clave estable + filtros (funciones puras)                                   #
# --------------------------------------------------------------------------- #

# Feed con <guid> explicito (clave estable) y temas distintos para filtrar.
_RSS_GUID_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Avance de IA y agentes</title>
      <link>https://example.com/ia</link>
      <guid>guid-ia</guid>
      <description>Nuevos agentes autonomos</description>
    </item>
    <item>
      <title>Resultado del partido</title>
      <link>https://example.com/gol</link>
      <guid>guid-gol</guid>
      <description>Un gol de ultimo minuto</description>
    </item>
  </channel>
</rss>
"""


def test_clave_usa_guid_y_fallback_enlace():
    items = rss.parsear_feed(_RSS_GUID_XML)
    assert items[0]["clave"] == "guid-ia"
    # _RSS_XML no trae guid: clave cae al enlace
    sin_guid = rss.parsear_feed(_RSS_XML)
    assert sin_guid[0]["clave"] == "https://example.com/1"


def test_clave_atom_usa_id():
    items = rss.parsear_feed(_ATOM_XML)
    # _ATOM_XML no tiene <id>: clave cae al enlace
    assert items[0]["clave"] == "https://example.com/a"


def test_item_pasa_filtros_incluir():
    items = rss.parsear_feed(_RSS_GUID_XML)
    # solo el de IA pasa con incluir="ia, agentes"
    pasa = [i for i in items if rss.item_pasa_filtros(i, "ia, agentes", "")]
    assert [i["clave"] for i in pasa] == ["guid-ia"]


def test_item_pasa_filtros_excluir():
    items = rss.parsear_feed(_RSS_GUID_XML)
    # excluir "gol" deja fuera el partido
    pasa = [i for i in items if rss.item_pasa_filtros(i, "", "gol")]
    assert [i["clave"] for i in pasa] == ["guid-ia"]


def test_item_pasa_filtros_incluir_y_excluir():
    items = rss.parsear_feed(_RSS_GUID_XML)
    # incluir agentes pero excluir "autonomos" => ninguno
    pasa = [i for i in items if rss.item_pasa_filtros(i, "agentes", "autonomos")]
    assert pasa == []


def test_item_pasa_filtros_vacios_pasan_todo():
    items = rss.parsear_feed(_RSS_GUID_XML)
    assert all(rss.item_pasa_filtros(i, "", "") for i in items)


# --------------------------------------------------------------------------- #
# Orden por fecha (funcion pura): mas nuevo arriba, sin fecha al final          #
# --------------------------------------------------------------------------- #


def test_fecha_a_orden_parsea_rfc822_y_iso():
    # RFC 822 (pubDate RSS) e ISO 8601 (Atom) deben ser comparables entre si.
    rfc = rss.fecha_a_orden("Mon, 02 Jun 2025 10:00:00 GMT")
    iso = rss.fecha_a_orden("2025-06-02T11:00:00Z")
    assert iso > rfc  # mismo dia, una hora mas tarde


def test_fecha_a_orden_sin_fecha_va_al_minimo():
    assert rss.fecha_a_orden("") == rss._FECHA_MINIMA
    assert rss.fecha_a_orden(None) == rss._FECHA_MINIMA
    assert rss.fecha_a_orden("no es una fecha") == rss._FECHA_MINIMA


def test_ordenar_items_por_fecha_mas_nuevo_arriba():
    items = [
        {"titulo": "viejo", "fecha": "Mon, 01 Jan 2024 00:00:00 GMT"},
        {"titulo": "nuevo", "fecha": "2025-06-02T10:00:00Z"},
        {"titulo": "medio", "fecha": "Wed, 15 Jan 2025 00:00:00 GMT"},
    ]
    ordenados = rss.ordenar_items_por_fecha(items)
    assert [i["titulo"] for i in ordenados] == ["nuevo", "medio", "viejo"]


def test_ordenar_items_sin_fecha_al_final_y_estable():
    items = [
        {"titulo": "sin-a", "fecha": ""},
        {"titulo": "con-fecha", "fecha": "2025-06-02T10:00:00Z"},
        {"titulo": "sin-b", "fecha": ""},
    ]
    ordenados = rss.ordenar_items_por_fecha(items)
    # El que tiene fecha va arriba; los sin fecha caen al final conservando su orden.
    assert [i["titulo"] for i in ordenados] == ["con-fecha", "sin-a", "sin-b"]


# --------------------------------------------------------------------------- #
# Fuentes: crear con filtros/redes + PUT parcial + re-SSRF al cambiar url      #
# --------------------------------------------------------------------------- #


def test_crear_fuente_con_filtros_y_redes(cliente):
    r = cliente.post(
        "/api/rss/fuentes",
        json={
            "nombre": "Diario",
            "url": _URL_OK,
            "incluir": ["ia", "agentes"],
            "excluir": "rumor",
            "redes_def": ["instagram", "x"],
        },
    )
    assert r.status_code == 200
    f = r.json()["fuente"]
    assert f["activo"] is True
    assert "ia" in f["incluir"] and "agentes" in f["incluir"]
    assert f["excluir"] == "rumor"
    # redes_def sale como lista en orden fijo (x antes que instagram)
    assert f["redes_def"] == ["x", "instagram"]


def test_crear_fuente_redes_def_invalida_400(cliente):
    r = cliente.post(
        "/api/rss/fuentes", json={"nombre": "X", "url": _URL_OK, "redes_def": ["myspace"]}
    )
    assert r.status_code == 400


def test_put_fuente_parcial(cliente):
    f = _fuente(cliente, "Original")
    r = cliente.put(
        f"/api/rss/fuentes/{f['id']}",
        json={"nombre": "Renombrada", "activo": False, "incluir": "gol"},
    )
    assert r.status_code == 200
    act = r.json()["fuente"]
    assert act["nombre"] == "Renombrada"
    assert act["activo"] is False
    assert act["incluir"] == "gol"
    assert act["url"] == _URL_OK  # intacto


def test_put_fuente_inexistente_404(cliente):
    assert cliente.put("/api/rss/fuentes/noexiste", json={"nombre": "X"}).status_code == 404


def test_put_fuente_reSSRF_al_cambiar_url(cliente):
    f = _fuente(cliente, "Original")
    # cambiar a una URL que apunta a una IP privada => bloqueada por el guard SSRF
    r = cliente.put(f"/api/rss/fuentes/{f['id']}", json={"url": "http://127.0.0.1/feed.xml"})
    assert r.status_code == 400
    assert "permitida" in r.json()["error"].lower()


def test_put_fuente_url_valida_se_actualiza(cliente):
    f = _fuente(cliente, "Original")
    nueva = "https://93.184.216.35/otro.xml"
    r = cliente.put(f"/api/rss/fuentes/{f['id']}", json={"url": nueva})
    assert r.status_code == 200
    assert r.json()["fuente"]["url"] == nueva


def test_put_fuente_marca_invalida_400(cliente):
    f = _fuente(cliente, "Original")
    r = cliente.put(f"/api/rss/fuentes/{f['id']}", json={"marca": "marca_falsa"})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Fuentes: bandera `propia` (sitio de marca propia => imagen original reusable)  #
# --------------------------------------------------------------------------- #


def test_crear_fuente_propia_por_defecto_false(cliente):
    """Una fuente nace `propia=False` salvo que se pida explicitamente."""
    f = _fuente(cliente, "Diario")
    assert f["propia"] is False


def test_crear_fuente_propia_true(cliente):
    """POST con `propia=true` -> la fuente devuelta tiene `propia: true`."""
    r = cliente.post(
        "/api/rss/fuentes",
        json={"nombre": "Sitio propio", "url": _URL_OK, "marca": "unotv", "propia": True},
    )
    assert r.status_code == 200
    f = r.json()["fuente"]
    assert f["propia"] is True
    # Persiste: al listar tambien sale propia=True.
    listada = next(x for x in cliente.get("/api/rss/fuentes").json()["fuentes"] if x["id"] == f["id"])
    assert listada["propia"] is True


def test_put_fuente_alterna_propia(cliente):
    """PUT alterna `propia` en ambos sentidos (whitelist del campo)."""
    f = _fuente(cliente, "Original")
    assert f["propia"] is False
    act = cliente.put(f"/api/rss/fuentes/{f['id']}", json={"propia": True}).json()["fuente"]
    assert act["propia"] is True
    act = cliente.put(f"/api/rss/fuentes/{f['id']}", json={"propia": False}).json()["fuente"]
    assert act["propia"] is False


def test_put_fuente_propia_no_se_toca_si_ausente(cliente):
    """Un PUT que no menciona `propia` la deja intacta (PUT parcial)."""
    f = cliente.post(
        "/api/rss/fuentes", json={"nombre": "Propia", "url": _URL_OK, "propia": True}
    ).json()["fuente"]
    act = cliente.put(f"/api/rss/fuentes/{f['id']}", json={"nombre": "Renombrada"}).json()["fuente"]
    assert act["nombre"] == "Renombrada"
    assert act["propia"] is True  # intacta


# --------------------------------------------------------------------------- #
# Serializacion: publicacion_a_dict expone tipo_contenido + imagen_fuente, y     #
# imagen_url cae a imagen_fuente cuando no hay archivo subido. Funcion PURA       #
# (catalogos marcas/redes), sin DB.                                             #
# --------------------------------------------------------------------------- #

_PUB_BASE: dict = {
    "id": "p1",
    "titulo": "Titular",
    "marca": "unotv",
    "red": "x",
    "contenido": "cuerpo",
    "estado": "borrador",
    "veredicto": "",
    "fecha_creacion": "2026-05-19T10:00:00Z",
    "fecha_actualizacion": "2026-05-19T10:00:00Z",
    "fecha_programada": "",
    "origen": "",
}


def test_publicacion_a_dict_expone_tipo_e_imagen_fuente():
    """tipo_contenido='fuente' + imagen_fuente se serializan tal cual."""
    d = publicacion_a_dict(
        {**_PUB_BASE, "tipo_contenido": "fuente", "imagen_fuente": "https://e.com/orig.jpg"}
    )
    assert d["tipo_contenido"] == "fuente"
    assert d["imagen_fuente"] == "https://e.com/orig.jpg"


def test_publicacion_a_dict_imagen_url_cae_a_imagen_fuente():
    """Sin receta (placa oculta) ni archivo subido, imagen_url cae a la URL de la fuente.

    (Con receta de marca, `imagen_url` apunta al render on-demand `/compuesta`; eso lo cubre
    `test_render_pieza`. Aquí probamos el respaldo a `imagen_fuente` cuando NO hay composición.)
    """
    d = publicacion_a_dict(
        {**_PUB_BASE, "tipo_contenido": "fuente", "imagen_fuente": "https://e.com/orig.jpg",
         "placa_oculta": True}
    )
    assert d["imagen"] == ""
    assert d["imagen_url"] == "https://e.com/orig.jpg"


def test_publicacion_a_dict_archivo_subido_gana_a_imagen_fuente():
    """Con archivo subido, imagen_url sirve el archivo local (no la URL externa)."""
    d = publicacion_a_dict(
        {**_PUB_BASE, "tipo_contenido": "fuente", "imagen_fuente": "https://e.com/orig.jpg",
         "imagen": "subida.jpg"}
    )
    assert d["imagen_url"] == "/api/media/subida.jpg"


def test_publicacion_a_dict_defaults_sin_imagen_de_fuente():
    """Sin receta, tipo ni imagen_fuente: tipo_contenido cae a 'ia' e imagen_fuente/imagen_url vacios."""
    d = publicacion_a_dict({**_PUB_BASE, "placa_oculta": True})
    assert d["tipo_contenido"] == "ia"
    assert d["imagen_fuente"] == ""
    assert d["imagen_url"] == ""


def test_publicacion_a_dict_fuente_original_prefiere_nombre_del_medio():
    """`fuente_original` expone el nombre del medio copiado en la promoción (`fuente_nombre`)."""
    d = publicacion_a_dict(
        {**_PUB_BASE, "fuente_nombre": "Récord", "url_fuente": "record.com.mx/nota-1?id=7"}
    )
    assert d["fuente_original"] == "Récord"


def test_publicacion_a_dict_fuente_original_deriva_dominio_de_url():
    """Piezas viejas sin `fuente_nombre`: `fuente_original` deriva el dominio de `url_fuente`.

    La URL se guarda CANÓNICA (sin esquema ni www), pero el helper es defensivo ante una
    URL completa con esquema y `www.`.
    """
    d = publicacion_a_dict({**_PUB_BASE, "url_fuente": "record.com.mx/nota-1?id=7"})
    assert d["fuente_original"] == "record.com.mx"
    d = publicacion_a_dict({**_PUB_BASE, "url_fuente": "https://www.Record.com.mx/nota-1"})
    assert d["fuente_original"] == "record.com.mx"


def test_publicacion_a_dict_fuente_original_vacia_sin_nota_de_origen():
    """Creación propia (sin nota de origen): `fuente_original` vacía (la UI omite fuente/fecha)."""
    d = publicacion_a_dict(_PUB_BASE)
    assert d["fuente_original"] == ""


def test_publicacion_a_dict_expone_etapa_ia():
    """La pieza serializa `etapa_ia` derivada por `pipeline_estado.etapa_de_pieza` (Flujo C #3)."""
    from keni_consola import pipeline_estado as pe

    # La etapa se deriva del CONTENIDO REAL (¿hay copy?, ¿hay imagen?), no de los flags
    # almacenados (a54a3267): sin copy real -> generando_copy.
    d = publicacion_a_dict({**_PUB_BASE, "contenido": ""})
    assert d["etapa_ia"] == pe.ETAPA_GENERANDO_COPY
    # con copy y copy-in (la pieza LLEVA imagen) pero sin foto real -> generando_arte
    # ("Falta imagen"): la placa/plantilla no cuenta, hace falta foto subida o de fuente (95c28829).
    d = publicacion_a_dict({**_PUB_BASE, "copy_in": "TITULAR"})
    assert d["etapa_ia"] == pe.ETAPA_GENERANDO_ARTE
    # estado terminal manda sobre la checklist
    d = publicacion_a_dict({**_PUB_BASE, "estado": "publicado"})
    assert d["etapa_ia"] == pe.ETAPA_PUBLICADA
    # toda etapa serializada pertenece al contrato del feed
    assert d["etapa_ia"] in pe.ETAPAS_PIEZA
