"""Tests del almacen de objetos de media (`keni_consola.almacen_media`).

Dos backends, OFFLINE:
  - DISCO (sin S3 cableado): comportamiento historico (guardar/leer/anti-traversal).
  - S3 (con S3_* cableado): S3 SIMULADO con `moto` (NO toca la red). Cubre que con S3
    cableado la media va al bucket y se lee de ahi, y que el nombre de objeto se repara.

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


def test_disco_borrar_prefijo(disco):
    """Borra un bundle anidado (claves multinivel) y no toca el resto de la media."""
    almacen_media.guardar_objeto("a.png", b"a", content_type="image/png")
    base = almacen_media.asegurar_dir()
    (base / "previews" / "sug-x" / "assets").mkdir(parents=True)
    (base / "previews" / "sug-x" / "index.html").write_bytes(b"<html>")
    (base / "previews" / "sug-x" / "assets" / "app.js").write_bytes(b"//js")

    n = almacen_media.borrar_prefijo("previews/sug-x/")

    assert n == 2
    assert not (base / "previews" / "sug-x").exists()
    assert almacen_media.leer_objeto("a.png") == b"a"  # el resto intacto


def test_disco_borrar_prefijo_inexistente_es_noop(disco):
    assert almacen_media.borrar_prefijo("previews/sug-nada/") == 0


def test_borrar_prefijo_vacio_es_noop(disco):
    assert almacen_media.borrar_prefijo("") == 0


def test_disco_guardar_y_leer_crudo_anidado(disco):
    almacen_media.guardar_crudo(
        "previews/sug-x/assets/app.js", b"//js", content_type="text/javascript"
    )
    assert almacen_media.leer_crudo("previews/sug-x/assets/app.js") == b"//js"
    assert almacen_media.leer_crudo("previews/sug-x/noexiste.js") is None


def test_crudo_rechaza_traversal(disco):
    with pytest.raises(ValueError):
        almacen_media.guardar_crudo("previews/../escapa.js", b"x", content_type="text/plain")
    assert almacen_media.leer_crudo("previews/../escapa.js") is None
    assert almacen_media.leer_crudo("/etc/passwd") is None


def test_disco_objeto_existe(disco):
    assert almacen_media.objeto_existe("y.png") is False
    almacen_media.guardar_objeto("y.png", b"y", content_type="image/png")
    assert almacen_media.objeto_existe("y.png") is True
    # Nombre inválido (separadores) -> False, sin reventar.
    assert almacen_media.objeto_existe("../x") is False


def test_disco_content_addressed_dedup(disco):
    """Mismo contenido -> misma key -> UN objeto; contenido distinto -> key distinta."""
    from keni_consola import media

    n1 = media.guardar_bytes_contenido(b"placa-identica", ext="png")
    n2 = media.guardar_bytes_contenido(b"placa-identica", ext="png")
    n3 = media.guardar_bytes_contenido(b"otra-placa", ext="png")
    assert n1 == n2  # mismo hash -> mismo nombre
    assert n1 != n3
    # Solo dos objetos físicos en el almacén (no tres).
    nombres = {nombre for (nombre, _mtime) in almacen_media.listar_objetos()}
    assert {n1, n3} <= nombres and len(nombres) == 2


def test_importar_imagen_es_content_addressed(disco, tmp_path):
    """`importar_imagen` de dos ficheros con el MISMO contenido devuelve la misma key."""
    from keni_consola import media

    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    a.write_bytes(b"composicion-identica")
    b.write_bytes(b"composicion-identica")
    assert media.importar_imagen(str(a)) == media.importar_imagen(str(b))


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


def test_s3_borrar_prefijo(s3):
    """En S3, `borrar_prefijo` borra claves anidadas crudas (lo que `borrar_objeto` rechaza)."""
    s3.put_object(Bucket="keni-media", Key="previews/sug-x/index.html", Body=b"<html>")
    s3.put_object(Bucket="keni-media", Key="previews/sug-x/assets/app.js", Body=b"//js")
    almacen_media.guardar_objeto("foto.png", b"img", content_type="image/png")

    n = almacen_media.borrar_prefijo("previews/sug-x/")

    assert n == 2
    restantes = {k for (k, _m) in almacen_media.listar_objetos()}
    assert not any(k.startswith("previews/sug-x/") for k in restantes)
    assert "foto.png" in restantes  # el resto del bucket intacto


def test_s3_guardar_y_leer_crudo_anidado(s3):
    almacen_media.guardar_crudo(
        "previews/sug-x/assets/app.js", b"//js", content_type="text/javascript"
    )
    assert almacen_media.leer_crudo("previews/sug-x/assets/app.js") == b"//js"
    assert almacen_media.leer_crudo("previews/sug-x/falta.js") is None
    obj = s3.get_object(Bucket="keni-media", Key="previews/sug-x/assets/app.js")
    assert obj["ContentType"] == "text/javascript"


def test_s3_prefijo_desconocido_o_traversal_rechazado(s3):
    # Defensa en profundidad: una key con un prefijo que NO es categoria, o con `..`, no se
    # acepta. Una categoria VALIDA (`fotos/...`) si (es como guardamos ahora).
    assert almacen_media.leer_objeto("desconocida/b.png") is None  # prefijo no es categoria
    assert almacen_media.leer_objeto("../secreto.png") is None
    assert almacen_media.leer_objeto("fotos/../secreto.png") is None  # traversal tras categoria
    with pytest.raises(ValueError):
        almacen_media._nombre_plano_seguro("a/b.png")
    with pytest.raises(ValueError):
        almacen_media._clave_segura("desconocida/b.png")
    # Una categoria valida + nombre plano pasa la validacion.
    assert almacen_media._clave_segura("fotos/abc.png") == "fotos/abc.png"


def test_s3_borrar(s3):
    almacen_media.guardar_objeto("y.png", b"y", content_type="image/png")
    assert almacen_media.leer_objeto("y.png") == b"y"
    almacen_media.borrar_objeto("y.png")
    assert almacen_media.leer_objeto("y.png") is None


def test_s3_objeto_existe(s3):
    assert almacen_media.objeto_existe("z.png") is False
    almacen_media.guardar_objeto("z.png", b"z", content_type="image/png")
    assert almacen_media.objeto_existe("z.png") is True
    assert almacen_media.objeto_existe("desconocida/b.png") is False


# --------------------------------------------------------------------------- #
# Categorias (subcarpetas por tipo): componer_clave / categoria_de            #
# --------------------------------------------------------------------------- #


def test_componer_clave_con_y_sin_categoria():
    assert almacen_media.componer_clave(None, "abc.png") == "abc.png"
    assert almacen_media.componer_clave("fotos", "abc.png") == "fotos/abc.png"
    with pytest.raises(ValueError):
        almacen_media.componer_clave("inventada", "abc.png")
    with pytest.raises(ValueError):
        almacen_media.componer_clave("fotos", "sub/abc.png")  # el nombre debe ser plano


def test_categoria_de():
    assert almacen_media.categoria_de("fotos/abc.png") == "fotos"
    assert almacen_media.categoria_de("logos/abc.png") == "logos"
    assert almacen_media.categoria_de("abc.png") is None          # key plana
    assert almacen_media.categoria_de("inventada/abc.png") is None  # prefijo no es categoria


def test_disco_guardar_leer_borrar_con_categoria(disco):
    clave = almacen_media.componer_clave("fotos", "abc.png")
    almacen_media.guardar_objeto(clave, b"foto", content_type="image/png")
    assert almacen_media.leer_objeto(clave) == b"foto"
    assert almacen_media.objeto_existe(clave) is True
    # El listado en disco devuelve la key RELATIVA con su carpeta (espejo de S3).
    nombres = {n for (n, _m) in almacen_media.listar_objetos()}
    assert "fotos/abc.png" in nombres
    almacen_media.borrar_objeto(clave)
    assert almacen_media.leer_objeto(clave) is None


def test_s3_guardar_leer_con_categoria(s3):
    clave = almacen_media.componer_clave("logos", "logo.png")
    almacen_media.guardar_objeto(clave, b"logo-bytes", content_type="image/png")
    assert almacen_media.leer_objeto(clave) == b"logo-bytes"
    # La key en el bucket lleva su carpeta.
    assert s3.get_object(Bucket="keni-media", Key="logos/logo.png")["Body"].read() == b"logo-bytes"
    nombres = {n for (n, _m) in almacen_media.listar_objetos()}
    assert "logos/logo.png" in nombres


def test_promover_objeto_copia_a_carpeta_disco(disco):
    """Promover COPIA a la carpeta destino, conserva el nombre plano y NO borra el origen."""
    origen = almacen_media.componer_clave("fotos", "deadbeef.png")
    almacen_media.guardar_objeto(origen, b"pixeles", content_type="image/png")
    destino = almacen_media.promover_objeto(origen, "logos")
    assert destino == "logos/deadbeef.png"
    assert almacen_media.leer_objeto(destino) == b"pixeles"
    # COPIA: el origen sigue existiendo (lo limpia el equipo al vaciar `fotos/`).
    assert almacen_media.leer_objeto(origen) == b"pixeles"
    # Idempotente: re-promover devuelve la misma key sin duplicar.
    assert almacen_media.promover_objeto(destino, "logos") == destino


def test_promover_objeto_inexistente_conserva_clave(disco):
    # Si el objeto no existe, devuelve la clave original (no perdemos la referencia).
    assert almacen_media.promover_objeto("fotos/noexiste.png", "logos") == "fotos/noexiste.png"
