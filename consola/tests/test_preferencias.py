"""Tests del almacen de preferencias locales (`keni_consola.preferencias`).

Cubre el nivel de ESFUERZO de generacion (`claude --effort`): valor por defecto,
guardado/normalizacion, validacion, borrado (vuelta al predeterminado), escritura
atomica y el helper `arg_esfuerzo()`. Todo aislado en tmp via `KENI_CONSOLA_PREFERENCIAS`.
"""

from __future__ import annotations

import pytest

from keni_consola import preferencias


@pytest.fixture
def prefs(monkeypatch, tmp_path):
    """Aisla el archivo de preferencias en tmp."""
    ruta = tmp_path / "preferencias.toml"
    monkeypatch.setenv("KENI_CONSOLA_PREFERENCIAS", str(ruta))
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


def test_guardar_persiste_en_disco(prefs):
    preferencias.guardar_esfuerzo("max")
    assert prefs.exists()
    assert 'esfuerzo = "max"' in prefs.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Vuelta al predeterminado (borrado)                                           #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("alias", ["", "predeterminado", "default", "AUTO"])
def test_predeterminado_borra_el_ajuste(prefs, alias):
    preferencias.guardar_esfuerzo("high")
    assert preferencias.guardar_esfuerzo(alias) == ""
    assert preferencias.obtener_esfuerzo() == ""
    assert preferencias.arg_esfuerzo() == []
    # El archivo ya no contiene la clave esfuerzo.
    if prefs.exists():
        assert "esfuerzo" not in prefs.read_text(encoding="utf-8")


def test_predeterminado_sin_archivo_no_falla(prefs):
    # Borrar cuando no hay nada guardado no debe romper ni crear basura invalida.
    assert preferencias.guardar_esfuerzo("") == ""
    assert preferencias.obtener_esfuerzo() == ""


# --------------------------------------------------------------------------- #
# Validacion                                                                   #
# --------------------------------------------------------------------------- #


def test_nivel_invalido_lanza_valueerror(prefs):
    with pytest.raises(ValueError):
        preferencias.guardar_esfuerzo("turbo")


def test_lectura_tolerante_a_valor_corrupto(prefs):
    # Un valor invalido en disco se ignora -> predeterminado (no revienta).
    prefs.write_text('esfuerzo = "inventado"\n', encoding="utf-8")
    assert preferencias.obtener_esfuerzo() == ""


def test_lectura_tolerante_a_toml_corrupto(prefs):
    prefs.write_text("esto no es toml = = =", encoding="utf-8")
    assert preferencias.obtener_esfuerzo() == ""
