"""Tests del análisis multi-dimensión del periodo.

Cubre los criterios de aceptación:
  - emite HALLAZGOS jerarquizados que cubren dimensiones DISTINTAS (vistas, red, formato,
    seguidores, engagement, pieza, periodo), ≥5 cuando el periodo da para ello;
  - la lectura difiere estructuralmente entre semana y mes (dimensión "periodo");
  - la variación de seguidores REPRESENTATIVA (señal) se distingue del ruido diario;
  - cierra con una sugerencia accionable (loop a la acción);
  - marca explícitamente cuando los datos son de muestra (no reales);
  - degrada con honestidad cuando no hay datos.
"""

from __future__ import annotations

from datetime import date

import pytest

from keni_metricas.analisis_diario import (
    HALLAZGOS_OBJETIVO,
    _hallazgo_seguidores,
    _senal_seguidores,
    construir_analisis,
    render_markdown,
)
from keni_metricas.fuentes.muestra import FuenteMuestra
from keni_metricas.historico import Historico
from keni_metricas.schema import Cuenta, Periodo, Pieza, Plataforma, ResumenMetricas

# --------------------------------------------------------------------------- #
# Dobles de fuente: control total de variación/piezas para los casos límite.   #
# --------------------------------------------------------------------------- #


class _FuenteVacia:
    """Fuente real sin cuentas: el caso 'sin datos' (no es muestra)."""

    nombre = "real"

    def cuentas(self) -> list[Cuenta]:
        return []

    def resumen(self, cuenta_id: str, rango: str) -> ResumenMetricas:  # pragma: no cover
        raise AssertionError("no debería pedirse el resumen de una fuente vacía")

    def mejores_piezas(self, cuenta_id: str, rango: str, n: int) -> list[Pieza]:
        return []


class _FuenteEstable:
    """Fuente real con UNA cuenta cuya variación está por debajo del umbral."""

    nombre = "real"

    def cuentas(self) -> list[Cuenta]:
        return [Cuenta(id="marca_a", nombre="Marca A", plataformas=[Plataforma.tiktok])]

    def resumen(self, cuenta_id: str, rango: str) -> ResumenMetricas:
        return ResumenMetricas(
            cuenta=cuenta_id,
            rango=rango,
            periodo=Periodo(desde=date(2026, 5, 20), hasta=date(2026, 5, 26)),
            visualizaciones=1000,
            alcance=None,
            interacciones=50,
            engagement_pct=5.0,
            seguidores_netos=0,
            variacion_vs_anterior={"visualizaciones_pct": 1.0},  # < umbral (5%)
            por_plataforma=[],
            fuente="real",
        )

    def mejores_piezas(self, cuenta_id: str, rango: str, n: int) -> list[Pieza]:
        return [
            Pieza(
                id="p1",
                plataforma=Plataforma.tiktok,
                titulo="Pieza estable",
                publicado=date(2026, 5, 25),
                visualizaciones=500,
                interacciones=30,
                engagement_pct=6.0,
                formato="reel",
            )
        ]


def _dimensiones(analisis: dict) -> set[str]:
    return {h["dimension"] for h in analisis["hallazgos"]}


# --------------------------------------------------------------------------- #
# Criterio 1: hallazgos multi-dimensión, jerarquizados, ≥5 cuando hay datos.   #
# --------------------------------------------------------------------------- #


def test_emite_hallazgos_multidimension():
    a = construir_analisis(FuenteMuestra(), "semana")
    assert a["hallazgos"], "la muestra debería producir hallazgos"
    # Al menos el objetivo de riqueza (petición de Mariana: ≥5 bullets específicos).
    assert len(a["hallazgos"]) >= HALLAZGOS_OBJETIVO
    dims = _dimensiones(a)
    # Cubre dimensiones DISTINTAS (no se centra en un solo dato).
    assert {"vistas", "red", "engagement"} <= dims
    assert len(dims) >= 3


def test_hallazgos_vistas_ordenados_por_magnitud_descendente():
    a = construir_analisis(FuenteMuestra(), "semana")
    vistas = [
        h for h in a["hallazgos"] if h["dimension"] == "vistas" and h["texto"].endswith("engagement.")
    ]
    # Los movimientos de vistas con variación se listan de mayor a menor cambio; el primero es
    # el más llamativo (aparece antes que cualquier otro hallazgo).
    assert a["hallazgos"][0]["dimension"] == "vistas"
    assert vistas, "debería haber movimientos de vistas narrados"


def test_cada_hallazgo_lleva_dimension_direccion_texto():
    a = construir_analisis(FuenteMuestra(), "semana")
    for h in a["hallazgos"]:
        assert h["dimension"]
        assert h["direccion"] in {"sube", "baja", "estable"}
        assert h["texto"]


# --------------------------------------------------------------------------- #
# Criterio 2: la lectura difiere estructuralmente entre semana y mes.          #
# --------------------------------------------------------------------------- #


def test_periodo_semana_narra_dia_mas_fuerte_y_flojo():
    serie = {
        "puntos": [
            {"fecha": "2026-06-01", "visualizaciones": 100, "interacciones": 5},
            {"fecha": "2026-06-02", "visualizaciones": 900, "interacciones": 40},
            {"fecha": "2026-06-03", "visualizaciones": 300, "interacciones": 12},
        ]
    }
    a = construir_analisis(_FuenteEstable(), "semana", serie_diaria=serie)
    periodo = [h for h in a["hallazgos"] if h["dimension"] == "periodo"]
    assert periodo, "la semana debe narrar el día más fuerte/flojo"
    assert "día más fuerte de la semana" in periodo[0]["texto"]
    assert "2-jun" in periodo[0]["texto"]  # el día de más vistas


def test_periodo_mes_narra_tendencia_intra_mes():
    # Primera mitad floja, segunda fuerte: tendencia "de menos a más".
    puntos = [{"fecha": f"2026-06-{d:02d}", "visualizaciones": 100, "interacciones": 5} for d in range(1, 11)]
    puntos += [{"fecha": f"2026-06-{d:02d}", "visualizaciones": 400, "interacciones": 20} for d in range(11, 21)]
    a = construir_analisis(_FuenteEstable(), "mes", serie_diaria={"puntos": puntos})
    periodo = [h for h in a["hallazgos"] if h["dimension"] == "periodo"]
    assert periodo, "el mes debe narrar la tendencia intra-mes"
    assert "segunda mitad" in periodo[0]["texto"]
    assert periodo[0]["direccion"] == "sube"


# --------------------------------------------------------------------------- #
# Criterio 3: variación de seguidores REPRESENTATIVA (señal vs. ruido).        #
# --------------------------------------------------------------------------- #


def test_senal_seguidores_detecta_desplome_representativo():
    # Ritmo habitual ~+200/día, con un desplome de -12 400 el 15-jun.
    puntos = [
        {"fecha": "2026-06-12", "total": 100000, "por_red": {"instagram": 60000, "tiktok": 40000}},
        {"fecha": "2026-06-13", "total": 100200, "por_red": {"instagram": 60200, "tiktok": 40000}},
        {"fecha": "2026-06-14", "total": 100400, "por_red": {"instagram": 60400, "tiktok": 40000}},
        {"fecha": "2026-06-15", "total": 88000, "por_red": {"instagram": 48000, "tiktok": 40000}},
        {"fecha": "2026-06-16", "total": 88200, "por_red": {"instagram": 48200, "tiktok": 40000}},
    ]
    señal = _senal_seguidores(puntos)
    assert señal is not None
    fecha, red, delta = señal
    assert fecha == "2026-06-15"
    assert red == "instagram"  # la red que más aportó al desplome
    assert delta < -10000
    h = _hallazgo_seguidores({"puntos": puntos, "neto": -11800})
    assert "15-jun" in h["texto"]
    assert "Instagram" in h["texto"]
    assert "muy por encima del ritmo" in h["texto"]
    assert h["direccion"] == "baja"


def test_seguidores_sin_senal_narra_neto_sereno():
    # Ritmo parejo: ningún día se sale del habitual → sin señal, solo el neto.
    puntos = [
        {"fecha": f"2026-06-{d:02d}", "total": 100000 + (d - 2) * 200, "por_red": {"instagram": 100000 + (d - 2) * 200}}
        for d in range(2, 9)
    ]
    assert _senal_seguidores(puntos) is None
    h = _hallazgo_seguidores({"puntos": puntos, "neto": 1200})
    assert "neto de 1.200 seguidores" in h["texto"]
    assert "dentro del ritmo habitual" in h["texto"]


def test_seguidores_sin_serie_no_emite_hallazgo():
    assert _hallazgo_seguidores(None) is None
    assert _hallazgo_seguidores({"puntos": [], "neto": 0}) is not None  # neto=0 sí informa


# --------------------------------------------------------------------------- #
# Criterio 4: cierra con una sugerencia accionable (loop a la acción).         #
# --------------------------------------------------------------------------- #


def test_cierra_con_siguiente_paso_accionable():
    a = construir_analisis(FuenteMuestra(), "semana")
    paso = a["siguiente_paso"]
    assert paso is not None
    assert paso["marca"]
    assert "Pídele a Claude" in paso["texto"]
    assert "lo decides tú" in paso["texto"].lower()


def test_render_markdown_incluye_hallazgos_y_siguiente_paso():
    md = render_markdown(construir_analisis(FuenteMuestra(), "semana"))
    assert md.startswith("## Análisis del periodo — semana")
    assert "**Lo que pasó:**" in md
    assert "**Siguiente paso:**" in md


# --------------------------------------------------------------------------- #
# Criterio 5: marca explícitamente cuando los datos son de muestra.            #
# --------------------------------------------------------------------------- #


def test_muestra_marcada_en_estructura():
    a = construir_analisis(FuenteMuestra(), "semana")
    assert a["es_muestra"] is True
    assert a["fuente"] == "muestra"
    assert "aviso" in a


def test_muestra_marcada_en_markdown():
    md = render_markdown(construir_analisis(FuenteMuestra(), "semana"))
    assert "DATOS DE MUESTRA" in md


def test_fuente_real_no_marca_muestra():
    a = construir_analisis(_FuenteEstable(), "semana")
    assert a["es_muestra"] is False
    assert "aviso" not in a
    md = render_markdown(a)
    assert "DATOS DE MUESTRA" not in md


# --------------------------------------------------------------------------- #
# Degradación honesta.                                                         #
# --------------------------------------------------------------------------- #


def test_sin_datos_degrada_honestamente():
    a = construir_analisis(_FuenteVacia(), "semana")
    assert a["hallazgos"] == []
    assert a["siguiente_paso"] is None
    md = render_markdown(a)
    assert "Sin datos suficientes" in md
    assert "**Siguiente paso:**" not in md


def test_marca_estable_se_narra_como_estabilidad_no_se_calla():
    a = construir_analisis(_FuenteEstable(), "semana")
    # 1% < umbral 5%: no es un movimiento fuerte, pero SÍ se informa (estabilidad honesta).
    vistas = [h for h in a["hallazgos"] if h["dimension"] == "vistas"]
    assert vistas, "una marca estable debe seguir generando un hallazgo de vistas"
    assert "estable" in vistas[0]["texto"].lower()


def test_rango_invalido_propaga_valueerror():
    with pytest.raises(ValueError):
        construir_analisis(FuenteMuestra(), "trimestre")


# --------------------------------------------------------------------------- #
# Variación REAL desde el histórico (no solo el modelo de la muestra).         #
# --------------------------------------------------------------------------- #


def test_usa_variacion_real_del_historico(tmp_path):
    """Con histórico previo, la variación del movimiento de vistas es la REAL."""
    h = Historico(tmp_path / "h.db")
    h.guardar(
        ResumenMetricas(
            cuenta="claro_sports",
            rango="semana",
            periodo=Periodo(desde=date(2020, 1, 1), hasta=date(2020, 1, 7)),
            visualizaciones=1000,
            alcance=700,
            interacciones=40,
            engagement_pct=4.0,
            seguidores_netos=0,
            por_plataforma=[],
            fuente="muestra",
        )
    )
    a = construir_analisis(FuenteMuestra(), "semana", historico=h)
    # La muestra de claro_sports ronda millones de vistas vs. baseline 1000: aparece un
    # movimiento de vistas al alza enorme entre los hallazgos.
    vistas = [h for h in a["hallazgos"] if h["dimension"] == "vistas"]
    assert any("Claro Sports" in x["texto"] and "subió" in x["texto"] for x in vistas)
