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

from .conftest import _cliente, lanzador_generacion_completa

# IP publica literal: pasa el guard SSRF sin tocar DNS. example.com no se resuelve aqui.
_URL_OK = "https://93.184.216.34/feed.xml"

# Salida mock de la generacion de skills: ✅ + bloque json con dos piezas (sin red real).
_SALIDA_SKILL = """✅ Copy listo.

```json
{"piezas": [{"red": "x", "texto": "Tweet desde el item."},
            {"red": "instagram", "texto": "IG desde el item."}]}
```
"""


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
# Items: filtros del feed + usado + ocultar_usados + inactivas + salud         #
# --------------------------------------------------------------------------- #


def test_items_aplica_filtros_del_feed(cliente, monkeypatch):
    f = cliente.post(
        "/api/rss/fuentes", json={"nombre": "Filtrada", "url": _URL_OK, "incluir": "ia"}
    ).json()["fuente"]
    monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _RSS_GUID_XML)
    datos = cliente.get(f"/api/rss/items?fuente={f['id']}").json()
    assert [i["clave"] for i in datos["items"]] == ["guid-ia"]


def test_items_marca_usado_y_ocultar(cliente, monkeypatch):
    f = _fuente(cliente, "Diario")
    monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _RSS_GUID_XML)
    # marca guid-gol como usado
    r = cliente.post("/api/rss/items/usado", json={"fuente_id": f["id"], "clave": "guid-gol"})
    assert r.status_code == 200
    # sin ocultar: aparece con usado=True
    datos = cliente.get(f"/api/rss/items?fuente={f['id']}").json()
    por_clave = {i["clave"]: i for i in datos["items"]}
    assert por_clave["guid-gol"]["usado"] is True
    assert por_clave["guid-ia"]["usado"] is False
    # ocultar_usados=1: desaparece el usado
    datos = cliente.get(f"/api/rss/items?fuente={f['id']}&ocultar_usados=1").json()
    assert [i["clave"] for i in datos["items"]] == ["guid-ia"]


def test_items_usado_desmarcar(cliente, monkeypatch):
    f = _fuente(cliente, "Diario")
    monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _RSS_GUID_XML)
    cliente.post("/api/rss/items/usado", json={"fuente_id": f["id"], "clave": "guid-ia"})
    cliente.post(
        "/api/rss/items/usado", json={"fuente_id": f["id"], "clave": "guid-ia", "usado": False}
    )
    datos = cliente.get(f"/api/rss/items?fuente={f['id']}&ocultar_usados=1").json()
    assert {i["clave"] for i in datos["items"]} == {"guid-ia", "guid-gol"}


def test_items_usado_fuente_inexistente_404(cliente):
    r = cliente.post("/api/rss/items/usado", json={"fuente_id": "noexiste", "clave": "k"})
    assert r.status_code == 404


def test_items_usado_falta_clave_400(cliente):
    f = _fuente(cliente, "Diario")
    r = cliente.post("/api/rss/items/usado", json={"fuente_id": f["id"]})
    assert r.status_code == 400


def test_items_inactivas_ocultas_salvo_flag(cliente, monkeypatch):
    f = _fuente(cliente, "Diario")
    cliente.put(f"/api/rss/fuentes/{f['id']}", json={"activo": False})
    monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _RSS_GUID_XML)
    # por defecto, la inactiva no aporta items
    assert cliente.get("/api/rss/items").json()["items"] == []
    # con incluir_inactivas=1 si
    datos = cliente.get("/api/rss/items?incluir_inactivas=1").json()
    assert len(datos["items"]) == 2


def test_items_actualiza_salud_ok(cliente, monkeypatch):
    f = _fuente(cliente, "Diario")
    monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _RSS_GUID_XML)
    cliente.get(f"/api/rss/items?fuente={f['id']}")
    actual = next(x for x in cliente.get("/api/rss/fuentes").json()["fuentes"] if x["id"] == f["id"])
    assert actual["ultimo_conteo"] == 2
    assert actual["ultimo_error"] == ""
    assert actual["ultima_actualizacion"]  # fecha registrada


def test_items_actualiza_salud_error(cliente, monkeypatch):
    f = _fuente(cliente, "Diario")

    def revienta(url):  # noqa: ANN001
        raise rss.RSSError("No se pudo contactar con el feed.")

    monkeypatch.setattr(rss, "_DESCARGADOR", revienta)
    cliente.get(f"/api/rss/items?fuente={f['id']}")
    actual = next(x for x in cliente.get("/api/rss/fuentes").json()["fuentes"] if x["id"] == f["id"])
    assert actual["ultimo_conteo"] == 0
    assert actual["ultimo_error"] == "No se pudo contactar con el feed."


# --------------------------------------------------------------------------- #
# POST /api/rss/generar: reutiliza el auto-guardado de Skills (runner mockeado) #
# --------------------------------------------------------------------------- #


def test_generar_autocrea_publicaciones_y_marca_usado(entorno, monkeypatch):
    monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _RSS_GUID_XML)
    cli = _cliente(lanzar_generacion=lanzador_generacion_completa(_SALIDA_SKILL))
    f = _fuente(cli, "Diario", marca="unotv")

    r = cli.post(
        "/api/rss/generar",
        json={
            "titulo": "Avance de IA y agentes",
            "resumen": "Nuevos agentes autonomos",
            "enlace": "https://example.com/ia",
            "marca": "unotv",
            "redes": ["x", "instagram"],
            "fuente_id": f["id"],
            "clave": "guid-ia",
        },
    )
    assert r.status_code == 200
    # La generacion completa (fake sincrona): su `resultado` tiene la forma de copy.
    res = r.json()["generacion"]["resultado"]
    for clave in ("resultado", "historial_id", "verdicto", "piezas", "publicaciones"):
        assert clave in res
    assert res["verdicto"] == "listo"
    assert [p["red"] for p in res["publicaciones"]] == ["x", "instagram"]
    assert all(p["estado"] == "borrador" for p in res["publicaciones"])
    # Persistidas de verdad
    assert len(cli.get("/api/publicaciones").json()["publicaciones"]) == 2
    # El item quedo marcado como usado (solo al completar con exito).
    items = cli.get(f"/api/rss/items?fuente={f['id']}&ocultar_usados=1").json()["items"]
    assert "guid-ia" not in {i["clave"] for i in items}


def test_generar_sin_fuente_no_marca_pero_genera(entorno):
    cli = _cliente(lanzar_generacion=lanzador_generacion_completa(_SALIDA_SKILL))
    r = cli.post(
        "/api/rss/generar",
        json={"titulo": "Solo titulo", "marca": "unotv", "redes": ["x"]},
    )
    assert r.status_code == 200
    assert len(r.json()["generacion"]["resultado"]["publicaciones"]) == 1


def test_generar_marca_invalida_400(cliente):
    r = cliente.post(
        "/api/rss/generar", json={"titulo": "T", "marca": "marca_falsa", "redes": ["x"]}
    )
    assert r.status_code == 400


def test_generar_skill_invalida_400(cliente):
    r = cliente.post(
        "/api/rss/generar",
        json={"titulo": "T", "marca": "unotv", "skill": "skill-pirata", "redes": ["x"]},
    )
    assert r.status_code == 400


def test_generar_titulo_obligatorio_400(cliente):
    r = cliente.post("/api/rss/generar", json={"marca": "unotv", "redes": ["x"]})
    assert r.status_code == 400


def test_generar_skill_por_defecto(entorno):
    capturado = {}
    base = lanzador_generacion_completa(_SALIDA_SKILL)

    def lanzar(gen_id, *, prompt, cwd, procesar, dir_temporal=None):  # noqa: ANN001
        capturado["prompt"] = prompt
        base(gen_id, prompt=prompt, cwd=cwd, procesar=procesar, dir_temporal=dir_temporal)

    cli = _cliente(lanzar_generacion=lanzar)
    r = cli.post(
        "/api/rss/generar", json={"titulo": "T", "resumen": "R", "marca": "unotv", "redes": ["x"]}
    )
    assert r.status_code == 200
    # skill por defecto: copy-desde-nota; la nota concatena titulo + resumen
    assert "copy-desde-nota" in capturado["prompt"]
    assert "T" in capturado["prompt"] and "R" in capturado["prompt"]
