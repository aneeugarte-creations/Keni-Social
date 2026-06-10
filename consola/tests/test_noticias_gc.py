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


def _cluster(cid, *, score=0.05, n_fuentes=1, estado="nuevo", contenido_id="",
             ultimo_visto=_VIEJO, marca="unotv"):
    repos.upsert_noticia_cluster({
        "id": cid, "titulo": f"Historia {cid}", "resumen": "r", "marca": marca,
        "categoria": "mx", "geo": "MX", "clave": f"t:{cid}", "n_items": 1, "n_fuentes": n_fuentes,
        "idiomas": ["es"], "senal": 0, "score": score, "breaking": 0,
        "primer_visto": _VIEJO, "ultimo_visto": ultimo_visto, "estado": estado,
        "contenido_id": contenido_id,
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
    _cluster("ligada", score=0.05, n_fuentes=1, contenido_id="c123")  # ligada -> conservar
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


def test_purga_items_huerfanos_viejos(entorno):
    """Items `nuevo` viejos y sin cluster (o cuyo cluster ya no existe) se purgan; recientes no."""
    repos.crear_noticias_items([
        {"fuente_id": "f", "fuente_nombre": "F", "categoria": "mx", "marca": "unotv",
         "titulo": "Huerfano viejo", "resumen": "r", "url": "https://e.com/1",
         "url_canonica": "e.com/1", "clave": "k-viejo", "cluster_id": "",
         "capturado_en": _VIEJO},
        {"fuente_id": "f", "fuente_nombre": "F", "categoria": "mx", "marca": "unotv",
         "titulo": "Huerfano nuevo", "resumen": "r", "url": "https://e.com/2",
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
    """Una historia `nuevo` sin actividad en el TTL caduca (descartado); lo usado/reciente no."""
    _cluster("vieja", ultimo_visto=_VIEJO, score=0.9, n_fuentes=3)  # ni el score alto la salva
    _cluster("reciente", ultimo_visto=_ahora())
    _cluster("usada", ultimo_visto=_VIEJO, estado="usado")
    _cluster("ligada", ultimo_visto=_VIEJO, contenido_id="c123")

    resumen = repos.caducar_pool(ttl_horas=72, retencion_horas=0)

    assert resumen["caducadas"] == 1
    assert repos.obtener_noticia_cluster("vieja")["estado"] == "descartado"
    assert repos.obtener_noticia_cluster("reciente")["estado"] == "nuevo"
    assert repos.obtener_noticia_cluster("usada")["estado"] == "usado"
    assert repos.obtener_noticia_cluster("ligada")["estado"] == "nuevo"  # ligada al tablero


def test_caducar_pool_ttl_cero_es_noop(entorno):
    _cluster("vieja", ultimo_visto=_VIEJO)
    assert repos.caducar_pool(ttl_horas=0) == {
        "caducadas": 0, "purgadas": 0, "items_purgados": 0,
    }
    assert repos.obtener_noticia_cluster("vieja")["estado"] == "nuevo"


def test_caducar_pool_retencion_purga_lo_caducado_con_sus_items(entorno):
    """Lo `descartado` sin usar y sin actividad en la retención se borra, con sus items."""
    _cluster("caducada", ultimo_visto=_VIEJO, estado="descartado")
    _cluster("caducada_fresca", ultimo_visto=_ahora(), estado="descartado")  # descartada a mano hoy
    repos.crear_noticias_items([
        {"fuente_id": "f", "titulo": "Item de la caducada", "clave": "k1",
         "cluster_id": "caducada", "capturado_en": _VIEJO},
        # Item SUELTO viejo (sin cluster): también es techo del archivo.
        {"fuente_id": "f", "titulo": "Suelto viejo", "clave": "k2",
         "cluster_id": "", "capturado_en": _VIEJO},
    ])

    resumen = repos.caducar_pool(ttl_horas=72, retencion_horas=336)

    assert resumen["purgadas"] == 1
    assert resumen["items_purgados"] == 2  # el del cluster + el suelto viejo
    assert repos.obtener_noticia_cluster("caducada") is None
    assert repos.obtener_noticia_cluster("caducada_fresca") is not None  # dentro de la retención
    items, _ = repos.listar_noticias_items(limite=500)
    assert {it["clave"] for it in items} == set()


def test_caducar_pool_retencion_cero_no_borra(entorno):
    _cluster("caducada", ultimo_visto=_VIEJO, estado="descartado")
    resumen = repos.caducar_pool(ttl_horas=72, retencion_horas=0)
    assert resumen["purgadas"] == 0
    assert repos.obtener_noticia_cluster("caducada") is not None
