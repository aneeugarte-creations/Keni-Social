"""Tests de los accessors de config para credenciales de agencias (AFP / Reuters).

Cubre la precedencia SECRETO (guardado por la UI) > ENV > DEFECTO de cada campo. Todo
OFFLINE, con los stores de secretos y de ajustes aislados en tmp.
"""

from __future__ import annotations

import pytest

from keni_consola import config, secretos


@pytest.fixture
def stores(monkeypatch, tmp_path):
    """Aisla el almacen de secretos y el de ajustes en tmp (sin tocar los reales)."""
    monkeypatch.setenv("KENI_CONSOLA_SECRETOS", str(tmp_path / "secretos.toml"))
    monkeypatch.setenv("KENI_CONSOLA_AJUSTES", str(tmp_path / "ajustes.toml"))
    for var in (
        "KENI_AFP_CLIENT_ID",
        "KENI_AFP_CLIENT_SECRET",
        "KENI_AFP_BASE_URL",
        "KENI_REUTERS_API_KEY",
        "KENI_REUTERS_BASE_URL",
    ):
        monkeypatch.delenv(var, raising=False)


# --------------------------------------------------------------------------- #
# AFP                                                                          #
# --------------------------------------------------------------------------- #


def test_afp_client_id_secreto_gana_a_env(stores, monkeypatch):
    monkeypatch.setenv("KENI_AFP_CLIENT_ID", "id-env")
    secretos.guardar_credencial_agencia("afp", "client_id", "id-ui")
    assert config.afp_client_id() == "id-ui"


def test_afp_client_id_cae_a_env(stores, monkeypatch):
    monkeypatch.setenv("KENI_AFP_CLIENT_ID", "id-env")
    assert config.afp_client_id() == "id-env"


def test_afp_client_id_none_sin_nada(stores):
    assert config.afp_client_id() is None


def test_afp_client_secret_secreto_gana_a_env(stores, monkeypatch):
    monkeypatch.setenv("KENI_AFP_CLIENT_SECRET", "sec-env")
    secretos.guardar_credencial_agencia("afp", "client_secret", "sec-ui")
    assert config.afp_client_secret() == "sec-ui"


def test_afp_client_secret_cae_a_env(stores, monkeypatch):
    monkeypatch.setenv("KENI_AFP_CLIENT_SECRET", "sec-env")
    assert config.afp_client_secret() == "sec-env"


def test_afp_base_url_secreto_gana(stores, monkeypatch):
    monkeypatch.setenv("KENI_AFP_BASE_URL", "https://env.afp.example")
    secretos.guardar_credencial_agencia("afp", "base_url", "https://ui.afp.example/")
    assert config.afp_base_url() == "https://ui.afp.example"  # sin barra final


def test_afp_base_url_cae_a_env(stores, monkeypatch):
    monkeypatch.setenv("KENI_AFP_BASE_URL", "https://env.afp.example/")
    assert config.afp_base_url() == "https://env.afp.example"


def test_afp_base_url_cae_al_defecto(stores):
    assert config.afp_base_url() == config.AFP_BASE_URL_DEF


def test_afp_configurado_hereda_secretos(stores):
    assert config.afp_configurado() is False
    secretos.guardar_credencial_agencia("afp", "client_id", "id-ui")
    secretos.guardar_credencial_agencia("afp", "client_secret", "sec-ui")
    assert config.afp_configurado() is True


# --------------------------------------------------------------------------- #
# Reuters                                                                      #
# --------------------------------------------------------------------------- #


def test_reuters_api_key_secreto_gana_a_env(stores, monkeypatch):
    monkeypatch.setenv("KENI_REUTERS_API_KEY", "key-env")
    secretos.guardar_credencial_agencia("reuters", "api_key", "key-ui")
    assert config.reuters_api_key() == "key-ui"


def test_reuters_api_key_cae_a_env(stores, monkeypatch):
    monkeypatch.setenv("KENI_REUTERS_API_KEY", "key-env")
    assert config.reuters_api_key() == "key-env"


def test_reuters_api_key_none_sin_nada(stores):
    assert config.reuters_api_key() is None


def test_reuters_base_url_secreto_gana(stores, monkeypatch):
    monkeypatch.setenv("KENI_REUTERS_BASE_URL", "https://env.reuters.example")
    secretos.guardar_credencial_agencia("reuters", "base_url", "https://ui.reuters.example/")
    assert config.reuters_base_url() == "https://ui.reuters.example"


def test_reuters_base_url_cae_al_defecto(stores):
    assert config.reuters_base_url() == config.REUTERS_BASE_URL_DEF


def test_reuters_configurado_hereda_secreto(stores):
    assert config.reuters_configurado() is False
    secretos.guardar_credencial_agencia("reuters", "api_key", "key-ui")
    assert config.reuters_configurado() is True
