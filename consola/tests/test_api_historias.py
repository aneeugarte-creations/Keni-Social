"""Tests de la API de HISTORIAS (/api/noticias/historias). OFFLINE: nunca se toca la red.

Sembramos `noticias_clusters` + sus `noticias_items` directo en `repos` (el daemon de ingesta
no corre en la suite) y ejercitamos: listado por recencia (`ultimo_visto` desc, `score` desempate)
+ filtros (marca/categoria/estado) + total, detalle con items, `usar` (lleva al tablero con
origen='historia', marca cluster + sus items usados) y `descartar`.
"""

from __future__ import annotations

from keni_consola import repos

from .conftest import _cliente  # noqa: F401  (usado por la fixture `cliente`)


def _sembrar_cluster(cid, *, score=0.5, marca="unotv", categoria="mx", estado="nuevo",
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


def test_historias_orden_por_recencia_desc_y_total(cliente):
    # La más NUEVA va primero aunque tenga menor `score` (recencia es el criterio primario).
    _sembrar_cluster("vieja", score=0.9, titulo="Historia vieja con score alto",
                     ultimo_visto="2026-06-01T12:00:00+00:00")
    _sembrar_cluster("nueva", score=0.2, titulo="Historia nueva con score bajo",
                     ultimo_visto="2026-06-05T12:00:00+00:00")
    datos = cliente.get("/api/noticias/historias").json()
    assert datos["total"] == 2
    assert [h["id"] for h in datos["historias"]] == ["nueva", "vieja"]
    assert datos["historias"][0]["marca_nombre"]  # marca-aware


def test_historias_score_desempata_misma_recencia(cliente):
    # Con el mismo `ultimo_visto`, el `score` mayor desempata primero.
    _sembrar_cluster("baja", score=0.2, titulo="Misma fecha, score bajo",
                     ultimo_visto="2026-06-05T12:00:00+00:00")
    _sembrar_cluster("alta", score=0.9, titulo="Misma fecha, score alto",
                     ultimo_visto="2026-06-05T12:00:00+00:00")
    datos = cliente.get("/api/noticias/historias").json()
    assert [h["id"] for h in datos["historias"]] == ["alta", "baja"]


def test_historias_incluye_enlaces_corroborantes(cliente):
    _sembrar_cluster("c1", items=[
        {"fuente_nombre": "Medio A", "url": "https://a.com/1", "titulo": "Titular A"},
        {"fuente_nombre": "Medio B", "url": "https://b.com/1", "titulo": "Titular B"},
    ])
    datos = cliente.get("/api/noticias/historias").json()
    enlaces = datos["historias"][0]["enlaces"]
    assert len(enlaces) == 2
    assert {e["fuente"] for e in enlaces} == {"Medio A", "Medio B"}
    assert all("url" in e and "titulo" in e for e in enlaces)


def test_historias_filtra_por_marca(cliente):
    _sembrar_cluster("u", marca="unotv")
    _sembrar_cluster("c", marca="claro-sports")
    datos = cliente.get("/api/noticias/historias", params={"marca": "claro-sports"}).json()
    assert datos["total"] == 1
    assert datos["historias"][0]["marca"] == "claro-sports"


def test_historias_filtra_por_categoria_y_estado(cliente):
    _sembrar_cluster("a", categoria="deportes")
    _sembrar_cluster("b", categoria="mx")
    assert cliente.get("/api/noticias/historias", params={"categoria": "deportes"}).json()["total"] == 1
    assert cliente.get("/api/noticias/historias", params={"estado": "nuevo"}).json()["total"] == 2
    assert cliente.get("/api/noticias/historias", params={"estado": "usado"}).json()["total"] == 0


def test_historias_marca_invalida_400(cliente):
    assert cliente.get("/api/noticias/historias", params={"marca": "no-existe"}).status_code == 400


def test_historias_estado_invalido_400(cliente):
    assert cliente.get("/api/noticias/historias", params={"estado": "raro"}).status_code == 400


# --------------------------------------------------------------------------- #
# detalle                                                                       #
# --------------------------------------------------------------------------- #


def test_detalle_devuelve_historia_y_items(cliente):
    _sembrar_cluster("c1", items=[
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
# usar / descartar                                                              #
# --------------------------------------------------------------------------- #


def test_usar_crea_borrador_con_origen_historia_y_marca_usado(cliente):
    _sembrar_cluster("c1", marca="unotv", titulo="Historia para usar", items=[
        {"url": "https://a.com/1", "titulo": "Titular A"},
    ])
    r = cliente.post("/api/noticias/historias/c1/usar", json={"generar": False})
    assert r.status_code == 200, r.text
    cont = r.json()["contenido"]
    assert cont["origen"] == "historia"
    assert cont["flujo"] == "importante"
    assert cont["titulo"] == "Historia para usar"
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
    _sembrar_cluster("c1")
    r = cliente.post(
        "/api/noticias/historias/c1/usar", json={"redes": ["x", "instagram"], "generar": False}
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["contenido"]["plataformas"]) == 2


def test_usar_idempotente_si_ya_usada(cliente):
    _sembrar_cluster("c1")
    primero = cliente.post("/api/noticias/historias/c1/usar", json={"generar": False}).json()
    segundo = cliente.post("/api/noticias/historias/c1/usar", json={"generar": False}).json()
    assert segundo.get("ya_usada") is True
    assert segundo["contenido"]["id"] == primero["contenido"]["id"]


def test_usar_inexistente_404(cliente):
    assert cliente.post("/api/noticias/historias/nope/usar", json={}).status_code == 404


def test_descartar_marca_descartada(cliente):
    _sembrar_cluster("c1")
    r = cliente.post("/api/noticias/historias/c1/descartar")
    assert r.status_code == 200, r.text
    assert r.json()["historia"]["estado"] == "descartado"
    assert repos.obtener_noticia_cluster("c1")["estado"] == "descartado"


def test_descartar_inexistente_404(cliente):
    assert cliente.post("/api/noticias/historias/nope/descartar").status_code == 404
