"""MACRO-EVENTO (Fase A): persistencia de `noticias_clusters.tema_macro`.

`tema_macro` agrupa varias HISTORIAS distintas bajo un mismo gran evento (p. ej. "Cumbre del
G7") SIN fusionarlas. El test puro cubre el serializer; el test con Postgres (fixture `entorno`)
cubre el UPDATE por lote y que un upsell de recalc NO lo pise (`_NO_PISAR`).
"""
from __future__ import annotations


def test_serializer_expone_tema_macro_y_default_vacio():
    """`_fila_a_noticia_cluster` mapea `tema_macro`; NULL/"" -> "" (sin macro-evento)."""
    from keni_consola.db_noticias.clusters import _fila_a_noticia_cluster

    base = {c: "" for c in _columnas_base()}
    base.update({"n_items": 0, "n_fuentes": 0, "senal": 0, "score": 0.0, "breaking": 0,
                 "traducido": 0, "peso_fuentes": 0.0, "velocidad": 0.0, "idiomas": "[]"})

    con_tema = {**base, "tema_macro": "Cumbre del G7"}
    assert _fila_a_noticia_cluster(con_tema)["tema_macro"] == "Cumbre del G7"

    sin_tema = {**base, "tema_macro": None}
    assert _fila_a_noticia_cluster(sin_tema)["tema_macro"] == ""


def test_marcar_clusters_tema_macro_lista_vacia_no_toca_bd():
    """`ids` vacío -> 0 sin abrir conexión (early-return puro, no requiere Postgres)."""
    from keni_consola.db_noticias.clusters import marcar_clusters_tema_macro

    assert marcar_clusters_tema_macro([], "Cumbre del G7") == 0
    assert marcar_clusters_tema_macro([""], "Cumbre del G7") == 0


def test_marcar_clusters_tema_macro_actualiza_y_persiste(entorno):  # noqa: ARG001
    """UPDATE por lote: sella `tema_macro` en los ids dados y deja intactos los demás.

    Requiere Postgres (fixture `entorno`); lo ejecuta el CI, no el dev local.
    """
    from keni_consola import repos

    for cid in ("c1", "c2", "c3"):
        repos.upsert_noticia_cluster({"id": cid, "titulo": cid, "marca": "unotv"})

    n = repos.marcar_clusters_tema_macro(["c1", "c2", "zzz-inexistente"], "Cumbre del G7")
    assert n == 2

    assert repos.obtener_noticia_cluster("c1")["tema_macro"] == "Cumbre del G7"
    assert repos.obtener_noticia_cluster("c2")["tema_macro"] == "Cumbre del G7"
    assert repos.obtener_noticia_cluster("c3")["tema_macro"] == ""


def test_upsert_no_pisa_tema_macro(entorno):  # noqa: ARG001
    """Un recalc del cluster (upsert sin `tema_macro`) NO borra el macro-evento ya sellado.

    Requiere Postgres (fixture `entorno`); lo ejecuta el CI, no el dev local.
    """
    from keni_consola import repos

    repos.upsert_noticia_cluster({"id": "c1", "titulo": "t", "marca": "unotv"})
    repos.marcar_clusters_tema_macro(["c1"], "Cumbre del G7")

    repos.upsert_noticia_cluster({"id": "c1", "titulo": "t2", "marca": "unotv"})

    cluster = repos.obtener_noticia_cluster("c1")
    assert cluster["titulo"] == "t2"  # el recalc SÍ refresca el agregado
    assert cluster["tema_macro"] == "Cumbre del G7"  # pero NO pisa el macro-evento


def test_subtema_persiste_desde_el_esquema_declarativo(entorno):  # noqa: ARG001
    """`noticias_clusters.subtema` (declarado en el CREATE TABLE) sella y vuelve por lote.

    Cubre que la columna existe en el DDL fuente-de-verdad (no solo vía migración): un
    cluster nuevo guarda subtema "" y `marcar_clusters_subtema` lo sella sin tocar los demás.
    Requiere Postgres (fixture `entorno`); lo ejecuta el CI, no el dev local.
    """
    from keni_consola import repos

    for cid in ("c1", "c2"):
        repos.upsert_noticia_cluster({"id": cid, "titulo": cid, "marca": "unotv"})
    assert repos.obtener_noticia_cluster("c1")["subtema"] == ""

    n = repos.marcar_clusters_subtema(["c1"], "Partidos")
    assert n == 1
    assert repos.obtener_noticia_cluster("c1")["subtema"] == "Partidos"
    assert repos.obtener_noticia_cluster("c2")["subtema"] == ""


def test_grupos_duplicados_activos_detecta_mismo_evento(entorno):  # noqa: ARG001
    """Dos temas ACTIVOS de la misma marca con el MISMO (tema_macro, subtema) son un grupo
    de posible duplicado; una faceta distinta o un campo vacio NO agrupan.

    Requiere Postgres (fixture `entorno`); lo ejecuta el CI, no el dev local.
    """
    from keni_consola import repos

    a = repos.crear_publicacion(
        titulo="A", marca="unotv", tema_macro="Mundial 2026", subtema="partidos"
    )
    b = repos.crear_publicacion(
        titulo="B", marca="unotv", tema_macro="Mundial 2026", subtema="partidos"
    )
    faceta_distinta = repos.crear_publicacion(
        titulo="C", marca="unotv", tema_macro="Mundial 2026", subtema="sedes"
    )
    sin_subtema = repos.crear_publicacion(titulo="D", marca="unotv", tema_macro="Mundial 2026")
    for pub in (a, b, faceta_distinta, sin_subtema):
        repos.crear_pieza_fila(publicacion_id=pub["id"], red="x")

    grupos = repos.grupos_duplicados_activos()
    assert ("unotv", "Mundial 2026", "partidos") in grupos
    assert all(clave[2] != "sedes" for clave in grupos)  # faceta unica: no agrupa


def test_grupos_duplicados_ignora_temas_ya_publicados(entorno):  # noqa: ARG001
    """Un tema cuya unica pieza ya esta PUBLICADA no compite en la cola: no cuenta como
    duplicado activo (queda un solo tema activo -> sin grupo).

    Requiere Postgres (fixture `entorno`); lo ejecuta el CI, no el dev local.
    """
    from keni_consola import repos

    a = repos.crear_publicacion(titulo="A", marca="unotv", tema_macro="Final", subtema="cronica")
    b = repos.crear_publicacion(titulo="B", marca="unotv", tema_macro="Final", subtema="cronica")
    repos.crear_pieza_fila(publicacion_id=a["id"], red="x")
    plat_b = repos.crear_pieza_fila(publicacion_id=b["id"], red="x")
    repos.actualizar_pieza_fila(plat_b["id"], {"estado": "publicado"})

    assert ("unotv", "Final", "cronica") not in repos.grupos_duplicados_activos()


def test_listado_de_piezas_expone_posible_duplicado(cliente):
    """`GET /api/piezas` anade `posible_duplicado` a cada pieza: True solo en las activas
    cuyo tema comparte macro-evento con OTRO tema activo de la marca."""
    from keni_consola import repos

    a = repos.crear_publicacion(
        titulo="A", marca="unotv", tema_macro="Mundial 2026", subtema="partidos"
    )
    b = repos.crear_publicacion(
        titulo="B", marca="unotv", tema_macro="Mundial 2026", subtema="partidos"
    )
    suelto = repos.crear_publicacion(titulo="C", marca="unotv")
    ids_dup = set()
    for pub in (a, b):
        ids_dup.add(repos.crear_pieza_fila(publicacion_id=pub["id"], red="x")["id"])
    id_suelto = repos.crear_pieza_fila(publicacion_id=suelto["id"], red="x")["id"]

    piezas = cliente.get("/api/piezas").json()["piezas"]
    por_id = {p["id"]: p for p in piezas}
    assert por_id[id_suelto]["posible_duplicado"] is False
    assert all(por_id[i]["posible_duplicado"] is True for i in ids_dup)


def _columnas_base() -> tuple[str, ...]:
    from keni_consola.db_noticias.clusters import _COLS_NOTICIA_CLUSTER

    return _COLS_NOTICIA_CLUSTER
