"""Tests del paquete de cliente: marcas/cuentas externalizadas a configuracion (#135).

OBJETIVO: anadir un cliente nuevo = anadir/seleccionar un `.toml`, SIN tocar la capa
base. Estos tests verifican:
  1. El cliente POR DEFECTO carga las 5 marcas de siempre (no se rompe nada).
  2. Seleccionar OTRO cliente via env var cambia el catalogo y las cuentas, sin que
     cambie una sola linea de codigo de `marcas.py` / `cuentas.py`.
  3. Un fichero de cliente invalido se rechaza con un error de dominio claro.

Cambiar de cliente exige limpiar la cache de `cargar_cliente` y RECARGAR los modulos
`marcas`/`cuentas` (materializan su catalogo al importar). El fixture restaura todo.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from keni_shared import cliente as cliente_mod
from keni_shared import cuentas as cuentas_mod
from keni_shared import marcas as marcas_mod

CLIENTE_DEMO = Path(__file__).parent / "clientes" / "demo.toml"


def _recargar() -> None:
    """Recarga la cadena cliente -> marcas -> cuentas tras cambiar el cliente activo."""
    cliente_mod.cargar_cliente.cache_clear()
    importlib.reload(marcas_mod)
    importlib.reload(cuentas_mod)


@pytest.fixture
def restaurar_cliente_amx(monkeypatch):
    """Tras el test, vuelve al cliente por defecto y recarga los modulos.

    Borra las env vars de seleccion ANTES de recargar (el orden de teardown de
    `monkeypatch` no esta garantizado respecto a este finalizador), para que la
    recarga final materialice el cliente por defecto y no el del test.
    """
    yield
    monkeypatch.delenv("KENI_CLIENTE_CONFIG", raising=False)
    monkeypatch.delenv("KENI_CLIENTE", raising=False)
    _recargar()


def test_cliente_por_defecto_es_amx_con_las_5_marcas():
    cli = cliente_mod.cargar_cliente()
    assert cli.id == "amx"
    assert [m.id for m in marcas_mod.MARCAS] == [
        "unotv",
        "claro-sports",
        "nacion-gamer",
        "piso-15",
        "fundacion",
    ]
    assert cuentas_mod.CUENTA_DEPORTES_PRINCIPAL == "claro_sports"
    assert cuentas_mod.CUENTAS_DEPORTES_HERMANAS == ("claro_sports_tv", "csport_golf")


def test_seleccionar_otro_cliente_cambia_marcas_sin_tocar_codigo(
    monkeypatch, restaurar_cliente_amx
):
    # Anadir un cliente = apuntar la env var a un `.toml`. No se edita codigo.
    monkeypatch.setenv("KENI_CLIENTE_CONFIG", str(CLIENTE_DEMO))
    _recargar()

    # El catalogo de marcas cambio a las del cliente demo.
    assert marcas_mod.ids() == ["acme-news", "acme-sports"]
    assert marcas_mod.es_marca("acme-sports")
    assert not marcas_mod.es_marca("claro-sports")  # ya no es la del cliente por defecto
    assert marcas_mod.etiqueta_de("acme-news") == "ACME News"
    assert marcas_mod.id_metricas_de("acme-sports") == "acme_sports"
    assert dict(marcas_mod.opciones_metricas()) == {
        "acme_news": "ACME News",
        "acme_sports": "ACME Sports",
    }

    # Y las cuentas de deportes tambien.
    assert cuentas_mod.CUENTA_DEPORTES_PRINCIPAL == "acme_sports"
    assert cuentas_mod.CUENTAS_DEPORTES_HERMANAS == ("acme_sports_tv",)


def test_cliente_por_nombre_en_directorio_empaquetado(monkeypatch, restaurar_cliente_amx):
    # KENI_CLIENTE selecciona por NOMBRE dentro de `clientes/`; "amx" es el empaquetado.
    monkeypatch.setenv("KENI_CLIENTE", "amx")
    _recargar()
    assert cliente_mod.cargar_cliente().id == "amx"
    assert marcas_mod.es_marca("claro-sports")


def test_cliente_invalido_se_rechaza_con_error_de_dominio(monkeypatch, tmp_path):
    malo = tmp_path / "malo.toml"
    malo.write_text('id = "malo"\nnombre = "Malo"\n', encoding="utf-8")  # sin [[marca]]
    monkeypatch.setenv("KENI_CLIENTE_CONFIG", str(malo))
    cliente_mod.cargar_cliente.cache_clear()
    with pytest.raises(cliente_mod.ClienteInvalido):
        cliente_mod.cargar_cliente()
    # ClienteInvalido es un ValueError (error de dominio, sin traceback crudo).
    assert issubclass(cliente_mod.ClienteInvalido, ValueError)
    cliente_mod.cargar_cliente.cache_clear()


def test_cliente_inexistente_se_rechaza(monkeypatch):
    monkeypatch.setenv("KENI_CLIENTE", "no_existe_xyz")
    cliente_mod.cargar_cliente.cache_clear()
    with pytest.raises(cliente_mod.ClienteInvalido):
        cliente_mod.cargar_cliente()
    cliente_mod.cargar_cliente.cache_clear()
