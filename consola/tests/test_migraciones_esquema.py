"""Migraciones VERSIONADAS de esquema (`_db_core.MIGRACIONES` + journal `schema_migraciones`).

Cubre el contrato del runner (`_db_core._aplicar_migraciones`):
  - el primer asegurado de esquema puebla el journal con TODAS las migraciones del registro;
  - una migracion ya registrada NO se re-ejecuta en el siguiente arranque (solo pendientes);
  - una migracion FALLIDA no se registra y ABORTA el arranque (y el siguiente la reintenta);
  - la huella de contenido (`re_aplicar_si_cambia`) re-aplica una migracion legada cuando
    cambian sus datos directores (caso real: anadir una columna a `_COLUMNAS_TS_CANON`);
  - estabilidad ante ejecucion CONCURRENTE (N hilos asegurando el esquema a la vez bajo el
    advisory lock cross-proceso): la migracion pendiente corre EXACTAMENTE una vez.

SKIP sin Postgres de pruebas (fixture `pg`, ver `tests/_postgres.py`; el journal se trunca
entre tests como el resto de tablas, asi cada test parte de un journal vacio).
"""

from __future__ import annotations

import threading

import pytest

from keni_consola import _db_core, db, motor_db

# La fixture `pg` se autodescubre via `pytest_plugins` en conftest (`tests._postgres`).


def _ids_journal() -> dict[str, str]:
    """Filas del journal {id: aplicado_en} leidas con conexion CRUDA (sin asegurar esquema)."""
    con = motor_db.conectar_cruda()
    try:
        filas = con.execute("SELECT id, aplicado_en FROM schema_migraciones").fetchall()
        return {fila["id"]: fila["aplicado_en"] for fila in filas}
    finally:
        con.close()


def _migracion_contadora(nombre: str, llamadas: list, **kwargs) -> _db_core.Migracion:
    """Migracion de prueba que solo cuenta sus ejecuciones (no toca el esquema)."""

    def fn(con):  # noqa: ANN001, ARG001
        llamadas.append(nombre)

    return _db_core.Migracion(nombre, fn, **kwargs)


# --------------------------------------------------------------------------- #
# Journal: primer arranque y "solo pendientes"                                 #
# --------------------------------------------------------------------------- #


def test_primer_asegurado_registra_todas_las_migraciones(pg):
    """El primer arranque sobre un journal vacio aplica y registra TODO el registro.

    (Es tambien el caso "BD existente pre-journal": las legadas son idempotentes, corren
    una ultima vez y quedan registradas; ver el comentario de compatibilidad en `_db_core`.)
    """
    db.listar_swaps_turno()  # primera operacion: asegura el esquema
    journal = _ids_journal()
    esperados = {_db_core._id_migracion(m) for m in _db_core.MIGRACIONES}
    assert esperados <= set(journal)
    assert all(journal[id_m] for id_m in esperados)  # aplicado_en poblado


def test_runner_aplica_solo_pendientes(pg, monkeypatch):
    db.listar_swaps_turno()  # primer asegurado: registra todas las actuales
    llamadas: list[str] = []
    extra = _migracion_contadora("9001-prueba-pendiente", llamadas)
    monkeypatch.setattr(
        _db_core, "MIGRACIONES_POST_DDL", (*_db_core.MIGRACIONES_POST_DDL, extra)
    )
    # Re-asegurar el esquema: SOLO la nueva esta pendiente.
    db._esquemas_asegurados.clear()
    db.listar_swaps_turno()
    assert llamadas == ["9001-prueba-pendiente"]
    assert "9001-prueba-pendiente" in _ids_journal()
    # Tercera pasada: ya registrada -> no se re-ejecuta.
    db._esquemas_asegurados.clear()
    db.listar_swaps_turno()
    assert llamadas == ["9001-prueba-pendiente"]


# --------------------------------------------------------------------------- #
# Fallos: no se registra y aborta el arranque                                  #
# --------------------------------------------------------------------------- #


def test_migracion_fallida_no_se_registra_y_aborta_el_arranque(pg, monkeypatch):
    db.listar_swaps_turno()  # deja registradas las migraciones reales

    def fn_rota(con):  # noqa: ANN001, ARG001
        raise RuntimeError("migracion rota a proposito")

    originales = _db_core.MIGRACIONES_POST_DDL
    monkeypatch.setattr(
        _db_core,
        "MIGRACIONES_POST_DDL",
        (*originales, _db_core.Migracion("9002-prueba-rota", fn_rota)),
    )
    db._esquemas_asegurados.clear()
    with pytest.raises(RuntimeError, match="migracion rota a proposito"):
        db.listar_swaps_turno()
    # No quedo registrada y el memo de esquema NO se enveneno (el arranque fallo de verdad).
    assert "9002-prueba-rota" not in _ids_journal()
    assert not db._esquemas_asegurados
    # Arreglada la migracion (aqui: retirada), el siguiente arranque sale adelante.
    monkeypatch.setattr(_db_core, "MIGRACIONES_POST_DDL", originales)
    assert db.listar_swaps_turno() == []


# --------------------------------------------------------------------------- #
# Huella de contenido (`re_aplicar_si_cambia`)                                 #
# --------------------------------------------------------------------------- #


def test_id_migracion_estable_y_con_huella():
    def fn(con):  # noqa: ANN001, ARG001
        pass

    fija = _db_core.Migracion("0050-fija", fn)
    assert _db_core._id_migracion(fija) == "0050-fija"  # one-shot: nombre estable a secas
    v1 = _db_core.Migracion("0051-legada", fn, re_aplicar_si_cambia=True, datos=("a",))
    v1bis = _db_core.Migracion("0051-legada", fn, re_aplicar_si_cambia=True, datos=("a",))
    v2 = _db_core.Migracion("0051-legada", fn, re_aplicar_si_cambia=True, datos=("a", "b"))
    assert _db_core._id_migracion(v1) == _db_core._id_migracion(v1bis)  # determinista
    assert _db_core._id_migracion(v1) != _db_core._id_migracion(v2)  # datos nuevos -> id nuevo
    assert _db_core._id_migracion(v1).startswith("0051-legada@")


def test_cambiar_datos_directores_re_aplica_la_migracion(pg, monkeypatch):
    """Caso real del flujo legado: anadir una entrada a la tupla directora (p.ej.
    `_COLUMNAS_TS_CANON`) debe re-aplicar la migracion UNA vez, sin tocar el journal a mano."""
    llamadas: list[str] = []
    base = _db_core.MIGRACIONES_POST_DDL
    v1 = _migracion_contadora(
        "9003-prueba-huella", llamadas, re_aplicar_si_cambia=True, datos=("col-a",)
    )
    monkeypatch.setattr(_db_core, "MIGRACIONES_POST_DDL", (*base, v1))
    db.listar_swaps_turno()
    assert llamadas == ["9003-prueba-huella"]
    # Misma version: no se re-aplica.
    db._esquemas_asegurados.clear()
    db.listar_swaps_turno()
    assert llamadas == ["9003-prueba-huella"]
    # "Alguien anade una columna a la tupla directora": huella nueva -> se re-aplica una vez.
    v2 = _migracion_contadora(
        "9003-prueba-huella", llamadas, re_aplicar_si_cambia=True, datos=("col-a", "col-b")
    )
    monkeypatch.setattr(_db_core, "MIGRACIONES_POST_DDL", (*base, v2))
    db._esquemas_asegurados.clear()
    db.listar_swaps_turno()
    assert llamadas == ["9003-prueba-huella", "9003-prueba-huella"]
    # Ambos ids (viejo y nuevo) quedan en el journal; el viejo es una fila inerte.
    journal = _ids_journal()
    assert _db_core._id_migracion(v1) in journal
    assert _db_core._id_migracion(v2) in journal


# --------------------------------------------------------------------------- #
# Concurrencia: doble asegurado simultaneo bajo el advisory lock               #
# --------------------------------------------------------------------------- #


def test_asegurado_concurrente_aplica_la_pendiente_una_sola_vez(pg, monkeypatch):
    """N hilos asegurando el esquema A LA VEZ (simula back/worker/daemons arrancando en un
    deploy): el advisory lock de esquema serializa y la migracion pendiente corre UNA vez."""
    llamadas: list[str] = []
    extra = _migracion_contadora("9004-prueba-concurrente", llamadas)
    monkeypatch.setattr(
        _db_core, "MIGRACIONES_POST_DDL", (*_db_core.MIGRACIONES_POST_DDL, extra)
    )
    n = 4
    arrancar = threading.Barrier(n, timeout=30)
    errores: list[Exception] = []

    def asegurar() -> None:
        try:
            arrancar.wait()
            con = motor_db.conectar_cruda()
            try:
                _db_core._crear_esquema(con)  # cada hilo, su conexion: como N procesos
            finally:
                con.close()
        except Exception as e:  # noqa: BLE001 -- el assert de abajo los reporta
            errores.append(e)

    hilos = [threading.Thread(target=asegurar) for _ in range(n)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=60)
    assert not errores
    assert llamadas == ["9004-prueba-concurrente"]  # exactamente una ejecucion total
    assert "9004-prueba-concurrente" in _ids_journal()


# --------------------------------------------------------------------------- #
# 0041: recuperar Campañas varadas en `comercial_campanias`                    #
# --------------------------------------------------------------------------- #


def _crear_comercial_campanias_legacy(con) -> None:  # noqa: ANN001
    """Recrea la tabla vieja `comercial_campanias` (con `marcas` ya backfilleada)."""
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS comercial_campanias (
            id                   TEXT PRIMARY KEY,
            marca                TEXT NOT NULL DEFAULT '',
            marcas               TEXT NOT NULL DEFAULT '[]',
            nombre               TEXT NOT NULL DEFAULT '',
            hashtags             TEXT NOT NULL DEFAULT '[]',
            activa               INTEGER NOT NULL DEFAULT 1,
            fecha_creacion       TEXT NOT NULL DEFAULT '',
            fecha_actualizacion  TEXT NOT NULL DEFAULT ''
        )
        """
    )


def test_recuperar_campanias_fusiona_cuando_ambas_existen(pg):
    """Estado-bug (el rename inerte dejó las dos tablas): las campañas varadas en
    `comercial_campanias` se mueven a `campanias` sin pisar lo creado tras el bug, y la
    tabla vieja se descarta."""
    db.listar_campanias()  # asegura el esquema (crea `campanias` vacía)
    con = motor_db.conectar_cruda()
    try:
        _crear_comercial_campanias_legacy(con)
        # 4 campañas varadas en la vieja + 1 ya creada en la nueva tras el bug (id distinto).
        for i in range(4):
            con.execute(
                "INSERT INTO comercial_campanias (id, nombre, marcas, hashtags) "
                "VALUES (?, ?, ?, ?)",
                (f"vieja{i}", f"Camp {i}", '["unotv"]', '["#x"]'),
            )
        con.execute(
            "INSERT INTO campanias (id, nombre, marcas, hashtags) VALUES (?, ?, ?, ?)",
            ("nueva0", "Post-bug", '["unotv"]', '["#y"]'),
        )
        con.commit()

        _db_core._recuperar_campanias_de_comercial(con)
        con.commit()

        ids = {f["id"] for f in con.execute("SELECT id FROM campanias").fetchall()}
        assert ids == {"vieja0", "vieja1", "vieja2", "vieja3", "nueva0"}  # nada se perdió
        assert not _db_core._tabla_existe(con, "comercial_campanias")  # vieja descartada
    finally:
        con.execute("DROP TABLE IF EXISTS comercial_campanias")  # no fuga si el test cae antes
        con.commit()
        con.close()


def test_recuperar_campanias_renombra_cuando_solo_existe_la_vieja(pg):
    """BD vieja sin reparar (solo `comercial_campanias`): se renombra a `campanias`."""
    db.listar_campanias()  # asegura el esquema
    con = motor_db.conectar_cruda()
    try:
        con.execute("DROP TABLE IF EXISTS campanias")
        _crear_comercial_campanias_legacy(con)
        con.execute(
            "INSERT INTO comercial_campanias (id, nombre, marcas, hashtags) "
            "VALUES (?, ?, ?, ?)",
            ("c1", "Única", '["unotv"]', '["#z"]'),
        )
        con.commit()

        _db_core._recuperar_campanias_de_comercial(con)
        con.commit()

        assert not _db_core._tabla_existe(con, "comercial_campanias")
        ids = {f["id"] for f in con.execute("SELECT id FROM campanias").fetchall()}
        assert ids == {"c1"}
    finally:
        con.execute("DROP TABLE IF EXISTS comercial_campanias")
        con.commit()
        con.close()
