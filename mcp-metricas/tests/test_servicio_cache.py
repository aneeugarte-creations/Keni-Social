"""Cache de config + fuente/cliente httpx en `servicio`/`config` (fix N+1 por pieza).

El tablero pide rendimiento pieza-a-pieza: antes cada llamada re-leía el config del
disco y construía una `FuenteMetricol` NUEVA (con su propio `httpx.Client`), abriendo
docenas de conexiones y quemando cuota. Aquí se verifica que:

  - `cargar_config()` se memoiza (no re-parsea el TOML si no cambia mtime/env).
  - `servicio._fuente()` reusa la MISMA fuente base (y su cliente httpx) entre llamadas.
  - un cambio en el config (mtime distinto, p.ej. token nuevo) invalida ambas caches y
    se refleja SIN reiniciar el proceso.

TODO OFFLINE: construir una `FuenteMetricol` no toca la red (solo guarda credenciales y
un `httpx.Client` ocioso); nunca hacemos una petición.
"""

from __future__ import annotations

import time

import pytest

from keni_metricas import config as _config
from keni_metricas import servicio


CONFIG_BASE = """\
fuente = "metricool"

[metricool.marcas.claro_sports]
user_token = "{token}"
user_id = "u-1"
blog_id = "b-1"
nombre = "Claro Sports"
"""


@pytest.fixture
def cfg_metricool(monkeypatch, tmp_path):
    """Config metricool en disco, con caches limpias y env de marcas desactivada."""
    ruta = tmp_path / "config.toml"
    ruta.write_text(CONFIG_BASE.format(token="tok-A"), encoding="utf-8")
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(ruta))
    monkeypatch.delenv("KENI_METRICAS_FUENTE", raising=False)
    monkeypatch.delenv("KENI_METRICAS_MARCAS", raising=False)
    monkeypatch.delenv("METRICOOL_USER_TOKEN", raising=False)
    monkeypatch.delenv("METRICOOL_USER_ID", raising=False)
    _config.reset_cache_config()
    servicio.reset_cache_fuente()
    yield ruta
    _config.reset_cache_config()
    servicio.reset_cache_fuente()


def _reescribir(ruta, token: str) -> None:
    """Reescribe el config con otro token y FUERZA un mtime distinto (granularidad)."""
    ruta.write_text(CONFIG_BASE.format(token=token), encoding="utf-8")
    # Empuja el mtime claramente al futuro para no depender de la resolución del FS.
    futuro = time.time() + 5
    import os

    os.utime(ruta, (futuro, futuro))


def test_cargar_config_memoiza_misma_instancia(cfg_metricool):
    a = _config.cargar_config()
    b = _config.cargar_config()
    # Sin cambios en disco/env: la MISMA instancia (no se re-parsea el TOML).
    assert a is b


def test_fuente_reusa_misma_base_y_cliente(cfg_metricool):
    f1 = servicio._fuente_base()
    f2 = servicio._fuente_base()
    assert f1 is f2, "la fuente base debe reusarse entre llamadas"
    # Mismo httpx.Client subyacente (keep-alive / pooling), no uno nuevo por pieza.
    assert getattr(f1, "_cli") is getattr(f2, "_cli")


def test_fuente_scoped_comparte_base(cfg_metricool):
    base = servicio._fuente_base()
    scoped = servicio._fuente("claro_sports")
    # El acotado por marca envuelve la base cacheada (no construye otra fuente/cliente).
    assert scoped._fuente is base


def test_cambio_de_token_invalida_caches(cfg_metricool):
    ruta = cfg_metricool
    cfg_antes = _config.cargar_config()
    fuente_antes = servicio._fuente_base()
    cli_antes = fuente_antes._cli
    assert cfg_antes.metricool.marcas["claro_sports"]["user_token"] == "tok-A"

    _reescribir(ruta, "tok-B")

    cfg_despues = _config.cargar_config()
    fuente_despues = servicio._fuente_base()
    # El mtime cambió: ambas caches se invalidan y reflejan el token nuevo.
    assert cfg_despues is not cfg_antes
    assert cfg_despues.metricool.marcas["claro_sports"]["user_token"] == "tok-B"
    assert fuente_despues is not fuente_antes, "fuente debe reconstruirse tras cambio"
    assert fuente_despues._cli is not cli_antes, "cliente nuevo tras cambio de config"


def test_reset_explicito_reconstruye(cfg_metricool):
    f1 = servicio._fuente_base()
    servicio.reset_cache_fuente()
    f2 = servicio._fuente_base()
    assert f1 is not f2
