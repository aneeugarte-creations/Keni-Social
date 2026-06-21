"""Tests del análisis diario con narrativa.

Cubre los tres criterios de aceptación del análisis diario:
  - resume top movimientos del periodo con la(s) pieza(s) que los explican;
  - cierra con una sugerencia accionable (loop a la acción);
  - marca explícitamente cuando los datos son de muestra (no reales).
Más la degradación honesta cuando no hay datos / la fuente es real.
"""

from __future__ import annotations

from datetime import date

import pytest

from keni_metricas.analisis_diario import (
    MAX_MOVIMIENTOS,
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
            )
        ]


# --------------------------------------------------------------------------- #
# Criterio 1: resume top movimientos con la(s) pieza(s) que los explican.      #
# --------------------------------------------------------------------------- #


def test_resume_movimientos_con_pieza_que_los_explica():
    a = construir_analisis(FuenteMuestra(), "semana")
    assert a["movimientos"], "la muestra debería tener movimientos por encima del umbral"
    assert len(a["movimientos"]) <= MAX_MOVIMIENTOS
    primero = a["movimientos"][0]
    # Cada movimiento trae dirección, variación y la pieza estrella que lo acompaña.
    assert primero["direccion"] in {"sube", "baja", "estable"}
    assert "variacion_vis_pct" in primero
    assert primero["pieza"] is not None
    assert primero["pieza"]["titulo"]


def test_movimientos_ordenados_por_magnitud_descendente():
    a = construir_analisis(FuenteMuestra(), "semana")
    magnitudes = [abs(m["variacion_vis_pct"]) for m in a["movimientos"]]
    assert magnitudes == sorted(magnitudes, reverse=True)


def test_render_markdown_lista_movimientos_y_piezas():
    md = render_markdown(construir_analisis(FuenteMuestra(), "semana"))
    assert md.startswith("## Análisis del periodo — semana")
    assert "**Lo que se movió:**" in md
    assert "Lo explica" in md  # la pieza que explica el movimiento


# --------------------------------------------------------------------------- #
# Criterio 2: cierra con una sugerencia accionable (loop a la acción).         #
# --------------------------------------------------------------------------- #


def test_cierra_con_siguiente_paso_accionable():
    a = construir_analisis(FuenteMuestra(), "semana")
    paso = a["siguiente_paso"]
    assert paso is not None
    assert paso["marca"]
    assert "Pídele a Claude" in paso["texto"]
    # Frontera: la decisión final queda en el equipo, no en la máquina.
    assert "lo decides tú" in paso["texto"].lower()


def test_render_markdown_incluye_siguiente_paso():
    md = render_markdown(construir_analisis(FuenteMuestra(), "semana"))
    assert "**Siguiente paso:**" in md


# --------------------------------------------------------------------------- #
# Criterio 3: marca explícitamente cuando los datos son de muestra.            #
# --------------------------------------------------------------------------- #


def test_muestra_marcada_en_estructura():
    a = construir_analisis(FuenteMuestra(), "semana")
    assert a["es_muestra"] is True
    assert a["fuente"] == "muestra"
    assert "aviso" in a  # campo de primer nivel


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
    assert a["movimientos"] == []
    assert a["siguiente_paso"] is None
    md = render_markdown(a)
    assert "Sin datos suficientes" in md
    assert "**Siguiente paso:**" not in md  # no inventa una acción sin base


def test_marca_estable_no_se_narra_como_movimiento():
    a = construir_analisis(_FuenteEstable(), "semana")
    # 1% < umbral 5%: no es movimiento, pero sí cuenta como estable.
    assert a["movimientos"] == []
    assert a["marcas_estables"] == 1
    md = render_markdown(a)
    assert "estable" in md.lower()
    assert "Sin datos suficientes" not in md  # hay datos, solo que estables


def test_rango_invalido_propaga_valueerror():
    with pytest.raises(ValueError):
        construir_analisis(FuenteMuestra(), "trimestre")


# --------------------------------------------------------------------------- #
# Variación REAL desde el histórico (no solo el modelo de la muestra).         #
# --------------------------------------------------------------------------- #


def test_usa_variacion_real_del_historico(tmp_path):
    """Con histórico previo, la variación del movimiento es la REAL, no la sintética."""
    h = Historico(tmp_path / "h.db")
    # Baseline muy bajo en un periodo anterior para forzar una variación enorme.
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
    cs = next((m for m in a["movimientos"] if m["marca_id"] == "claro_sports"), None)
    assert cs is not None
    # La muestra de claro_sports ronda millones de vistas vs. baseline 1000:
    # la variación real es enorme y positiva, muy por encima del modelo sintético.
    assert cs["variacion_vis_pct"] > 1000
