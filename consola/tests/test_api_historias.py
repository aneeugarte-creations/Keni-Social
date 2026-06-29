"""Tests de la API de HISTORIAS (/api/noticias/historias). OFFLINE: nunca se toca la red.

Inicializamos `noticias_clusters` + sus `noticias_items` directo en `repos` (el daemon de ingesta
no corre en la suite) y ejercitamos: listado por recencia (`ultimo_visto` desc, `score` desempate)
+ filtros (marca/categoria/estado) + total, detalle con items, `usar` (lleva al tablero con
origen='historia', marca cluster + sus items usados) y `descartar`.
"""

from __future__ import annotations

from keni_consola import repos

from .conftest import _cliente  # noqa: F401  (usado por la fixture `cliente`)


def _inicializar_cluster(cid, *, score=0.5, marca="unotv", categoria="mx", estado="nuevo",
                     titulo="Historia de prueba", n_fuentes=2, breaking=0,
                     ultimo_visto="2026-06-05T12:00:00+00:00", items=None,
                     idioma="", traducido=0, titulo_es="", resumen_es=""):
    """Crea un cluster + (opcional) sus items enlazados; devuelve el cluster persistido."""
    repos.upsert_noticia_cluster({
        "id": cid,
        "titulo": titulo,
        "resumen": "Resumen de la historia",
        "marca": marca,
        "categoria": categoria,
        "geo": "MX",
        "clave": f"t:{cid}",
        "n_items": len(items or []),
        "n_fuentes": n_fuentes,
        "idiomas": ["es"],
        "idioma": idioma,
        "traducido": traducido,
        "titulo_es": titulo_es,
        "resumen_es": resumen_es,
        "senal": 100,
        "score": score,
        "breaking": breaking,
        "primer_visto": "2026-06-01T00:00:00+00:00",
        "ultimo_visto": ultimo_visto,
        "estado": estado,
    })
    for i, it in enumerate(items or []):
        base = {
            "fuente_id": it.get("fuente_id", f"f{i}"),
            "fuente_nombre": it.get("fuente_nombre", f"Fuente {i}"),
            "categoria": categoria,
            "marca": marca,
            "titulo": it.get("titulo", f"Articulo {i}"),
            "resumen": "r",
            "url": it.get("url", f"https://example.com/{cid}/{i}"),
            "url_canonica": it.get("url", f"example.com/{cid}/{i}"),
            "clave": f"{cid}-{i}",
            "cluster_id": cid,
            "capturado_en": "2026-06-05T12:00:00+00:00",
        }
        repos.crear_noticias_items([base])
        # crear_noticias_items no fija cluster_id en conflicto; lo aseguramos por id real.
        items_db, _ = repos.listar_noticias_items(limite=500)
        match = next(x for x in items_db if x["clave"] == base["clave"])
        repos.asignar_cluster_item(match["id"], cid)
    return repos.obtener_noticia_cluster(cid)


# --------------------------------------------------------------------------- #
# listado                                                                       #
# --------------------------------------------------------------------------- #


def test_historias_vacio(cliente):
    datos = cliente.get("/api/noticias/historias").json()
    assert datos == {"historias": [], "total": 0}


def test_historias_orden_por_score_desc_y_total(cliente):
    # La de MAYOR score va primero aunque sea más vieja: la jerarquización (algoritmo de
    # ponderación) es el criterio primario; la recencia solo desempata.
    _inicializar_cluster("vieja", score=0.9, titulo="Historia vieja con score alto",
                     ultimo_visto="2026-06-01T12:00:00+00:00")
    _inicializar_cluster("nueva", score=0.2, titulo="Historia nueva con score bajo",
                     ultimo_visto="2026-06-05T12:00:00+00:00")
    datos = cliente.get("/api/noticias/historias").json()
    assert datos["total"] == 2
    assert [h["id"] for h in datos["historias"]] == ["vieja", "nueva"]
    assert datos["historias"][0]["marca_nombre"]  # marca-aware


def test_historias_recencia_desempata_mismo_score(cliente):
    # Con el mismo `score`, la más reciente (`ultimo_visto`) desempata primero.
    _inicializar_cluster("vieja", score=0.5, titulo="Mismo score, más vieja",
                     ultimo_visto="2026-06-01T12:00:00+00:00")
    _inicializar_cluster("nueva", score=0.5, titulo="Mismo score, más nueva",
                     ultimo_visto="2026-06-05T12:00:00+00:00")
    datos = cliente.get("/api/noticias/historias").json()
    assert [h["id"] for h in datos["historias"]] == ["nueva", "vieja"]


def test_historias_incluye_enlaces_corroborantes(cliente):
    _inicializar_cluster("c1", items=[
        {"fuente_nombre": "Medio A", "url": "https://a.com/1", "titulo": "Titular A"},
        {"fuente_nombre": "Medio B", "url": "https://b.com/1", "titulo": "Titular B"},
    ])
    datos = cliente.get("/api/noticias/historias").json()
    enlaces = datos["historias"][0]["enlaces"]
    assert len(enlaces) == 2
    assert {e["fuente"] for e in enlaces} == {"Medio A", "Medio B"}
    assert all("url" in e and "titulo" in e for e in enlaces)


def test_historia_expone_id_de_fuente_para_marcar_origen(cliente):
    """La historia trae `primera_fuente_id` y cada enlace su `fuente_id`, para que la UI marque
    el origen (p. ej. Google Trends) sin fiarse del nombre del medio (en Trends, un outlet suelto)."""
    repos.upsert_noticia_cluster({
        "id": "gt", "titulo": "Tema viral", "resumen": "r", "marca": "unotv",
        "categoria": "mx", "geo": "MX", "clave": "t:gt", "n_items": 1, "n_fuentes": 1,
        "idiomas": ["es"], "senal": 100, "score": 0.5,
        "primer_visto": "2026-06-01T00:00:00+00:00", "ultimo_visto": "2026-06-05T12:00:00+00:00",
        "estado": "nuevo", "primera_fuente": "google-trends",
    })
    repos.crear_noticias_items([{
        "fuente_id": "google-trends", "fuente_nombre": "朝日新聞", "categoria": "mx",
        "marca": "unotv", "titulo": "Titular", "resumen": "r",
        "url": "https://medio.jp/x", "url_canonica": "medio.jp/x", "clave": "gt-0",
        "capturado_en": "2026-06-05T12:00:00+00:00",
    }])
    items_db, _ = repos.listar_noticias_items(limite=500)
    repos.asignar_cluster_item(next(x for x in items_db if x["clave"] == "gt-0")["id"], "gt")

    historia = cliente.get("/api/noticias/historias").json()["historias"][0]
    assert historia["primera_fuente_id"] == "google-trends"
    assert historia["enlaces"]
    assert all(e["fuente_id"] == "google-trends" for e in historia["enlaces"])


def test_historias_filtra_por_marca(cliente):
    _inicializar_cluster("u", marca="unotv")
    _inicializar_cluster("c", marca="claro-sports")
    datos = cliente.get("/api/noticias/historias", params={"marca": "claro-sports"}).json()
    assert datos["total"] == 1
    assert datos["historias"][0]["marca"] == "claro-sports"


def test_historias_filtra_por_estado(cliente):
    # Ya NO se filtra por categoría (el eje es marca/línea editorial): solo estado.
    _inicializar_cluster("a")
    _inicializar_cluster("b")
    assert cliente.get("/api/noticias/historias", params={"estado": "nuevo"}).json()["total"] == 2
    assert cliente.get("/api/noticias/historias", params={"estado": "usado"}).json()["total"] == 0


def test_historias_marca_invalida_400(cliente):
    assert cliente.get("/api/noticias/historias", params={"marca": "no-existe"}).status_code == 400


def test_historias_estado_invalido_400(cliente):
    assert cliente.get("/api/noticias/historias", params={"estado": "raro"}).status_code == 400


# --------------------------------------------------------------------------- #
# pieza_estado — transparencia del feed (el badge NO miente)                    #
# Una historia 'usado' solo significa "promovida", NO "en el feed": la pieza sale REAL  #
# en el feed cuando existe su fila pieza CON copy. `pieza_estado` deriva  #
# ese estado real para que la UI nunca diga "En el feed" si la pieza no está.            #
# --------------------------------------------------------------------------- #


def _usar_sin_pieza(cid):
    """Enlaza el cluster a un `contenido` usado SIN filas de plataforma (no sale en el feed)."""
    cont = repos.crear_publicacion(clase="contenido", titulo="Tema", marca="unotv")
    repos.actualizar_noticia_cluster(cid, estado="usado", publicacion_id=cont["id"])
    return cont


def _anadir_pieza(publicacion_id, *, falta_copy):
    repos.crear_pieza_fila(
        publicacion_id=publicacion_id, red="x", falta_copy=falta_copy, falta_imagen=True
    )


def _pieza_estado(cliente, cid):
    # Vía detalle: devuelve la historia sea cual sea su estado (no la filtra el listado).
    return cliente.get(f"/api/noticias/historias/{cid}").json()["historia"]["pieza_estado"]


def test_pieza_estado_en_pool_si_nueva(cliente):
    _inicializar_cluster("c1")  # estado 'nuevo'
    assert _pieza_estado(cliente, "c1") == "en_pool"


def test_pieza_estado_descartada(cliente):
    _inicializar_cluster("c1", estado="descartado")
    assert _pieza_estado(cliente, "c1") == "descartada"


def test_pieza_estado_en_cola_si_usada_sin_pieza(cliente):
    # Usada pero sin fila de plataforma (dedup / sin redes / copy por encolar): NO está en el
    # feed -> 'en_cola' (el badge no debe decir "En el feed").
    _inicializar_cluster("c1")
    _usar_sin_pieza("c1")
    assert _pieza_estado(cliente, "c1") == "en_cola"


def test_pieza_estado_generando_si_pieza_sin_copy(cliente):
    _inicializar_cluster("c1")
    cont = _usar_sin_pieza("c1")
    _anadir_pieza(cont["id"], falta_copy=True)
    assert _pieza_estado(cliente, "c1") == "generando"


def test_pieza_estado_en_feed_solo_con_pieza_y_copy(cliente):
    _inicializar_cluster("c1")
    cont = _usar_sin_pieza("c1")
    _anadir_pieza(cont["id"], falta_copy=False)
    assert _pieza_estado(cliente, "c1") == "en_feed"


def test_pieza_estado_en_listado_batch(cliente):
    # El listado computa `pieza_estado` en batch (sin N+1): una usada-sin-pieza y una nueva.
    _inicializar_cluster("c1", score=0.9)
    _usar_sin_pieza("c1")
    _inicializar_cluster("c2", score=0.1)
    historias = cliente.get("/api/noticias/historias").json()["historias"]
    por_id = {h["id"]: h["pieza_estado"] for h in historias}
    assert por_id == {"c1": "en_cola", "c2": "en_pool"}


# --------------------------------------------------------------------------- #
# devolver — rescatar una historia promovida que se quedó sin copy             #
# --------------------------------------------------------------------------- #


def test_devolver_rescata_al_pool_una_historia_atascada(cliente):
    # Promovida sin copy en el feed (en_cola): devolver borra el tema huérfano, reabre el cluster
    # y sus items, y la historia reaparece en el pool para decidir de nuevo.
    _inicializar_cluster("c1")
    cont = _usar_sin_pieza("c1")
    repos.marcar_items_cluster_usados("c1", cont["id"])
    assert _pieza_estado(cliente, "c1") == "en_cola"
    r = cliente.post("/api/noticias/historias/c1/devolver")
    assert r.status_code == 200
    assert r.json()["historia"]["pieza_estado"] == "en_pool"
    assert _pieza_estado(cliente, "c1") == "en_pool"
    assert repos.obtener_publicacion(cont["id"]) is None
    assert all(it["estado"] == "nuevo" for it in repos.items_de_cluster("c1"))


def test_devolver_no_toca_una_historia_ya_en_el_feed(cliente):
    _inicializar_cluster("c1")
    cont = _usar_sin_pieza("c1")
    _anadir_pieza(cont["id"], falta_copy=False)  # con copy real -> en_feed
    assert cliente.post("/api/noticias/historias/c1/devolver").status_code == 409
    assert repos.obtener_publicacion(cont["id"]) is not None


def test_devolver_409_si_sigue_en_el_pool(cliente):
    _inicializar_cluster("c1")  # 'nuevo': nada que devolver
    assert cliente.post("/api/noticias/historias/c1/devolver").status_code == 409


def test_devolver_404_si_no_existe(cliente):
    assert cliente.post("/api/noticias/historias/noexiste/devolver").status_code == 404


# --------------------------------------------------------------------------- #
# detalle                                                                       #
# --------------------------------------------------------------------------- #


def test_detalle_devuelve_historia_y_items(cliente):
    _inicializar_cluster("c1", items=[
        {"url": "https://a.com/1", "titulo": "Titular A"},
        {"url": "https://b.com/1", "titulo": "Titular B"},
    ])
    datos = cliente.get("/api/noticias/historias/c1").json()
    assert datos["historia"]["id"] == "c1"
    assert len(datos["items"]) == 2
    assert all(it["cluster_id"] == "c1" for it in datos["items"])


def test_detalle_inexistente_404(cliente):
    assert cliente.get("/api/noticias/historias/nope").status_code == 404


# --------------------------------------------------------------------------- #
# Tracking de fuentes: timeline + corroboración ponderada en la respuesta       #
# --------------------------------------------------------------------------- #


def test_historia_expone_timeline_de_fuentes_y_peso(cliente):
    # El daemon persiste `fuentes_detalle`/`peso_fuentes`/`primera_fuente*` al recalcular;
    # aquí se siembran directo y la API debe exponerlos (timeline con tier legible).
    repos.upsert_noticia_cluster({
        "id": "c1",
        "titulo": "Historia corroborada por potentes",
        "marca": "unotv",
        "clave": "t:c1",
        "n_fuentes": 2,
        "score": 0.7,
        "ultimo_visto": "2026-06-05T12:00:00+00:00",
        "peso_fuentes": 4.0,
        "velocidad": 1.0,
        "primera_fuente": "fa",
        "primera_fuente_nombre": "Reuters",
        "fuentes_detalle": [
            {"fuente_id": "fa", "fuente": "Reuters", "host": "reuters.com", "peso": 2.0,
             "primer_visto": "2026-06-05T10:00:00+00:00", "n_items": 1},
            {"fuente_id": "fb", "fuente": "BBC", "host": "bbc.com", "peso": 2.0,
             "primer_visto": "2026-06-05T10:15:00+00:00", "n_items": 1},
        ],
    })
    h = cliente.get("/api/noticias/historias/c1").json()["historia"]
    assert h["peso_fuentes"] == 4.0
    # Los PESOS de mérito vivos (perfil de la marca) viajan con la historia: la UI enseña el
    # cálculo (señal × peso = aporte; mérito × confianza = score) sin caja negra.
    assert set(h["score_pesos"]) >= {"frescura", "marca", "evento", "viralidad", "velocidad"}
    assert h["score_pesos"]["piso_confianza"] > 0
    assert h["score_pesos"]["velocidad"] > 0  # v2 reactiva velocidad (perfil UnoTV)
    assert h["primera_fuente_nombre"] == "Reuters"
    assert [f["fuente"] for f in h["fuentes"]] == ["Reuters", "BBC"]
    assert all(f["tier"] == "potente" for f in h["fuentes"])
    assert h["fuentes"][0]["primer_visto"] == "2026-06-05T10:00:00+00:00"


def test_enlaces_traen_publicado_en_y_tier(cliente):
    _inicializar_cluster("c1", items=[
        {"fuente_nombre": "Medio A", "url": "https://a.com/1", "titulo": "Titular A"},
    ])
    enlaces = cliente.get("/api/noticias/historias").json()["historias"][0]["enlaces"]
    assert enlaces[0]["publicado_en"]  # cae a capturado_en si el feed no traía pubDate
    assert enlaces[0]["tier"] == "normal"  # items inicializados sin fuente_peso -> 1.0


# --------------------------------------------------------------------------- #
# Rendimiento por fuente (GET /api/noticias/fuentes/stats)                      #
# --------------------------------------------------------------------------- #


def _inicializar_para_stats():
    """Dos historias (una usada) y dos fuentes: `fa` abrió la usada; `fb` corrobora ambas."""
    repos.upsert_noticia_cluster({
        "id": "h1", "titulo": "Historia usada", "marca": "unotv", "clave": "t:h1",
        "estado": "usado", "publicacion_id": "cont-1", "primera_fuente": "fa",
        "ultimo_visto": "2026-06-05T12:00:00+00:00",
    })
    repos.upsert_noticia_cluster({
        "id": "h2", "titulo": "Historia nueva", "marca": "unotv", "clave": "t:h2",
        "estado": "nuevo", "primera_fuente": "fb",
        "ultimo_visto": "2026-06-05T12:00:00+00:00",
    })
    # capturado_en por defecto = ahora: dentro de la ventana de stats.
    repos.crear_noticias_items([
        {"fuente_id": "fa", "fuente_nombre": "Reuters", "fuente_peso": 2.0, "marca": "unotv",
         "titulo": "A1", "clave": "fa-1", "cluster_id": "h1"},
        {"fuente_id": "fa", "fuente_nombre": "Reuters", "fuente_peso": 2.0, "marca": "unotv",
         "titulo": "A2", "clave": "fa-2", "cluster_id": "h1"},
        {"fuente_id": "fb", "fuente_nombre": "Medio B", "fuente_peso": 1.0, "marca": "unotv",
         "titulo": "B1", "clave": "fb-1", "cluster_id": "h1"},
        {"fuente_id": "fb", "fuente_nombre": "Medio B", "fuente_peso": 1.0, "marca": "unotv",
         "titulo": "B2", "clave": "fb-2", "cluster_id": "h2"},
    ])


def test_stats_fuentes_cuenta_historias_primeras_y_usadas(cliente):
    _inicializar_para_stats()
    datos = cliente.get("/api/noticias/fuentes/stats", params={"marca": "unotv"}).json()
    por_fuente = {f["fuente_id"]: f for f in datos["fuentes"]}
    fa, fb = por_fuente["fa"], por_fuente["fb"]
    assert fa["items"] == 2
    assert fa["historias"] == 1
    assert fa["primeras"] == 1  # abrió h1
    assert fa["usadas"] == 1
    assert fa["tasa_uso"] == 1.0
    assert fa["tier"] == "potente"
    assert fb["items"] == 2
    assert fb["historias"] == 2
    assert fb["primeras"] == 1  # abrió h2
    assert fb["usadas"] == 1
    assert fb["tasa_uso"] == 0.5
    # Orden: más historias primero.
    assert datos["fuentes"][0]["fuente_id"] == "fb"


def test_stats_fuentes_marca_invalida_400(cliente):
    assert cliente.get("/api/noticias/fuentes/stats", params={"marca": "nope"}).status_code == 400


def _inicializar_trends():
    """Una historia de Trends con dos medios distintos (no latinos) bajo el mismo fuente_id."""
    repos.upsert_noticia_cluster({
        "id": "ht", "titulo": "Tema en tendencia", "marca": "unotv", "clave": "t:ht",
        "estado": "nuevo", "primera_fuente": "google-trends",
        "ultimo_visto": "2026-06-05T12:00:00+00:00",
    })
    repos.crear_noticias_items([
        {"fuente_id": "google-trends", "fuente_nombre": "朝日新聞", "marca": "unotv",
         "titulo": "T1", "clave": "gt-1", "cluster_id": "ht"},
        {"fuente_id": "google-trends", "fuente_nombre": "وكالة صدى نيوز", "marca": "unotv",
         "titulo": "T2", "clave": "gt-2", "cluster_id": "ht"},
    ])


def test_stats_fuentes_google_trends_es_un_canal_unico(cliente):
    """Google Trends agrega muchos medios bajo un fuente_id; en rendimiento se muestra como UN
    canal 'Google Trends', no por el MAX(fuente_nombre) (un medio suelto, a menudo no latino)."""
    _inicializar_trends()
    datos = cliente.get("/api/noticias/fuentes/stats", params={"marca": "unotv"}).json()
    gt = next(f for f in datos["fuentes"] if f["fuente_id"] == "google-trends")
    assert gt["fuente_nombre"] == "Google Trends"
    assert gt["items"] == 2


def test_descubrimiento_devuelve_estado_y_rendimiento(cliente, monkeypatch):
    monkeypatch.setattr("keni_consola.config.trends_activo", lambda: True)
    monkeypatch.setattr("keni_consola.config.trends_geos", lambda: ("MX",))
    _inicializar_trends()
    datos = cliente.get("/api/noticias/descubrimiento", params={"marca": "unotv"}).json()
    assert datos["activo"] is True
    assert datos["geos"] == ["MX"]
    assert datos["max_por_tema"] == 3
    assert datos["stats"]["fuente_nombre"] == "Google Trends"
    assert datos["stats"]["items"] == 2


def test_descubrimiento_sin_aportes_devuelve_stats_nulo(cliente):
    """Sin items de Trends en la ventana, el canal reporta estado pero `stats` = null."""
    datos = cliente.get("/api/noticias/descubrimiento", params={"marca": "unotv"}).json()
    assert datos["stats"] is None
    assert "activo" in datos


_TRENDS_XML_VIVO = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0"><channel>'
    "<item><title>Eclipse solar</title><ht:approx_traffic>200 mil+</ht:approx_traffic>"
    "<ht:news_item><ht:news_item_title>Dónde ver el eclipse</ht:news_item_title>"
    "<ht:news_item_url>https://medio.mx/eclipse</ht:news_item_url>"
    "<ht:news_item_source>UnoTV</ht:news_item_source></ht:news_item></item>"
    "</channel></rss>"
)


def test_descubrimiento_terminos_en_vivo(cliente, monkeypatch):
    """La lista de términos en vivo descarga el RSS de Trends (mock) y lo devuelve por geo."""
    monkeypatch.setattr("keni_consola.config.trends_geos", lambda: ("MX",))
    monkeypatch.setattr("keni_consola.dominio.http_feed.validar_url", lambda u: (u, None))
    monkeypatch.setattr("keni_consola.dominio.http_feed._descargar_real", lambda u: _TRENDS_XML_VIVO)
    datos = cliente.get("/api/noticias/descubrimiento/terminos").json()
    assert datos["geos"] == ["MX"]
    assert datos["errores"] == []
    assert datos["terminos"][0]["termino"] == "Eclipse solar"
    assert datos["terminos"][0]["noticias"][0]["fuente"] == "UnoTV"


def test_descubrimiento_terminos_geo_caido_no_rompe(cliente, monkeypatch):
    """Un geo que falla al descargar se omite con su aviso; la respuesta no casca."""
    monkeypatch.setattr("keni_consola.config.trends_geos", lambda: ("MX",))
    monkeypatch.setattr("keni_consola.dominio.http_feed.validar_url", lambda u: (u, None))

    def explota(_url):
        from keni_consola.dominio import http_feed
        raise http_feed.RSSError("No se pudo contactar con el feed.")

    monkeypatch.setattr("keni_consola.dominio.http_feed._descargar_real", explota)
    datos = cliente.get("/api/noticias/descubrimiento/terminos").json()
    assert datos["terminos"] == []
    assert any("MX" in e for e in datos["errores"])


def test_cluster_por_url_canonica_cruza_items_de_cualquier_fuente(cliente):
    # Cruce exacto del clustering a NIVEL DE ITEM: encuentra el cluster aunque la url no sea
    # la clave del representativo (igualdad o prefijo `?` sobre la canónica de dedup).
    _inicializar_cluster("c1")
    repos.crear_noticias_items([{
        "fuente_id": "fx", "fuente_nombre": "Medio X", "titulo": "Titular",
        "clave": "a.com/nota?id=7", "cluster_id": "c1",
        "url": "https://a.com/nota?id=7", "url_canonica": "a.com/nota?id=7",
    }])
    assert repos.cluster_por_url_canonica("a.com/nota", "2020-01-01T00:00:00") == "c1"
    assert repos.cluster_por_url_canonica("a.com/otra", "2020-01-01T00:00:00") == ""
    assert repos.cluster_por_url_canonica("", "2020-01-01T00:00:00") == ""


# --------------------------------------------------------------------------- #
# usar / descartar                                                              #
# --------------------------------------------------------------------------- #


def test_usar_crea_borrador_con_origen_historia_y_marca_usado(cliente):
    _inicializar_cluster("c1", marca="unotv", titulo="Historia para usar", items=[
        {"url": "https://a.com/1", "titulo": "Titular A"},
    ])
    r = cliente.post("/api/noticias/historias/c1/usar", json={"generar": False})
    assert r.status_code == 200, r.text
    cont = r.json()["contenido"]
    assert cont["origen"] == "historia"
    assert cont["flujo"] == "importante"
    assert cont["titulo"] == "Historia para usar"
    # La LÍNEA del plan queda persistida en el contenido (la categoría de la historia):
    # cuenta en el cupo diario y hereda los horarios de su categoría.
    assert cont["categoria"] == "mx"
    # El cluster quedó usado + enlazado.
    refrescado = repos.obtener_noticia_cluster("c1")
    assert refrescado["estado"] == "usado"
    assert refrescado["publicacion_id"] == cont["id"]
    # Sus items quedaron usados + enlazados.
    items = repos.items_de_cluster("c1")
    assert items and all(it["estado"] == "usado" and it["publicacion_id"] == cont["id"] for it in items)
    # Aparece en el tablero con origen 'historia'.
    tablero = cliente.get("/api/publicaciones").json()["contenidos"]
    assert any(c["origen"] == "historia" for c in tablero)


def test_usar_con_redes_crea_plataformas(cliente):
    _inicializar_cluster("c1")
    r = cliente.post(
        "/api/noticias/historias/c1/usar", json={"redes": ["x", "instagram"], "generar": False}
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["contenido"]["plataformas"]) == 2


def test_usar_idempotente_si_ya_usada(cliente):
    _inicializar_cluster("c1")
    primero = cliente.post("/api/noticias/historias/c1/usar", json={"generar": False}).json()
    segundo = cliente.post("/api/noticias/historias/c1/usar", json={"generar": False}).json()
    assert segundo.get("ya_usada") is True
    assert segundo["contenido"]["id"] == primero["contenido"]["id"]


def test_usar_inexistente_404(cliente):
    assert cliente.post("/api/noticias/historias/nope/usar", json={}).status_code == 404


_TITULO_ES = "Taiwán espera aprobar pronto la venta de armas de EE. UU."


def _fake_traducir_ok(items, *, ejecutor=None):
    return [{"id": items[0]["id"], "titulo_es": _TITULO_ES, "resumen_es": "Resumen ES", "ok": True}]


def _fake_traducir_falla(items, *, ejecutor=None):
    return [{"id": items[0]["id"], "titulo_es": items[0]["titulo"], "resumen_es": "", "ok": False}]


def test_usar_extranjera_traduce_en_el_acto(cliente, monkeypatch):
    # Una historia en inglés sin traducir se traduce EN EL ACTO antes de bajar al tablero;
    # nunca sale en inglés y la traducción queda persistida en el cluster.
    monkeypatch.setattr("keni_consola.dominio.traducir.traducir_items", _fake_traducir_ok)
    _inicializar_cluster(
        "c1", titulo="Taiwan hopes US arms sale package can be approved soon",
        idioma="en", traducido=0,
    )
    r = cliente.post("/api/noticias/historias/c1/usar", json={"generar": False})
    assert r.status_code == 200, r.text
    assert r.json()["contenido"]["titulo"] == _TITULO_ES
    refrescado = repos.obtener_noticia_cluster("c1")
    assert bool(refrescado["traducido"]) is True
    assert refrescado["titulo_es"] == _TITULO_ES


def test_usar_extranjera_falla_traduccion_503(cliente, monkeypatch):
    # Si Haiku falla, NO se baja inglés al feed: 503 y la historia sigue sin usar (se reintenta).
    monkeypatch.setattr("keni_consola.dominio.traducir.traducir_items", _fake_traducir_falla)
    _inicializar_cluster(
        "c1", titulo="Taiwan hopes US arms sale package can be approved soon",
        idioma="en", traducido=0,
    )
    r = cliente.post("/api/noticias/historias/c1/usar", json={"generar": False})
    assert r.status_code == 503, r.text
    assert repos.obtener_noticia_cluster("c1")["estado"] != "usado"


def test_usar_extranjera_traducida_usa_titulo_es(cliente):
    # Ya traducida: el contenido nace con el título en español, nunca el original en inglés.
    _inicializar_cluster(
        "c1", titulo="Taiwan hopes US arms sale package can be approved soon",
        idioma="en", traducido=1, titulo_es="Taiwán espera que el paquete de armas de EE. UU. se apruebe pronto",
        resumen_es="Resumen en español",
    )
    r = cliente.post("/api/noticias/historias/c1/usar", json={"generar": False})
    assert r.status_code == 200, r.text
    assert r.json()["contenido"]["titulo"] == "Taiwán espera que el paquete de armas de EE. UU. se apruebe pronto"


def test_descartar_borra_la_historia_y_deja_lapida(cliente):
    # Descartar = BORRADO: la fila del cluster desaparece y sus items quedan como lápida
    # `descartado` (anti-reaparición). La respuesta reporta `estado='descartado'` por contrato.
    _inicializar_cluster("c1", items=[{"url": "https://a.com/1", "titulo": "Titular A"}])
    r = cliente.post("/api/noticias/historias/c1/descartar")
    assert r.status_code == 200, r.text
    assert r.json()["historia"]["estado"] == "descartado"
    assert repos.obtener_noticia_cluster("c1") is None  # la fila se borró
    # El item sobrevive como lápida `descartado` (bloquea la re-ingesta) y suelta su `cluster_id`
    # (el cluster ya no existe: no debe quedar colgando de una fila inexistente).
    items, _ = repos.listar_noticias_items(limite=500)
    lapidas = [it for it in items if it["url"] == "https://a.com/1"]
    assert lapidas and all(it["estado"] == "descartado" for it in lapidas)
    assert all(it["cluster_id"] == "" for it in lapidas)


def test_descartar_inexistente_404(cliente):
    assert cliente.post("/api/noticias/historias/nope/descartar").status_code == 404


def test_descartar_idempotente_si_ya_no_existe(cliente):
    # Doble descarte (o cluster ya purgado): el primero borra, el segundo es 404 amistoso.
    _inicializar_cluster("c1")
    assert cliente.post("/api/noticias/historias/c1/descartar").status_code == 200
    assert cliente.post("/api/noticias/historias/c1/descartar").status_code == 404


# --------------------------------------------------------------------------- #
# descartar-lote (papelera estilo correo: seleccionar + descartar)              #
# --------------------------------------------------------------------------- #


def test_descartar_lote_marca_solo_las_pasadas(cliente):
    _inicializar_cluster("a")
    _inicializar_cluster("b")
    _inicializar_cluster("c")
    r = cliente.post(
        "/api/noticias/historias/descartar-lote", json={"ids": ["a", "b", "a", "nope"]}
    )
    assert r.status_code == 200, r.text
    # 'a' deduplicada (no cuenta doble) y 'nope' inexistente (ignorada): solo a + b.
    assert r.json() == {"descartadas": 2}
    # Descartar = BORRADO: las filas de a y b desaparecen; c intacta.
    assert repos.obtener_noticia_cluster("a") is None
    assert repos.obtener_noticia_cluster("b") is None
    assert repos.obtener_noticia_cluster("c")["estado"] == "nuevo"  # intacta


def test_descartar_lote_lista_vacia_no_borra_nada(cliente):
    _inicializar_cluster("a")
    r = cliente.post("/api/noticias/historias/descartar-lote", json={"ids": []})
    assert r.status_code == 200
    assert r.json() == {"descartadas": 0}
    assert repos.obtener_noticia_cluster("a")["estado"] == "nuevo"  # intacta


def test_descartar_lote_ids_no_lista_400(cliente):
    r = cliente.post("/api/noticias/historias/descartar-lote", json={"ids": "a"})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# borrar-lote / borrar-todo (HARD delete: cluster + artículos; "dejar a 0")      #
# --------------------------------------------------------------------------- #


def test_borrar_lote_elimina_clusters_y_articulos(cliente):
    _inicializar_cluster("a", items=[{"url": "https://a.com/1"}])
    _inicializar_cluster("b")
    r = cliente.post("/api/noticias/historias/borrar-lote", json={"ids": ["a", "nope"]})
    assert r.status_code == 200, r.text
    assert r.json() == {"borradas": 1}  # 'nope' inexistente, ignorada
    assert repos.obtener_noticia_cluster("a") is None
    assert repos.obtener_noticia_cluster("b") is not None
    assert repos.items_de_cluster("a") == []  # los artículos también se fueron


def test_borrar_lote_ids_no_lista_400(cliente):
    assert (
        cliente.post("/api/noticias/historias/borrar-lote", json={"ids": "a"}).status_code == 400
    )


def test_borrar_todo_vacia_solo_la_marca(cliente):
    _inicializar_cluster("u1", marca="unotv", items=[{"url": "https://a.com/1"}])
    _inicializar_cluster("u2", marca="unotv")
    _inicializar_cluster("c1", marca="claro-sports")
    r = cliente.post("/api/noticias/historias/borrar-todo", json={"marca": "unotv"})
    assert r.status_code == 200, r.text
    assert r.json() == {"borradas": 2}
    assert repos.obtener_noticia_cluster("u1") is None
    assert repos.obtener_noticia_cluster("u2") is None
    assert repos.items_de_cluster("u1") == []  # artículos de la marca, fuera
    assert repos.obtener_noticia_cluster("c1") is not None  # otra marca intacta


def test_borrar_todo_respeta_filtro_estado(cliente):
    _inicializar_cluster("n", marca="unotv", estado="nuevo")
    _inicializar_cluster("d", marca="unotv", estado="descartado")
    r = cliente.post(
        "/api/noticias/historias/borrar-todo", json={"marca": "unotv", "estado": "descartado"}
    )
    assert r.status_code == 200
    assert r.json() == {"borradas": 1}
    assert repos.obtener_noticia_cluster("d") is None
    assert repos.obtener_noticia_cluster("n") is not None  # 'nuevo' no tocado


def test_borrar_todo_marca_invalida_400(cliente):
    r = cliente.post("/api/noticias/historias/borrar-todo", json={"marca": "no-existe"})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Relevancia EXPLICABLE + umbral en el contrato de la API                       #
# --------------------------------------------------------------------------- #


def _sembrar_expl(verificacion_fuente="verificado"):
    """Una historia fresca + corroborada + con encaje de marca, verificada (cumple umbral)."""
    from datetime import UTC, datetime

    repos.upsert_noticia_cluster({
        "id": "expl", "titulo": "Sismo sacude la CDMX esta mañana",
        "resumen": "El gobierno de México activa el protocolo", "marca": "unotv",
        "categoria": "mx", "geo": "MX", "clave": "t:expl", "n_items": 2, "n_fuentes": 3,
        "idiomas": ["es"], "senal": 100, "score": 0.7, "breaking": 0,
        "verificacion": "corroborada", "verificacion_fuente": verificacion_fuente,
        "score_razon": "3 fuentes · reciente · relevante para la marca (cdmx, sismo)",
        "score_desglose": {"corroboracion": 0.48, "frescura": 1.0, "viralidad": 0.33,
                            "marca": 0.67, "rendimiento": 0.0, "breaking": 0,
                            "palabras": ["cdmx", "sismo"]},
        "primer_visto": "2026-06-01T00:00:00+00:00",
        "ultimo_visto": datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds"),
        "estado": "nuevo",
    })


def test_historias_exponen_explicacion_y_umbral(cliente, monkeypatch):
    """Con la máquina ON + historia verificada que cumple umbral, `promovible=True`."""
    monkeypatch.setenv("KENI_PIPELINE_RECOLECTAR", "1")  # auto-promoción ENCENDIDA
    _sembrar_expl()

    datos = cliente.get("/api/noticias/historias").json()
    h = next(x for x in datos["historias"] if x["id"] == "expl")

    # Explicación persistida del score (razón humana + desglose por señal).
    assert "relevante para la marca" in h["score_razon"]
    assert h["score_desglose"]["palabras"] == ["cdmx", "sismo"]
    # "Sale sola al feed" HONESTO: máquina ON + verificada + umbral → promovible.
    assert h["promovible"] is True
    assert h["promovible_motivo"]


def test_historias_promovible_false_si_maquina_apagada(cliente, monkeypatch):
    """El badge es HONESTO: con la máquina APAGADA (default), nada sale solo aunque cumpla umbral."""
    monkeypatch.delenv("KENI_PIPELINE_RECOLECTAR", raising=False)
    _sembrar_expl()
    datos = cliente.get("/api/noticias/historias").json()
    h = next(x for x in datos["historias"] if x["id"] == "expl")
    assert h["promovible"] is False
    assert "apagada" in h["promovible_motivo"]


def test_historias_promovible_false_si_sin_verificar(cliente, monkeypatch):
    """Aunque la máquina esté ON, una historia sin verificar (la admisión la filtraría) no es promovible."""
    monkeypatch.setenv("KENI_PIPELINE_RECOLECTAR", "1")
    _sembrar_expl(verificacion_fuente="")  # pendiente de verificación
    datos = cliente.get("/api/noticias/historias").json()
    h = next(x for x in datos["historias"] if x["id"] == "expl")
    assert h["promovible"] is False
    assert "verificación" in h["promovible_motivo"]


def test_historias_umbral_no_promovible_explica_por_que(cliente, monkeypatch):
    """Con la máquina ON y verificada pero sin encaje de marca, falla el UMBRAL: motivo legible.

    Sin vocabulario de marca el score RECALCULADO no alcanza el umbral de producción, así
    que la PRIMERA regla que falla es la del score (`evaluar_umbral` rules 3<4): el motivo
    legible lo explica."""
    from datetime import UTC, datetime

    monkeypatch.setenv("KENI_PIPELINE_RECOLECTAR", "1")  # máquina ON: aislamos el fallo al umbral
    _inicializar_cluster(
        "sin-encaje", titulo="Celebrity gossip from Hollywood",
        ultimo_visto=datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds"),
    )
    # Verificada para pasar el gate de verificación y aislar el fallo del umbral.
    repos.marcar_cluster_verificacion("sin-encaje", "verificado")
    datos = cliente.get("/api/noticias/historias").json()
    h = next(x for x in datos["historias"] if x["id"] == "sin-encaje")
    assert h["promovible"] is False
    assert "umbral de producción" in h["promovible_motivo"]


# --------------------------------------------------------------------------- #
# Etapas de Investigación visibles por historia (ADR 0011): verificación + marca por IA  #
# --------------------------------------------------------------------------- #


def test_historia_expone_verificacion_fuente_y_marca_por_ia(cliente):
    """La historia trae el verificacion verificación de su contenido (verificación) y si la marca fue IA."""
    cont = repos.crear_publicacion(
        clase="contenido", titulo="Tema verificado", marca="unotv", categoria="mx",
        verificacion_fuente="verificado",
    )
    _inicializar_cluster("h-verificación", marca="unotv")
    repos.actualizar_noticia_cluster("h-verificación", estado="usado", publicacion_id=cont["id"])
    repos.marcar_cluster_marca_ia("h-verificación")

    h = next(
        x for x in cliente.get("/api/noticias/historias", params={"marca": "unotv"}).json()["historias"]
        if x["id"] == "h-verificación"
    )
    assert h["verificacion_fuente"] == "verificado"  # verificacion verificación del contenido asociado (batch)
    assert h["marca_clasificada_por_ia"] is True


def test_historia_sin_contenido_ni_ia_trae_campos_vacios(cliente):
    _inicializar_cluster("h-plain", marca="unotv")
    h = next(
        x for x in cliente.get("/api/noticias/historias", params={"marca": "unotv"}).json()["historias"]
        if x["id"] == "h-plain"
    )
    assert h["verificacion_fuente"] == ""
    assert h["marca_clasificada_por_ia"] is False


def test_historia_expone_verificacion_nativo_del_cluster_sin_contenido(cliente):
    """ADR 0011: la verificación vive en la HISTORIA. Una 'problema' SIN contenido (no se materializó)
    expone su verificacion igual — así la Mesa de Investigación la muestra ❗, no como 'sin verificación'."""
    _inicializar_cluster("h-prob", marca="unotv")
    repos.marcar_cluster_verificacion("h-prob", "rechazado", '{"resumen": "dato falso"}')

    historias = cliente.get(
        "/api/noticias/historias", params={"marca": "unotv"}
    ).json()["historias"]
    h = next(x for x in historias if x["id"] == "h-prob")
    assert h["verificacion_fuente"] == "rechazado"  # nativo del cluster, sin contenido enlazado

    # El detalle también lo expone (mismo verificacion nativo).
    det = cliente.get("/api/noticias/historias/h-prob").json()["historia"]
    assert det["verificacion_fuente"] == "rechazado"


def test_marcar_cluster_verificacion_persiste_y_no_se_pisa_en_recalc(entorno):
    """ADR 0011: `marcar_cluster_verificacion` sella el verificacion en la historia y un recalc (upsert) sin
    verificacion NO lo borra (`verificacion_fuente`/`verificar_hallazgos` en `_NO_PISAR`)."""
    _inicializar_cluster("h-v", marca="unotv")
    repos.marcar_cluster_verificacion("h-v", "verificado", '{"resumen":"ok"}')
    c = repos.obtener_noticia_cluster("h-v")
    assert c["verificacion_fuente"] == "verificado"
    assert c["verificar_hallazgos"] == '{"resumen":"ok"}'
    # Recalc del daemon (mismo id, sin verificacion): no debe revertir la verificación.
    _inicializar_cluster("h-v", marca="unotv", titulo="Historia re-puntuada")
    c2 = repos.obtener_noticia_cluster("h-v")
    assert c2["verificacion_fuente"] == "verificado"  # preservado pese al upsert
    assert c2["titulo"] == "Historia re-puntuada"  # el resto del recalc sí entra
