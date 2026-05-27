from __future__ import annotations

import pytest

from keni_metricas.agregador import FuenteCompuesta
from keni_metricas.config import CuentaConfig
from keni_metricas.fuentes.base import CuentaNoEncontrada
from keni_metricas.presupuesto import Presupuesto
from keni_metricas.schema import MetricaPlataforma, Pieza, Plataforma


class AdaptadorFalso:
    """Adaptador en memoria para probar la agregacion sin red.

    `alcance` por defecto es None (la mayoria de plataformas no lo miden, #138);
    se puede fijar explicitamente para simular Meta (que si lo mide).
    """

    def __init__(self, plataforma: Plataforma, vis: int, inter: int, alcance: int | None = None):
        self.plataforma = plataforma
        self._vis = vis
        self._inter = inter
        self._alcance = alcance

    def disponible(self) -> bool:
        return True

    def metricas(self, handle, desde, hasta):
        return MetricaPlataforma(
            plataforma=self.plataforma,
            visualizaciones=self._vis,
            alcance=self._alcance,
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


def test_resumen_suma_solo_lo_comparable():
    """interacciones SE suma (homogenea); visualizaciones se suma como total
    informativo; pero el engagement global NO se divide sobre bases heterogeneas
    (FB impresiones + TikTok reproducciones): es None (#138)."""
    r = _fuente().resumen("marca", "semana")
    assert r.interacciones == 340  # 20 + 320: misma magnitud en ambas redes
    assert r.visualizaciones == 5000  # total informativo (no se usa como base)
    # con 2 plataformas de base heterogenea, el engagement global no es comparable
    assert r.engagement_pct is None
    assert r.fuente == "real"
    assert {m.plataforma for m in r.por_plataforma} == {Plataforma.facebook, Plataforma.tiktok}


def test_engagement_una_sola_plataforma_si_se_calcula():
    """Con una unica plataforma, la base es homogenea: el engagement SI se calcula."""
    cuenta = CuentaConfig(id="m", nombre="M", plataformas={Plataforma.tiktok: "h"})
    fuente = FuenteCompuesta(
        [cuenta], {Plataforma.tiktok: AdaptadorFalso(Plataforma.tiktok, 4000, 320)}
    )
    r = fuente.resumen("m", "semana")
    assert r.engagement_pct == 8.0  # 320/4000*100, base homogenea


def test_alcance_no_disponible_es_none_no_cero():
    """Las plataformas que no miden alcance lo reportan None (AUSENTE), nunca 0.
    El agregado suma SOLO las que lo miden; un 0 falso hundiria el total (#138)."""
    cuenta = CuentaConfig(
        id="m",
        nombre="M",
        plataformas={Plataforma.facebook: "h1", Plataforma.tiktok: "h2"},
    )
    fuente = FuenteCompuesta(
        [cuenta],
        {
            # Meta mide alcance (700); TikTok no lo mide (None, no 0).
            Plataforma.facebook: AdaptadorFalso(Plataforma.facebook, 1000, 20, alcance=700),
            Plataforma.tiktok: AdaptadorFalso(Plataforma.tiktok, 4000, 320),
        },
    )
    r = fuente.resumen("m", "semana")
    # el alcance agregado es SOLO el de Meta; TikTok (None) queda excluido, no suma 0
    assert r.alcance == 700
    por_plat = {m.plataforma: m.alcance for m in r.por_plataforma}
    assert por_plat[Plataforma.facebook] == 700
    assert por_plat[Plataforma.tiktok] is None  # AUSENTE, no 0


def test_alcance_es_none_si_ninguna_plataforma_lo_mide():
    """Si NINGUNA plataforma mide alcance, el agregado es None (ausencia), no 0."""
    cuenta = CuentaConfig(
        id="m",
        nombre="M",
        plataformas={Plataforma.youtube: "h1", Plataforma.tiktok: "h2"},
    )
    fuente = FuenteCompuesta(
        [cuenta],
        {
            Plataforma.youtube: AdaptadorFalso(Plataforma.youtube, 2000, 100),
            Plataforma.tiktok: AdaptadorFalso(Plataforma.tiktok, 4000, 320),
        },
    )
    r = fuente.resumen("m", "semana")
    assert r.alcance is None  # ni YouTube ni TikTok miden alcance: AUSENTE, no 0


def test_visualizaciones_no_es_base_del_engagement_global():
    """Aunque visualizaciones se sume como total, NO se usa como denominador del
    engagement global cuando hay >1 plataforma (no se divide sobre bases mixtas)."""
    r = _fuente().resumen("marca", "semana")
    # si se dividiera (mal) sobre el total seria 340/5000*100 = 6.8; ahora es None
    assert r.engagement_pct is None
    assert r.engagement_pct != 6.8


def test_mejores_piezas_ordena_entre_plataformas():
    piezas = _fuente().mejores_piezas("marca", "semana", 2)
    assert [p.plataforma for p in piezas] == [Plataforma.tiktok, Plataforma.facebook]  # 8% > 2%


def test_cuentas_solo_plataformas_con_adaptador():
    cuentas = _fuente().cuentas()
    assert cuentas[0].plataformas == [Plataforma.facebook, Plataforma.tiktok]


# --- multi-marca ------------------------------------------------------------
def _fuente_multi_marca() -> FuenteCompuesta:
    """Dos marcas que comparten un mismo set de adaptadores."""
    marca_a = CuentaConfig(
        id="marca_a",
        nombre="Marca A",
        plataformas={Plataforma.facebook: "a_fb", Plataforma.tiktok: "a_tk"},
    )
    marca_b = CuentaConfig(
        id="marca_b",
        nombre="Marca B",
        plataformas={Plataforma.facebook: "b_fb"},
    )
    adaptadores = {
        Plataforma.facebook: AdaptadorFalso(Plataforma.facebook, 1000, 20),
        Plataforma.tiktok: AdaptadorFalso(Plataforma.tiktok, 4000, 320),
    }
    return FuenteCompuesta([marca_a, marca_b], adaptadores)


def test_multi_marca_cada_cuenta_se_resuelve_independiente():
    fuente = _fuente_multi_marca()
    # cada marca aparece con sus propias plataformas
    cuentas = {c.id: c for c in fuente.cuentas()}
    assert set(cuentas) == {"marca_a", "marca_b"}
    assert cuentas["marca_a"].plataformas == [Plataforma.facebook, Plataforma.tiktok]
    assert cuentas["marca_b"].plataformas == [Plataforma.facebook]

    # marca_a agrega fb+tiktok; marca_b solo fb
    ra = fuente.resumen("marca_a", "semana")
    rb = fuente.resumen("marca_b", "semana")
    assert ra.visualizaciones == 5000
    assert rb.visualizaciones == 1000
    assert {m.plataforma for m in ra.por_plataforma} == {Plataforma.facebook, Plataforma.tiktok}
    assert [m.plataforma for m in rb.por_plataforma] == [Plataforma.facebook]
    # ambas con cobertura completa (todas las plataformas tienen adaptador)
    assert ra.cobertura.completa and rb.cobertura.completa


def test_multi_marca_presupuesto_es_global_entre_cuentas():
    """El Presupuesto se comparte entre cuentas: agotarlo en una omite en la otra."""
    # 1 sola operacion de facebook permitida en toda la ejecucion
    presupuesto = Presupuesto(caps={Plataforma.facebook: 1, Plataforma.tiktok: 10})
    fuente = FuenteCompuesta(
        [
            CuentaConfig(id="m1", nombre="M1", plataformas={Plataforma.facebook: "h"}),
            CuentaConfig(id="m2", nombre="M2", plataformas={Plataforma.facebook: "h"}),
        ],
        {Plataforma.facebook: AdaptadorFalso(Plataforma.facebook, 1000, 20)},
        presupuesto,
    )
    r1 = fuente.resumen("m1", "semana")
    r2 = fuente.resumen("m2", "semana")
    # la primera consume la unica unidad de facebook; la segunda se omite
    assert r1.cobertura.completa
    assert Plataforma.facebook in r2.cobertura.omitidas


# --- cuenta inexistente -----------------------------------------------------
def test_buscar_cuenta_inexistente_lista_disponibles():
    fuente = _fuente_multi_marca()
    with pytest.raises(CuentaNoEncontrada) as exc:
        fuente.resumen("no_existe", "semana")
    # el mensaje enumera las cuentas que SI existen (sin afirmar el texto exacto)
    msg = str(exc.value)
    assert "marca_a" in msg and "marca_b" in msg

    with pytest.raises(CuentaNoEncontrada):
        fuente.mejores_piezas("no_existe", "semana", 3)


def test_buscar_sin_cuentas_configuradas():
    fuente = FuenteCompuesta([], {})
    with pytest.raises(CuentaNoEncontrada):
        fuente.resumen("cualquiera", "semana")


# --- mejores_piezas con omisiones -------------------------------------------
def test_mejores_piezas_omite_plataforma_sin_adaptador():
    """Una plataforma configurada sin adaptador no aporta piezas (se salta)."""
    cuenta = CuentaConfig(
        id="marca",
        nombre="Marca",
        plataformas={Plataforma.facebook: "h1", Plataforma.tiktok: "h2"},
    )
    # solo facebook tiene adaptador; tiktok no
    fuente = FuenteCompuesta(
        [cuenta], {Plataforma.facebook: AdaptadorFalso(Plataforma.facebook, 1000, 20)}
    )
    piezas = fuente.mejores_piezas("marca", "semana", 5)
    assert [p.plataforma for p in piezas] == [Plataforma.facebook]


def test_mejores_piezas_omite_plataforma_sin_presupuesto():
    cuenta = CuentaConfig(
        id="marca",
        nombre="Marca",
        plataformas={Plataforma.facebook: "h1", Plataforma.tiktok: "h2"},
    )
    presupuesto = Presupuesto(caps={Plataforma.tiktok: 0})  # tiktok agotada
    fuente = FuenteCompuesta(
        [cuenta],
        {
            Plataforma.facebook: AdaptadorFalso(Plataforma.facebook, 1000, 20),
            Plataforma.tiktok: AdaptadorFalso(Plataforma.tiktok, 4000, 320),
        },
        presupuesto,
    )
    piezas = fuente.mejores_piezas("marca", "semana", 5)
    assert [p.plataforma for p in piezas] == [Plataforma.facebook]  # tiktok omitida


def test_mejores_piezas_recorta_a_n():
    """Aunque haya mas piezas que n, devuelve como mucho n (ordenadas)."""
    piezas = _fuente().mejores_piezas("marca", "semana", 1)
    assert len(piezas) == 1
    assert piezas[0].plataforma is Plataforma.tiktok  # mayor engagement
