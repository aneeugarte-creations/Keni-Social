"""Tests de la API de Campañas (HTTP, vía TestClient). Todo OFFLINE (fuente muestra).

Una campaña agrupa piezas por hashtag y puede abarcar VARIAS marcas (multimarca); su
analítica se computa al vuelo sobre el listado de piezas del periodo de cada marca. La
fuente de muestra NO inventa hashtags (los datos reales ya existen), así que en modo
muestra una campaña sale sin piezas: la mayoría de tests valida la FORMA de la respuesta y
el CRUD; el matching por hashtag y la agregación multimarca se prueban con un listado
inyectado (`monkeypatch`), sin depender de datos sembrados.
"""

from __future__ import annotations

from keni_consola import campanias


def _crear(cli, **campos):
    cuerpo = {"marcas": ["unotv"], "nombre": "Chihuahua", "hashtags": ["#Chihuahua"], **campos}
    return cli.post("/api/comercial/campanias", json=cuerpo)


def test_crear_listar_y_detalle(cliente):
    r = _crear(cliente)
    assert r.status_code == 201, r.text
    cam = r.json()["campania"]
    assert cam["marcas"] == ["unotv"]
    assert cam["marcas_nombres"] == ["UnoTV"]
    # El casing se CONSERVA tal cual se escribió (sin '#'): '#Chihuahua' -> 'Chihuahua'.
    assert cam["hashtags"] == ["Chihuahua"]
    assert cam["activa"] is True

    lista = cliente.get("/api/comercial/campanias")
    assert lista.status_code == 200
    assert any(c["id"] == cam["id"] for c in lista.json()["campanias"])

    d = cliente.get(f"/api/comercial/campanias/{cam['id']}")
    assert d.status_code == 200
    assert d.json()["campania"]["id"] == cam["id"]


def test_crear_multimarca(cliente):
    r = _crear(cliente, marcas=["unotv", "claro-sports"])
    assert r.status_code == 201, r.text
    cam = r.json()["campania"]
    assert cam["marcas"] == ["unotv", "claro-sports"]
    assert cam["marcas_nombres"] == ["UnoTV", "Claro Sports"]
    # El filtro por marca devuelve la campaña si la INCLUYE.
    incluida = cliente.get("/api/comercial/campanias?marca=claro-sports").json()["campanias"]
    assert any(c["id"] == cam["id"] for c in incluida)


def test_crear_conserva_casing_y_deduplica(cliente):
    # Dedup case-insensitive pero conservando el casing de la PRIMERA aparición.
    r = _crear(cliente, hashtags=["#Chihuahua", "chihuahua", "  #MX "])
    assert r.status_code == 201, r.text
    assert r.json()["campania"]["hashtags"] == ["Chihuahua", "MX"]


def test_crear_sin_hashtag_es_400(cliente):
    r = _crear(cliente, hashtags=[])
    assert r.status_code == 400
    assert "hashtag" in r.json()["error"].lower()


def test_crear_sin_marca_es_400(cliente):
    r = _crear(cliente, marcas=[])
    assert r.status_code == 400


def test_crear_marca_invalida_es_400(cliente):
    r = _crear(cliente, marcas=["no-existe"])
    assert r.status_code == 400


def test_actualizar_y_borrar(cliente):
    cam = _crear(cliente).json()["campania"]
    u = cliente.put(
        f"/api/comercial/campanias/{cam['id']}",
        json={
            "nombre": "Chihuahua 2026",
            "marcas": ["unotv", "claro-sports"],
            "hashtags": ["#Chihuahua", "#Turismo"],
        },
    )
    assert u.status_code == 200, u.text
    assert u.json()["campania"]["nombre"] == "Chihuahua 2026"
    assert u.json()["campania"]["marcas"] == ["unotv", "claro-sports"]
    assert u.json()["campania"]["hashtags"] == ["Chihuahua", "Turismo"]

    b = cliente.delete(f"/api/comercial/campanias/{cam['id']}")
    assert b.status_code == 200
    assert cliente.get(f"/api/comercial/campanias/{cam['id']}").status_code == 404


def test_analitica_devuelve_forma_kpis_tabla_tendencia_comparativa(cliente):
    cam = _crear(cliente).json()["campania"]
    r = cliente.get(f"/api/comercial/campanias/{cam['id']}/analitica?rango=mes")
    assert r.status_code == 200, r.text
    datos = r.json()
    # Forma del contrato: KPIs, piezas (lista), tendencia (puntos) y comparativa completa.
    assert {"visualizaciones", "interacciones", "engagement_pct", "piezas"} <= datos["kpis"].keys()
    assert isinstance(datos["piezas"], list)
    assert isinstance(datos["tendencia"]["puntos"], list)
    assert {"visualizaciones", "interacciones", "engagement_pct", "piezas"} <= datos["comparativa"].keys()
    assert "delta" in datos["comparativa"]["visualizaciones"]
    # Invariante: la suma de la tendencia diaria cuadra con el total de visualizaciones
    # (cada pieza se atribuye a su día de publicación, una sola vez). Vale aun con 0 piezas.
    suma_tend = sum(p["visualizaciones"] for p in datos["tendencia"]["puntos"])
    assert suma_tend == datos["kpis"]["visualizaciones"]


def test_analitica_matchea_hashtag_sin_importar_casing(cliente, monkeypatch):
    # El hashtag se guarda con casing ('Chihuahua') pero matchea posts con '#chihuahua',
    # '#CHIHUAHUA' o '#Chihuahua'. Un post sin el hashtag queda fuera.
    cam = _crear(cliente, hashtags=["#Chihuahua"]).json()["campania"]

    def _listado_falso(rango, marca=None):
        base = {
            "red": "instagram", "publicado": "2026-06-01", "url": "", "formato": "foto",
            "engagement_pct": 5.0, "interacciones": 100, "visualizaciones": 1000,
        }
        return [
            {**base, "id": "a", "titulo": "Sí", "texto": "Gran día en la sierra #chihuahua"},
            {**base, "id": "b", "titulo": "Sí2", "texto": "Turismo total #CHIHUAHUA #MX"},
            {**base, "id": "c", "titulo": "No", "texto": "Sin etiqueta de campaña #Sonora"},
        ]

    monkeypatch.setattr(campanias.servicio, "construir_listado_piezas", _listado_falso)
    r = cliente.get(f"/api/comercial/campanias/{cam['id']}/analitica?rango=mes")
    assert r.status_code == 200, r.text
    datos = r.json()
    ids = {p["id"] for p in datos["piezas"]}
    assert ids == {"a", "b"}  # los dos con #chihuahua en cualquier case; 'c' fuera
    assert datos["kpis"]["piezas"] == 2
    assert datos["kpis"]["visualizaciones"] == 2000


def test_analitica_multimarca_agrega_todas_las_marcas(cliente, monkeypatch):
    # Una campaña con dos marcas agrega las piezas de AMBAS (una llamada al listado por
    # marca). El listado falso devuelve una pieza por marca, etiquetada con #Chihuahua.
    cam = _crear(cliente, marcas=["unotv", "claro-sports"]).json()["campania"]

    def _listado_falso(rango, marca=None):
        return [{
            "id": f"p-{marca}", "red": "instagram", "titulo": f"Post {marca}",
            "texto": "campaña #Chihuahua", "publicado": "2026-06-01", "url": "",
            "formato": "foto", "engagement_pct": 5.0, "interacciones": 100, "visualizaciones": 1000,
        }]

    monkeypatch.setattr(campanias.servicio, "construir_listado_piezas", _listado_falso)
    datos = cliente.get(f"/api/comercial/campanias/{cam['id']}/analitica?rango=mes").json()
    # Dos marcas -> dos piezas distintas agregadas (una por marca).
    assert datos["kpis"]["piezas"] == 2
    assert datos["kpis"]["visualizaciones"] == 2000
    assert len({p["id"] for p in datos["piezas"]}) == 2


def test_analitica_campania_inexistente_es_404(cliente):
    r = cliente.get("/api/comercial/campanias/nada/analitica")
    assert r.status_code == 404
