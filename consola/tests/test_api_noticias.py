"""Tests de la API del motor de ingesta (/api/noticias). OFFLINE: nunca se toca la red.

Inicializamos `noticias_items` directo en `repos` (el daemon de ingesta no corre en la suite) y
ejercitamos: listado recientes-primero, filtros (marca/categoria/estado/q), paginación
(limit/offset + total), `usar` (lleva al tablero con origen='noticia' + estado=usado),
`descartar` y el resumen de `cobertura`.
"""

from __future__ import annotations

from datetime import UTC

from keni_consola import repos

from .conftest import _cliente  # noqa: F401  (usado por la fixture `cliente`)


def _inicializar(**campos):
    """Crea un item de archivo con defaults razonables; devuelve su dict ya persistido."""
    base = {
        "fuente_id": "f1",
        "fuente_nombre": "Fuente",
        "categoria": "mx",
        "marca": "unotv",
        "titulo": "Titulo de prueba",
        "resumen": "Resumen de prueba",
        "url": "https://example.com/n",
        "url_canonica": "example.com/n",
        "clave": "example.com/n",
        "capturado_en": "2026-06-05T12:00:00+00:00",
    }
    base.update(campos)
    repos.crear_noticias_items([base])
    # Recupera el creado (listamos sin filtro y buscamos por clave/fuente).
    items, _ = repos.listar_noticias_items(limite=200)
    return next(it for it in items if it["clave"] == base["clave"] and it["fuente_id"] == base["fuente_id"])


def test_listar_vacio(cliente):
    datos = cliente.get("/api/noticias").json()
    assert datos == {"items": [], "total": 0}


def test_listar_recientes_primero_y_total(cliente):
    _inicializar(fuente_id="a", clave="k1", capturado_en="2026-06-01T00:00:00+00:00", titulo="vieja")
    _inicializar(fuente_id="b", clave="k2", capturado_en="2026-06-05T00:00:00+00:00", titulo="nueva")
    datos = cliente.get("/api/noticias").json()
    assert datos["total"] == 2
    assert [it["titulo"] for it in datos["items"]] == ["nueva", "vieja"]
    # marca_nombre resuelto (marca-aware en la UI).
    assert datos["items"][0]["marca_nombre"]


def test_filtra_por_marca(cliente):
    _inicializar(fuente_id="a", clave="k1", marca="unotv")
    _inicializar(fuente_id="b", clave="k2", marca="claro-sports")
    datos = cliente.get("/api/noticias", params={"marca": "claro-sports"}).json()
    assert datos["total"] == 1
    assert datos["items"][0]["marca"] == "claro-sports"


def test_marca_invalida_400(cliente):
    assert cliente.get("/api/noticias", params={"marca": "no-existe"}).status_code == 400


def test_filtra_por_estado(cliente):
    # Ya NO se filtra por categoría (el eje es marca/línea editorial): solo estado.
    _inicializar(fuente_id="a", clave="k1", categoria="deportes")
    _inicializar(fuente_id="b", clave="k2", categoria="mx")
    assert cliente.get("/api/noticias", params={"estado": "nuevo"}).json()["total"] == 2
    assert cliente.get("/api/noticias", params={"estado": "usado"}).json()["total"] == 0


def test_estado_invalido_400(cliente):
    assert cliente.get("/api/noticias", params={"estado": "raro"}).status_code == 400


def test_busqueda_q_en_titulo_y_resumen(cliente):
    _inicializar(fuente_id="a", clave="k1", titulo="Reforma energética aprobada")
    _inicializar(fuente_id="b", clave="k2", titulo="Otra cosa", resumen="habla de la Reforma")
    _inicializar(fuente_id="c", clave="k3", titulo="Nada que ver", resumen="deportes")
    datos = cliente.get("/api/noticias", params={"q": "reforma"}).json()
    assert datos["total"] == 2


def test_filtra_desde(cliente):
    _inicializar(fuente_id="a", clave="k1", capturado_en="2026-06-01T00:00:00+00:00")
    _inicializar(fuente_id="b", clave="k2", capturado_en="2026-06-05T00:00:00+00:00")
    datos = cliente.get("/api/noticias", params={"desde": "2026-06-03T00:00:00+00:00"}).json()
    assert datos["total"] == 1


def test_paginacion_limit_offset(cliente):
    for i in range(5):
        _inicializar(fuente_id=f"f{i}", clave=f"k{i}",
                 capturado_en=f"2026-06-0{i + 1}T00:00:00+00:00")
    pag1 = cliente.get("/api/noticias", params={"limit": 2, "offset": 0}).json()
    pag2 = cliente.get("/api/noticias", params={"limit": 2, "offset": 2}).json()
    assert pag1["total"] == 5 and pag2["total"] == 5
    assert len(pag1["items"]) == 2 and len(pag2["items"]) == 2
    # Sin solape entre páginas.
    assert {it["id"] for it in pag1["items"]}.isdisjoint({it["id"] for it in pag2["items"]})


# --------------------------------------------------------------------------- #
# usar / descartar                                                             #
# --------------------------------------------------------------------------- #


def test_usar_crea_borrador_y_marca_usado(cliente):
    it = _inicializar(fuente_id="a", clave="k1", marca="unotv", titulo="Noticia para usar")
    r = cliente.post(f"/api/noticias/{it['id']}/usar", json={"generar": False})
    assert r.status_code == 200, r.text
    cont = r.json()["contenido"]
    assert cont["origen"] == "noticia"
    assert cont["flujo"] == "importante"
    assert cont["titulo"] == "Noticia para usar"
    assert r.json()["copy_en_proceso"] is False
    # El item quedó usado + enlazado al contenido.
    refrescado = repos.obtener_noticia_item(it["id"])
    assert refrescado["estado"] == "usado"
    assert refrescado["publicacion_id"] == cont["id"]
    # Aparece en el tablero con origen 'noticia'.
    tablero = cliente.get("/api/publicaciones").json()["contenidos"]
    assert any(c["origen"] == "noticia" for c in tablero)


def test_usar_con_redes_crea_plataformas(cliente):
    it = _inicializar(fuente_id="a", clave="k1")
    r = cliente.post(
        f"/api/noticias/{it['id']}/usar", json={"redes": ["x", "instagram"], "generar": False}
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["contenido"]["plataformas"]) == 2


def test_usar_idempotente_si_ya_usado(cliente):
    it = _inicializar(fuente_id="a", clave="k1")
    primero = cliente.post(f"/api/noticias/{it['id']}/usar", json={"generar": False}).json()
    segundo = cliente.post(f"/api/noticias/{it['id']}/usar", json={"generar": False}).json()
    assert segundo.get("ya_usada") is True
    assert segundo["contenido"]["id"] == primero["contenido"]["id"]


def test_usar_inexistente_404(cliente):
    assert cliente.post("/api/noticias/nope/usar", json={}).status_code == 404


def test_descartar_marca_descartado(cliente):
    it = _inicializar(fuente_id="a", clave="k1")
    r = cliente.post(f"/api/noticias/{it['id']}/descartar")
    assert r.status_code == 200, r.text
    assert r.json()["item"]["estado"] == "descartado"
    assert repos.obtener_noticia_item(it["id"])["estado"] == "descartado"


def test_descartar_inexistente_404(cliente):
    assert cliente.post("/api/noticias/nope/descartar").status_code == 404


# --------------------------------------------------------------------------- #
# cobertura                                                                    #
# --------------------------------------------------------------------------- #


def test_cobertura_resume_salud(cliente):
    from datetime import datetime

    ahora = datetime.now(UTC).isoformat()
    # Una fuente activa + items recientes (capturados AHORA, dentro de la ventana de 24h).
    repos.crear_fuente_rss("Demo", "https://example.com/feed.xml", categoria="mx")
    _inicializar(fuente_id="a", clave="k1", categoria="mx", capturado_en=ahora)
    _inicializar(fuente_id="b", clave="k2", categoria="deportes", capturado_en=ahora)
    datos = cliente.get("/api/noticias/cobertura").json()
    assert datos["feeds_activos"] >= 1
    assert datos["items_total"] == 2
    assert datos["items_24h"] == 2
    # Desglose por categoría de las últimas 24h.
    assert datos["items_24h_por_categoria"].get("mx") == 1
    assert datos["items_24h_por_categoria"].get("deportes") == 1


# --------------------------------------------------------------------------- #
# Monitor de SALUD (Ola D): construir_salud (PURA) + _frescura_min            #
# --------------------------------------------------------------------------- #


def test_frescura_min_calcula_minutos_y_none_sin_item():
    from datetime import datetime

    from keni_consola.api import noticias

    ahora = datetime(2026, 6, 5, 12, 0, 0, tzinfo=UTC)
    assert noticias._frescura_min("2026-06-05T11:30:00+00:00", ahora=ahora) == 30
    assert noticias._frescura_min("", ahora=ahora) is None
    assert noticias._frescura_min("no-es-fecha", ahora=ahora) is None


def test_construir_salud_resumen_stale_y_huecos():
    from datetime import datetime

    from keni_consola.api import noticias

    ahora = datetime(2026, 6, 5, 12, 0, 0, tzinfo=UTC)
    feeds = [
        # Fresco (10 min): activo, no stale, categoría mx (con items 24h).
        {"id": "f1", "nombre": "Fresco", "categoria": "mx", "marca": "unotv", "activo": True,
         "desactivado_auto": False, "ultima_actualizacion": "x", "ultimo_error": "",
         "errores_seguidos": 0, "items_24h": 5, "ultimo_item": "2026-06-05T11:50:00+00:00"},
        # Stale (300 min > SLA 180): activo, categoría deportes SIN items 24h -> hueco.
        {"id": "f2", "nombre": "Viejo", "categoria": "deportes", "marca": "unotv", "activo": True,
         "desactivado_auto": False, "ultima_actualizacion": "x", "ultimo_error": "boom",
         "errores_seguidos": 2, "items_24h": 0, "ultimo_item": "2026-06-05T07:00:00+00:00"},
        # Auto-desactivado: no cuenta como activo ni como categoría esperada.
        {"id": "f3", "nombre": "Muerto", "categoria": "gaming", "marca": "unotv", "activo": False,
         "desactivado_auto": True, "ultima_actualizacion": "x", "ultimo_error": "muerto",
         "errores_seguidos": 8, "items_24h": 0, "ultimo_item": ""},
    ]
    distribuciones = {"por_categoria": {"mx": 5}, "por_idioma": {"es": 5}}
    salud = noticias.construir_salud(feeds, distribuciones, sla_min=180, ahora=ahora)
    r = salud["resumen"]
    assert r["feeds_total"] == 3
    assert r["activos"] == 2
    assert r["auto_desactivados"] == 1
    assert r["fallando"] == 2  # f2 y f3 tienen ultimo_error
    assert r["stale"] == 1  # solo f2 (activo + frescura > SLA)
    assert r["items_24h"] == 5
    assert r["por_categoria"] == {"mx": 5}
    assert r["por_idioma"] == {"es": 5}
    # 'deportes' es esperada (feed activo) pero sin items 24h -> hueco. 'gaming' no cuenta (inactivo).
    assert r["huecos"] == ["deportes"]
    assert r["frescura_global_min"] == 10
    # Por feed: frescura derivada.
    por_id = {f["id"]: f for f in salud["feeds"]}
    assert por_id["f1"]["frescura_min"] == 10
    assert por_id["f3"]["frescura_min"] is None
    assert por_id["f1"]["marca_nombre"] == "UnoTV"


def test_salud_endpoint_shape_y_filtro_marca(cliente):
    from datetime import datetime

    ahora = datetime.now(UTC).isoformat()
    repos.crear_fuente_rss("FeedUno", "https://example.com/f1.xml", marca="unotv", categoria="mx")
    _inicializar(fuente_id="z", clave="kz", categoria="mx", marca="unotv", capturado_en=ahora)
    datos = cliente.get("/api/noticias/salud?marca=unotv").json()
    assert "resumen" in datos
    assert "feeds" in datos
    assert datos["resumen"]["activos"] >= 1
    # Marca no permitida -> 400.
    assert cliente.get("/api/noticias/salud?marca=noexiste").status_code == 400
