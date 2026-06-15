"""Tests del CRUD editorial reutilizable en Postgres (ADR 0006).

Fuentes RSS (+ items vistos + salud), grupos de hashtags y franjas editoriales: CRUD
que vive en Postgres (`keni_consola.db`).
"""

from __future__ import annotations

from keni_consola import db


# --------------------------------------------------------------------------- #
# Esquema on-demand                                                            #
# --------------------------------------------------------------------------- #


def test_tablas_editoriales_se_crean_on_demand(entorno):
    """La primera operacion crea las tablas y devuelve vacio (no excepcion)."""
    assert db.listar_fuentes_rss() == []
    assert db.listar_grupos_hashtags() == []
    assert db.listar_franjas() == []
    assert db.contar_fuentes_rss() == 0
    assert db.contar_grupos_hashtags() == 0


def test_esquema_editorial_idempotente(entorno):
    """Re-crear el esquema varias veces no falla ni duplica."""
    db.listar_fuentes_rss()
    db.listar_grupos_hashtags()
    db.listar_franjas()
    assert db.listar_fuentes_rss() == []


# --------------------------------------------------------------------------- #
# Fuentes RSS                                                                  #
# --------------------------------------------------------------------------- #


def test_crear_listar_obtener_fuente_rss(entorno):
    f = db.crear_fuente_rss(
        "Diario", "https://example.com/feed.xml", marca="unotv",
        incluir="gol", excluir="rumor", redes_def="x,facebook",
    )
    # Contrato del dict (mismas claves que daba la capa de ficheros; SIN `creado`). Incluye
    # las columnas del scheduling/salud de RSS (categoria, intervalo_min, proximo_sondeo,
    # prioridad, pausado_hasta, errores_seguidos, desactivado_auto, ultimo_filtrados) y el
    # `peso` editorial (pondera la corroboración del ranking; normal=1.0 por defecto).
    assert set(f) == {
        "id", "nombre", "url", "marca", "fecha", "activo", "incluir", "excluir",
        "redes_def", "ultima_actualizacion", "ultimo_error", "ultimo_conteo", "propia",
        "categoria", "intervalo_min", "proximo_sondeo", "prioridad", "pausado_hasta",
        "errores_seguidos", "desactivado_auto", "ultimo_filtrados", "peso",
    }
    assert f["nombre"] == "Diario"
    assert f["activo"] is True
    assert f["propia"] is False
    assert f["peso"] == 1.0
    assert f["incluir"] == "gol"
    assert f["redes_def"] == "x,facebook"
    assert f["ultimo_conteo"] == 0
    assert db.obtener_fuente_rss(f["id"])["url"] == "https://example.com/feed.xml"
    assert any(x["id"] == f["id"] for x in db.listar_fuentes_rss())
    assert db.contar_fuentes_rss() == 1


def test_listar_fuentes_rss_recientes_primero(entorno):
    a = db.crear_fuente_rss("A", "https://a.example.com/f.xml", marca="unotv")
    b = db.crear_fuente_rss("B", "https://b.example.com/f.xml", marca="unotv")
    ids = [x["id"] for x in db.listar_fuentes_rss()]
    # La mas reciente (B) va primero (orden por `creado` DESC).
    assert ids.index(b["id"]) < ids.index(a["id"])


def test_actualizar_fuente_rss(entorno):
    f = db.crear_fuente_rss("X", "https://x.example.com/f.xml", marca="unotv")
    edit = db.actualizar_fuente_rss(f["id"], {"nombre": "Y", "activo": False, "marca": "claro"})
    assert edit["nombre"] == "Y"
    assert edit["activo"] is False
    assert edit["marca"] == "claro"
    # Campo no editable se ignora (no rompe).
    assert db.actualizar_fuente_rss(f["id"], {"ultimo_conteo": 99})["nombre"] == "Y"
    assert db.actualizar_fuente_rss("noexiste", {"nombre": "Z"}) is None


def test_registrar_salud_fuente_rss(entorno):
    f = db.crear_fuente_rss("X", "https://x.example.com/f.xml", marca="unotv")
    db.registrar_salud_fuente_rss(f["id"], conteo=7, error="")
    leida = db.obtener_fuente_rss(f["id"])
    assert leida["ultimo_conteo"] == 7
    assert leida["ultimo_error"] == ""
    assert leida["ultima_actualizacion"]  # fecha de hoy, no vacia
    db.registrar_salud_fuente_rss(f["id"], conteo=0, error="timeout")
    assert db.obtener_fuente_rss(f["id"])["ultimo_error"] == "timeout"


def test_borrar_fuente_rss_limpia_items_vistos(entorno):
    f = db.crear_fuente_rss("X", "https://x.example.com/f.xml", marca="unotv")
    db.marcar_item(f["id"], "item-1", True)
    assert db.claves_vistas(f["id"]) == {"item-1"}
    assert db.borrar_fuente_rss(f["id"]) is True
    assert db.obtener_fuente_rss(f["id"]) is None
    # Los items vistos de esa fuente se limpian.
    assert db.claves_vistas(f["id"]) == set()
    assert db.borrar_fuente_rss(f["id"]) is False


def test_items_vistos_idempotentes_y_sin_fuente(entorno):
    # marcar_item NO exige fuente existente.
    db.marcar_item("fuente-fantasma", "k1", True)
    db.marcar_item("fuente-fantasma", "k1", True)  # idempotente
    db.marcar_item("fuente-fantasma", "k2", True)
    assert db.claves_vistas("fuente-fantasma") == {"k1", "k2"}
    db.marcar_item("fuente-fantasma", "k1", False)
    assert db.claves_vistas("fuente-fantasma") == {"k2"}


# --------------------------------------------------------------------------- #
# Grupos de hashtags                                                           #
# --------------------------------------------------------------------------- #


def test_crud_grupos_hashtags(entorno):
    g = db.crear_grupo_hashtags("Deportes", marca="unotv", hashtags=["#gol", "#mundial"])
    assert set(g) == {"id", "nombre", "marca", "hashtags"}
    assert g["hashtags"] == ["#gol", "#mundial"]
    assert db.obtener_grupo_hashtags(g["id"])["nombre"] == "Deportes"
    assert db.contar_grupos_hashtags() == 1
    edit = db.actualizar_grupo_hashtags(g["id"], {"nombre": "Deporte", "hashtags": ["#gol"]})
    assert edit["nombre"] == "Deporte"
    assert edit["hashtags"] == ["#gol"]
    assert db.actualizar_grupo_hashtags("noexiste", {"nombre": "Z"}) is None
    assert db.borrar_grupo_hashtags(g["id"]) is True
    assert db.borrar_grupo_hashtags(g["id"]) is False
    assert db.obtener_grupo_hashtags(g["id"]) is None


# --------------------------------------------------------------------------- #
# Franjas editoriales                                                          #
# --------------------------------------------------------------------------- #


def test_crud_franjas_editoriales(entorno):
    f = db.crear_franja(2, "09:00", marca="unotv", red="x")
    assert set(f) == {"id", "marca", "red", "dia_semana", "hora", "categoria"}
    assert f["dia_semana"] == 2
    assert any(x["id"] == f["id"] for x in db.listar_franjas())
    # Orden determinista por (dia_semana, hora, id).
    db.crear_franja(0, "08:00", marca="unotv")
    dias = [x["dia_semana"] for x in db.listar_franjas()]
    assert dias == sorted(dias)
    assert db.borrar_franja(f["id"]) is True
    assert db.borrar_franja(f["id"]) is False
