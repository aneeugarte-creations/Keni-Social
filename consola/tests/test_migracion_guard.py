"""Guarda de migración para blue-green: `hay_migraciones_pendientes` + sonda CLI `--hay-pendientes`.

El deploy decide si un cutover blue-green es seguro preguntando si hay migración de esquema
pendiente. "Pendiente" DEBE coincidir EXACTAMENTE con lo que aplicaría el arranque: la función
reutiliza el MISMO `_id_migracion` y el MISMO registro (`MIGRACIONES`) que el runner, así que un
id ausente del journal cuenta como pendiente. Si divergiera (un falso "no pendientes"), una
migración se colaría en el solape blue-green: el fallo grave que esta guarda evita.

SIN Postgres (corre en el gate `contrato`): una conexión FALSA controla el contenido del journal;
la lógica de ids es la real (registro + `_id_migracion`), no una copia.
"""

from __future__ import annotations

from keni_consola import _db_core, config, migracion


class _ConFalsa:
    """Conexión mínima: solo responde al SELECT del journal con los ids que se le den."""

    def __init__(self, ids_journal):
        self._filas = [{"id": i} for i in ids_journal]
        self.cerrada = False

    def execute(self, sql, params=None):  # noqa: ANN001, ARG002
        assert "schema_migraciones" in sql
        return self

    def fetchall(self):
        return self._filas

    def close(self):
        self.cerrada = True


def _ids_de_todo_el_registro() -> set[str]:
    """Los ids con que el arranque registraría TODAS las migraciones (la verdad del runner)."""
    return {_db_core._id_migracion(m) for m in _db_core.MIGRACIONES}


def test_journal_completo_no_hay_pendientes():
    """Journal con TODOS los ids del registro -> nada que aplicar."""
    con = _ConFalsa(_ids_de_todo_el_registro())
    assert _db_core.hay_migraciones_pendientes(con) is False


def test_journal_vacio_hay_pendientes():
    """Journal vacío (BD nueva) -> todas pendientes."""
    assert _db_core.hay_migraciones_pendientes(_ConFalsa(set())) is True


def test_falta_un_id_del_registro_hay_pendientes():
    """Quitar UN id del registro al journal lo deja pendiente (coincide con lo que se aplicaría)."""
    ids = _ids_de_todo_el_registro()
    uno = next(iter(ids))
    assert _db_core.hay_migraciones_pendientes(_ConFalsa(ids - {uno})) is True


def test_id_extra_en_journal_no_cuenta():
    """Un id en el journal que ya no está en el registro (fila inerte) NO genera pendientes."""
    con = _ConFalsa(_ids_de_todo_el_registro() | {"9999-inerte"})
    assert _db_core.hay_migraciones_pendientes(con) is False


def test_cli_sin_database_url_es_fail_safe(monkeypatch):
    """FAIL-SAFE: sin `DATABASE_URL` no se puede determinar -> se asume pendiente (stop-the-world)."""
    monkeypatch.setattr(config, "database_url", lambda: None)
    assert migracion.hay_migraciones_pendientes() == migracion.EXIT_HAY_PENDIENTES


def test_cli_error_de_conexion_es_fail_safe(monkeypatch):
    """FAIL-SAFE: si la sonda revienta al conectar/leer, se asume pendiente (stop-the-world)."""
    monkeypatch.setattr(config, "database_url", lambda: "postgresql://x/y")

    def _revienta():
        raise RuntimeError("sin Postgres")

    monkeypatch.setattr(migracion.motor_db, "conectar_cruda", _revienta)
    assert migracion.hay_migraciones_pendientes() == migracion.EXIT_HAY_PENDIENTES


def test_cli_sin_pendientes_sale_cero(monkeypatch):
    """Con journal completo (vía conexión falsa) la sonda CLI sale 0 = blue-green seguro."""
    monkeypatch.setattr(config, "database_url", lambda: "postgresql://x/y")
    monkeypatch.setattr(
        migracion.motor_db, "conectar_cruda", lambda: _ConFalsa(_ids_de_todo_el_registro())
    )
    assert migracion.hay_migraciones_pendientes() == 0
