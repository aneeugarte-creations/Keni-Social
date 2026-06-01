"""Tests de la API Comercial (HTTP, vía TestClient). Todo OFFLINE.

Usa la fixture `cliente` (conftest), que aísla la persistencia en tmp y no toca la
red. La captura programada NO se arranca aquí (vive en `__main__`, no en `crear_app`).
"""

from __future__ import annotations

from datetime import date, timedelta


def _hace_dias(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


URL = "https://www.instagram.com/p/ABC123/"


def _crear(cli, **campos):
    cuerpo = {"url": URL, **campos}
    return cli.post("/api/comercial/publicaciones", json=cuerpo)


def test_opciones(cliente):
    r = cliente.get("/api/comercial/opciones")
    assert r.status_code == 200
    datos = r.json()
    assert {"marcas", "redes", "estados", "metricas"} <= datos.keys()
    ids_estado = {e["id"] for e in datos["estados"]}
    assert {"activa", "pausada", "cerrada"} == ids_estado
    assert {m["id"] for m in datos["metricas"]} == {"interacciones", "visualizaciones", "alcance"}


def test_crear_y_detalle(cliente):
    r = _crear(
        cliente,
        titulo="Spot Verano",
        marca="unotv",
        red="instagram",
        cliente="ACME",
        campania="Verano",
        publicado=_hace_dias(10),
        objetivo=100,
        metrica_objetivo="interacciones",
    )
    assert r.status_code == 201, r.text
    pub = r.json()["publicacion"]
    assert pub["marca_nombre"] == "UnoTV"
    assert pub["red_nombre"]  # resuelto en servidor
    assert pub["actual"]["alcance"] > 0
    assert pub["serie"]  # historico sembrado
    assert pub["alcanzado"] is True  # objetivo bajo en pieza de 10 dias

    # Detalle por id incluye serie.
    d = cliente.get(f"/api/comercial/publicaciones/{pub['id']}")
    assert d.status_code == 200
    assert d.json()["publicacion"]["serie"]


def test_crear_url_invalida(cliente):
    r = cliente.post("/api/comercial/publicaciones", json={"url": "no-es-un-enlace"})
    assert r.status_code == 400
    assert "http" in r.json()["error"]


def test_posts_seleccionables(cliente):
    """El selector de posts responde con estructura y procedencia (muestra en test)."""
    r = cliente.get("/api/comercial/posts?marca=unotv&red=instagram")
    assert r.status_code == 200, r.text
    datos = r.json()
    assert isinstance(datos["posts"], list)
    assert datos["es_muestra"] is True
    assert datos["fuente"] == "muestra"


def test_posts_marca_invalida(cliente):
    r = cliente.get("/api/comercial/posts?marca=no-existe")
    assert r.status_code == 400


def test_crear_por_post_seleccionado(cliente):
    """Alta por `id_post_metricool` + marca + red (sin pegar enlace)."""
    r = cliente.post(
        "/api/comercial/publicaciones",
        json={
            "id_post_metricool": "post-abc-123",
            "marca": "unotv",
            "red": "instagram",
            "titulo": "Pieza seleccionada",
            "publicado": _hace_dias(10),
        },
    )
    assert r.status_code == 201, r.text
    pub = r.json()["publicacion"]
    assert pub["id_post_metricool"] == "post-abc-123"
    assert pub["marca"] == "unotv"
    assert pub["red"] == "instagram"


def test_crear_por_id_post_exige_marca_y_red(cliente):
    sin_marca = cliente.post(
        "/api/comercial/publicaciones",
        json={"id_post_metricool": "x", "red": "instagram"},
    )
    assert sin_marca.status_code == 400
    sin_red = cliente.post(
        "/api/comercial/publicaciones",
        json={"id_post_metricool": "x", "marca": "unotv"},
    )
    assert sin_red.status_code == 400


def test_crear_marca_invalida(cliente):
    r = _crear(cliente, marca="no-existe")
    assert r.status_code == 400


def test_listar_y_filtro_estado(cliente):
    _crear(cliente, campania="C1", estado="activa", publicado=_hace_dias(5))
    _crear(cliente, campania="C2", estado="pausada", publicado=_hace_dias(5))
    todas = cliente.get("/api/comercial/publicaciones").json()["publicaciones"]
    assert len(todas) == 2
    activas = cliente.get("/api/comercial/publicaciones?estado=activa").json()["publicaciones"]
    assert len(activas) == 1
    assert activas[0]["estado"] == "activa"


def test_actualizar(cliente):
    pub = _crear(cliente, publicado=_hace_dias(5), objetivo=0).json()["publicacion"]
    r = cliente.put(
        f"/api/comercial/publicaciones/{pub['id']}",
        json={"estado": "pausada", "objetivo": 50, "metrica_objetivo": "interacciones"},
    )
    assert r.status_code == 200, r.text
    actualizado = r.json()["publicacion"]
    assert actualizado["estado"] == "pausada"
    assert actualizado["objetivo"] == 50
    # Bajar el objetivo a 50 en una pieza de 5 dias debe marcar el aviso.
    assert actualizado["alcanzado"] is True


def test_refrescar_una_y_todas(cliente):
    pub = _crear(cliente, estado="activa", publicado=_hace_dias(3)).json()["publicacion"]
    r1 = cliente.post(f"/api/comercial/publicaciones/{pub['id']}/refrescar")
    assert r1.status_code == 200
    r2 = cliente.post("/api/comercial/refrescar")
    assert r2.status_code == 200
    assert r2.json()["actualizadas"] >= 1


def test_reporte_json_y_md(cliente):
    pub = _crear(
        cliente, titulo="Pieza KPI", cliente="ACME", publicado=_hace_dias(8), objetivo=100
    ).json()["publicacion"]

    # JSON para verlo en la UI.
    rj = cliente.get(f"/api/comercial/reporte?publicacion={pub['id']}")
    assert rj.status_code == 200
    rep = rj.json()["reporte"]
    assert rep["tipo"] == "publicacion"
    assert rep["actual"]["alcance"] > 0

    # Markdown como descarga.
    rm = cliente.get(f"/api/comercial/reporte?publicacion={pub['id']}&formato=md")
    assert rm.status_code == 200
    assert "text/markdown" in rm.headers["content-type"]
    assert "attachment" in rm.headers["content-disposition"]
    assert "Reporte comercial" in rm.text


def test_reporte_campania(cliente):
    _crear(cliente, campania="Mundial", publicado=_hace_dias(6))
    _crear(cliente, campania="Mundial", publicado=_hace_dias(6))
    r = cliente.get("/api/comercial/reporte?campania=Mundial")
    assert r.status_code == 200
    assert r.json()["reporte"]["total"]["piezas"] == 2


def test_cifras_marcadas_como_muestra(cliente):
    """Mientras no haya APIs reales, todo va marcado como dato de muestra (#124).

    La cifra sintética no debe confundirse con datos reales: el flag `es_muestra`
    (y la `fuente` "muestra") tiene que viajar en cada respuesta que expone cifras.
    """
    pub = _crear(cliente, campania="Mundial", publicado=_hace_dias(7), objetivo=100).json()[
        "publicacion"
    ]

    # Alta + detalle: la pieza serializada se marca como muestra.
    assert pub["es_muestra"] is True
    assert pub["fuente"] == "muestra"
    detalle = cliente.get(f"/api/comercial/publicaciones/{pub['id']}").json()["publicacion"]
    assert detalle["es_muestra"] is True

    # Listado: flag común a nivel de respuesta + en cada item.
    lista = cliente.get("/api/comercial/publicaciones").json()
    assert lista["es_muestra"] is True
    assert lista["fuente"] == "muestra"
    assert all(p["es_muestra"] is True for p in lista["publicaciones"])

    # Reporte de pieza (JSON): el flag viaja en el reporte.
    rep_pieza = cliente.get(f"/api/comercial/reporte?publicacion={pub['id']}").json()["reporte"]
    assert rep_pieza["es_muestra"] is True
    assert rep_pieza["fuente"] == "muestra"

    # Reporte de campaña (JSON): idem.
    rep_camp = cliente.get("/api/comercial/reporte?campania=Mundial").json()["reporte"]
    assert rep_camp["es_muestra"] is True
    assert rep_camp["fuente"] == "muestra"

    # Markdown entregable: lleva el aviso visible de procedencia.
    md = cliente.get(f"/api/comercial/reporte?publicacion={pub['id']}&formato=md").text
    assert "Datos de muestra" in md


def test_reporte_sin_parametros(cliente):
    r = cliente.get("/api/comercial/reporte")
    assert r.status_code == 400


def test_eliminar(cliente):
    pub = _crear(cliente, publicado=_hace_dias(2)).json()["publicacion"]
    r = cliente.delete(f"/api/comercial/publicaciones/{pub['id']}")
    assert r.status_code == 200
    # Ya no existe.
    assert cliente.get(f"/api/comercial/publicaciones/{pub['id']}").status_code == 404
