"""Integridad del esquema endurecido (ADR 0012): FKs, CHECK, version optimista, tipos jsonb.

Backend Postgres real (fixture `pg`, ver `tests/_postgres.py`; SKIP si no hay Postgres de
pruebas). El journal de migraciones se trunca entre tests, asi que cada test parte de un
esquema recien (re)migrado: ejercita TAMBIEN la idempotencia de las migraciones de integridad.
"""
from __future__ import annotations

import pytest

from keni_consola import _db_core, db, motor_db
from keni_consola._db_core.migraciones_integridad import _FKS, _migrar_fks_hub

# La fixture `pg` se autodescubre via `pytest_plugins` en conftest (`tests._postgres`).


def _cruda():
    return motor_db.conectar_cruda()


# --------------------------------------------------------------------------- #
# Bloque 1: FOREIGN KEYS (cascada + rechazo de huerfanos + limpieza previa)     #
# --------------------------------------------------------------------------- #


def test_fks_creadas(pg):
    db.listar_swaps_turno()  # asegura el esquema
    con = _cruda()
    try:
        nombres = {
            f["conname"]
            for f in con.execute(
                "SELECT conname FROM pg_constraint WHERE contype = 'f'"
            ).fetchall()
        }
    finally:
        con.close()
    for tabla, columna, *_ in _FKS:
        assert f"fk_{tabla}_{columna}" in nombres


def test_fk_cascade_borra_hijas(pg):
    """Borrar un `contenido` arrastra sus filas por plataforma (y, transitivamente, sus hijas)."""
    c = db.crear_contenido(titulo="t")
    p = db.crear_contenido_plataforma(contenido_id=c["id"], red="x")
    db.crear_comentario(contenido_id=c["id"], texto="hola", autor={"id": "u", "usuario": "u"})
    db.registrar_copy_version(
        plataforma_id=p["id"], contenido_id=c["id"], copy="v1",
        autor={"id": "u", "usuario": "u"},
    )
    assert db.borrar_contenido(c["id"]) is True
    assert db.obtener_contenido_plataforma(p["id"]) is None
    assert db.listar_comentarios(c["id"]) == []
    assert db.listar_copy_versiones(p["id"]) == []


def test_fk_rechaza_plataforma_huerfana(pg):
    db.listar_swaps_turno()  # esquema
    con = _cruda()
    try:
        with pytest.raises(motor_db.IntegrityError):
            con.execute(
                "INSERT INTO contenido_plataforma (id, contenido_id, creado, actualizado) "
                "VALUES (?, ?, ?, ?)",
                ("phuerf", "no-existe", "x", "x"),
            )
            con.commit()
    finally:
        con.close()


def test_fks_idempotentes_y_limpian_huerfanos(pg):
    """Re-aplicar la migracion de FKs sobre una BD con HUERFANOS los borra y recrea la FK.

    Simula el deploy real: una BD pre-FK con filas colgadas (incluido el sentinel '').
    """
    c = db.crear_contenido(titulo="t")
    con = _cruda()
    try:
        # Suelta la FK y mete huerfanos (id inexistente + sentinel '').
        con.execute("ALTER TABLE contenido_plataforma DROP CONSTRAINT fk_contenido_plataforma_contenido_id")
        con.execute(
            "INSERT INTO contenido_plataforma (id, contenido_id, creado, actualizado) "
            "VALUES ('o1', 'ghost', 'x', 'x')"
        )
        con.execute(
            "INSERT INTO contenido_plataforma (id, contenido_id, creado, actualizado) "
            "VALUES ('o2', '', 'x', 'x')"
        )
        con.commit()
        # Re-aplica la migracion: limpia huerfanos y recrea la FK.
        _migrar_fks_hub(con)
        con.commit()
        n = con.execute(
            "SELECT count(*) AS n FROM contenido_plataforma WHERE id IN ('o1', 'o2')"
        ).fetchone()["n"]
        assert n == 0
        # La fila legitima sobrevive; la FK vuelve a existir.
        existe = con.execute(
            "SELECT 1 FROM pg_constraint WHERE conname = 'fk_contenido_plataforma_contenido_id'"
        ).fetchone()
        assert existe is not None
    finally:
        con.close()
    assert db.obtener_contenido(c["id"]) is not None


# --------------------------------------------------------------------------- #
# Bloque 2: CHECK de allowlist en campos de estado                              #
# --------------------------------------------------------------------------- #


def test_checks_creados(pg):
    db.listar_swaps_turno()
    con = _cruda()
    try:
        nombres = {
            f["conname"]
            for f in con.execute(
                "SELECT conname FROM pg_constraint WHERE contype = 'c'"
            ).fetchall()
        }
    finally:
        con.close()
    for ck in (
        "ck_contenido_estado",
        "ck_contenido_plataforma_estado",
        "ck_contenido_aprobaciones_decision",
        "ck_usuarios_rol",
        "ck_contenido_qa_veredicto",
    ):
        assert ck in nombres


def test_check_rechaza_estado_invalido(pg):
    c = db.crear_contenido(titulo="t")
    con = _cruda()
    try:
        with pytest.raises(motor_db.IntegrityError):
            con.execute("UPDATE contenido SET estado = 'bogus' WHERE id = ?", (c["id"],))
            con.commit()
    finally:
        con.close()


def test_check_qa_veredicto_acepta_vacio_y_canonicos(pg):
    c = db.crear_contenido(titulo="t")
    con = _cruda()
    try:
        for v in ("", "en_curso", "no_verificado", "problema", "caducada", "saltada"):
            con.execute("UPDATE contenido SET qa_veredicto = ? WHERE id = ?", (v, c["id"]))
            con.commit()
        with pytest.raises(motor_db.IntegrityError):
            con.execute("UPDATE contenido SET qa_veredicto = 'inventado' WHERE id = ?", (c["id"],))
            con.commit()
    finally:
        con.close()


def test_checks_normalizan_valores_invalidos_preexistentes(pg):
    """Re-aplicar la migracion sobre datos sucios normaliza al default antes del CHECK."""
    from keni_consola._db_core.migraciones_integridad import _migrar_checks_dominio

    c = db.crear_contenido(titulo="t")
    con = _cruda()
    try:
        con.execute("ALTER TABLE contenido DROP CONSTRAINT ck_contenido_estado")
        con.execute("UPDATE contenido SET estado = 'zzz' WHERE id = ?", (c["id"],))
        con.commit()
        _migrar_checks_dominio(con)
        con.commit()
        v = con.execute("SELECT estado FROM contenido WHERE id = ?", (c["id"],)).fetchone()["estado"]
        assert v == "pendiente"
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Bloque 3: CONCURRENCIA OPTIMISTA (`version`)                                   #
# --------------------------------------------------------------------------- #


def test_version_nace_en_cero_y_sube_en_cada_edicion(pg):
    c = db.crear_contenido(titulo="t")
    assert c["version"] == 0
    u1 = db.actualizar_contenido(c["id"], {"titulo": "a"})
    assert u1["version"] == 1
    u2 = db.actualizar_contenido(c["id"], {"titulo": "b"})
    assert u2["version"] == 2
    p = db.crear_contenido_plataforma(contenido_id=c["id"], red="x")
    assert p["version"] == 0
    pu = db.actualizar_contenido_plataforma(p["id"], {"copy": "hi"})
    assert pu["version"] == 1


def test_version_obsoleta_levanta_conflicto(pg):
    c = db.crear_contenido(titulo="t")
    db.actualizar_contenido(c["id"], {"titulo": "a"})  # version -> 1
    # Un editor con la version vieja (0) choca: NO pisa el cambio.
    with pytest.raises(db.ConflictoVersion):
        db.actualizar_contenido(c["id"], {"titulo": "z"}, version_esperada=0)
    # La version correcta SI aplica.
    u = db.actualizar_contenido(c["id"], {"titulo": "z"}, version_esperada=1)
    assert u["titulo"] == "z"
    assert u["version"] == 2


def test_version_esperada_en_inexistente_da_none_no_conflicto(pg):
    assert db.actualizar_contenido("no-existe", {"titulo": "x"}, version_esperada=0) is None


def test_version_plataforma_obsoleta_levanta_conflicto(pg):
    c = db.crear_contenido(titulo="t")
    p = db.crear_contenido_plataforma(contenido_id=c["id"], red="x")
    db.actualizar_contenido_plataforma(p["id"], {"copy": "uno"})  # version -> 1
    with pytest.raises(db.ConflictoVersion):
        db.actualizar_contenido_plataforma(p["id"], {"copy": "dos"}, version_esperada=0)


def test_transicion_estado_sube_version(pg):
    """El AVANCE de estado (pipeline) tambien sube la version (carrera pipeline↔humano)."""
    c = db.crear_contenido(titulo="t")
    p = db.crear_contenido_plataforma(contenido_id=c["id"], red="x", estado="en_revision")
    v0 = db.obtener_contenido_plataforma(p["id"])["version"]
    db.transicionar_estado_publicacion(p["id"], "en_revision", "aprobado")
    v1 = db.obtener_contenido_plataforma(p["id"])["version"]
    assert v1 == v0 + 1
