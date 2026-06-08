"""Exclusiones por marca de las etapas de auto-producción (`config.marca_apagada`).

Semántica: una marca se EXCLUYE de una etapa con un override falsy en el store (`ENV::marca`);
sin override no está apagada (la etapa corre para ella, gateada por el global como siempre). Se
monkeypatchea el store (`ajustes.obtener`), sin tocar Postgres ni el fichero de ajustes.
"""

from __future__ import annotations

from keni_consola import ajustes_catalogo, config


def _store(monkeypatch, datos: dict[str, str]):
    monkeypatch.setattr("keni_consola.ajustes.obtener", lambda clave: datos.get(clave))


def test_sin_override_no_esta_apagada(monkeypatch):
    _store(monkeypatch, {})
    assert config.marca_apagada(config.ENV_PIPELINE, "claro-sports") is False
    assert config.marca_apagada(config.ENV_AUTOGEN_ARTE, "nacion-gamer") is False


def test_override_falsy_apaga_la_marca(monkeypatch):
    _store(monkeypatch, {config.clave_por_marca(config.ENV_PIPELINE, "nacion-gamer"): "0"})
    assert config.marca_apagada(config.ENV_PIPELINE, "nacion-gamer") is True   # excluida
    assert config.marca_apagada(config.ENV_PIPELINE, "claro-sports") is False  # sin override


def test_override_truthy_no_apaga(monkeypatch):
    _store(monkeypatch, {config.clave_por_marca(config.ENV_AUTOGEN_ARTE, "claro-sports"): "1"})
    assert config.marca_apagada(config.ENV_AUTOGEN_ARTE, "claro-sports") is False


def test_clave_por_marca_formato():
    assert config.clave_por_marca("KENI_PIPELINE", "unotv") == "KENI_PIPELINE::unotv"


def test_catalogo_expone_toggles_por_marca():
    claves = {a.clave for a in ajustes_catalogo.catalogo()}
    assert config.clave_por_marca(config.ENV_PIPELINE, "nacion-gamer") in claves
    assert config.clave_por_marca(config.ENV_AUTOGEN_ARTE, "unotv") in claves
    # "Crear noticias" (KENI_INGESTA) ahora también tiene fila por marca.
    assert config.clave_por_marca(config.ENV_INGESTA, "unotv") in claves
    # Las tres etapas (ingesta + copy + arte) van en `automatizacion_marca`; la publicación, en
    # su propio grupo `publicacion_marca`. Todos los toggles por marca son `bool`.
    por_marca = [a for a in ajustes_catalogo.catalogo() if config.SEP_MARCA in a.clave]
    assert por_marca and all(
        a.tipo == "bool" and a.grupo in {"automatizacion_marca", "publicacion_marca"}
        for a in por_marca
    )


def test_catalogo_expone_publicacion_por_marca():
    claves = {a.clave for a in ajustes_catalogo.catalogo()}
    assert config.clave_por_marca(config.ENV_PUBLICAR_REAL, "fundacion") in claves
    pub_marca = [a for a in ajustes_catalogo.catalogo() if a.grupo == "publicacion_marca"]
    assert pub_marca and all(config.ENV_PUBLICAR_REAL in a.clave for a in pub_marca)


def test_publicar_real_para_maestro_y_excepcion(monkeypatch):
    # Maestro OFF: ninguna marca publica de verdad.
    _store(monkeypatch, {})
    monkeypatch.delenv(config.ENV_PUBLICAR_REAL, raising=False)
    assert config.publicar_real_para("claro-sports") is False

    # Maestro ON: publican todas salvo las excluidas con override falsy por marca.
    _store(monkeypatch, {config.clave_por_marca(config.ENV_PUBLICAR_REAL, "fundacion"): "0"})
    monkeypatch.setenv(config.ENV_PUBLICAR_REAL, "1")
    assert config.publicar_real_para("claro-sports") is True   # sin override: sigue al maestro
    assert config.publicar_real_para("fundacion") is False     # excluida explícitamente
