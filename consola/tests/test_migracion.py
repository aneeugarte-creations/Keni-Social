"""Tests de la migracion one-shot del cutover (`keni_consola.migracion`) + guardia de arranque.

Dos partes:
  - DB (SQLite -> Postgres): SKIP si no hay Postgres. Verifica que copia las filas y que es
    IDEMPOTENTE (re-correr no duplica).
  - Media (disco -> S3): S3 SIMULADO con moto. Verifica que sube los objetos y salta los que
    ya existen (idempotente).
  - Guardia de arranque (`db.arrancar_persistencia`): que REHUSA arrancar si Postgres vacio +
    SQLite local con datos (con Postgres), y que en local es transparente.
"""

from __future__ import annotations

import pytest

from keni_consola import almacen_media, db, migracion

from ._postgres import limpiar_postgres, requiere_postgres

# --------------------------------------------------------------------------- #
# Helper: siembra un consola.db SQLite con datos                              #
# --------------------------------------------------------------------------- #


def _sembrar_sqlite(ruta) -> None:
    """Crea un consola.db SQLite con el esquema real y unas filas en varias tablas.

    Fija el entorno SOLO durante la siembra (SQLite, sin DATABASE_URL) y lo RESTAURA al
    salir, para no contaminar la fase de migracion (que apunta a Postgres) ni otros tests.
    """
    import os

    prev_db = os.environ.get("KENI_CONSOLA_DB")
    prev_url = os.environ.get("DATABASE_URL")
    os.environ["KENI_CONSOLA_DB"] = str(ruta)
    os.environ.pop("DATABASE_URL", None)
    try:
        db.crear_tarea("proj1", "Tarea A", "detalle A")
        db.crear_tarea("proj2", "Tarea B")
        pub = db.crear_publicacion_comercial(
            "https://x/1", titulo="P1", cliente="amx", objetivo=50
        )
        db.registrar_snapshot_comercial(pub["id"], "2026-01-01T00:00:00", 5, 50)
        from keni_consola import auth

        auth.crear_usuario("ana", "clave-de-prueba", "admin")
    finally:
        # Restaura el entorno previo (lo que cada test fije DESPUES es lo que vale).
        if prev_db is None:
            os.environ.pop("KENI_CONSOLA_DB", None)
        else:
            os.environ["KENI_CONSOLA_DB"] = prev_db
        if prev_url is not None:
            os.environ["DATABASE_URL"] = prev_url


# --------------------------------------------------------------------------- #
# DB: SQLite -> Postgres (skip si no hay Postgres)                            #
# --------------------------------------------------------------------------- #


def test_migrar_db_copia_filas_e_idempotente(monkeypatch, tmp_path):
    url = requiere_postgres()
    limpiar_postgres(url)
    ruta_sqlite = tmp_path / "consola.db"
    _sembrar_sqlite(ruta_sqlite)

    # Ahora migramos: DATABASE_URL al Postgres de pruebas, origen el SQLite sembrado.
    monkeypatch.setenv("KENI_CONSOLA_DB", str(ruta_sqlite))
    monkeypatch.setenv("DATABASE_URL", url)

    conteos = migracion.migrar_db()
    assert conteos["tareas"] == 2
    assert conteos["comercial_publicaciones"] == 1
    assert conteos["comercial_snapshots"] == 1
    assert conteos["usuarios"] == 1

    # En Postgres ya estan las filas (las leemos por las funciones reales, que ahora van a PG).
    assert len(db.listar_tareas()) == 2
    assert len(db.listar_publicaciones_comerciales()) == 1
    from keni_consola import auth

    assert len(auth.listar_usuarios()) == 1

    # IDEMPOTENTE: re-migrar no duplica (ON CONFLICT DO NOTHING).
    migracion.migrar_db()
    assert len(db.listar_tareas()) == 2
    assert len(db.listar_publicaciones_comerciales()) == 1
    assert len(auth.listar_usuarios()) == 1
    limpiar_postgres(url)


def test_migrar_db_sin_database_url_falla(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("KENI_CONSOLA_DB", str(tmp_path / "consola.db"))
    with pytest.raises(SystemExit):
        migracion.migrar_db()


def test_migrar_db_sin_sqlite_origen_falla(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x:y@db:5432/keni")
    monkeypatch.setenv("KENI_CONSOLA_DB", str(tmp_path / "noexiste.db"))
    with pytest.raises(SystemExit):
        migracion.migrar_db()


def test_migrar_db_dry_run_no_escribe(monkeypatch, tmp_path):
    url = requiere_postgres()
    limpiar_postgres(url)
    ruta_sqlite = tmp_path / "consola.db"
    _sembrar_sqlite(ruta_sqlite)
    monkeypatch.setenv("KENI_CONSOLA_DB", str(ruta_sqlite))
    monkeypatch.setenv("DATABASE_URL", url)

    conteos = migracion.migrar_db(dry_run=True)
    assert conteos["tareas"] == 2  # cuenta el ORIGEN
    # Pero NO escribio en Postgres.
    assert db.listar_tareas() == []
    limpiar_postgres(url)


# --------------------------------------------------------------------------- #
# Media: disco -> S3 (moto)                                                   #
# --------------------------------------------------------------------------- #

pytest.importorskip("moto", reason="moto no instalado: tests de migracion S3 omitidos")


@pytest.fixture
def media_disco_y_s3(monkeypatch, tmp_path):
    """Siembra media en disco y cablea un S3 moto destino; devuelve (cliente, dir_origen)."""
    import boto3
    from moto import mock_aws

    dir_media = tmp_path / "media"
    dir_media.mkdir()
    (dir_media / "a.png").write_bytes(b"imagen-a")
    (dir_media / "b.jpg").write_bytes(b"imagen-b")
    monkeypatch.setenv("KENI_CONSOLA_MEDIA", str(dir_media))
    monkeypatch.setenv("S3_ENDPOINT", "http://files:3900")
    monkeypatch.setenv("S3_REGION", "us-east-1")
    monkeypatch.setenv("S3_BUCKET", "keni-media")
    monkeypatch.setenv("S3_ACCESS_KEY", "test-access")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret")
    with mock_aws():
        cliente = boto3.client("s3", region_name="us-east-1")
        cliente.create_bucket(Bucket="keni-media")
        monkeypatch.setattr(almacen_media, "_cliente_s3", cliente)
        yield cliente, dir_media
    almacen_media._resetear_cliente_s3()


def test_migrar_media_sube_objetos(media_disco_y_s3):
    cliente, _ = media_disco_y_s3
    copiados, saltados = migracion.migrar_media()
    assert copiados == 2 and saltados == 0
    assert cliente.get_object(Bucket="keni-media", Key="a.png")["Body"].read() == b"imagen-a"
    assert cliente.get_object(Bucket="keni-media", Key="b.jpg")["Body"].read() == b"imagen-b"


def test_migrar_media_idempotente(media_disco_y_s3):
    migracion.migrar_media()
    copiados, saltados = migracion.migrar_media()  # segunda vez: todo ya existe
    assert copiados == 0 and saltados == 2


def test_migrar_media_dry_run_no_sube(media_disco_y_s3):
    cliente, _ = media_disco_y_s3
    copiados, _ = migracion.migrar_media(dry_run=True)
    assert copiados == 2
    # No subio nada: el objeto no existe en el bucket.
    with pytest.raises(cliente.exceptions.NoSuchKey):
        cliente.get_object(Bucket="keni-media", Key="a.png")


def test_migrar_media_sin_s3_falla(monkeypatch, tmp_path):
    for var in ("S3_ENDPOINT", "S3_ACCESS_KEY", "S3_SECRET_KEY"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(SystemExit):
        migracion.migrar_media()


# --------------------------------------------------------------------------- #
# Guardia de arranque (db.arrancar_persistencia)                             #
# --------------------------------------------------------------------------- #


def test_arranque_local_es_transparente(monkeypatch, tmp_path):
    """Sin DATABASE_URL (perfil local) el guardia solo crea el esquema; no rehusa nunca."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("KENI_CONSOLA_DB", str(tmp_path / "consola.db"))
    db.crear_tarea("p", "Tengo datos locales")
    # No lanza, aunque haya datos locales: en local no hay nada que orfanar.
    db.arrancar_persistencia()
    assert len(db.listar_tareas()) == 1


def test_arranque_rehusa_si_postgres_vacio_con_sqlite_local(monkeypatch, tmp_path):
    """Postgres VACIO + SQLite local CON datos => REHUSA arrancar (no orfana datos)."""
    url = requiere_postgres()
    limpiar_postgres(url)
    ruta_sqlite = tmp_path / "consola.db"
    _sembrar_sqlite(ruta_sqlite)  # SQLite local con datos
    monkeypatch.setenv("KENI_CONSOLA_DB", str(ruta_sqlite))
    monkeypatch.setenv("DATABASE_URL", url)  # Postgres vacio (recien truncado)

    with pytest.raises(db.PersistenciaError) as exc:
        db.arrancar_persistencia()
    assert "migracion" in str(exc.value).lower()
    limpiar_postgres(url)


def test_arranque_ok_tras_migrar(monkeypatch, tmp_path):
    """Tras migrar (Postgres con datos), el guardia es transparente (cutover hecho)."""
    url = requiere_postgres()
    limpiar_postgres(url)
    ruta_sqlite = tmp_path / "consola.db"
    _sembrar_sqlite(ruta_sqlite)
    monkeypatch.setenv("KENI_CONSOLA_DB", str(ruta_sqlite))
    monkeypatch.setenv("DATABASE_URL", url)
    migracion.migrar_db()  # cutover: ahora Postgres TIENE datos
    db.arrancar_persistencia()  # no lanza: Postgres con datos -> seguro
    limpiar_postgres(url)


def test_arranque_postgres_vacio_sin_sqlite_ok(monkeypatch, tmp_path):
    """Postgres vacio y SIN SQLite local (primer deploy real) => arranca sin error."""
    url = requiere_postgres()
    limpiar_postgres(url)
    monkeypatch.setenv("KENI_CONSOLA_DB", str(tmp_path / "noexiste.db"))
    monkeypatch.setenv("DATABASE_URL", url)
    db.arrancar_persistencia()  # no lanza: no hay datos locales que orfanar
    limpiar_postgres(url)
