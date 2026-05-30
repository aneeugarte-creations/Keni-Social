"""Tests de la migración de datos legados al tablero de contenido (`migrar_contenido`).

Cubren el mapeo de tareas y piezas, el parseo del texto libre de redes, y la idempotencia
(re-ejecutar no duplica). Reusa la fixture `entorno` (Postgres de pruebas o skip).
"""

from __future__ import annotations

from keni_consola import db, migrar_contenido


def test_parsear_redes_mapea_y_separa_formatos():
    redes, sobrantes = migrar_contenido._parsear_redes("FB, IG, X (REEL)")
    assert redes == ["facebook", "instagram", "x"]
    assert "REEL" in sobrantes


def test_migra_tarea_a_contenido_clase_tarea(entorno):
    t = db.crear_tarea("", "Revisar relevo", "con detalle", responsable=None)
    db.actualizar_estado_tarea(t["id"], "en_curso")
    assert migrar_contenido.migrar_tareas() == 1
    items = db.listar_contenido(clase="tarea")
    assert len(items) == 1
    assert items[0]["titulo"] == "Revisar relevo"
    assert items[0]["descripcion"] == "con detalle"
    assert items[0]["estado"] == "en_curso"
    assert items[0]["origen"] == f"tarea:{t['id']}"


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


def test_migracion_es_idempotente(entorno):
    db.crear_tarea("", "Una tarea")
    db.crear_pieza_rota(programa="P", red_social="IG")
    primera = migrar_contenido.migrar()
    assert primera == {"tareas": 1, "piezas": 1, "publicaciones": 0}
    segunda = migrar_contenido.migrar()
    assert segunda == {"tareas": 0, "piezas": 0, "publicaciones": 0}
    assert len(db.listar_contenido()) == 2
