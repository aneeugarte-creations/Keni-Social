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
    assert config.marca_apagada(config.ENV_AUTO_AVANCE, "nacion-gamer") is False


def test_override_falsy_apaga_la_marca(monkeypatch):
    _store(monkeypatch, {config.clave_por_marca(config.ENV_PIPELINE, "nacion-gamer"): "0"})
    assert config.marca_apagada(config.ENV_PIPELINE, "nacion-gamer") is True   # excluida
    assert config.marca_apagada(config.ENV_PIPELINE, "claro-sports") is False  # sin override


def test_override_truthy_no_apaga(monkeypatch):
    _store(monkeypatch, {config.clave_por_marca(config.ENV_AUTOGEN, "claro-sports"): "1"})
    assert config.marca_apagada(config.ENV_AUTOGEN, "claro-sports") is False


def test_clave_por_marca_formato():
    assert config.clave_por_marca("KENI_AUTO_AVANCE", "unotv") == "KENI_AUTO_AVANCE::unotv"


def test_catalogo_expone_toggles_por_marca():
    claves = {a.clave for a in ajustes_catalogo.catalogo()}
    assert config.clave_por_marca(config.ENV_PIPELINE, "nacion-gamer") in claves
    assert config.clave_por_marca(config.ENV_AUTO_AVANCE, "claro-sports") in claves
    assert config.clave_por_marca(config.ENV_AUTOGEN_ARTE, "unotv") in claves
    por_marca = [a for a in ajustes_catalogo.catalogo() if config.SEP_MARCA in a.clave]
    assert por_marca and all(
        a.tipo == "bool" and a.grupo == "automatizacion_marca" for a in por_marca
    )
