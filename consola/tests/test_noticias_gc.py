"""Tests del GC del pool de noticias por RELEVANCIA (`db_noticias.purgar_pool_irrelevante`).

Siembra `noticias_clusters` + `noticias_items` directo en `repos` y comprueba que la purga
borra SOLO el ruido (historias `nuevo`, de una fuente, score bajo e inactivas) y CONSERVA lo
usado/ligado/corroborado/score alto/reciente. NO es un TTL (la edad es solo una condición).
Usa la fixture `entorno` (Postgres de pruebas; se salta si no hay).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from keni_consola import repos

_VIEJO = "2020-01-01T00:00:00+00:00"


def _ahora() -> str:
    return datetime.now(UTC).isoformat()


def _cluster(cid, *, score=0.05, n_fuentes=1, estado="nuevo", publicacion_id="",
             ultimo_visto=_VIEJO, marca="unotv"):
    repos.upsert_noticia_cluster({
        "id": cid, "titulo": f"Historia {cid}", "resumen": "r", "marca": marca,
        "categoria": "mx", "geo": "MX", "clave": f"t:{cid}", "n_items": 1, "n_fuentes": n_fuentes,
        "idiomas": ["es"], "senal": 0, "score": score, "breaking": 0,
        "primer_visto": _VIEJO, "ultimo_visto": ultimo_visto, "estado": estado,
        "publicacion_id": publicacion_id,
    })
    return cid


def _ids(estado=None):
    clusters, _ = repos.listar_noticia_clusters(estado=estado, limite=500)
    return {c["id"] for c in clusters}


def test_purga_ruido_conserva_lo_valioso(entorno):
    """Borra la historia de una fuente, score bajo e inactiva; conserva el resto."""
    _cluster("ruido", score=0.05, n_fuentes=1)                    # purgable
    _cluster("corroborada", score=0.05, n_fuentes=3)             # multi-fuente -> conservar
    _cluster("score_alto", score=0.9, n_fuentes=1)              # score alto -> conservar
    _cluster("usada", score=0.05, n_fuentes=1, estado="usado")  # usada -> conservar
    _cluster("ligada", score=0.05, n_fuentes=1, publicacion_id="c123")  # ligada -> conservar
    _cluster("reciente", score=0.05, n_fuentes=1, ultimo_visto=_ahora())  # reciente -> conservar

    resumen = repos.purgar_pool_irrelevante(score_umbral=0.15, inactividad_horas=1)

    assert resumen["clusters"] == 1
    vivos = _ids()
    assert "ruido" not in vivos
    assert {"corroborada", "score_alto", "usada", "ligada", "reciente"} <= vivos


def test_dry_run_cuenta_sin_borrar(entorno):
    _cluster("ruido", score=0.05, n_fuentes=1)

    resumen = repos.purgar_pool_irrelevante(score_umbral=0.15, inactividad_horas=1, dry_run=True)

    assert resumen["clusters"] == 1 and resumen["dry_run"] == 1
    assert "ruido" in _ids()  # NO se borró


def test_no_borra_por_edad_sola(entorno):
    """Una historia VIEJA pero de score alto (o multi-fuente) NO se purga: no es un TTL."""
    _cluster("vieja_buena", score=0.9, n_fuentes=1, ultimo_visto=_VIEJO)

    repos.purgar_pool_irrelevante(score_umbral=0.15, inactividad_horas=1)

    assert "vieja_buena" in _ids()


def test_purga_items_sueltos_viejos(entorno):
    """Items `nuevo` viejos y sin cluster (o cuyo cluster ya no existe) se purgan; recientes no."""
    repos.crear_noticias_items([
        {"fuente_id": "f", "fuente_nombre": "F", "categoria": "mx", "marca": "unotv",
         "titulo": "Suelto viejo", "resumen": "r", "url": "https://e.com/1",
         "url_canonica": "e.com/1", "clave": "k-viejo", "cluster_id": "",
         "capturado_en": _VIEJO},
        {"fuente_id": "f", "fuente_nombre": "F", "categoria": "mx", "marca": "unotv",
         "titulo": "Suelto nuevo", "resumen": "r", "url": "https://e.com/2",
         "url_canonica": "e.com/2", "clave": "k-nuevo", "cluster_id": "",
         "capturado_en": _ahora()},
    ])

    resumen = repos.purgar_pool_irrelevante(score_umbral=0.15, inactividad_horas=1)

    assert resumen["items"] == 1
    items, _ = repos.listar_noticias_items(limite=500)
    claves = {it["clave"] for it in items}
    assert "k-viejo" not in claves
    assert "k-nuevo" in claves


# --------------------------------------------------------------------------- #
# CADUCIDAD del pool por edad (`db_noticias.caducar_pool`): TTL + retención    #
# --------------------------------------------------------------------------- #


def test_caducar_pool_expira_lo_viejo_y_conserva_lo_vivo(entorno):
    """Una historia `nuevo` sin actividad en el TTL caduca (se BORRA); lo usado/reciente no.

    Caducar = descartar: la fila del cluster desaparece y sus items quedan LÁPIDA `descartado`
    (anti-reaparición), no se marca el cluster `descartado` (ese estado a nivel de cluster ya no
    existe)."""
    _cluster("vieja", ultimo_visto=_VIEJO, score=0.9, n_fuentes=3)  # ni el score alto la salva
    _cluster("reciente", ultimo_visto=_ahora())
    _cluster("usada", ultimo_visto=_VIEJO, estado="usado")
    _cluster("ligada", ultimo_visto=_VIEJO, publicacion_id="c123")
    repos.crear_noticias_items([
        {"fuente_id": "f", "titulo": "Item de la vieja", "clave": "k-vieja",
         "cluster_id": "vieja", "capturado_en": _VIEJO},
    ])

    resumen = repos.caducar_pool(ttl_horas=72, retencion_horas=0)

    assert resumen["caducadas"] == 1
    assert repos.obtener_noticia_cluster("vieja") is None  # la fila se borró
    assert repos.obtener_noticia_cluster("reciente")["estado"] == "nuevo"
    assert repos.obtener_noticia_cluster("usada")["estado"] == "usado"
    assert repos.obtener_noticia_cluster("ligada")["estado"] == "nuevo"  # ligada al tablero
    # El item de la caducada sobrevive como lápida `descartado` (bloquea la re-ingesta).
    items, _ = repos.listar_noticias_items(limite=500)
    por_clave = {it["clave"]: it for it in items}
    assert por_clave["k-vieja"]["estado"] == "descartado"


def test_caducar_pool_ttl_cero_es_noop(entorno):
    _cluster("vieja", ultimo_visto=_VIEJO)
    assert repos.caducar_pool(ttl_horas=0) == {
        "caducadas": 0, "purgadas": 0, "items_purgados": 0,
    }
    assert repos.obtener_noticia_cluster("vieja")["estado"] == "nuevo"


def test_caducar_pool_retencion_borra_lapidas_e_items_sueltos_viejos(entorno):
    """La retención borra del todo las lápidas viejas (cluster ya inexistente) y los sueltos viejos."""
    # Cluster viejo: el TTL lo borra y deja su item como lápida; la retención borra la lápida.
    _cluster("caducada", ultimo_visto=_VIEJO)
    repos.crear_noticias_items([
        {"fuente_id": "f", "titulo": "Item de la caducada", "clave": "k1",
         "cluster_id": "caducada", "capturado_en": _VIEJO},
        # Item SUELTO viejo (sin cluster): también es techo del archivo.
        {"fuente_id": "f", "titulo": "Suelto viejo", "clave": "k2",
         "cluster_id": "", "capturado_en": _VIEJO},
    ])

    resumen = repos.caducar_pool(ttl_horas=72, retencion_horas=336)

    assert resumen["caducadas"] == 1
    assert repos.obtener_noticia_cluster("caducada") is None
    # Ambos items (la lápida de la caducada + el suelto viejo) se purgan en la misma pasada.
    assert resumen["items_purgados"] == 2
    items, _ = repos.listar_noticias_items(limite=500)
    assert {it["clave"] for it in items} == set()


def _item_por_clave(clave):
    items, _ = repos.listar_noticias_items(limite=500)
    return next((it for it in items if it["clave"] == clave), None)


def test_descartar_cluster_suelta_cluster_id_de_la_lapida(entorno):
    """Descartar borra el cluster; su item lápida no queda apuntando a la fila inexistente."""
    _cluster("desc", ultimo_visto=_ahora())
    repos.crear_noticias_items([
        {"fuente_id": "f", "titulo": "It", "clave": "k-desc", "cluster_id": "desc",
         "capturado_en": _ahora()},
    ])

    assert repos.descartar_cluster("desc") is True

    it = _item_por_clave("k-desc")
    assert it["estado"] == "descartado"
    assert it["cluster_id"] == ""  # no cuelga del cluster borrado


def test_purga_suelta_cluster_id_de_items_supervivientes(entorno):
    """Un item RECIENTE de un cluster purgado sobrevive, pero suelta su `cluster_id`."""
    _cluster("ruido", score=0.05, n_fuentes=1)  # purgable
    repos.crear_noticias_items([
        {"fuente_id": "f", "titulo": "It reciente", "clave": "k-superv", "cluster_id": "ruido",
         "capturado_en": _ahora()},  # reciente: no entra en el borrado de items
    ])

    repos.purgar_pool_irrelevante(score_umbral=0.15, inactividad_horas=1)

    assert "ruido" not in _ids()
    it = _item_por_clave("k-superv")
    assert it is not None and it["cluster_id"] == ""  # sobrevive, ya no cuelga


def test_caducar_suelta_cluster_id_de_la_lapida(entorno):
    """La lápida `descartado` de una historia caducada no apunta al cluster borrado."""
    _cluster("caducada", ultimo_visto=_VIEJO)
    repos.crear_noticias_items([
        {"fuente_id": "f", "titulo": "Item", "clave": "k1", "cluster_id": "caducada",
         "capturado_en": _VIEJO},
    ])

    repos.caducar_pool(ttl_horas=72, retencion_horas=0)

    it = _item_por_clave("k1")
    assert it["estado"] == "descartado" and it["cluster_id"] == ""


def test_caducar_pool_retencion_cero_no_borra_lapidas(entorno):
    """Con retención 0 el TTL borra el cluster pero su item lápida sobrevive (no se purga)."""
    _cluster("caducada", ultimo_visto=_VIEJO)
    repos.crear_noticias_items([
        {"fuente_id": "f", "titulo": "Item de la caducada", "clave": "k1",
         "cluster_id": "caducada", "capturado_en": _VIEJO},
    ])
    resumen = repos.caducar_pool(ttl_horas=72, retencion_horas=0)
    assert resumen["caducadas"] == 1
    assert resumen["items_purgados"] == 0
    assert repos.obtener_noticia_cluster("caducada") is None
    items, _ = repos.listar_noticias_items(limite=500)
    assert {it["clave"] for it in items} == {"k1"}  # la lápida sigue ahí


# --------------------------------------------------------------------------- #
# Purga de lo USADO huérfano (`db_noticias.purgar_usados_huerfanos`)           #
# --------------------------------------------------------------------------- #


def _cluster_usado(cid, *, publicacion_id, ultimo_visto=_VIEJO):
    _cluster(cid, estado="usado", publicacion_id=publicacion_id, ultimo_visto=ultimo_visto)
    repos.crear_noticias_items([
        {"fuente_id": "f", "titulo": f"Item {cid}", "clave": f"k-{cid}",
         "cluster_id": cid, "capturado_en": _VIEJO},
    ])
    repos.marcar_items_cluster_usados(cid, publicacion_id)
    return cid


def test_purgar_usados_huerfanos_borra_lo_ligado_a_temas_borrados(entorno):
    """Una historia `usado` vieja cuya publicación ya NO existe se purga; sus items quedan
    lápida `descartado` sin cluster ni publicación (los borra luego la retención normal)."""
    vivo = repos.crear_publicacion(clase="contenido", titulo="Tema vivo", marca="unotv")
    _cluster_usado("huerfana", publicacion_id="pub-borrada")
    _cluster_usado("con-tema", publicacion_id=vivo["id"])
    _cluster_usado("huerfana-reciente", publicacion_id="pub-borrada-2", ultimo_visto=_ahora())

    resumen = repos.purgar_usados_huerfanos(60)

    assert resumen["historias"] == 1
    assert repos.obtener_noticia_cluster("huerfana") is None
    # Lo usado con publicación VIVA y lo huérfano RECIENTE no se tocan.
    assert repos.obtener_noticia_cluster("con-tema")["estado"] == "usado"
    assert repos.obtener_noticia_cluster("huerfana-reciente")["estado"] == "usado"
    it = _item_por_clave("k-huerfana")
    assert it["estado"] == "descartado"
    assert it["cluster_id"] == "" and it["publicacion_id"] == ""
    assert _item_por_clave("k-con-tema")["estado"] == "usado"


def test_purgar_usados_huerfanos_alapida_items_sueltos(entorno):
    """Un item `usado` SUELTO (sin cluster vivo) con publicación borrada y viejo pasa a lápida."""
    repos.crear_noticias_items([
        {"fuente_id": "f", "titulo": "Suelto usado", "clave": "k-suelto",
         "cluster_id": "", "capturado_en": _VIEJO},
    ])
    it = _item_por_clave("k-suelto")
    repos.actualizar_noticia_item(it["id"], estado="usado", publicacion_id="pub-borrada")

    resumen = repos.purgar_usados_huerfanos(60)

    assert resumen["items"] == 1
    it = _item_por_clave("k-suelto")
    assert it["estado"] == "descartado" and it["publicacion_id"] == ""


def test_purgar_usados_huerfanos_cero_es_noop(entorno):
    _cluster_usado("huerfana", publicacion_id="pub-borrada")
    assert repos.purgar_usados_huerfanos(0) == {"historias": 0, "items": 0}
    assert repos.obtener_noticia_cluster("huerfana")["estado"] == "usado"


# --------------------------------------------------------------------------- #
# Retención de `rss_items_vistos` (`db_noticias.purgar_rss_vistos`)            #
# --------------------------------------------------------------------------- #


def _envejecer_vista(fuente_id, clave, visto_en):
    from keni_consola.db import jobs as db_jobs

    con = db_jobs._conectar()
    try:
        con.execute(
            "UPDATE rss_items_vistos SET visto_en = ? WHERE fuente_id = ? AND clave = ?",
            (visto_en, fuente_id, clave),
        )
        con.commit()
    finally:
        con.close()


def test_purgar_rss_vistos_borra_lo_viejo_y_conserva_lo_reciente(entorno):
    repos.marcar_item("f1", "k-viejo", True)
    repos.marcar_item("f1", "k-reciente", True)
    _envejecer_vista("f1", "k-viejo", "2020-01-01T00:00:00")

    assert repos.purgar_rss_vistos(180) == 1
    assert repos.claves_vistas("f1") == {"k-reciente"}


def test_purgar_rss_vistos_respeta_filas_sin_fecha_y_cero(entorno):
    """Sin `visto_en` no hay evidencia de edad (no se purga); `dias=0` es no-op."""
    repos.marcar_item("f1", "k-sin-fecha", True)
    _envejecer_vista("f1", "k-sin-fecha", "")
    repos.marcar_item("f1", "k-viejo", True)
    _envejecer_vista("f1", "k-viejo", "2020-01-01T00:00:00")

    assert repos.purgar_rss_vistos(0) == 0
    assert repos.claves_vistas("f1") == {"k-sin-fecha", "k-viejo"}
    assert repos.purgar_rss_vistos(180) == 1
    assert repos.claves_vistas("f1") == {"k-sin-fecha"}
