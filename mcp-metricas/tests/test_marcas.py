"""Acotamiento por marca (KENI_METRICAS_MARCAS / campo `marcas` del config).

Una persona declara que marcas gestiona y la fuente solo expone esas. Debe
aplicar a la fuente `muestra` y a la `real` (FuenteCompuesta), y NO cambiar el
comportamiento historico cuando no se declara nada.
"""

from __future__ import annotations

import pytest

from keni_metricas.config import Config, FuenteScoped, cargar_config, construir_fuente
from keni_metricas.fuentes.base import CuentaNoEncontrada
from keni_metricas.fuentes.muestra import FuenteMuestra


@pytest.fixture(autouse=True)
def _entorno_limpio(monkeypatch, tmp_path):
    # parte siempre de un entorno sin marcas ni config en disco, fuente de muestra.
    # La fuente única por defecto es `metricool`; estos tests prueban el ACOTADO
    # por marcas sobre la fuente de muestra (offline), así que la fijamos explícita.
    monkeypatch.delenv("KENI_METRICAS_MARCAS", raising=False)
    monkeypatch.setenv("KENI_METRICAS_FUENTE", "muestra")
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(tmp_path / "noexiste.toml"))


# --- sin marcas: comportamiento por defecto (todas) -------------------------


def test_sin_marcas_devuelve_fuente_cruda(monkeypatch):
    fuente = construir_fuente(cargar_config())
    assert isinstance(fuente, FuenteMuestra)  # NO envuelta
    assert len(fuente.cuentas()) == 7


def test_marcas_vacia_no_envuelve():
    fuente = construir_fuente(Config(fuente="muestra", marcas=[]))
    assert isinstance(fuente, FuenteMuestra)


# --- con marcas via env var -------------------------------------------------


def test_env_acota_cuentas(monkeypatch):
    monkeypatch.setenv("KENI_METRICAS_MARCAS", "claro_sports,unotv")
    fuente = construir_fuente(cargar_config())
    assert isinstance(fuente, FuenteScoped)
    assert {c.id for c in fuente.cuentas()} == {"claro_sports", "unotv"}


def test_env_resumen_dentro_de_alcance(monkeypatch):
    monkeypatch.setenv("KENI_METRICAS_MARCAS", "claro_sports")
    fuente = construir_fuente(cargar_config())
    r = fuente.resumen("claro_sports", "semana")
    assert r.cuenta == "claro_sports"
    assert r.fuente == "muestra"


def test_env_rechaza_fuera_de_alcance(monkeypatch):
    monkeypatch.setenv("KENI_METRICAS_MARCAS", "claro_sports")
    fuente = construir_fuente(cargar_config())
    # 'unotv' existe en la fuente subyacente, pero no en el alcance
    with pytest.raises(CuentaNoEncontrada):
        fuente.resumen("unotv", "semana")
    with pytest.raises(CuentaNoEncontrada):
        fuente.mejores_piezas("unotv", "semana", 3)


def test_env_espacios_y_duplicados(monkeypatch):
    monkeypatch.setenv("KENI_METRICAS_MARCAS", " claro_sports , unotv , claro_sports ,")
    fuente = construir_fuente(cargar_config())
    assert {c.id for c in fuente.cuentas()} == {"claro_sports", "unotv"}


# --- con marcas via config.toml + prioridad de la env var -------------------


def test_config_toml_acota(monkeypatch, tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        'fuente = "muestra"\nmarcas = ["nacion_gamer", "piso_15"]\n', encoding="utf-8"
    )
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(cfg_file))
    cfg = cargar_config()
    assert cfg.marcas == ["nacion_gamer", "piso_15"]
    fuente = construir_fuente(cfg)
    assert {c.id for c in fuente.cuentas()} == {"nacion_gamer", "piso_15"}


def test_env_var_gana_sobre_config_toml(monkeypatch, tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('marcas = ["nacion_gamer"]\n', encoding="utf-8")
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(cfg_file))
    monkeypatch.setenv("KENI_METRICAS_MARCAS", "claro_sports")
    cfg = cargar_config()
    assert cfg.marcas == ["claro_sports"]


# --- aplica tambien a la fuente real (FuenteCompuesta) ----------------------


def test_aplica_a_fuente_real(monkeypatch):
    monkeypatch.setenv("KENI_METRICAS_FUENTE", "real")
    monkeypatch.setenv("KENI_METRICAS_PERMITIR_REAL", "1")  # fallback opt-in
    monkeypatch.setenv("KENI_METRICAS_MARCAS", "claro_sports")
    fuente = construir_fuente(cargar_config())
    assert isinstance(fuente, FuenteScoped)
    assert fuente.nombre == "real"  # delega el nombre de la fuente envuelta
    with pytest.raises(CuentaNoEncontrada):
        fuente.resumen("unotv", "semana")
