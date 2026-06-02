"""Tests del puente metricas -> priorizacion (Fase 5). PURO + degradacion (sin red/DB)."""

from __future__ import annotations

from keni_consola import metricas_priorizacion as mp
from keni_consola import priorizacion


# --------------------------------------------------------------------------- #
# bonus_desde_engagement: PURO, escala relativa acotada                         #
# --------------------------------------------------------------------------- #


def test_bonus_relativo_a_la_marca_que_mas_rinde():
    """La marca de mayor engagement recibe el bonus maximo; el resto, proporcional."""
    bonus = mp.bonus_desde_engagement({"a": 10.0, "b": 5.0})
    assert bonus["a"] == priorizacion.BONUS_METRICAS_MAX
    assert bonus["b"] == round(priorizacion.BONUS_METRICAS_MAX * 0.5, 2)


def test_bonus_ignora_marcas_sin_engagement():
    """Engagement <=0, None o no numerico no aporta señal."""
    bonus = mp.bonus_desde_engagement({"a": 8.0, "b": 0.0, "c": None, "d": "x"})
    assert set(bonus) == {"a"}
    assert bonus["a"] == priorizacion.BONUS_METRICAS_MAX


def test_bonus_vacio_si_nadie_tiene_engagement():
    assert mp.bonus_desde_engagement({}) == {}
    assert mp.bonus_desde_engagement({"a": 0.0, "b": -1.0}) == {}


# --------------------------------------------------------------------------- #
# bonus_por_marca: GATEADO + BEST-EFFORT (degrada sin romper)                    #
# --------------------------------------------------------------------------- #


def test_flag_off_no_consulta_metricas(monkeypatch):
    """Con `KENI_PRIORIZA_METRICAS` OFF devuelve {} sin tocar la fachada (como hoy)."""
    monkeypatch.setattr(mp.config, "prioriza_metricas_activo", lambda: False)
    # Si tocara la fachada, este parche lo haria explotar -> el test fallaria.
    monkeypatch.setattr(
        mp, "_engagement_marca", lambda *a, **k: (_ for _ in ()).throw(AssertionError())
    )
    assert mp.bonus_por_marca() == {}


def test_flag_on_construye_bonus_desde_engagement(monkeypatch):
    """Con el flag ON, agrega el engagement por marca y lo convierte en bonus."""
    monkeypatch.setattr(mp.config, "prioriza_metricas_activo", lambda: True)
    monkeypatch.setattr(mp.config, "prioriza_metricas_rango", lambda: "mes")
    monkeypatch.setattr(mp.marcas, "ids", lambda: ["uno", "dos"])
    engagement = {"uno": 9.0, "dos": 3.0}
    monkeypatch.setattr(
        mp, "_engagement_marca", lambda marca_id, rango: engagement.get(marca_id)
    )
    bonus = mp.bonus_por_marca()
    assert bonus["uno"] == priorizacion.BONUS_METRICAS_MAX
    assert bonus["dos"] == round(priorizacion.BONUS_METRICAS_MAX * (3.0 / 9.0), 2)


def test_flag_on_pero_sin_datos_degrada_a_vacio(monkeypatch):
    """Flag ON pero la fachada no da engagement para ninguna marca -> {} (sin romper)."""
    monkeypatch.setattr(mp.config, "prioriza_metricas_activo", lambda: True)
    monkeypatch.setattr(mp.config, "prioriza_metricas_rango", lambda: "mes")
    monkeypatch.setattr(mp.marcas, "ids", lambda: ["uno", "dos"])
    monkeypatch.setattr(mp, "_engagement_marca", lambda *a, **k: None)
    assert mp.bonus_por_marca() == {}


def test_un_fallo_global_no_propaga(monkeypatch):
    """Cualquier excepcion en el calculo se traga y devuelve {} (nunca tumba la lista)."""
    monkeypatch.setattr(mp.config, "prioriza_metricas_activo", lambda: True)
    monkeypatch.setattr(
        mp.marcas, "ids", lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    assert mp.bonus_por_marca() == {}
