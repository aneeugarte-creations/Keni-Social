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
                     ultimo_visto="2026-06-05T12:00:00+00:00", items=None):
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
# en el feed cuando existe su fila contenido_plataforma CON copy. `pieza_estado` deriva  #
# ese estado real para que la UI nunca diga "En el feed" si la pieza no está.            #
# --------------------------------------------------------------------------- #


def _usar_sin_pieza(cid):
    """Enlaza el cluster a un `contenido` usado SIN filas de plataforma (no sale en el feed)."""
    cont = repos.crear_contenido(clase="contenido", titulo="Tema", marca="unotv")
    repos.actualizar_noticia_cluster(cid, estado="usado", contenido_id=cont["id"])
    return cont


def _anadir_pieza(contenido_id, *, falta_copy):
    repos.crear_contenido_plataforma(
        contenido_id=contenido_id, red="x", falta_copy=falta_copy, falta_imagen=True
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
    # feed -> 'en_cola'. Es el bug del piloto: antes el badge decía "En el feed" igualmente.
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
    # Los PESOS vivos de la fórmula viajan con la historia: la UI enseña el cálculo
    # (señal × peso = aporte) sin caja negra.
    assert set(h["score_pesos"]) >= {"corroboracion", "velocidad", "frescura", "viralidad", "marca"}
    assert h["score_pesos"]["corroboracion"] > 0
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
        "estado": "usado", "contenido_id": "cont-1", "primera_fuente": "fa",
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
    assert refrescado["contenido_id"] == cont["id"]
    # Sus items quedaron usados + enlazados.
    items = repos.items_de_cluster("c1")
    assert items and all(it["estado"] == "usado" and it["contenido_id"] == cont["id"] for it in items)
    # Aparece en el tablero con origen 'historia'.
    tablero = cliente.get("/api/contenido").json()["contenidos"]
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


def test_descartar_marca_descartada(cliente):
    _inicializar_cluster("c1")
    r = cliente.post("/api/noticias/historias/c1/descartar")
    assert r.status_code == 200, r.text
    assert r.json()["historia"]["estado"] == "descartado"
    assert repos.obtener_noticia_cluster("c1")["estado"] == "descartado"


def test_descartar_inexistente_404(cliente):
    assert cliente.post("/api/noticias/historias/nope/descartar").status_code == 404


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
    assert repos.obtener_noticia_cluster("a")["estado"] == "descartado"
    assert repos.obtener_noticia_cluster("b")["estado"] == "descartado"
    assert repos.obtener_noticia_cluster("c")["estado"] == "nuevo"  # intacta


def test_descartar_lote_lista_vacia_no_borra_nada(cliente):
    _inicializar_cluster("a")
    r = cliente.post("/api/noticias/historias/descartar-lote", json={"ids": []})
    assert r.status_code == 200
    assert r.json() == {"descartadas": 0}
    assert repos.obtener_noticia_cluster("a")["estado"] == "nuevo"


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


def test_historias_exponen_explicacion_y_umbral(cliente):
    """Cada historia trae score_razon/score_desglose persistidos y la evaluación del umbral."""
    from datetime import UTC, datetime

    repos.upsert_noticia_cluster({
        "id": "expl", "titulo": "Sismo sacude la CDMX esta mañana",
        "resumen": "El gobierno de México activa el protocolo", "marca": "unotv",
        "categoria": "mx", "geo": "MX", "clave": "t:expl", "n_items": 2, "n_fuentes": 3,
        "idiomas": ["es"], "senal": 100, "score": 0.7, "breaking": 0,
        "verificacion": "corroborada",
        "score_razon": "3 fuentes · reciente · relevante para la marca (cdmx, sismo)",
        "score_desglose": {"corroboracion": 0.48, "frescura": 1.0, "viralidad": 0.33,
                            "marca": 0.67, "rendimiento": 0.0, "breaking": 0,
                            "palabras": ["cdmx", "sismo"]},
        "primer_visto": "2026-06-01T00:00:00+00:00",
        "ultimo_visto": datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds"),
        "estado": "nuevo",
    })

    datos = cliente.get("/api/noticias/historias").json()
    h = next(x for x in datos["historias"] if x["id"] == "expl")

    # Explicación persistida del score (razón humana + desglose por señal).
    assert "relevante para la marca" in h["score_razon"]
    assert h["score_desglose"]["palabras"] == ["cdmx", "sismo"]
    # Umbral: la MISMA evaluación que la promoción CI (fresca+corroborada+con marca → supera).
    assert h["promovible"] is True
    assert h["promovible_motivo"]


def test_historias_umbral_no_promovible_explica_por_que(cliente):
    """Una historia sin encaje de marca expone promovible=False con el motivo legible.

    Sin vocabulario de marca el score RECALCULADO no alcanza el umbral de producción, así
    que la PRIMERA regla que falla es la del score (`evaluar_umbral` rules 3<4): el motivo
    legible lo explica."""
    from datetime import UTC, datetime

    _inicializar_cluster(
        "sin-encaje", titulo="Celebrity gossip from Hollywood",
        ultimo_visto=datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds"),
    )
    datos = cliente.get("/api/noticias/historias").json()
    h = next(x for x in datos["historias"] if x["id"] == "sin-encaje")
    assert h["promovible"] is False
    assert "umbral de producción" in h["promovible_motivo"]


# --------------------------------------------------------------------------- #
# Etapas de Investigación visibles por historia (ADR 0011): QA + marca por IA  #
# --------------------------------------------------------------------------- #


def test_historia_expone_verificacion_fuente_y_marca_por_ia(cliente):
    """La historia trae el verificacion QA de su contenido (verificación) y si la marca fue IA."""
    cont = repos.crear_contenido(
        clase="contenido", titulo="Tema verificado", marca="unotv", categoria="mx",
        verificacion_fuente="no_verificado",
    )
    _inicializar_cluster("h-qa", marca="unotv")
    repos.actualizar_noticia_cluster("h-qa", estado="usado", contenido_id=cont["id"])
    repos.marcar_cluster_marca_ia("h-qa")

    h = next(
        x for x in cliente.get("/api/noticias/historias", params={"marca": "unotv"}).json()["historias"]
        if x["id"] == "h-qa"
    )
    assert h["verificacion_fuente"] == "no_verificado"  # verificacion QA del contenido asociado (batch)
    assert h["marca_clasificada_por_ia"] is True


def test_historia_sin_contenido_ni_ia_trae_campos_vacios(cliente):
    _inicializar_cluster("h-plain", marca="unotv")
    h = next(
        x for x in cliente.get("/api/noticias/historias", params={"marca": "unotv"}).json()["historias"]
        if x["id"] == "h-plain"
    )
    assert h["verificacion_fuente"] == ""
    assert h["marca_clasificada_por_ia"] is False


def test_historia_expone_qa_nativo_del_cluster_sin_contenido(cliente):
    """ADR 0011 F3: la QA vive en la HISTORIA. Una 'problema' SIN contenido (no se materializó)
    expone su verificacion igual — así la Mesa de Investigación la muestra ❗, no como 'sin QA'."""
    _inicializar_cluster("h-prob", marca="unotv")
    repos.marcar_cluster_qa("h-prob", "problema", '{"resumen": "dato falso"}')

    historias = cliente.get(
        "/api/noticias/historias", params={"marca": "unotv"}
    ).json()["historias"]
    h = next(x for x in historias if x["id"] == "h-prob")
    assert h["verificacion_fuente"] == "problema"  # nativo del cluster, sin contenido enlazado

    # El detalle también lo expone (mismo verificacion nativo).
    det = cliente.get("/api/noticias/historias/h-prob").json()["historia"]
    assert det["verificacion_fuente"] == "problema"


def test_marcar_cluster_qa_persiste_y_no_se_pisa_en_recalc(entorno):
    """ADR 0011 F3: `marcar_cluster_qa` sella el verificacion en la historia y un recalc (upsert) sin
    verificacion NO lo borra (`verificacion_fuente`/`verificar_hallazgos` en `_NO_PISAR`)."""
    _inicializar_cluster("h-v", marca="unotv")
    repos.marcar_cluster_qa("h-v", "no_verificado", '{"resumen":"ok"}')
    c = repos.obtener_noticia_cluster("h-v")
    assert c["verificacion_fuente"] == "no_verificado"
    assert c["verificar_hallazgos"] == '{"resumen":"ok"}'
    # Recalc del daemon (mismo id, sin verificacion): no debe revertir la verificación.
    _inicializar_cluster("h-v", marca="unotv", titulo="Historia re-puntuada")
    c2 = repos.obtener_noticia_cluster("h-v")
    assert c2["verificacion_fuente"] == "no_verificado"  # preservado pese al upsert
    assert c2["titulo"] == "Historia re-puntuada"  # el resto del recalc sí entra
