"""Tests de la API de Campañas (HTTP, vía TestClient). Todo OFFLINE (fuente muestra).

Una campaña agrupa piezas por hashtag y puede abarcar VARIAS marcas (multimarca); su
analítica se computa al vuelo sobre el listado de piezas del periodo de cada marca. La
fuente de muestra NO inventa hashtags (los datos reales ya existen), así que en modo
muestra una campaña sale sin piezas: la mayoría de tests valida la FORMA de la respuesta y
el CRUD; el matching por hashtag y la agregación multimarca se prueban con un listado
inyectado (`monkeypatch`), sin depender de datos inicializados.
"""

from __future__ import annotations

from keni_consola import campanias


def _crear(cli, **campos):
    cuerpo = {"marcas": ["unotv"], "nombre": "Chihuahua", "hashtags": ["#Chihuahua"], **campos}
    return cli.post("/api/campanias", json=cuerpo)


def test_crear_listar_y_detalle(cliente):
    r = _crear(cliente)
    assert r.status_code == 201, r.text
    cam = r.json()["campania"]
    assert cam["marcas"] == ["unotv"]
    assert cam["marcas_nombres"] == ["UnoTV"]
    # El casing se CONSERVA tal cual se escribió (sin '#'): '#Chihuahua' -> 'Chihuahua'.
    assert cam["hashtags"] == ["Chihuahua"]
    assert cam["activa"] is True

    lista = cliente.get("/api/campanias")
    assert lista.status_code == 200
    assert any(c["id"] == cam["id"] for c in lista.json()["campanias"])

    d = cliente.get(f"/api/campanias/{cam['id']}")
    assert d.status_code == 200
    assert d.json()["campania"]["id"] == cam["id"]


def test_crear_multimarca(cliente):
    r = _crear(cliente, marcas=["unotv", "claro-sports"])
    assert r.status_code == 201, r.text
    cam = r.json()["campania"]
    assert cam["marcas"] == ["unotv", "claro-sports"]
    assert cam["marcas_nombres"] == ["UnoTV", "Claro Sports"]
    # El filtro por marca devuelve la campaña si la INCLUYE.
    incluida = cliente.get("/api/campanias?marca=claro-sports").json()["campanias"]
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
        f"/api/campanias/{cam['id']}",
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

    b = cliente.delete(f"/api/campanias/{cam['id']}")
    assert b.status_code == 200
    assert cliente.get(f"/api/campanias/{cam['id']}").status_code == 404


def test_analitica_devuelve_forma_kpis_tabla_tendencia_comparativa(cliente):
    cam = _crear(cliente).json()["campania"]
    r = cliente.get(f"/api/campanias/{cam['id']}/analitica?rango=mes")
    assert r.status_code == 200, r.text
    datos = r.json()
    # Forma del contrato: KPIs, piezas (lista), tendencia (puntos) y comparativa completa.
    assert {"visualizaciones", "interacciones", "engagement_pct", "piezas"} <= datos["kpis"].keys()
    assert isinstance(datos["piezas"], list)
    assert isinstance(datos["tendencia"]["puntos"], list)
    assert {"visualizaciones", "interacciones", "engagement_pct", "piezas"} <= datos["comparativa"].keys()
    assert "delta" in datos["comparativa"]["visualizaciones"]
    # Desglose por red presente (lista de filas con la forma esperada).
    assert isinstance(datos["desglose_red"], list)
    # Invariante: la suma de la tendencia diaria cuadra con el total de visualizaciones
    # (cada pieza se atribuye a su día de publicación, una sola vez). Vale aun con 0 piezas.
    suma_tend = sum(p["visualizaciones"] for p in datos["tendencia"]["puntos"])
    assert suma_tend == datos["kpis"]["visualizaciones"]


def test_desglose_por_red_agrega_e_iguala_los_kpis(cliente, monkeypatch):
    """El desglose por red suma una fila por red, con sus granulares, y el total cuadra
    con los KPIs (cada pieza cuenta una vez)."""
    cam = _crear(cliente, hashtags=["#Chihuahua"]).json()["campania"]

    def _listado_falso(rango, marca=None):
        base = {"titulo": "x", "publicado": "2026-06-01", "url": "", "engagement_pct": 5.0}
        return [
            {**base, "id": "ig1", "red": "instagram", "formato": "reel", "texto": "a #chihuahua",
             "visualizaciones": 1000, "interacciones": 100, "likes": 80, "comentarios": 10,
             "compartidos": 7, "guardados": 3},
            {**base, "id": "ig2", "red": "instagram", "formato": "foto", "texto": "b #chihuahua",
             "visualizaciones": 500, "interacciones": 50, "likes": 40, "comentarios": 5,
             "compartidos": 3, "guardados": 2},
            {**base, "id": "tk1", "red": "tiktok", "formato": "video", "texto": "c #chihuahua",
             "visualizaciones": 2000, "interacciones": 300, "likes": 250, "comentarios": 30,
             "compartidos": 20, "guardados": 0},
        ]

    monkeypatch.setattr(campanias.servicio, "construir_listado_piezas", _listado_falso)
    datos = cliente.get(f"/api/campanias/{cam['id']}/analitica?rango=mes").json()
    desglose = {f["red"]: f for f in datos["desglose_red"]}
    assert set(desglose) == {"instagram", "tiktok"}
    # Ordenado por visualizaciones desc: tiktok (2000) antes que instagram (1500).
    assert [f["red"] for f in datos["desglose_red"]] == ["tiktok", "instagram"]
    assert desglose["instagram"]["piezas"] == 2
    assert desglose["instagram"]["visualizaciones"] == 1500
    assert desglose["instagram"]["likes"] == 120
    # El total del desglose cuadra con los KPIs.
    assert sum(f["visualizaciones"] for f in datos["desglose_red"]) == datos["kpis"]["visualizaciones"]
    assert sum(f["piezas"] for f in datos["desglose_red"]) == datos["kpis"]["piezas"]


def test_cross_post_incluye_gemelas_sin_hashtag(cliente, monkeypatch):
    """Una pieza cross-posteada a otra red SIN el hashtag (mismo cuerpo de caption) se
    cuenta en la campaña y se marca `por_cross_post`; contenido no relacionado NO entra."""
    cam = _crear(cliente, hashtags=["#Chihuahua"]).json()["campania"]
    cuerpo = "Gran reportaje desde la sierra tarahumara este fin de semana"

    def _listado_falso(rango, marca=None):
        base = {"titulo": "x", "publicado": "2026-06-01", "url": "", "engagement_pct": 5.0,
                "interacciones": 100}
        return [
            {**base, "id": "ig1", "red": "instagram", "formato": "reel",
             "texto": f"{cuerpo} #Chihuahua", "visualizaciones": 1000},
            {**base, "id": "tk1", "red": "tiktok", "formato": "video",  # mismo cuerpo, sin hashtag
             "texto": cuerpo, "visualizaciones": 2000},
            {**base, "id": "x1", "red": "x", "formato": "texto",  # no relacionada
             "texto": "Otra noticia distinta sin relacion alguna con lo anterior",
             "visualizaciones": 500},
        ]

    monkeypatch.setattr(campanias.servicio, "construir_listado_piezas", _listado_falso)
    datos = cliente.get(f"/api/campanias/{cam['id']}/analitica?rango=mes").json()
    filas = {p["id"]: p for p in datos["piezas"]}
    assert set(filas) == {"ig1", "tk1"}  # x1 (no relacionada) queda fuera
    assert datos["cross_posts"] == 1
    assert filas["ig1"]["por_cross_post"] is False
    assert filas["tk1"]["por_cross_post"] is True
    assert datos["kpis"]["piezas"] == 2
    assert datos["kpis"]["visualizaciones"] == 3000


def test_cross_post_no_empareja_captions_genericos_cortos(cliente, monkeypatch):
    """Un cuerpo demasiado corto NO siembra cross-post (evita falsos positivos): un TikTok
    corto sin el hashtag no se cuela por coincidir con un IG corto etiquetado."""
    cam = _crear(cliente, hashtags=["#Chihuahua"]).json()["campania"]

    def _listado_falso(rango, marca=None):
        base = {"titulo": "x", "publicado": "2026-06-01", "url": "", "engagement_pct": 5.0,
                "interacciones": 10, "visualizaciones": 100}
        return [
            {**base, "id": "ig1", "red": "instagram", "texto": "Gol! #Chihuahua"},
            {**base, "id": "tk1", "red": "tiktok", "texto": "Gol!"},  # corto: no debe entrar
        ]

    monkeypatch.setattr(campanias.servicio, "construir_listado_piezas", _listado_falso)
    datos = cliente.get(f"/api/campanias/{cam['id']}/analitica?rango=mes").json()
    assert {p["id"] for p in datos["piezas"]} == {"ig1"}
    assert datos["cross_posts"] == 0


def test_pieza_trae_marca_de_origen(cliente, monkeypatch):
    """Cada fila lleva su marca de origen (nombre legible desde `cuenta`/id_metricas), para
    poder agrupar y comparar en campañas multimarca."""
    cam = _crear(cliente, marcas=["unotv", "claro-sports"], hashtags=["#Chihuahua"]).json()["campania"]

    def _listado_falso(rango, marca=None):
        # `marca` es el id_metricas (guion_bajo); la fuente real lo sella en `cuenta`.
        return [{
            "id": f"p-{marca}", "red": "instagram", "titulo": f"Post {marca}",
            "texto": "campaña #Chihuahua", "publicado": "2026-06-01", "url": "",
            "formato": "foto", "engagement_pct": 5.0, "interacciones": 100,
            "visualizaciones": 1000, "cuenta": marca,
        }]

    monkeypatch.setattr(campanias.servicio, "construir_listado_piezas", _listado_falso)
    datos = cliente.get(f"/api/campanias/{cam['id']}/analitica?rango=mes").json()
    marca_por_id = {p["id"]: p["marca"] for p in datos["piezas"]}
    assert marca_por_id == {"p-unotv": "UnoTV", "p-claro_sports": "Claro Sports"}


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
    r = cliente.get(f"/api/campanias/{cam['id']}/analitica?rango=mes")
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
    datos = cliente.get(f"/api/campanias/{cam['id']}/analitica?rango=mes").json()
    # Dos marcas -> dos piezas distintas agregadas (una por marca).
    assert datos["kpis"]["piezas"] == 2
    assert datos["kpis"]["visualizaciones"] == 2000
    assert len({p["id"] for p in datos["piezas"]}) == 2


def test_inorganico_boost_es_fila_propia_y_campanias_con_nombre_se_excluyen(cliente, monkeypatch):
    """Lo inorgánico (Meta Ads): un POST IMPULSADO que casa por caption con una pieza de la
    campaña entra como FILA PROPIA (publicación inorgánica), con sus impresiones en la columna
    "Ads" y `es_inorganico=True`. Las campañas de pago con NOMBRE PROPIO (aunque contengan la
    palabra 'campaña') NO entran: viven en la sección Ads del dashboard. El conteo de
    piezas incluye el inorgánico; las visualizaciones orgánicas no se inflan."""
    cam = _crear(cliente, hashtags=["#Chihuahua"]).json()["campania"]
    cuerpo = "Gran reportaje en la sierra tarahumara este fin de semana"

    def _listado_falso(rango, marca=None):
        return [{
            "id": "ig1", "red": "instagram", "titulo": "Reportaje", "texto": f"{cuerpo} #Chihuahua",
            "publicado": "2026-06-01", "url": "", "formato": "reel", "engagement_pct": 5.0,
            "interacciones": 100, "visualizaciones": 1000, "cuenta": "claro_sports",
        }]

    def _ads_falso(rango, marca=None):
        return [
            # Boost del mismo contenido en FB (titular = primera línea del caption) -> fila.
            {"nombre": f'Publicación: "{cuerpo}"', "red": "facebook", "impresiones": 5000,
             "gasto": 300.0, "clics": 100, "moneda": "MXN", "inicio": "2026-06-01",
             "es_post_impulsado": True, "caption": cuerpo, "cuenta": "claro_sports"},
            # Campaña con nombre propio que contiene 'campaña' -> NO debe arrastrarse.
            {"nombre": "ALCANCE CAMPAÑA ASUS TUF A14", "red": "facebook", "impresiones": 99999,
             "gasto": 500.0, "clics": 0, "moneda": "MXN", "es_post_impulsado": False, "caption": ""},
        ]

    monkeypatch.setattr(campanias.servicio, "construir_listado_piezas", _listado_falso)
    monkeypatch.setattr(campanias.servicio, "construir_ads", _ads_falso)
    datos = cliente.get(f"/api/campanias/{cam['id']}/analitica?rango=mes").json()

    filas = {p["id"]: p for p in datos["piezas"]}
    # La pieza orgánica NO lleva pagadas; el boost es una fila aparte (id 'ad:...').
    assert filas["ig1"]["visualizaciones_pagadas"] == 0 and filas["ig1"]["es_inorganico"] is False
    inorg = [p for p in datos["piezas"] if p["es_inorganico"]]
    assert len(inorg) == 1
    assert inorg[0]["visualizaciones_pagadas"] == 5000 and inorg[0]["visualizaciones"] == 0
    assert inorg[0]["red"] == "facebook" and inorg[0]["marca"] == "Claro Sports"
    # ASUS (nombre propio) NO aparece como pieza.
    assert all("ASUS" not in p["titulo"] for p in datos["piezas"])
    # Totales inorgánicos = solo el boost; el conteo de piezas lo incluye (1 org + 1 inorg).
    assert datos["inorganico"]["visualizaciones"] == 5000
    assert datos["inorganico"]["campanias"] == 1
    assert datos["kpis"]["piezas"] == 2
    # Las visualizaciones ORGÁNICAS no se inflan con el inorgánico.
    assert datos["kpis"]["visualizaciones"] == 1000


def test_comparativa_piezas_cuenta_inorganico_en_ambos_periodos(cliente, monkeypatch):
    """La comparativa de "Piezas" enfrenta dos totales del mismo tipo: si el conteo actual
    incluye los boosts (inorgánico), el del periodo anterior también. Sin esto, una campaña
    con boosts en ambos periodos mostraría un crecimiento de piezas falso (actual con boost
    contra anterior sin él)."""
    cam = _crear(cliente, hashtags=["#Chihuahua"]).json()["campania"]
    cuerpo = "Gran reportaje en la sierra tarahumara este fin de semana"

    def _listado_falso(rango, marca=None):
        # Una pieza orgánica con el hashtag en CADA periodo (actual y anterior).
        return [{
            "id": f"ig-{rango}", "red": "instagram", "titulo": "Reportaje",
            "texto": f"{cuerpo} #Chihuahua", "publicado": "2026-06-01", "url": "",
            "formato": "reel", "engagement_pct": 5.0, "interacciones": 100,
            "visualizaciones": 1000, "cuenta": "claro_sports",
        }]

    def _ads_falso(rango, marca=None):
        # Un boost del mismo contenido en CADA periodo: ambos casan con su pieza orgánica.
        return [{
            "nombre": f'Publicación: "{cuerpo}"', "red": "facebook", "impresiones": 5000,
            "gasto": 300.0, "clics": 100, "moneda": "MXN", "inicio": "2026-06-01",
            "es_post_impulsado": True, "caption": cuerpo, "cuenta": "claro_sports",
        }]

    monkeypatch.setattr(campanias.servicio, "construir_listado_piezas", _listado_falso)
    monkeypatch.setattr(campanias.servicio, "construir_ads", _ads_falso)
    datos = cliente.get(f"/api/campanias/{cam['id']}/analitica?rango=mes").json()

    # Actual: 1 orgánica + 1 boost = 2 piezas. Anterior: igual (2), no 1.
    assert datos["kpis"]["piezas"] == 2
    assert datos["comparativa"]["piezas"]["actual"] == 2
    assert datos["comparativa"]["piezas"]["anterior"] == 2
    assert datos["comparativa"]["piezas"]["delta"] == 0


def test_analitica_campania_inexistente_es_404(cliente):
    r = cliente.get("/api/campanias/nada/analitica")
    assert r.status_code == 404


# --- Descarga de la analítica (export csv|md|json) ----------------------------


def _pieza_falsa(**extra):
    base = {
        "id": "ig1", "red": "instagram", "titulo": "Reportaje sierra",
        "texto": "Gran reportaje en la sierra tarahumara #Chihuahua", "publicado": "2026-06-01",
        "url": "https://ejemplo/ig1", "formato": "reel", "engagement_pct": 5.0,
        "interacciones": 100, "visualizaciones": 1000, "cuenta": "unotv",
    }
    return {**base, **extra}


def test_export_csv_trae_filas_de_piezas(cliente, monkeypatch):
    cam = _crear(cliente, hashtags=["#Chihuahua"]).json()["campania"]
    monkeypatch.setattr(
        campanias.servicio, "construir_listado_piezas", lambda *a, **k: [_pieza_falsa()]
    )
    r = cliente.get(f"/api/campanias/{cam['id']}/export?fmt=csv&rango=mes")
    assert r.status_code == 200, r.text
    assert "text/csv" in r.headers["content-type"]
    assert "attachment" in r.headers["content-disposition"]
    cuerpo = r.text
    # Cabecera con las columnas (incluidas las de pauta en modo normal) + la fila de la pieza.
    assert "Vistas" in cuerpo and "Ads" in cuerpo and "Origen" in cuerpo
    assert "Reportaje sierra" in cuerpo and "1000" in cuerpo


def test_export_md_es_reporte_legible(cliente, monkeypatch):
    cam = _crear(cliente, hashtags=["#Chihuahua"]).json()["campania"]
    monkeypatch.setattr(campanias.servicio, "construir_listado_piezas", lambda *a, **k: [])
    r = cliente.get(f"/api/campanias/{cam['id']}/export?fmt=md&rango=mes")
    assert r.status_code == 200
    assert "text/markdown" in r.headers["content-type"]
    cuerpo = r.text
    assert cuerpo.startswith("# Chihuahua")
    assert "## Resumen" in cuerpo and "## Piezas del periodo" in cuerpo


def test_export_json_devuelve_el_payload(cliente, monkeypatch):
    cam = _crear(cliente, hashtags=["#Chihuahua"]).json()["campania"]
    monkeypatch.setattr(campanias.servicio, "construir_listado_piezas", lambda *a, **k: [])
    r = cliente.get(f"/api/campanias/{cam['id']}/export?fmt=json&rango=mes")
    assert r.status_code == 200
    assert "application/json" in r.headers["content-type"]
    datos = r.json()  # texto JSON parseable
    assert datos["campania"]["id"] == cam["id"]
    assert "kpis" in datos and "piezas" in datos


def test_export_fmt_desconocido_cae_a_csv(cliente, monkeypatch):
    cam = _crear(cliente, hashtags=["#Chihuahua"]).json()["campania"]
    monkeypatch.setattr(campanias.servicio, "construir_listado_piezas", lambda *a, **k: [])
    r = cliente.get(f"/api/campanias/{cam['id']}/export?fmt=pdf&rango=mes")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]


def test_export_modo_cliente_oculta_la_pauta(cliente, monkeypatch):
    """ocultar_ads=1: el archivo no lleva rastro de pauta (sin columnas Ads/Origen, sin
    bloque inorgánico, y las vistas pagadas fundidas en las orgánicas)."""
    cam = _crear(cliente, hashtags=["#Chihuahua"]).json()["campania"]
    cuerpo = "Gran reportaje en la sierra tarahumara este fin de semana"

    def _listado_falso(rango, marca=None):
        return [_pieza_falsa(texto=f"{cuerpo} #Chihuahua", cuenta="claro_sports")]

    def _ads_falso(rango, marca=None):
        return [{
            "nombre": f'Publicación: "{cuerpo}"', "red": "facebook", "impresiones": 5000,
            "gasto": 300.0, "clics": 100, "moneda": "MXN", "inicio": "2026-06-01",
            "es_post_impulsado": True, "caption": cuerpo, "cuenta": "claro_sports",
        }]

    monkeypatch.setattr(campanias.servicio, "construir_listado_piezas", _listado_falso)
    monkeypatch.setattr(campanias.servicio, "construir_ads", _ads_falso)

    normal = cliente.get(f"/api/campanias/{cam['id']}/export?fmt=csv&rango=mes").text
    assert "Ads" in normal and "Inorgánico" in normal  # el boost se ve como fila inorgánica

    cli = cliente.get(f"/api/campanias/{cam['id']}/export?fmt=csv&rango=mes&ocultar_ads=1").text
    assert "Ads" not in cli and "Origen" not in cli

    j = cliente.get(f"/api/campanias/{cam['id']}/export?fmt=json&rango=mes&ocultar_ads=1").json()
    assert "inorganico" not in j
    assert all("visualizaciones_pagadas" not in p for p in j["piezas"])


def test_export_campania_inexistente_es_404(cliente):
    r = cliente.get("/api/campanias/nada/export?fmt=csv")
    assert r.status_code == 404
