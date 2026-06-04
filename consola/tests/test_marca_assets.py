"""Tests de los assets de marca (mocks sustituibles). Aisla el store en `tmp_path`.

Genera PNG mock con Pillow (real, ligero). NO toca red ni BD; el directorio del store se
aisla con `KENI_MARCA_ASSETS_DIR` para no escribir en la config del usuario.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from keni_consola import marca_assets


@pytest.fixture
def store(monkeypatch, tmp_path):
    """Aisla el store de assets de marca en `tmp_path`."""
    monkeypatch.setenv(marca_assets.ENV_ASSETS_DIR, str(tmp_path / "marca_assets"))
    return tmp_path / "marca_assets"


def test_genera_mock_cuando_no_hay_oficial(store):
    """Sin asset oficial, fabrica y cachea un PNG mock; devuelve su ruta."""
    ruta = marca_assets.ruta_asset("unotv", marca_assets.TIPO_LOGO)
    assert ruta
    p = Path(ruta)
    assert p.is_file()
    assert p.suffix == ".png"
    assert "mock" in p.name  # es el mock, no el oficial


def test_mock_se_cachea_y_no_se_regenera(store):
    """La segunda llamada reusa el mock cacheado (misma ruta, no lo re-fabrica)."""
    r1 = marca_assets.ruta_asset("claro-sports", marca_assets.TIPO_LOGO)
    mtime1 = Path(r1).stat().st_mtime_ns
    r2 = marca_assets.ruta_asset("claro-sports", marca_assets.TIPO_LOGO)
    assert r1 == r2
    assert Path(r2).stat().st_mtime_ns == mtime1  # no se reescribio


def test_oficial_gana_al_mock(store):
    """Si existe el PNG oficial, se devuelve ese y NO el mock (sustituible sin tocar codigo)."""
    oficial = marca_assets.ruta_oficial("unotv", marca_assets.TIPO_LOGO)
    oficial.parent.mkdir(parents=True, exist_ok=True)
    oficial.write_bytes(b"\x89PNG\r\n\x1a\n-falso-pero-existe")
    ruta = marca_assets.ruta_asset("unotv", marca_assets.TIPO_LOGO)
    assert ruta == str(oficial)
    assert marca_assets.tiene_oficial("unotv", marca_assets.TIPO_LOGO)


def test_tipos_soportados(store):
    """Logo, marca de agua y pleca generan cada uno su mock."""
    for tipo in marca_assets.TIPOS:
        ruta = marca_assets.ruta_asset("unotv", tipo)
        assert Path(ruta).is_file()


def test_tipo_desconocido_lanza(store):
    with pytest.raises(marca_assets.MarcaAssetError):
        marca_assets.ruta_asset("unotv", "billboard")


def test_no_fabricar_mock_devuelve_vacio_si_no_hay_oficial(store):
    """Con `fabricar_mock=False` y sin oficial, devuelve "" (degrada al wordmark del motor)."""
    assert marca_assets.ruta_asset("unotv", marca_assets.TIPO_LOGO, fabricar_mock=False) == ""


def test_marca_sin_identidad_visual_usa_color_generico(store):
    """Una marca del catalogo sin rojo propio (p.ej. nacion-gamer) genera mock igualmente."""
    ruta = marca_assets.ruta_asset("nacion-gamer", marca_assets.TIPO_LOGO)
    assert Path(ruta).is_file()
