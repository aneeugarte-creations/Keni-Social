"""Tests de la migración de datos legados al tablero de contenido (`migrar_contenido`).

Cubren el mapeo de piezas, el parseo del texto libre de redes, y la idempotencia
(re-ejecutar no duplica). Reusa la fixture `entorno` (Postgres de pruebas o skip).
"""

from __future__ import annotations

from keni_consola import db, migrar_contenido, repos


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
    # listo -> en_revision; material entregado -> no falta imagen; copy no -> falta copy.
    assert all(x["estado"] == "en_revision" for x in plats)
    assert all(x["falta_imagen"] is False for x in plats)
    assert all(x["falta_copy"] is True for x in plats)


def test_migra_tipo_pieza_como_etiqueta(entorno):
    """`tipo_pieza` (texto libre del Excel) se preserva como ETIQUETA del contenido."""
    db.crear_pieza_rota(
        programa="Mundial",
        red_social="IG",
        contenido_sugerido="Reel del gol",
        tipo_pieza="REEL",
    )
    assert migrar_contenido.migrar_piezas() == 1
    item = db.listar_contenido(clase="contenido")[0]
    etiqueta_ids = repos.etiquetas_por_contenido().get(item["id"], [])
    nombres = {
        (repos.obtener_etiqueta(eid) or {}).get("nombre", "") for eid in etiqueta_ids
    }
    # Normalizada a minúsculas (mismo patrón que importador_calendario).
    assert "reel" in nombres


def test_migra_tipo_pieza_reutiliza_etiqueta_existente(entorno):
    """Dos piezas con el mismo `tipo_pieza` comparten UNA sola etiqueta (no se duplica)."""
    db.crear_pieza_rota(programa="A", red_social="IG", contenido_sugerido="x", tipo_pieza="HISTORIA")
    db.crear_pieza_rota(programa="B", red_social="FB", contenido_sugerido="y", tipo_pieza="historia")
    migrar_contenido.migrar_piezas()
    historias = [e for e in repos.listar_etiquetas() if (e.get("nombre") or "").lower() == "historia"]
    assert len(historias) == 1


def test_pieza_con_evento_es_flujo_evento(entorno):
    ev = db.crear_evento_rota("Partido", fecha="2026-06-01", hora="20:00")
    db.crear_pieza_rota(evento_id=ev["id"], red_social="WEB", contenido_sugerido="Nota")
    migrar_contenido.migrar_piezas()
    item = db.listar_contenido(clase="contenido")[0]
    assert item["flujo"] == "evento"


def test_pieza_evergreen_es_flujo_evergreen(entorno):
    db.crear_pieza_rota(programa="Siempre", always_on=True, contenido_sugerido="Evergreen")
    migrar_contenido.migrar_piezas()
    item = db.listar_contenido(clase="contenido")[0]
    assert item["flujo"] == "evergreen"


def test_migracion_es_idempotente(entorno):
    db.crear_pieza_rota(programa="P", red_social="IG")
    primera = migrar_contenido.migrar()
    assert primera == {"piezas": 1}
    segunda = migrar_contenido.migrar()
    assert segunda == {"piezas": 0}
    assert len(db.listar_contenido()) == 1
