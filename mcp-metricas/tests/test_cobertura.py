"""Cobertura: que plataformas respondieron vs. se omitieron (y por que).

Garantiza que una plataforma omitida (sin credenciales / sin presupuesto / error
de API) aparece como `omitida` con su `motivo` en la respuesta, para que los ceros
nunca se confundan con datos reales.
"""

from __future__ import annotations

from keni_metricas.agregador import FuenteCompuesta
from keni_metricas.config import CuentaConfig
from keni_metricas.fuentes.muestra import FuenteMuestra
from keni_metricas.picos import detectar_picos
from keni_metricas.picos import render_markdown as render_picos
from keni_metricas.presupuesto import Presupuesto
from keni_metricas.reporte import construir_reporte, render_markdown
from keni_metricas.schema import MetricaPlataforma, MotivoOmision, Pieza, Plataforma


class AdaptadorOK:
    def __init__(self, plataforma: Plataforma, vis: int = 1000, inter: int = 50):
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


class AdaptadorFallaAPI(AdaptadorOK):
    """Adaptador disponible pero cuya API falla: devuelve None / [] (degradacion)."""

    def metricas(self, handle, desde, hasta):
        return None

    def piezas(self, handle, desde, hasta, n):
        return []


def _cuenta(plataformas: dict[Plataforma, str]) -> CuentaConfig:
    return CuentaConfig(id="marca", nombre="Marca", plataformas=plataformas)


def test_sin_credenciales_se_reporta_como_omitida():
    # facebook tiene adaptador; tiktok esta configurada pero NO tiene adaptador
    cuenta = _cuenta({Plataforma.facebook: "h1", Plataforma.tiktok: "h2"})
    fuente = FuenteCompuesta([cuenta], {Plataforma.facebook: AdaptadorOK(Plataforma.facebook)})

    r = fuente.resumen("marca", "semana")

    assert r.cobertura is not None
    assert r.cobertura.ok == [Plataforma.facebook]
    assert r.cobertura.omitidas == [Plataforma.tiktok]
    assert r.cobertura.motivo == {"tiktok": MotivoOmision.sin_credenciales}
    assert not r.cobertura.completa
    # el cero de tiktok NO suma datos: el total es solo lo de facebook
    assert r.visualizaciones == 1000


def test_error_api_se_reporta_como_omitida():
    cuenta = _cuenta({Plataforma.facebook: "h1", Plataforma.youtube: "h2"})
    fuente = FuenteCompuesta(
        [cuenta],
        {
            Plataforma.facebook: AdaptadorOK(Plataforma.facebook),
            Plataforma.youtube: AdaptadorFallaAPI(Plataforma.youtube),
        },
    )

    r = fuente.resumen("marca", "semana")

    assert r.cobertura.ok == [Plataforma.facebook]
    assert r.cobertura.omitidas == [Plataforma.youtube]
    assert r.cobertura.motivo["youtube"] == MotivoOmision.error_api


def test_presupuesto_agotado_se_reporta_como_omitida():
    cuenta = _cuenta({Plataforma.facebook: "h1", Plataforma.x: "h2"})
    presupuesto = Presupuesto(caps={Plataforma.x: 0})  # X sin presupuesto desde el inicio
    fuente = FuenteCompuesta(
        [cuenta],
        {
            Plataforma.facebook: AdaptadorOK(Plataforma.facebook),
            Plataforma.x: AdaptadorOK(Plataforma.x),
        },
        presupuesto,
    )

    r = fuente.resumen("marca", "semana")

    assert Plataforma.facebook in r.cobertura.ok
    assert r.cobertura.omitidas == [Plataforma.x]
    assert r.cobertura.motivo["x"] == MotivoOmision.presupuesto_agotado


def test_cobertura_completa_cuando_todo_responde():
    cuenta = _cuenta({Plataforma.facebook: "h1", Plataforma.tiktok: "h2"})
    fuente = FuenteCompuesta(
        [cuenta],
        {
            Plataforma.facebook: AdaptadorOK(Plataforma.facebook),
            Plataforma.tiktok: AdaptadorOK(Plataforma.tiktok),
        },
    )

    r = fuente.resumen("marca", "semana")

    assert r.cobertura.completa
    assert not r.cobertura.omitidas
    assert set(r.cobertura.ok) == {Plataforma.facebook, Plataforma.tiktok}


def test_cobertura_serializa_a_json():
    cuenta = _cuenta({Plataforma.facebook: "h1", Plataforma.tiktok: "h2"})
    fuente = FuenteCompuesta([cuenta], {Plataforma.facebook: AdaptadorOK(Plataforma.facebook)})

    dump = fuente.resumen("marca", "semana").model_dump(mode="json")

    assert dump["cobertura"]["omitidas"] == ["tiktok"]
    assert dump["cobertura"]["motivo"] == {"tiktok": "sin_credenciales"}
    assert dump["cobertura"]["ok"] == ["facebook"]


def test_muestra_siempre_cobertura_completa():
    fuente = FuenteMuestra()
    cuenta = next(c for c in fuente.cuentas() if c.id == "claro_sports")
    r = fuente.resumen("claro_sports", "mes")
    assert r.cobertura is not None
    assert r.cobertura.completa
    assert set(r.cobertura.ok) == set(cuenta.plataformas)
    assert not r.cobertura.omitidas


# --- Surfacing en reporte y picos -------------------------------------------


def _fuente_parcial() -> FuenteCompuesta:
    """Una cuenta donde tiktok no tiene credenciales (omitida)."""
    cuenta = _cuenta({Plataforma.facebook: "h1", Plataforma.tiktok: "h2"})
    return FuenteCompuesta([cuenta], {Plataforma.facebook: AdaptadorOK(Plataforma.facebook)})


def test_reporte_marca_cuentas_parciales():
    rep = construir_reporte(_fuente_parcial(), "semana", top=1)
    assert rep["cobertura"]["completa"] is False
    assert rep["cobertura"]["cuentas_parciales"] == ["marca"]
    # la fila de la cuenta lleva su propia cobertura
    cob_fila = rep["cuentas"][0]["resumen"]["cobertura"]
    assert cob_fila["omitidas"] == ["tiktok"]


def test_reporte_markdown_incluye_nota_cobertura():
    md = render_markdown(construir_reporte(_fuente_parcial(), "semana", top=1))
    assert "Cobertura" in md
    assert "tiktok" in md
    assert "sin credenciales" in md
    assert "NO son datos reales" in md


def test_reporte_muestra_cobertura_completa():
    rep = construir_reporte(FuenteMuestra(), "semana", top=1)
    assert rep["cobertura"]["completa"] is True
    assert rep["cobertura"]["cuentas_parciales"] == []
    md = render_markdown(rep)
    assert "cobertura parcial" not in md.lower()


def test_picos_reporta_cobertura_parcial():
    rep = detectar_picos(_fuente_parcial(), "semana", 50)
    assert rep["cobertura"]["completa"] is False
    assert rep["cobertura"]["cuentas_parciales"] == ["marca"]
    md = render_picos(rep)
    assert "Cobertura parcial" in md


def test_picos_muestra_sin_aviso_cobertura():
    rep = detectar_picos(FuenteMuestra(), "semana", 50)
    assert rep["cobertura"]["completa"] is True
    assert "Cobertura parcial" not in render_picos(rep)
