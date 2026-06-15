"""Tests del almacen de secretos de la consola (`keni_consola.secretos`).

Cubre: roundtrip guardar/obtener/borrar, permisos 0600 del archivo, proveedor por
defecto, estado/pista, y que el VALOR de la clave NUNCA aparezca fuera del propio
campo `api_key` (ni en la pista, ni en el estado). Todo OFFLINE.
"""

from __future__ import annotations

import pytest

from keni_consola import secretos

_CLAVE = "sk-test-1234567890ABCD"


@pytest.fixture
def almacen(monkeypatch, tmp_path):
    """Aisla el archivo de secretos en tmp via `KENI_CONSOLA_SECRETOS`."""
    ruta = tmp_path / "secretos.toml"
    monkeypatch.setenv("KENI_CONSOLA_SECRETOS", str(ruta))
    return ruta


def test_roundtrip_guardar_obtener(almacen):
    assert secretos.obtener_clave_imagen() is None
    secretos.guardar_clave_imagen("openai", _CLAVE)
    assert secretos.obtener_clave_imagen() == _CLAVE
    assert secretos.obtener_proveedor_imagen() == "openai"


def test_borrar_deja_sin_clave(almacen):
    secretos.guardar_clave_imagen("openai", _CLAVE)
    secretos.borrar_clave_imagen()
    assert secretos.obtener_clave_imagen() is None
    estado = secretos.estado_imagen()
    assert estado["configurado"] is False
    assert estado["pista"] == ""


def test_borrar_sin_clave_no_lanza(almacen):
    secretos.borrar_clave_imagen()
    assert secretos.obtener_clave_imagen() is None


def test_permisos_0600(almacen):
    secretos.guardar_clave_imagen("openai", _CLAVE)
    assert almacen.exists()
    assert (almacen.stat().st_mode & 0o777) == 0o600


def test_proveedor_por_defecto_si_vacio(almacen):
    secretos.guardar_clave_imagen("", _CLAVE)
    assert secretos.obtener_proveedor_imagen() == secretos.PROVEEDOR_DEFECTO


def test_proveedor_por_defecto_sin_archivo(almacen):
    assert secretos.obtener_proveedor_imagen() == "openrouter"


def test_estado_pista_solo_ultimos_4(almacen):
    secretos.guardar_clave_imagen("openai", _CLAVE)
    estado = secretos.estado_imagen()
    assert estado["configurado"] is True
    assert estado["proveedor"] == "openai"
    # la pista revela solo los ultimos 4 caracteres, nunca la clave entera
    assert estado["pista"] == "····" + _CLAVE[-4:]
    assert _CLAVE not in estado["pista"]
    assert estado["pista"].startswith("····")


def test_estado_no_filtra_la_clave(almacen):
    """El dict de estado NO debe contener la clave entera en ningun campo."""
    secretos.guardar_clave_imagen("openai", _CLAVE)
    estado = secretos.estado_imagen()
    assert "api_key" not in estado
    for valor in estado.values():
        assert _CLAVE not in str(valor)


def test_clave_en_disco_pero_no_en_estado(almacen):
    """La clave SI vive en el archivo 0600, pero el estado solo expone la pista."""
    secretos.guardar_clave_imagen("openai", _CLAVE)
    # en disco esta (es el almacen local), protegida por 0600
    assert _CLAVE in almacen.read_text(encoding="utf-8")
    # pero el estado publico no la revela
    assert _CLAVE not in str(secretos.estado_imagen())


def test_archivo_corrupto_no_lanza(almacen):
    almacen.write_text("esto no es toml valido [[[", encoding="utf-8")
    assert secretos.obtener_clave_imagen() is None
    assert secretos.estado_imagen()["configurado"] is False


# --------------------------------------------------------------------------- #
# Modelo de imagen elegido por la UI                                          #
# --------------------------------------------------------------------------- #


def test_modelo_ausente_por_defecto(almacen):
    assert secretos.obtener_modelo_imagen() is None


def test_guardar_obtener_modelo(almacen):
    secretos.guardar_modelo_imagen("openai/gpt-5-image")
    assert secretos.obtener_modelo_imagen() == "openai/gpt-5-image"


def test_modelo_vacio_se_trata_como_ausente(almacen):
    secretos.guardar_modelo_imagen("   ")
    assert secretos.obtener_modelo_imagen() is None


def test_guardar_modelo_preserva_clave_y_proveedor(almacen):
    """Guardar el modelo NO debe pisar la clave ni el proveedor ya guardados."""
    secretos.guardar_clave_imagen("openrouter", _CLAVE)
    secretos.guardar_modelo_imagen("openai/gpt-5-image")
    assert secretos.obtener_clave_imagen() == _CLAVE
    assert secretos.obtener_proveedor_imagen() == "openrouter"
    assert secretos.obtener_modelo_imagen() == "openai/gpt-5-image"


def test_guardar_clave_preserva_modelo(almacen):
    """Reguardar la clave NO debe borrar el modelo ya elegido por la UI."""
    secretos.guardar_modelo_imagen("openai/gpt-5-image")
    secretos.guardar_clave_imagen("openrouter", _CLAVE)
    assert secretos.obtener_modelo_imagen() == "openai/gpt-5-image"
    assert secretos.obtener_clave_imagen() == _CLAVE


def test_guardar_modelo_mantiene_0600(almacen):
    secretos.guardar_modelo_imagen("openai/gpt-5-image")
    assert (almacen.stat().st_mode & 0o777) == 0o600
