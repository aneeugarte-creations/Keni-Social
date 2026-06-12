"""Tests del nivel de ESFUERZO de generacion (`keni_consola.preferencias`).

Consolidacion: la fuente de verdad es el AJUSTE `KENI_ESFUERZO` del catalogo (store de
ajustes > env), y el TOML local de preferencias queda como FALLBACK LEGADO de lectura.
Cubre: valor por defecto, guardado (ya en el store de ajustes) + normalizacion,
validacion, vuelta al predeterminado, la precedencia store > env > TOML legado, la
migracion (el guardado retira la clave legada) y el helper `arg_esfuerzo()`. Todo
aislado en tmp via `KENI_CONSOLA_PREFERENCIAS` + `KENI_CONSOLA_AJUSTES`.
"""

from __future__ import annotations

import pytest

from keni_consola import ajustes, config, preferencias


@pytest.fixture
def prefs(monkeypatch, tmp_path):
    """Aisla el TOML legado Y el store de ajustes en tmp (y limpia la env del esfuerzo)."""
    ruta = tmp_path / "preferencias.toml"
    monkeypatch.setenv("KENI_CONSOLA_PREFERENCIAS", str(ruta))
    monkeypatch.setenv("KENI_CONSOLA_AJUSTES", str(tmp_path / "ajustes.toml"))
    monkeypatch.delenv(config.ENV_ESFUERZO, raising=False)
    return ruta


# --------------------------------------------------------------------------- #
# Por defecto                                                                  #
# --------------------------------------------------------------------------- #


def test_esfuerzo_por_defecto_vacio(prefs):
    assert preferencias.obtener_esfuerzo() == ""
    assert preferencias.arg_esfuerzo() == []


# --------------------------------------------------------------------------- #
# Guardado + helper de argv                                                    #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("nivel", ["low", "medium", "high", "xhigh", "max"])
def test_guardar_nivel_valido(prefs, nivel):
    assert preferencias.guardar_esfuerzo(nivel) == nivel
    assert preferencias.obtener_esfuerzo() == nivel
    assert preferencias.arg_esfuerzo() == ["--effort", nivel]


def test_guardar_normaliza_mayusculas_y_espacios(prefs):
    assert preferencias.guardar_esfuerzo("  HIGH  ") == "high"
    assert preferencias.obtener_esfuerzo() == "high"


def test_guardar_persiste_en_el_store_de_ajustes(prefs):
    """El guardado escribe el AJUSTE `KENI_ESFUERZO` (fuente unica), no el TOML legado."""
    preferencias.guardar_esfuerzo("max")
    assert ajustes.obtener(config.ENV_ESFUERZO) == "max"
    # El TOML legado NO recibe el valor nuevo (solo se usa como fallback de lectura).
    if prefs.exists():
        assert 'esfuerzo = "max"' not in prefs.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Vuelta al predeterminado                                                      #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("alias", ["", "predeterminado", "default", "AUTO"])
def test_predeterminado_guarda_vacio(prefs, alias):
    preferencias.guardar_esfuerzo("high")
    assert preferencias.guardar_esfuerzo(alias) == ""
    assert preferencias.obtener_esfuerzo() == ""
    assert preferencias.arg_esfuerzo() == []
    # Se persiste un "" EXPLICITO (gana al TOML legado y a la env), no se borra la clave.
    assert ajustes.obtener(config.ENV_ESFUERZO) == ""


def test_predeterminado_sin_nada_guardado_no_falla(prefs):
    assert preferencias.guardar_esfuerzo("") == ""
    assert preferencias.obtener_esfuerzo() == ""


# --------------------------------------------------------------------------- #
# Precedencia store > env > TOML legado (migracion suave)                       #
# --------------------------------------------------------------------------- #


def test_fallback_al_toml_legado_sin_ajuste_nuevo(prefs):
    """Lo guardado con la UI vieja sigue valiendo si nadie escribio el ajuste nuevo."""
    prefs.write_text('esfuerzo = "max"\n', encoding="utf-8")
    assert preferencias.obtener_esfuerzo() == "max"
    assert preferencias.arg_esfuerzo() == ["--effort", "max"]


def test_env_gana_al_toml_legado(prefs, monkeypatch):
    prefs.write_text('esfuerzo = "max"\n', encoding="utf-8")
    monkeypatch.setenv(config.ENV_ESFUERZO, "low")
    assert preferencias.obtener_esfuerzo() == "low"


def test_store_gana_a_env_y_a_toml_legado(prefs, monkeypatch):
    prefs.write_text('esfuerzo = "max"\n', encoding="utf-8")
    monkeypatch.setenv(config.ENV_ESFUERZO, "low")
    ajustes.guardar(config.ENV_ESFUERZO, "medium")
    assert preferencias.obtener_esfuerzo() == "medium"


def test_vacio_explicito_en_store_gana_al_toml_legado(prefs):
    """Un «Predeterminado» elegido en la UI nueva NO resucita el valor viejo."""
    prefs.write_text('esfuerzo = "max"\n', encoding="utf-8")
    ajustes.guardar(config.ENV_ESFUERZO, "")
    assert preferencias.obtener_esfuerzo() == ""
    assert preferencias.arg_esfuerzo() == []


def test_guardar_retira_la_clave_legada(prefs):
    """Migracion definitiva: el primer guardado limpia el TOML viejo."""
    prefs.write_text('esfuerzo = "max"\n', encoding="utf-8")
    preferencias.guardar_esfuerzo("high")
    assert "esfuerzo" not in prefs.read_text(encoding="utf-8")
    assert preferencias.obtener_esfuerzo() == "high"


# --------------------------------------------------------------------------- #
# Validacion                                                                   #
# --------------------------------------------------------------------------- #


def test_nivel_invalido_lanza_valueerror(prefs):
    with pytest.raises(ValueError):
        preferencias.guardar_esfuerzo("turbo")


def test_lectura_tolerante_a_valor_corrupto(prefs):
    # Un valor invalido en el TOML legado se ignora -> predeterminado (no revienta).
    prefs.write_text('esfuerzo = "inventado"\n', encoding="utf-8")
    assert preferencias.obtener_esfuerzo() == ""


def test_lectura_tolerante_a_toml_corrupto(prefs):
    prefs.write_text("esto no es toml = = =", encoding="utf-8")
    assert preferencias.obtener_esfuerzo() == ""


def test_valor_corrupto_en_store_cae_al_predeterminado(prefs):
    # El store manda aunque traiga basura: NO se cae al legado (seria resucitarlo).
    prefs.write_text('esfuerzo = "max"\n', encoding="utf-8")
    ajustes.guardar(config.ENV_ESFUERZO, "turbo")
    assert preferencias.obtener_esfuerzo() == ""


def test_etiquetas_cubren_todos_los_niveles(prefs):
    # Fuente unica de etiquetas para el catalogo y el shim: sin huecos.
    assert set(preferencias.ESFUERZO_ETIQUETAS) == {"", *preferencias.ESFUERZOS_VALIDOS}
