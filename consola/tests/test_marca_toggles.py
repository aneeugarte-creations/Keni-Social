"""Toggles por marca de las etapas de auto-producción (`config.*_para_marca`).

Precedencia: override por-marca del store > flag GLOBAL de la etapa. Se monkeypatchea el store
(`ajustes.obtener`) y el accesor global, sin tocar Postgres ni el fichero de ajustes.
"""

from __future__ import annotations

from keni_consola import ajustes_catalogo, config


def _store(monkeypatch, datos: dict[str, str]):
    monkeypatch.setattr("keni_consola.ajustes.obtener", lambda clave: datos.get(clave))


def test_sin_override_cae_al_global(monkeypatch):
    _store(monkeypatch, {})
    monkeypatch.setattr(config, "pipeline_activo", lambda: True)
    monkeypatch.setattr(config, "autogen_activo", lambda: False)
    assert config.pipeline_activo_para_marca("claro-sports") is True
    assert config.autogen_activo_para_marca("claro-sports") is False


def test_override_apaga_una_marca_con_global_encendido(monkeypatch):
    monkeypatch.setattr(config, "pipeline_activo", lambda: True)
    _store(monkeypatch, {config.clave_por_marca(config.ENV_PIPELINE, "nacion-gamer"): "0"})
    assert config.pipeline_activo_para_marca("nacion-gamer") is False   # override OFF
    assert config.pipeline_activo_para_marca("claro-sports") is True    # sin override -> global


def test_override_enciende_una_marca_con_global_apagado(monkeypatch):
    monkeypatch.setattr(config, "autogen_activo", lambda: False)
    _store(monkeypatch, {config.clave_por_marca(config.ENV_AUTOGEN, "claro-sports"): "1"})
    assert config.autogen_activo_para_marca("claro-sports") is True     # override ON
    assert config.autogen_activo_para_marca("nacion-gamer") is False    # sin override -> global


def test_clave_por_marca_formato():
    assert config.clave_por_marca("KENI_AUTO_AVANCE", "unotv") == "KENI_AUTO_AVANCE::unotv"


def test_catalogo_expone_toggles_por_marca():
    claves = {a.clave for a in ajustes_catalogo.catalogo()}
    # Una etapa × una marca de cada (las 4 etapas y varias marcas se generan en caliente).
    assert config.clave_por_marca(config.ENV_PIPELINE, "nacion-gamer") in claves
    assert config.clave_por_marca(config.ENV_AUTO_AVANCE, "claro-sports") in claves
    assert config.clave_por_marca(config.ENV_AUTOGEN_ARTE, "unotv") in claves
    # Todos los toggles por marca son booleanos y del grupo nuevo.
    por_marca = [a for a in ajustes_catalogo.catalogo() if config.SEP_MARCA in a.clave]
    assert por_marca and all(a.tipo == "bool" and a.grupo == "automatizacion_marca" for a in por_marca)
