"""Tests del almacen de objetos de media (`keni_consola.almacen_media`).

Dos backends, OFFLINE:
  - DISCO (sin S3 cableado): comportamiento historico (guardar/leer/anti-traversal).
  - S3 (con S3_* cableado): S3 SIMULADO con `moto` (NO toca la red). Cubre que con S3
    cableado la media va al bucket y se lee de ahi, y que el nombre de objeto se sanea.

El swap de backend lo decide `config.s3_configurado()` segun los env `S3_*`.
"""

from __future__ import annotations

import pytest

from keni_consola import almacen_media, config

# moto (S3 simulado) es opcional: si no esta, los tests de S3 se SALTAN (CI sin moto verde).
# boto3 se importa de forma diferida dentro de las fixtures S3 (no a nivel de modulo, para
# no romper el import si moto/boto3 no estan).
pytest.importorskip("moto", reason="moto no instalado: tests de S3 omitidos")


# --------------------------------------------------------------------------- #
# Backend DISCO (sin S3 cableado)                                             #
# --------------------------------------------------------------------------- #


@pytest.fixture
def disco(monkeypatch, tmp_path):
    """Aisla el dir de media en tmp y BORRA cualquier S3_* (=> backend disco)."""
    for var in ("S3_ENDPOINT", "S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_REGION", "S3_BUCKET"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("KENI_CONSOLA_MEDIA", str(tmp_path / "media"))
    almacen_media._resetear_cliente_s3()
    return tmp_path


def test_disco_activo_sin_s3(disco):
    assert almacen_media.s3_activo() is False


def test_disco_guardar_y_leer(disco):
    almacen_media.guardar_objeto("abc.png", b"datos-png", content_type="image/png")
    assert almacen_media.leer_objeto("abc.png") == b"datos-png"


def test_disco_leer_inexistente_none(disco):
    assert almacen_media.leer_objeto("noexiste.png") is None


def test_disco_anti_traversal(disco):
    assert almacen_media.leer_objeto("../../etc/passwd") is None
    assert almacen_media.resolver_media("../../etc/passwd") is None
    assert almacen_media.resolver_media("/etc/passwd") is None


def test_disco_borrar(disco):
    almacen_media.guardar_objeto("x.png", b"x", content_type="image/png")
    almacen_media.borrar_objeto("x.png")
    assert almacen_media.leer_objeto("x.png") is None


# --------------------------------------------------------------------------- #
# Backend S3 (S3 simulado con moto)                                           #
# --------------------------------------------------------------------------- #


@pytest.fixture
def s3(monkeypatch, tmp_path):
    """Cablea S3_* a un S3 SIMULADO (moto) con el bucket creado. Backend = S3.

    `mock_aws` de moto v5 intercepta clientes boto3 SIN endpoint_url custom (estilo AWS).
    Nuestro `_s3()` construye el cliente con `endpoint_url` (Garage), que moto NO intercepta;
    por eso INYECTAMOS un cliente moto (estilo AWS) en el cache `_cliente_s3` para que el
    codigo lo use tal cual. El swap de backend lo siguen decidiendo los env `S3_*`.
    """
    import boto3
    from moto import mock_aws

    monkeypatch.setenv("S3_ENDPOINT", "http://files:3900")
    monkeypatch.setenv("S3_REGION", "us-east-1")
    monkeypatch.setenv("S3_BUCKET", "keni-media")
    monkeypatch.setenv("S3_ACCESS_KEY", "test-access")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret")
    # El dir de disco tambien aislado (no debe usarse, pero por si acaso).
    monkeypatch.setenv("KENI_CONSOLA_MEDIA", str(tmp_path / "media"))
    with mock_aws():
        cliente = boto3.client("s3", region_name="us-east-1")
        cliente.create_bucket(Bucket="keni-media")
        # Inyecta el cliente moto en el cache para que `_s3()` lo devuelva sin reconstruir.
        monkeypatch.setattr(almacen_media, "_cliente_s3", cliente)
        yield cliente
    almacen_media._resetear_cliente_s3()


def test_s3_activo_con_credenciales(s3):
    assert almacen_media.s3_activo() is True
    assert config.s3_configurado() is True


def test_s3_guardar_y_leer(s3):
    almacen_media.guardar_objeto("foto.png", b"contenido-imagen", content_type="image/png")
    assert almacen_media.leer_objeto("foto.png") == b"contenido-imagen"


def test_s3_guarda_content_type(s3):
    almacen_media.guardar_objeto("foto.png", b"x", content_type="image/png")
    obj = s3.get_object(Bucket="keni-media", Key="foto.png")
    assert obj["ContentType"] == "image/png"


def test_s3_leer_inexistente_none(s3):
    assert almacen_media.leer_objeto("noexiste.png") is None


def test_s3_nombre_con_separador_rechazado(s3):
    # Defensa en profundidad: una key con `/` o `..` no se acepta (aunque siempre la
    # generamos nosotros como uuid+ext).
    assert almacen_media.leer_objeto("a/b.png") is None
    assert almacen_media.leer_objeto("../secreto.png") is None
    with pytest.raises(ValueError):
        almacen_media._nombre_objeto_seguro("a/b.png")


def test_s3_borrar(s3):
    almacen_media.guardar_objeto("y.png", b"y", content_type="image/png")
    assert almacen_media.leer_objeto("y.png") == b"y"
    almacen_media.borrar_objeto("y.png")
    assert almacen_media.leer_objeto("y.png") is None
