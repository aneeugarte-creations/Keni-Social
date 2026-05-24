from __future__ import annotations

from keni_metricas.agregador import FuenteCompuesta
from keni_metricas.config import cargar_config, construir_fuente
from keni_metricas.fuentes.muestra import FuenteMuestra


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
