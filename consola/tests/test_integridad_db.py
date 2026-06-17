"""Tests de INTEGRIDAD de la persistencia (ola integridad/perf del backend).

Cubre los fixes de la auditoria de integridad:
  - lotes todo-o-nada (`crear_publicaciones` en UNA transaccion),
  - CAS de estado en `actualizar_pieza` (`estado_esperado`),
  - filtro multi-marca en SQL (`listar/contar_piezas(marca=[...])`),
  - UNIQUE de turnos de rota (carrera del check-then-insert),
  - normalizacion idempotente de timestamps TEXT al canon UTC-sin-offset,
  - ids de snapshots de pieza a hex completo (32).

Usa el Postgres de pruebas via la fixture `entorno` (skip si no hay).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from keni_consola import _db_core, db
from keni_consola.motor_db import IntegrityError


# --------------------------------------------------------------------------- #
# Lote de piezas: TODO-O-NADA                                           #
# --------------------------------------------------------------------------- #


def test_crear_publicaciones_lote_ok(entorno):
    creadas = db.crear_publicaciones(
        [
            {"marca": "unotv", "red": "x", "titulo": "A", "contenido": "a"},
            {"marca": "unotv", "red": "instagram", "titulo": "B", "contenido": "b"},
        ]
    )
    assert len(creadas) == 2
    assert all(p["id"] for p in creadas)
    assert len(db.listar_piezas()) == 2


def test_crear_publicaciones_lote_es_atomico(entorno):
    """Si una pieza del lote viola una restriccion (doble-reserva del MISMO slot de
    parrilla), NINGUNA queda insertada (antes quedaban las anteriores al fallo)."""
    lote = [
        {"marca": "unotv", "red": "x", "titulo": "Primera", "contenido": "a"},
        {
            "marca": "unotv", "red": "x", "titulo": "Slot 1", "contenido": "b",
            "estado": "programado", "fecha_programada": "2026-06-15T10:00",
        },
        {
            # MISMO (marca, red, fecha_programada) programado -> idx_parrilla_slot_uniq
            "marca": "unotv", "red": "x", "titulo": "Slot 2 (choca)", "contenido": "c",
            "estado": "programado", "fecha_programada": "2026-06-15T10:00",
        },
    ]
    with pytest.raises(IntegrityError):
        db.crear_publicaciones(lote)
    # Todo-o-nada: ni la primera (valida) quedo.
    assert db.listar_piezas() == []


# --------------------------------------------------------------------------- #
# CAS de estado en actualizar_pieza                                      #
# --------------------------------------------------------------------------- #


def test_actualizar_publicacion_cas_aplica_si_el_estado_coincide(entorno):
    pub = db.crear_pieza("unotv", "x", titulo="T", contenido="c")
    out = db.actualizar_pieza(
        pub["id"], {"estado": "en_revision", "titulo": "T2"}, estado_esperado="borrador"
    )
    assert out is not None
    assert out["estado"] == "en_revision"
    assert out["titulo"] == "T2"


def test_actualizar_publicacion_cas_no_toca_nada_si_el_estado_se_movio(entorno):
    """Si el estado actual ya NO es el esperado, no se escribe NADA (ni plataforma ni
    padre): cierra el TOCTOU del PUT generico."""
    pub = db.crear_pieza("unotv", "x", titulo="Original", contenido="c")
    # Otro flujo la movio a aprobado entre el snapshot del caller y su escritura:
    assert db.actualizar_pieza(pub["id"], {"estado": "en_revision"}) is not None
    out = db.actualizar_pieza(
        pub["id"],
        {"estado": "programado", "titulo": "Pisada"},
        estado_esperado="borrador",  # snapshot viejo
    )
    assert out is None
    releida = db.obtener_pieza(pub["id"])
    assert releida["estado"] == "en_revision"  # no se piso
    assert releida["titulo"] == "Original"  # el padre TAMPOCO se toco (atomicidad)


def test_actualizar_publicacion_atomica_plataforma_y_padre(entorno):
    """Titulo (padre) + estado (plataforma) en una sola llamada quedan ambos aplicados."""
    pub = db.crear_pieza("unotv", "x", titulo="V1", contenido="c")
    out = db.actualizar_pieza(pub["id"], {"titulo": "V2", "estado": "en_revision"})
    assert out["titulo"] == "V2" and out["estado"] == "en_revision"


# --------------------------------------------------------------------------- #
# Filtro multi-marca en SQL (feed con marcas preferentes)                      #
# --------------------------------------------------------------------------- #


def test_listar_y_contar_publicaciones_multi_marca(entorno):
    db.crear_pieza("unotv", "x", titulo="U1", contenido="c")
    db.crear_pieza("claro-sports", "x", titulo="C1", contenido="c")
    db.crear_pieza("nacion-gamer", "x", titulo="N1", contenido="c")

    dos = db.listar_piezas(marca=["unotv", "claro-sports"])
    assert {p["marca"] for p in dos} == {"unotv", "claro-sports"}
    assert db.contar_piezas(marca=["unotv", "claro-sports"]) == 2
    # Una sola marca como lista equivale al filtro simple.
    assert db.contar_piezas(marca=["unotv"]) == db.contar_piezas(marca="unotv")
    # Lista vacia / solo vacios = sin filtro (como None).
    assert db.contar_piezas(marca=[]) == 3


def test_keyset_multi_marca_pagina_sin_saltos(entorno):
    """El keyset con `marca IN (...)` recorre TODAS las piezas de las marcas del foco, sin
    paginas cortas ni filas saltadas (el bug del post-filtro en memoria)."""
    for i in range(3):
        db.crear_pieza("unotv", "x", titulo=f"U{i}", contenido="c")
        db.crear_pieza("claro-sports", "instagram", titulo=f"C{i}", contenido="c")
        db.crear_pieza("nacion-gamer", "x", titulo=f"N{i}", contenido="c")

    marcas = ["unotv", "claro-sports"]
    vistas: list[str] = []
    cursor = None
    for _ in range(10):  # tope defensivo
        pagina = db.listar_piezas(marca=marcas, limite=2, cursor=cursor)
        if not pagina:
            break
        vistas.extend(p["id"] for p in pagina)
        ultima = pagina[-1]
        cursor = (ultima["fecha_creacion"], ultima["id"])
        if len(pagina) < 2:
            break
    assert len(vistas) == 6  # las 6 piezas del foco, exactas
    assert len(set(vistas)) == 6  # sin repetidos ni saltos


# --------------------------------------------------------------------------- #
# UNIQUE de turnos de rota (carrera del check-then-insert)                     #
# --------------------------------------------------------------------------- #


def test_turno_rota_duplicado_exacto_choca(entorno):
    db.crear_turno_rota(
        "2026-06-08", "2026-06-09", miembro_id="m1", miembro_nombre="Luis",
        franja_id="f1", marca="unotv",
    )
    with pytest.raises(IntegrityError):
        db.crear_turno_rota(
            "2026-06-08", "2026-06-09", miembro_id="m1", miembro_nombre="Luis",
            franja_id="f1", marca="unotv",
        )


def test_turno_rota_sin_miembro_no_choca(entorno):
    """El indice es PARCIAL (`miembro_id <> ''`): dos huecos sin miembro no chocan."""
    db.crear_turno_rota("2026-06-08", "2026-06-09", franja_id="f1", marca="unotv")
    db.crear_turno_rota("2026-06-08", "2026-06-09", franja_id="f1", marca="unotv")
    assert len(db.listar_turnos_rota(semana="2026-06-08")) == 2


# --------------------------------------------------------------------------- #
# Normalizacion idempotente de timestamps TEXT al canon UTC-sin-offset         #
# --------------------------------------------------------------------------- #


def test_normalizar_timestamps_texto_idempotente(entorno):
    """`_normalizar_timestamps_texto` lleva al canon (UTC sin offset) las columnas TEXT
    de forma idempotente. Las columnas timestamptz (nativas) están garantizadas por el tipo.
    Esta prueba cubre las columnas TEXT que quedan en `contenido`:
    `pieza.preparado_en` (canon segundos) y `fecha_programada` (canon minutos).
    """
    c = db.crear_publicacion(titulo="TS", marca="unotv")
    plat = db.crear_pieza_fila(publicacion_id=c["id"], red="x")
    con = db._conectar()
    try:
        # Columna NATIVA (timestamptz, 0033): un literal aware UTC entra por el cast del driver.
        con.execute(
            "UPDATE publicacion SET creado = ? WHERE id = ?",
            ("2026-01-01T10:00:00+00:00", c["id"]),  # aware UTC
        )
        # Columnas que SIGUEN siendo TEXT: formatos legados (naive con microsegundos / segundos)
        # que la normalizacion debe recortar al canon.
        con.execute(
            "UPDATE pieza SET preparado_en = ?, fecha_programada = ? WHERE id = ?",
            ("2026-01-01T10:00:00.123456", "2026-01-02T18:00:00", plat["id"]),
        )
        con.commit()
        _db_core._normalizar_timestamps_texto(con)
        _db_core._normalizar_timestamps_texto(con)  # idempotente: segunda pasada no rompe
        # `contenido.creado` es timestamptz: vuelve como `datetime` aware UTC (no string).
        creado = con.execute(
            "SELECT creado FROM publicacion WHERE id = ?", (c["id"],)
        ).fetchone()["creado"]
        assert creado == datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        # Columnas TEXT: canon UTC-sin-offset, idempotente.
        fila_p = con.execute(
            "SELECT preparado_en, fecha_programada FROM pieza WHERE id = ?",
            (plat["id"],),
        ).fetchone()
        assert fila_p["preparado_en"] == "2026-01-01T10:00:00"  # sin microsegundos
        assert fila_p["fecha_programada"] == "2026-01-02T18:00"  # canon de parrilla: minutos
    finally:
        con.close()


def test_contenido_actualizado_timestamptz_convierte_offsets_no_utc(entorno):
    """`contenido.actualizado` es `timestamptz`: un literal con offset NO-UTC se convierte
    al INSTANTE UTC por el cast de entrada del driver/Postgres. Vuelve como `datetime` aware:
    la igualdad de datetimes aware compara por instante, asi que -06:00 a las 10:00 equivale
    a 16:00 UTC.
    """
    c = db.crear_publicacion(titulo="TS2", marca="unotv")
    con = db._conectar()
    try:
        con.execute(
            "UPDATE publicacion SET actualizado = ? WHERE id = ?",
            ("2026-01-01T10:00:00-06:00", c["id"]),  # CDMX -> 16:00 UTC
        )
        con.commit()
        _db_core._normalizar_timestamps_texto(con)  # no-op para esta columna nativa
        actualizado = con.execute(
            "SELECT actualizado FROM publicacion WHERE id = ?", (c["id"],)
        ).fetchone()["actualizado"]
        assert actualizado == datetime(2026, 1, 1, 16, 0, 0, tzinfo=timezone.utc)
    finally:
        con.close()


def test_normalizar_timestamps_cubre_noticias_y_feeds(entorno):
    """Las columnas del motor de noticias (aware + microsegundos historicos) entran al canon.

    `capturado_en`/`ultimo_visto`/`proximo_sondeo` se comparan LEXICOGRAFICAMENTE (ventanas
    24h, `feeds_vencidos`, GC del pool): los valores legados con "+00:00" y microsegundos
    deben normalizarse; los ya-canon no se tocan (idempotente).
    """
    fuente = db.crear_fuente_rss("F", "https://ej.mx/rss")
    db.crear_noticias_items([{"clave": "k1", "fuente_id": fuente["id"],
                              "capturado_en": "2026-01-01T10:00:00.123456+00:00"}])
    con = db._conectar()
    try:
        con.execute(
            "UPDATE fuentes_rss SET ultima_actualizacion = ?, proximo_sondeo = ? WHERE id = ?",
            ("2026-01-01T10:00:00.500000+00:00", "2026-01-01T10:10:00+00:00", fuente["id"]),
        )
        con.execute(
            "INSERT INTO noticias_clusters (id, ultimo_visto, primer_visto) VALUES (?, ?, ?)",
            ("cl-ts-canon", "2026-01-01T09:00:00-06:00", "2026-01-01T08:00:00+00:00"),
        )
        con.commit()
        _db_core._normalizar_timestamps_texto(con)
        _db_core._normalizar_timestamps_texto(con)  # idempotente
        f = con.execute(
            "SELECT ultima_actualizacion, proximo_sondeo FROM fuentes_rss WHERE id = ?",
            (fuente["id"],),
        ).fetchone()
        assert f["ultima_actualizacion"] == "2026-01-01T10:00:00"
        assert f["proximo_sondeo"] == "2026-01-01T10:10:00"
        it = con.execute(
            "SELECT capturado_en FROM noticias_items WHERE clave = ?", ("k1",)
        ).fetchone()
        assert it["capturado_en"] == "2026-01-01T10:00:00"
        cl = con.execute(
            "SELECT ultimo_visto, primer_visto FROM noticias_clusters WHERE id = ?",
            ("cl-ts-canon",),
        ).fetchone()
        assert cl["ultimo_visto"] == "2026-01-01T15:00:00"  # CDMX -> UTC
        assert cl["primer_visto"] == "2026-01-01T08:00:00"
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Clustering del pool: items_sin_cluster excluye descartados                   #
# --------------------------------------------------------------------------- #


def test_items_sin_cluster_excluye_descartados(entorno):
    """Un item del pool en `descartado` NO entra al paso de clustering.

    Si entrara, una gemela de cajón ya apartada (descarte fino o borrado de lote en bloque)
    se re-clusterizaría y el auto-feed la convertiría en pieza igualmente — el agujero que
    cierra este filtro, coherente con el de `marcar_items_cluster_usados`.
    """
    fuente = db.crear_fuente_rss("F", "https://ej.mx/rss")
    db.crear_noticias_items([
        {"clave": "vivo", "fuente_id": fuente["id"], "titulo": "Sigue vivo",
         "estado": "nuevo", "capturado_en": "2026-06-10T10:00:00"},
        {"clave": "muerto", "fuente_id": fuente["id"], "titulo": "Ya apartado",
         "estado": "descartado", "capturado_en": "2026-06-10T10:00:00"},
    ])
    sin_cluster = db.items_sin_cluster("2026-06-01T00:00:00", 100)
    claves = {i["clave"] for i in sin_cluster}
    assert "vivo" in claves
    assert "muerto" not in claves


# --------------------------------------------------------------------------- #
# Ids de snapshots de pieza: hex completo (32)                                 #
# --------------------------------------------------------------------------- #


def test_snapshot_pieza_id_hex_completo(entorno):
    assert db.registrar_snapshot_pieza(
        "pieza-1", "unotv", "x", "foto", "2026-06-09T10:00:00", {"interacciones": 5}
    )
    con = db._conectar()
    try:
        fila = con.execute(
            "SELECT id FROM metricas_pieza_snapshots WHERE pieza_id = ?", ("pieza-1",)
        ).fetchone()
    finally:
        con.close()
    assert len(fila["id"]) == 32  # uuid4().hex completo (riesgo de colision por volumen)
