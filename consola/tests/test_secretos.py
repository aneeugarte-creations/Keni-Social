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


# --------------------------------------------------------------------------- #
# Claves GLOBALES de fotos de stock (Pexels / Pixabay)                        #
# --------------------------------------------------------------------------- #

_CLAVE_STOCK = "pexels-key-9876ZZZZ"


def test_roundtrip_clave_stock(almacen):
    assert secretos.obtener_clave_stock("pexels") is None
    secretos.guardar_clave_stock("pexels", _CLAVE_STOCK)
    assert secretos.obtener_clave_stock("pexels") == _CLAVE_STOCK
    # otro proveedor no se ve afectado
    assert secretos.obtener_clave_stock("pixabay") is None


def test_clave_stock_aislada_por_proveedor(almacen):
    secretos.guardar_clave_stock("pexels", "AAA1")
    secretos.guardar_clave_stock("pixabay", "BBB2")
    assert secretos.obtener_clave_stock("pexels") == "AAA1"
    assert secretos.obtener_clave_stock("pixabay") == "BBB2"


def test_borrar_clave_stock(almacen):
    secretos.guardar_clave_stock("pexels", "AAA1")
    secretos.guardar_clave_stock("pixabay", "BBB2")
    secretos.borrar_clave_stock("pexels")
    assert secretos.obtener_clave_stock("pexels") is None
    # borrar uno NO toca el otro proveedor
    assert secretos.obtener_clave_stock("pixabay") == "BBB2"


def test_guardar_clave_stock_proveedor_no_valido_no_escribe(almacen):
    secretos.guardar_clave_stock("openverse", "x")  # openverse no lleva clave
    assert secretos.obtener_clave_stock("openverse") is None
    assert not almacen.exists()


def test_estado_clave_stock_no_filtra_la_clave(almacen):
    secretos.guardar_clave_stock("pexels", _CLAVE_STOCK)
    estado = secretos.estado_clave_stock("pexels")
    assert estado["configurado"] is True
    assert estado["pista"] == "····" + _CLAVE_STOCK[-4:]
    assert _CLAVE_STOCK not in estado["pista"]


def test_clave_stock_0600_y_en_disco(almacen):
    secretos.guardar_clave_stock("pexels", _CLAVE_STOCK)
    assert (almacen.stat().st_mode & 0o777) == 0o600
    assert _CLAVE_STOCK in almacen.read_text(encoding="utf-8")


def test_clave_stock_convive_con_imagen(almacen):
    """Guardar stock NO debe descartar el bloque [imagen] ni viceversa."""
    secretos.guardar_clave_imagen("openrouter", _CLAVE)
    secretos.guardar_clave_stock("pexels", _CLAVE_STOCK)
    assert secretos.obtener_clave_imagen() == _CLAVE
    assert secretos.obtener_clave_stock("pexels") == _CLAVE_STOCK


# --------------------------------------------------------------------------- #
# Credenciales de AGENCIAS de noticias/foto (AFP / Reuters)                   #
# --------------------------------------------------------------------------- #

_CRED_AFP = "prueba-afp-3210"


def test_roundtrip_credencial_agencia(almacen):
    assert secretos.obtener_credencial_agencia("afp", "client_id") is None
    secretos.guardar_credencial_agencia("afp", "client_id", "id-123")
    assert secretos.obtener_credencial_agencia("afp", "client_id") == "id-123"
    # otro campo de la misma agencia no se ve afectado
    assert secretos.obtener_credencial_agencia("afp", "client_secret") is None


def test_credencial_agencia_aislada_por_campo(almacen):
    secretos.guardar_credencial_agencia("afp", "client_id", "id-123")
    secretos.guardar_credencial_agencia("afp", "client_secret", _CRED_AFP)
    # guardar el segundo campo NO pisa el primero
    assert secretos.obtener_credencial_agencia("afp", "client_id") == "id-123"
    assert secretos.obtener_credencial_agencia("afp", "client_secret") == _CRED_AFP


def test_credencial_agencia_aislada_por_agencia(almacen):
    secretos.guardar_credencial_agencia("afp", "client_id", "id-afp")
    secretos.guardar_credencial_agencia("reuters", "api_key", "key-reuters")
    assert secretos.obtener_credencial_agencia("afp", "client_id") == "id-afp"
    assert secretos.obtener_credencial_agencia("reuters", "api_key") == "key-reuters"
    # afp no tiene api_key; reuters no tiene client_id
    assert secretos.obtener_credencial_agencia("afp", "api_key") is None
    assert secretos.obtener_credencial_agencia("reuters", "client_id") is None


def test_borrar_agencia_limpia_solo_esa(almacen):
    secretos.guardar_credencial_agencia("afp", "client_id", "id-afp")
    secretos.guardar_credencial_agencia("afp", "client_secret", _CRED_AFP)
    secretos.guardar_credencial_agencia("reuters", "api_key", "key-reuters")
    secretos.borrar_agencia("afp")
    assert secretos.obtener_credencial_agencia("afp", "client_id") is None
    assert secretos.obtener_credencial_agencia("afp", "client_secret") is None
    # borrar afp NO toca reuters
    assert secretos.obtener_credencial_agencia("reuters", "api_key") == "key-reuters"


def test_borrar_agencia_inexistente_no_lanza(almacen):
    secretos.borrar_agencia("afp")
    assert secretos.obtener_credencial_agencia("afp", "client_id") is None


def test_estado_credencial_agencia_no_filtra(almacen):
    secretos.guardar_credencial_agencia("afp", "client_secret", _CRED_AFP)
    estado = secretos.estado_credencial_agencia("afp", "client_secret")
    assert estado["configurado"] is True
    assert estado["pista"] == "····" + _CRED_AFP[-4:]
    assert _CRED_AFP not in estado["pista"]
    # un campo sin guardar: no configurado, sin pista
    vacio = secretos.estado_credencial_agencia("afp", "client_id")
    assert vacio == {"configurado": False, "pista": ""}


def test_credencial_agencia_0600_y_en_disco(almacen):
    secretos.guardar_credencial_agencia("afp", "client_secret", _CRED_AFP)
    assert (almacen.stat().st_mode & 0o777) == 0o600
    assert _CRED_AFP in almacen.read_text(encoding="utf-8")


def test_agencias_conviven_con_stock_e_imagen(almacen):
    """Escribir agencias NO debe descartar [imagen] ni [stock] (ni al revés)."""
    secretos.guardar_clave_imagen("openrouter", _CLAVE)
    secretos.guardar_clave_stock("pexels", _CLAVE_STOCK)
    secretos.guardar_credencial_agencia("afp", "client_id", "id-afp")
    secretos.guardar_credencial_agencia("reuters", "api_key", "key-reuters")
    # todo sigue presente tras los escritos cruzados
    assert secretos.obtener_clave_imagen() == _CLAVE
    assert secretos.obtener_clave_stock("pexels") == _CLAVE_STOCK
    assert secretos.obtener_credencial_agencia("afp", "client_id") == "id-afp"
    assert secretos.obtener_credencial_agencia("reuters", "api_key") == "key-reuters"
