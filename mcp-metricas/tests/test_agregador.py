from __future__ import annotations

from keni_metricas.agregador import FuenteCompuesta
from keni_metricas.config import CuentaConfig
from keni_metricas.schema import MetricaPlataforma, Pieza, Plataforma


class AdaptadorFalso:
    """Adaptador en memoria para probar la agregacion sin red."""

    def __init__(self, plataforma: Plataforma, vis: int, inter: int):
        self.plataforma = plataforma
        self._vis = vis
        self._inter = inter

    def disponible(self) -> bool:
        return True

    def metricas(self, handle, desde, hasta):
        return MetricaPlataforma(
            plataforma=self.plataforma,
            visualizaciones=self._vis,
            alcance=int(self._vis * 0.7),
            interacciones=self._inter,
            engagement_pct=round(self._inter / self._vis * 100, 1),
        )

    def piezas(self, handle, desde, hasta, n):
        return [
            Pieza(
                id=f"{self.plataforma.value}-1",
                plataforma=self.plataforma,
                titulo="pieza",
                publicado=hasta,
                visualizaciones=self._vis,
                interacciones=self._inter,
                engagement_pct=round(self._inter / self._vis * 100, 1),
            )
        ]


def _fuente() -> FuenteCompuesta:
    cuenta = CuentaConfig(
        id="marca",
        nombre="Marca",
        plataformas={Plataforma.facebook: "h1", Plataforma.tiktok: "h2"},
    )
    adaptadores = {
        Plataforma.facebook: AdaptadorFalso(Plataforma.facebook, 1000, 20),
        Plataforma.tiktok: AdaptadorFalso(Plataforma.tiktok, 4000, 320),
    }
    return FuenteCompuesta([cuenta], adaptadores)


def test_resumen_suma_plataformas():
    r = _fuente().resumen("marca", "semana")
    assert r.visualizaciones == 5000
    assert r.interacciones == 340
    assert r.engagement_pct == 6.8  # 340/5000*100
    assert r.fuente == "real"
    assert {m.plataforma for m in r.por_plataforma} == {Plataforma.facebook, Plataforma.tiktok}


def test_mejores_piezas_ordena_entre_plataformas():
    piezas = _fuente().mejores_piezas("marca", "semana", 2)
    assert [p.plataforma for p in piezas] == [Plataforma.tiktok, Plataforma.facebook]  # 8% > 2%


def test_cuentas_solo_plataformas_con_adaptador():
    cuentas = _fuente().cuentas()
    assert cuentas[0].plataformas == [Plataforma.facebook, Plataforma.tiktok]
