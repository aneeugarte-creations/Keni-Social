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


def test_pexels_key_secreto_por_marca_gana(stores, monkeypatch):
    monkeypatch.setenv("KENI_PEXELS_API_KEY", "global-key")
    secretos.guardar_clave_stock("unotv", "pexels", "marca-key")
    assert config.pexels_api_key("unotv") == "marca-key"  # secreto por marca gana
    assert config.pexels_api_key("claro-sports") == "global-key"  # cae a la global
    assert config.pexels_api_key("") == "global-key"  # sin marca: solo la global


def test_pexels_key_none_sin_nada(stores):
    assert config.pexels_api_key("unotv") is None
    assert config.pexels_api_key("") is None


def test_pixabay_key_por_marca(stores):
    secretos.guardar_clave_stock("unotv", "pixabay", "px-marca")
    assert config.pixabay_api_key("unotv") == "px-marca"
    assert config.pixabay_api_key("otra") is None


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
