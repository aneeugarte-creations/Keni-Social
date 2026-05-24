from __future__ import annotations

import pytest

from keni_metricas.agregador import FuenteCompuesta
from keni_metricas.config import CuentaConfig
from keni_metricas.presupuesto import Presupuesto, PresupuestoExcedido
from keni_metricas.schema import MetricaPlataforma, Plataforma


def test_consumir_agota_y_lanza():
    p = Presupuesto(caps={Plataforma.x: 2})
    p.consumir(Plataforma.x)
    p.consumir(Plataforma.x)
    assert p.restantes(Plataforma.x) == 0
    with pytest.raises(PresupuestoExcedido):
        p.consumir(Plataforma.x)


def test_env_override(monkeypatch):
    monkeypatch.setenv("KENI_PRESUPUESTO_YOUTUBE", "1")
    p = Presupuesto()
    p.consumir(Plataforma.youtube)
    with pytest.raises(PresupuestoExcedido):
        p.consumir(Plataforma.youtube)


def test_reiniciar():
    p = Presupuesto(caps={Plataforma.tiktok: 1})
    p.consumir(Plataforma.tiktok)
    p.reiniciar()
    p.consumir(Plataforma.tiktok)  # tras reiniciar vuelve a haber cupo
    assert p.uso() == {"tiktok": 1}


class _Fake:
    def __init__(self, plat: Plataforma):
        self.plataforma = plat

    def disponible(self) -> bool:
        return True

    def metricas(self, h, d, ha):
        return MetricaPlataforma(
            plataforma=self.plataforma, visualizaciones=100, alcance=70, interacciones=5, engagement_pct=5.0
        )

    def piezas(self, h, d, ha, n):
        return []


def test_agregador_omite_plataforma_sin_presupuesto():
    cuenta = CuentaConfig(
        id="m", nombre="M", plataformas={Plataforma.facebook: "h", Plataforma.tiktok: "h2"}
    )
    fuente = FuenteCompuesta(
        [cuenta],
        {Plataforma.facebook: _Fake(Plataforma.facebook), Plataforma.tiktok: _Fake(Plataforma.tiktok)},
        Presupuesto(caps={Plataforma.facebook: 0}),  # Facebook sin cupo
    )
    plats = {m.plataforma for m in fuente.resumen("m", "semana").por_plataforma}
    assert Plataforma.facebook not in plats
    assert Plataforma.tiktok in plats
