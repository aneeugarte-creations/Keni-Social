"""Tests del parseo de `[google_analytics]` en el config (`keni_metricas.config`).

Cubre el modelo de auth (app global + property_id por marca), la precedencia de las
env `GA_OAUTH_*` sobre el TOML, y los estados derivados (app_configurada / conectada /
marcas_configuradas).
"""

from __future__ import annotations

from keni_metricas import config as c


def test_parsea_app_global_y_property_por_marca():
    datos = {
        "google_analytics": {
            "client_id": "ci",
            "client_secret": "cs",
            "refresh_token": "rt",
            "marcas": {
                "unotv": {"property_id": "123", "dominio": "unotv.com"},
                "sin_prop": {},
            },
        }
    }
    ga = c._parsear_google_analytics(datos)
    assert ga.app_configurada is True
    assert ga.conectada is True
    # solo la marca con property_id queda configurada; la otra se conserva pero se omite
    assert ga.marcas_configuradas() == {"unotv": {"property_id": "123", "dominio": "unotv.com"}}
    assert "sin_prop" in ga.marcas


def test_sin_refresh_token_no_conectada():
    datos = {
        "google_analytics": {
            "client_id": "a",
            "client_secret": "b",
            "marcas": {"unotv": {"property_id": "1"}},
        }
    }
    ga = c._parsear_google_analytics(datos)
    assert ga.app_configurada is True
    assert ga.conectada is False
    assert ga.marcas_configuradas() == {}  # sin conexión no hay marca operativa


def test_env_gana_al_toml(monkeypatch):
    monkeypatch.setenv("GA_OAUTH_CLIENT_ID", "ENV_CID")
    monkeypatch.setenv("GA_OAUTH_REFRESH_TOKEN", "ENV_RT")
    ga = c._parsear_google_analytics(
        {"google_analytics": {"client_id": "file", "client_secret": "cs"}}
    )
    assert ga.client_id == "ENV_CID"
    assert ga.refresh_token == "ENV_RT"


def test_seccion_ausente_da_config_vacia():
    ga = c._parsear_google_analytics({})
    assert ga.app_configurada is False
    assert ga.conectada is False
    assert ga.marcas == {}
