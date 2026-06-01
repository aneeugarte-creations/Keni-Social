"""Tests de la migración de datos legados al tablero de contenido (`migrar_contenido`).

Cubren el mapeo de piezas, el parseo del texto libre de redes, y la idempotencia
(re-ejecutar no duplica). Reusa la fixture `entorno` (Postgres de pruebas o skip).
"""

from __future__ import annotations

from keni_consola import db, ficheros, migrar_contenido, repos


def test_parsear_redes_mapea_y_separa_formatos():
    redes, sobrantes = migrar_contenido._parsear_redes("FB, IG, X (REEL)")
    assert redes == ["facebook", "instagram", "x"]
    assert "REEL" in sobrantes


def test_migra_pieza_con_redes_y_checklist(entorno):
    db.crear_pieza_rota(
        programa="Mundial",
        red_social="FB, IG, X",
        contenido_sugerido="Resumen del partido",
        dia="2026-06-01",
        estado="listo",
        material_entregado=True,
        contenido_entregado=False,
        always_on=False,
    )
    assert migrar_contenido.migrar_piezas() == 1
    items = db.listar_contenido(clase="contenido")
    assert len(items) == 1
    item = items[0]
    assert item["titulo"] == "Resumen del partido"
    assert item["programa"] == "Mundial"
    plats = db.listar_contenido_plataforma(item["id"])
    assert {x["red"] for x in plats} == {"facebook", "instagram", "x"}
    # listo -> aprobado; material entregado -> no falta imagen; copy no -> falta copy.
    assert all(x["estado"] == "aprobado" for x in plats)
    assert all(x["falta_imagen"] is False for x in plats)
    assert all(x["falta_copy"] is True for x in plats)


def test_pieza_con_evento_es_flujo_evento(entorno):
    ev = db.crear_evento_rota("Partido", fecha="2026-06-01", hora="20:00")
    db.crear_pieza_rota(evento_id=ev["id"], red_social="WEB", contenido_sugerido="Nota")
    migrar_contenido.migrar_piezas()
    item = db.listar_contenido(clase="contenido")[0]
    assert item["flujo"] == "evento"


def test_pieza_evergreen_es_flujo_evergreen(entorno):
    db.crear_pieza_rota(programa="Siempre", always_on=True, contenido_sugerido="Perenne")
    migrar_contenido.migrar_piezas()
    item = db.listar_contenido(clase="contenido")[0]
    assert item["flujo"] == "evergreen"


def test_migra_plantilla_plano_yaml_a_catalogo_unificado(entorno):
    # Plantilla de copy plano legada en YAML -> catálogo unificado (modo 'plano'), preservando id.
    p = ficheros.crear_plantilla("Saludo", marca="unotv", red="x", contenido="Hola equipo")
    assert migrar_contenido.migrar_plantillas_plano() == 1
    migrada = repos.obtener_plantilla_contenido(p["id"])
    assert migrada is not None
    assert migrada["modo"] == "plano"
    assert migrada["contenido"] == "Hola equipo"
    assert migrada["marca"] == "unotv"
    # Idempotente: re-ejecutar no duplica.
    assert migrar_contenido.migrar_plantillas_plano() == 0


def test_migracion_es_idempotente(entorno):
    db.crear_pieza_rota(programa="P", red_social="IG")
    primera = migrar_contenido.migrar()
    assert primera == {
        "piezas": 1, "publicaciones": 0, "plantillas_plano": 0,
        "fuentes_rss": 0, "grupos_hashtags": 0, "franjas": 0,
    }
    segunda = migrar_contenido.migrar()
    assert segunda == {
        "piezas": 0, "publicaciones": 0, "plantillas_plano": 0,
        "fuentes_rss": 0, "grupos_hashtags": 0, "franjas": 0,
    }
    assert len(db.listar_contenido()) == 1
