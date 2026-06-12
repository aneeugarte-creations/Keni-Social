"""Tests de la API Comercial (HTTP, vía TestClient). Todo OFFLINE.

Usa la fixture `cliente` (conftest), que aísla la persistencia en tmp y no toca la
red. La captura programada NO se arranca aquí (vive en `__main__`, no en `crear_app`).
AQUÍ NO HAY CIFRAS SINTÉTICAS: cuando un test necesita datos, inyecta la lectura
"real" monkeypatcheando `comercial.metricas_pieza.recalcular` (frontera Metricool);
sin lectura, las series quedan vacías y los resúmenes en ceros.
"""

from __future__ import annotations

from datetime import date, timedelta

from keni_consola import comercial


def _hace_dias(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


URL = "https://www.instagram.com/p/ABC123/"


def _crear(cli, **campos):
    cuerpo = {"url": URL, **campos}
    return cli.post("/api/comercial/publicaciones", json=cuerpo)


def _con_lectura(monkeypatch, interacciones=1500, visualizaciones=42000):
    lectura = {
        "encontrado": True,
        "interacciones": interacciones,
        "visualizaciones": visualizaciones,
    }
    monkeypatch.setattr(comercial.metricas_pieza, "recalcular", lambda m, r, i: lectura)


def _crear_con_datos(cli, monkeypatch, **campos):
    """Alta por id de post con una lectura real inyectada (la vía con cifras)."""
    _con_lectura(monkeypatch)
    cuerpo = {
        "id_post_metricool": campos.pop("id_post_metricool", "post-datos"),
        "marca": "unotv",
        "red": "instagram",
        **campos,
    }
    return cli.post("/api/comercial/publicaciones", json=cuerpo)


def test_opciones(cliente):
    r = cliente.get("/api/comercial/opciones")
    assert r.status_code == 200
    datos = r.json()
    assert {"marcas", "redes", "estados", "metricas"} <= datos.keys()
    ids_estado = {e["id"] for e in datos["estados"]}
    assert {"activa", "pausada", "cerrada"} == ids_estado
    assert {m["id"] for m in datos["metricas"]} == {"interacciones", "visualizaciones", "alcance"}


def test_crear_y_detalle(cliente, monkeypatch):
    r = _crear_con_datos(
        cliente,
        monkeypatch,
        titulo="Spot Verano",
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
    assert pub["actual"]["visualizaciones"] > 0
    assert pub["serie"]  # primer punto real capturado en el alta
    assert pub["alcanzado"] is True  # la lectura supera el objetivo

    # Detalle por id incluye serie.
    d = cliente.get(f"/api/comercial/publicaciones/{pub['id']}")
    assert d.status_code == 200
    assert d.json()["publicacion"]["serie"]


def test_crear_url_invalida(cliente):
    r = cliente.post("/api/comercial/publicaciones", json={"url": "no-es-un-enlace"})
    assert r.status_code == 400
    assert "http" in r.json()["error"]


def test_posts_seleccionables(cliente):
    """El selector de posts responde con estructura y procedencia (`fuente`)."""
    r = cliente.get("/api/comercial/posts?marca=unotv&red=instagram")
    assert r.status_code == 200, r.text
    datos = r.json()
    assert isinstance(datos["posts"], list)
    assert datos["fuente"]  # procedencia presente
    assert "es_muestra" not in datos


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


def test_actualizar(cliente, monkeypatch):
    pub = _crear_con_datos(cliente, monkeypatch, publicado=_hace_dias(5), objetivo=0).json()[
        "publicacion"
    ]
    r = cliente.put(
        f"/api/comercial/publicaciones/{pub['id']}",
        json={"estado": "pausada", "objetivo": 50, "metrica_objetivo": "interacciones"},
    )
    assert r.status_code == 200, r.text
    actualizado = r.json()["publicacion"]
    assert actualizado["estado"] == "pausada"
    assert actualizado["objetivo"] == 50
    # Bajar el objetivo a 50 con una lectura de 1500 interacciones marca el aviso.
    assert actualizado["alcanzado"] is True


def test_refrescar_una_y_todas(cliente):
    pub = _crear(cliente, estado="activa", publicado=_hace_dias(3)).json()["publicacion"]
    r1 = cliente.post(f"/api/comercial/publicaciones/{pub['id']}/refrescar")
    assert r1.status_code == 200
    r2 = cliente.post("/api/comercial/refrescar")
    assert r2.status_code == 200
    assert r2.json()["actualizadas"] >= 1


def test_reporte_json_y_md(cliente, monkeypatch):
    pub = _crear_con_datos(
        cliente, monkeypatch, titulo="Pieza KPI", cliente="ACME",
        publicado=_hace_dias(8), objetivo=100,
    ).json()["publicacion"]

    # JSON para verlo en la UI.
    rj = cliente.get(f"/api/comercial/reporte?publicacion={pub['id']}")
    assert rj.status_code == 200
    rep = rj.json()["reporte"]
    assert rep["tipo"] == "publicacion"
    assert rep["actual"]["visualizaciones"] > 0

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


def test_sin_fuente_no_hay_cifras_ni_flags_de_muestra(cliente):
    """Sin datos en la fuente NO se inventa nada ni existen flags de muestra.

    El alta por URL (sin `id_post_metricool`) no puede leer de Metricool: la serie
    queda vacía, el resumen en ceros, y ninguna respuesta lleva `es_muestra` ni el
    Markdown el viejo aviso de datos sintéticos.
    """
    pub = _crear(cliente, campania="Mundial", publicado=_hace_dias(7), objetivo=100).json()[
        "publicacion"
    ]

    # Alta + detalle: sin cifras inventadas y sin flag.
    assert "es_muestra" not in pub
    assert pub["serie"] == []
    assert pub["actual"]["interacciones"] == 0
    assert pub["actual"]["visualizaciones"] == 0
    detalle = cliente.get(f"/api/comercial/publicaciones/{pub['id']}").json()["publicacion"]
    assert "es_muestra" not in detalle

    # Listado: procedencia a nivel de respuesta, sin flags.
    lista = cliente.get("/api/comercial/publicaciones").json()
    assert "es_muestra" not in lista
    assert "fuente" in lista
    assert all("es_muestra" not in p for p in lista["publicaciones"])

    # Reportes (pieza y campaña): sin flag.
    rep_pieza = cliente.get(f"/api/comercial/reporte?publicacion={pub['id']}").json()["reporte"]
    assert "es_muestra" not in rep_pieza
    rep_camp = cliente.get("/api/comercial/reporte?campania=Mundial").json()["reporte"]
    assert "es_muestra" not in rep_camp

    # Markdown entregable: sin el viejo aviso de datos sintéticos.
    md = cliente.get(f"/api/comercial/reporte?publicacion={pub['id']}&formato=md").text
    assert "Datos de muestra" not in md


def test_reporte_sin_parametros(cliente):
    r = cliente.get("/api/comercial/reporte")
    assert r.status_code == 400


def test_eliminar(cliente):
    pub = _crear(cliente, publicado=_hace_dias(2)).json()["publicacion"]
    r = cliente.delete(f"/api/comercial/publicaciones/{pub['id']}")
    assert r.status_code == 200
    # Ya no existe.
    assert cliente.get(f"/api/comercial/publicaciones/{pub['id']}").status_code == 404
