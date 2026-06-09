"""Tests de la API de Campañas (HTTP, vía TestClient). Todo OFFLINE (fuente muestra).

Una campaña agrupa piezas por hashtag; su analítica se computa al vuelo sobre el listado
de piezas del periodo. En modo muestra, la fuente siembra `#Chihuahua` de forma
determinista, así que una campaña con ese hashtag tiene piezas sin tocar la red.
"""

from __future__ import annotations


def _crear(cli, **campos):
    cuerpo = {"marca": "unotv", "nombre": "Chihuahua", "hashtags": ["#Chihuahua"], **campos}
    return cli.post("/api/comercial/campanias", json=cuerpo)


def test_crear_listar_y_detalle(cliente):
    r = _crear(cliente)
    assert r.status_code == 201, r.text
    cam = r.json()["campania"]
    assert cam["marca"] == "unotv"
    assert cam["marca_nombre"] == "UnoTV"
    assert cam["hashtags"] == ["chihuahua"]  # normalizado: sin '#', minúsculas
    assert cam["activa"] is True

    lista = cliente.get("/api/comercial/campanias?marca=unotv")
    assert lista.status_code == 200
    assert any(c["id"] == cam["id"] for c in lista.json()["campanias"])

    d = cliente.get(f"/api/comercial/campanias/{cam['id']}")
    assert d.status_code == 200
    assert d.json()["campania"]["id"] == cam["id"]


def test_crear_normaliza_y_deduplica_hashtags(cliente):
    r = _crear(cliente, hashtags=["#Chihuahua", "chihuahua", "  #MX "])
    assert r.status_code == 201, r.text
    assert r.json()["campania"]["hashtags"] == ["chihuahua", "mx"]


def test_crear_sin_hashtag_es_400(cliente):
    r = _crear(cliente, hashtags=[])
    assert r.status_code == 400
    assert "hashtag" in r.json()["error"].lower()


def test_crear_marca_invalida_es_400(cliente):
    r = _crear(cliente, marca="no-existe")
    assert r.status_code == 400


def test_actualizar_y_borrar(cliente):
    cam = _crear(cliente).json()["campania"]
    u = cliente.put(
        f"/api/comercial/campanias/{cam['id']}",
        json={"nombre": "Chihuahua 2026", "hashtags": ["#Chihuahua", "#Turismo"]},
    )
    assert u.status_code == 200, u.text
    assert u.json()["campania"]["nombre"] == "Chihuahua 2026"
    assert u.json()["campania"]["hashtags"] == ["chihuahua", "turismo"]

    b = cliente.delete(f"/api/comercial/campanias/{cam['id']}")
    assert b.status_code == 200
    assert cliente.get(f"/api/comercial/campanias/{cam['id']}").status_code == 404


def test_analitica_devuelve_kpis_tabla_tendencia_comparativa(cliente):
    cam = _crear(cliente).json()["campania"]
    r = cliente.get(f"/api/comercial/campanias/{cam['id']}/analitica?rango=mes")
    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["es_muestra"] is True
    # En muestra se siembra #Chihuahua: la campaña debe tener piezas y KPIs > 0.
    assert datos["piezas"], "la campaña de muestra debe traer piezas con #Chihuahua"
    assert datos["kpis"]["visualizaciones"] > 0
    assert datos["kpis"]["interacciones"] > 0
    # La suma de la tendencia diaria cuadra con el total de visualizaciones (cada pieza
    # se atribuye a su día de publicación, una sola vez).
    suma_tend = sum(p["visualizaciones"] for p in datos["tendencia"]["puntos"])
    assert suma_tend == datos["kpis"]["visualizaciones"]
    # La comparativa trae los cuatro KPIs con su delta.
    assert {"visualizaciones", "interacciones", "engagement_pct", "piezas"} <= datos["comparativa"].keys()
    assert "delta" in datos["comparativa"]["visualizaciones"]


def test_analitica_campania_inexistente_es_404(cliente):
    r = cliente.get("/api/comercial/campanias/nada/analitica")
    assert r.status_code == 404
