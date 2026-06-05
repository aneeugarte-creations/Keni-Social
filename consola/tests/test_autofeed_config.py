"""Accesores de config del auto-feed (Ola E). PURO (sin BD): solo env + defaults.

Cubre: defaults, parseo de umbral (float, fuera de rango → def), cap global, override por
marca (`KENI_AUTOFEED_CAP::<marca>`, incl. 0 = desactiva), intervalo, y el gate maestro.
"""

from __future__ import annotations

import pytest

from keni_consola import config, marcas


@pytest.fixture
def limpio(monkeypatch):
    """Borra todas las env del auto-feed + el maestro para partir de defaults."""
    for var in (
        config.ENV_AUTOFEED,
        config.ENV_AUTOFEED_UMBRAL,
        config.ENV_AUTOFEED_CAP,
        config.ENV_AUTOFEED_INTERVALO_MIN,
        config.ENV_MAQUINA,
    ):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def test_defaults(limpio):
    assert config.autofeed_activo() is False
    assert config.autofeed_umbral() == config.AUTOFEED_UMBRAL_DEF == 0.5
    assert config.autofeed_cap() == config.AUTOFEED_CAP_DEF == 20
    assert config.autofeed_intervalo_min() == config.AUTOFEED_INTERVALO_MIN_DEF == 10


def test_activo_lee_flag(limpio):
    limpio.setenv(config.ENV_AUTOFEED, "1")
    assert config.autofeed_activo() is True
    limpio.setenv(config.ENV_AUTOFEED, "off")
    assert config.autofeed_activo() is False


def test_umbral_valido(limpio):
    limpio.setenv(config.ENV_AUTOFEED_UMBRAL, "0.8")
    assert config.autofeed_umbral() == 0.8


def test_umbral_invalido_y_fuera_de_rango_cae_a_def(limpio):
    limpio.setenv(config.ENV_AUTOFEED_UMBRAL, "no-numero")
    assert config.autofeed_umbral() == config.AUTOFEED_UMBRAL_DEF
    limpio.setenv(config.ENV_AUTOFEED_UMBRAL, "1.5")
    assert config.autofeed_umbral() == config.AUTOFEED_UMBRAL_DEF
    limpio.setenv(config.ENV_AUTOFEED_UMBRAL, "-0.1")
    assert config.autofeed_umbral() == config.AUTOFEED_UMBRAL_DEF


def test_cap_global(limpio):
    limpio.setenv(config.ENV_AUTOFEED_CAP, "7")
    assert config.autofeed_cap() == 7
    # min 0: negativos se acotan a 0
    limpio.setenv(config.ENV_AUTOFEED_CAP, "-3")
    assert config.autofeed_cap() == 0


def test_cap_override_por_marca(limpio):
    marca = marcas.ids()[0]
    limpio.setenv(config.ENV_AUTOFEED_CAP, "20")
    # Sin override: la marca cae al global.
    assert config.autofeed_cap(marca) == 20
    # Con override: manda el override por marca.
    limpio.setenv(config.clave_por_marca(config.ENV_AUTOFEED_CAP, marca), "5")
    assert config.autofeed_cap(marca) == 5
    # Otra marca SIN override sigue al global.
    otra = marcas.ids()[1] if len(marcas.ids()) > 1 else marca
    if otra != marca:
        assert config.autofeed_cap(otra) == 20


def test_cap_override_cero_desactiva_marca(limpio):
    marca = marcas.ids()[0]
    limpio.setenv(config.ENV_AUTOFEED_CAP, "20")
    limpio.setenv(config.clave_por_marca(config.ENV_AUTOFEED_CAP, marca), "0")
    assert config.autofeed_cap(marca) == 0


def test_cap_override_ilegible_cae_al_global(limpio):
    marca = marcas.ids()[0]
    limpio.setenv(config.ENV_AUTOFEED_CAP, "11")
    limpio.setenv(config.clave_por_marca(config.ENV_AUTOFEED_CAP, marca), "no-numero")
    assert config.autofeed_cap(marca) == 11


def test_intervalo_minimo_1(limpio):
    limpio.setenv(config.ENV_AUTOFEED_INTERVALO_MIN, "0")
    assert config.autofeed_intervalo_min() == 1
    limpio.setenv(config.ENV_AUTOFEED_INTERVALO_MIN, "30")
    assert config.autofeed_intervalo_min() == 30


def test_gate_maestro_apaga_aunque_toggle_on(limpio):
    limpio.setenv(config.ENV_AUTOFEED, "1")
    # Maestro OFF (def): el gate compuesto da False aunque el toggle propio sea True.
    gate = config.gate_maquina(config.autofeed_activo)
    assert config.autofeed_activo() is True
    assert gate() is False
    # Maestro ON: el gate sigue al toggle.
    limpio.setenv(config.ENV_MAQUINA, "1")
    assert gate() is True
