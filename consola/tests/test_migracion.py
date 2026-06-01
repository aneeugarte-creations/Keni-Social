"""Tests del modulo de migracion (`keni_consola.migracion`) + arranque de la persistencia.

Tras la ADR 0004 (Postgres unico backend) el cutover SQLite -> Postgres es HISTORIA: el
modulo conserva `asegurar_esquema` como NO-OP idempotente (compatibilidad con
`deploy.sh --solo-db`) y la migracion de media disco -> S3, que sigue vigente.

Cubre:
  - `asegurar_esquema`: crea/migra el esquema en Postgres (idempotente); sin `DATABASE_URL`
    falla con un mensaje accionable.
  - Media (disco -> S3): S3 SIMULADO con moto. Sube los objetos y salta los que ya existen.
  - `db.arrancar_persistencia()`: crea el esquema y no orfana nada (ya no hay SQLite).
"""

from __future__ import annotations

import pytest

from keni_consola import almacen_media, db, migracion

from ._postgres import limpiar_postgres, requiere_postgres


# --------------------------------------------------------------------------- #
# DB: asegurar_esquema (no-op idempotente tras ADR 0004)                      #
# --------------------------------------------------------------------------- #


def test_asegurar_esquema_crea_y_es_idempotente(monkeypatch):
    url = requiere_postgres()
    limpiar_postgres(url)
    monkeypatch.setenv("DATABASE_URL", url)
    # Primera vez: crea el esquema.
    assert migracion.asegurar_esquema() is True
    assert db.listar_swaps_turno() == []
    # Segunda vez: idempotente, no rompe (`CREATE TABLE IF NOT EXISTS` + ALTERs guardados).
    assert migracion.asegurar_esquema() is True
    limpiar_postgres(url)


def test_asegurar_esquema_sin_database_url_falla(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    for var in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB",
                "POSTGRES_HOST", "POSTGRES_PORT"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(SystemExit) as exc:
        migracion.asegurar_esquema()
    assert "DATABASE_URL" in str(exc.value)


def test_asegurar_esquema_dry_run_no_abre_conexion(monkeypatch):
    """`dry_run` no toca la DB: util para validar entorno sin riesgo."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://hay-url-pero-no-se-usa@x:1/y")
    assert migracion.asegurar_esquema(dry_run=True) is True


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
# Arranque de la persistencia (`db.arrancar_persistencia`)                    #
# --------------------------------------------------------------------------- #


def test_arrancar_persistencia_crea_esquema_y_es_idempotente(monkeypatch):
    """Tras la ADR 0004 el arranque solo crea/migra el esquema (no orfana nada)."""
    url = requiere_postgres()
    limpiar_postgres(url)
    monkeypatch.setenv("DATABASE_URL", url)
    db.arrancar_persistencia()
    db.arrancar_persistencia()  # idempotente: segundo arranque tampoco rompe
    # La aplicacion puede usar las tablas tras el arranque.
    assert db.listar_swaps_turno() == []
    limpiar_postgres(url)


def test_arrancar_persistencia_sin_database_url_falla(monkeypatch):
    """Sin Postgres configurado, el arranque PROPAGA un error claro (no servir en blanco)."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    for var in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB",
                "POSTGRES_HOST", "POSTGRES_PORT"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(RuntimeError) as exc:
        db.arrancar_persistencia()
    assert "DATABASE_URL" in str(exc.value)
