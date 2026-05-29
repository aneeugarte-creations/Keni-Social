"""Cache de métricas: lazy fill, refresco de combo y estado del refresco en 2º plano.

TODO OFFLINE: la fuente es de muestra (`KENI_METRICAS_CONFIG` inexistente, lo fija
`entorno`) y la persistencia va al Postgres de pruebas (`entorno` lo provisiona y trunca
`metricas_cache` entre tests). No hay red ni APIs externas.
"""

from __future__ import annotations

import threading
import time

import pytest

from keni_consola import metricas_cache as mc
from keni_consola import repos


@pytest.fixture(autouse=True)
def _reset_estado():
    """Resetea el estado de refresco EN MEMORIA antes y después de cada test."""
    mc._ESTADO.update(corriendo=False, iniciado_en="", terminado_en="", ultimo_error="")
    yield
    mc._ESTADO.update(corriendo=False, iniciado_en="", terminado_en="", ultimo_error="")


def test_lazy_fill_guarda_la_primera_vez_y_relee_de_cache(entorno, monkeypatch):
    # 1ª lectura: no hay cache -> calcula vía servicio, guarda y devuelve.
    rep, generado_en = mc.reporte("mes", None)
    assert rep["fuente"] == "muestra"
    assert generado_en  # ISO no vacío

    # Quedó persistido en la tabla de cache.
    entrada = repos.leer_metricas_cache(mc._clave(mc.TIPO_REPORTE, "mes", None))
    assert entrada is not None
    assert entrada["generado_en"] == generado_en

    # 2ª lectura: NO debe recalcular (si lo hiciera, esta trampa explotaría).
    def _explota(*_a, **_k):
        raise AssertionError("no debería recalcular: el combo ya está en cache")

    monkeypatch.setattr(mc.servicio, "construir_reporte", _explota)
    rep2, generado_en2 = mc.reporte("mes", None)
    assert generado_en2 == generado_en
    assert rep2["fuente"] == "muestra"


def test_refrescar_combo_actualiza_generado_en(entorno, monkeypatch):
    # Timestamps deterministas: dos instantes distintos.
    tiempos = iter(["2026-05-29T10:00:00", "2026-05-29T11:00:00"])
    monkeypatch.setattr(mc, "_ahora", lambda: next(tiempos))

    rep1, gen1 = mc.reporte("semana", None)
    assert gen1 == "2026-05-29T10:00:00"

    # Refrescar el combo lo recalcula (bypass cache) y reestampa el timestamp.
    mc.refrescar_combo("semana", None)
    entrada = repos.leer_metricas_cache(mc._clave(mc.TIPO_REPORTE, "semana", None))
    assert entrada["generado_en"] == "2026-05-29T11:00:00"


def test_estado_reporta_generado_en_del_combo(entorno):
    _rep, gen = mc.reporte("mes", "claro_sports")
    est = mc.estado("mes", "claro_sports")
    assert est["corriendo"] is False
    assert est["generado_en"] == gen
    # Un combo aún sin cachear devuelve generado_en vacío.
    assert mc.estado("7d", "unotv")["generado_en"] == ""


def test_disparar_refresco_es_idempotente(entorno, monkeypatch):
    # Bloqueamos el barrido para observar el estado "corriendo" de forma determinista.
    bloqueo = threading.Event()
    llamadas: list = []

    def _fake_refrescar_todo(prioritario=None):
        llamadas.append(prioritario)
        bloqueo.wait(2.0)
        return 1

    monkeypatch.setattr(mc, "refrescar_todo", _fake_refrescar_todo)

    e1 = mc.disparar_refresco("mes", None)
    assert e1["corriendo"] is True

    # 2ª llamada mientras corre: NO arranca otro barrido.
    e2 = mc.disparar_refresco("mes", None)
    assert e2["corriendo"] is True

    bloqueo.set()
    for _ in range(100):
        if not mc._ESTADO["corriendo"]:
            break
        time.sleep(0.02)
    assert mc._ESTADO["corriendo"] is False
    assert llamadas == [("mes", None)]  # un único barrido real, con el combo prioritario
