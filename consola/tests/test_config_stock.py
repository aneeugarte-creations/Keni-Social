"""Tests de los accessors de config para fuentes de stock por marca.

Cubre la precedencia de la API key (secreto por marca > clave global por entorno) y el
parseo del CSV de fuentes habilitadas (`KENI_STOCK_FUENTES[::marca]`). Todo OFFLINE,
con los stores de secretos y de ajustes aislados en tmp.
"""

from __future__ import annotations

import pytest

from keni_consola import ajustes, config, secretos


@pytest.fixture
def stores(monkeypatch, tmp_path):
    """Aisla el almacen de secretos y el de ajustes en tmp (sin tocar los reales)."""
    monkeypatch.setenv("KENI_CONSOLA_SECRETOS", str(tmp_path / "secretos.toml"))
    monkeypatch.setenv("KENI_CONSOLA_AJUSTES", str(tmp_path / "ajustes.toml"))
    monkeypatch.delenv("KENI_PEXELS_API_KEY", raising=False)
    monkeypatch.delenv("KENI_PIXABAY_API_KEY", raising=False)
    monkeypatch.delenv("KENI_STOCK_FUENTES", raising=False)


def test_pexels_key_secreto_ui_gana_a_env(stores, monkeypatch):
    monkeypatch.setenv("KENI_PEXELS_API_KEY", "global-env")
    secretos.guardar_clave_stock("pexels", "ui-key")
    assert config.pexels_api_key() == "ui-key"  # el secreto guardado por la UI gana


def test_pexels_key_cae_a_env(stores, monkeypatch):
    monkeypatch.setenv("KENI_PEXELS_API_KEY", "global-env")
    assert config.pexels_api_key() == "global-env"  # sin secreto UI: cae a la env global


def test_pexels_key_none_sin_nada(stores):
    assert config.pexels_api_key() is None


def test_pixabay_key_global(stores):
    secretos.guardar_clave_stock("pixabay", "px-ui")
    assert config.pixabay_api_key() == "px-ui"


def test_fuentes_activas_none_sin_config(stores):
    # Sin CSV: None = sin filtro (todas las fuentes disponibles).
    assert config.fuentes_stock_activas("unotv") is None
    assert config.fuentes_stock_activas("") is None


def test_fuentes_activas_csv_por_marca(stores):
    ajustes.guardar("KENI_STOCK_FUENTES::unotv", "wikimedia, openverse")
    assert config.fuentes_stock_activas("unotv") == {"wikimedia", "openverse"}
    # otra marca sin override: sigue sin filtro
    assert config.fuentes_stock_activas("claro-sports") is None


def test_fuentes_activas_global_como_fallback(stores):
    ajustes.guardar("KENI_STOCK_FUENTES", "openverse")
    # una marca sin override propio hereda el global
    assert config.fuentes_stock_activas("unotv") == {"openverse"}
