from __future__ import annotations

import pytest

from keni_metricas.agregador import FuenteCompuesta
from keni_metricas.config import ConfigInvalida, cargar_config, construir_fuente
from keni_metricas.fuentes.muestra import FuenteMuestra


def _escribir_config(monkeypatch, tmp_path, contenido: str):
    """Escribe un config.toml temporal y lo apunta via env, aislando las env vars."""
    monkeypatch.delenv("KENI_METRICAS_FUENTE", raising=False)
    monkeypatch.delenv("KENI_METRICAS_MARCAS", raising=False)
    ruta = tmp_path / "config.toml"
    ruta.write_text(contenido, encoding="utf-8")
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(ruta))
    return ruta


def test_default_es_muestra(monkeypatch, tmp_path):
    monkeypatch.delenv("KENI_METRICAS_FUENTE", raising=False)
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(tmp_path / "noexiste.toml"))
    fuente = construir_fuente(cargar_config())
    assert isinstance(fuente, FuenteMuestra)
    assert fuente.nombre == "muestra"


def test_fuente_real_por_env(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_METRICAS_FUENTE", "real")
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(tmp_path / "noexiste.toml"))
    fuente = construir_fuente(cargar_config())
    assert isinstance(fuente, FuenteCompuesta)
    assert fuente.nombre == "real"


# --- B1: TOML mal formado -> ConfigInvalida en espanol, sin traceback tomllib --
def test_b1_toml_mal_formado_lanza_config_invalida(monkeypatch, tmp_path):
    ruta = _escribir_config(monkeypatch, tmp_path, 'fuente = "muestra"\n[[cuenta]\nid = "x"\n')
    with pytest.raises(ConfigInvalida) as exc:
        cargar_config()
    msg = str(exc.value)
    # mensaje en espanol, con la ruta y (en 3.11+) la linea del fallo
    assert "error de sintaxis TOML" in msg
    assert str(ruta) in msg
    assert "linea 2" in msg
    # es capturable como ValueError (contrato para los CLIs y el doctor)
    assert isinstance(exc.value, ValueError)


# --- B4: cuenta sin nombre / plataforma invalida -> ConfigInvalida que cuenta ---
def test_b4_cuenta_sin_nombre(monkeypatch, tmp_path):
    _escribir_config(monkeypatch, tmp_path, '[[cuenta]]\nid = "amx"\n')
    with pytest.raises(ConfigInvalida) as exc:
        cargar_config()
    msg = str(exc.value)
    assert "nombre" in msg
    assert "amx" in msg  # identifica QUE cuenta falla


def test_b4_cuenta_sin_id(monkeypatch, tmp_path):
    _escribir_config(monkeypatch, tmp_path, '[[cuenta]]\nnombre = "AMX"\n')
    with pytest.raises(ConfigInvalida, match="id"):
        cargar_config()


def test_b4_plataforma_invalida(monkeypatch, tmp_path):
    _escribir_config(
        monkeypatch,
        tmp_path,
        '[[cuenta]]\nid = "amx"\nnombre = "AMX"\n'
        '[cuenta.plataformas]\nmyspace = "@amx"\n',
    )
    with pytest.raises(ConfigInvalida) as exc:
        cargar_config()
    msg = str(exc.value)
    assert "myspace" in msg  # nombra la plataforma invalida
    assert "facebook" in msg and "instagram" in msg  # lista las validas


def test_b4_cuenta_valida_se_carga(monkeypatch, tmp_path):
    _escribir_config(
        monkeypatch,
        tmp_path,
        '[[cuenta]]\nid = "amx"\nnombre = "AMX"\n'
        '[cuenta.plataformas]\ninstagram = "@amx"\n',
    )
    cfg = cargar_config()
    assert len(cfg.cuentas) == 1
    assert cfg.cuentas[0].nombre == "AMX"


# --- B5: fuente desconocida -> ConfigInvalida listando las validas -------------
def test_b5_fuente_desconocida_lanza_config_invalida(monkeypatch, tmp_path):
    _escribir_config(monkeypatch, tmp_path, 'fuente = "magia"\n')
    with pytest.raises(ConfigInvalida) as exc:
        cargar_config()
    msg = str(exc.value)
    assert "magia" in msg
    assert "muestra" in msg and "real" in msg  # lista los valores validos


def test_b5_fuente_invalida_por_env(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(tmp_path / "noexiste.toml"))
    monkeypatch.setenv("KENI_METRICAS_FUENTE", "ninguna")
    with pytest.raises(ConfigInvalida, match="muestra, real"):
        cargar_config()
