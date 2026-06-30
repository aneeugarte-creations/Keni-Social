"""Tests de `dominio.actividad_pool`: sella el gasto de una sub-llamada del pool bajo su ETAPA.

OFFLINE: no llama a `claude` ni a la BD (monkeypatchea `generaciones.crear`, `registrar_cierre` y
`traducir.tomar_metricas_acumuladas`). Cubre la pieza que hace VISIBLE el coste de las sub-llamadas
(Cotejar/Subtema del job de Fusionar; Traducir en el acto) que antes quedaba huérfano.
"""

from __future__ import annotations

from keni_consola import generaciones, presupuesto_ia
from keni_consola.dominio import actividad_pool
from keni_consola.dominio import traducir as _trad


def test_registrar_sella_etapa_explicita_y_vuelca_gasto(monkeypatch):
    """Toma las métricas del hilo, crea la generación con la etapa explícita y vuelca su gasto."""
    monkeypatch.setattr(
        _trad, "tomar_metricas_acumuladas",
        lambda: {"tokens_in": 10, "tokens_out": 5, "total_cost_usd": 0.01},
    )
    creados: list[dict] = []
    cierres: list[dict] = []
    monkeypatch.setattr(generaciones, "crear", lambda reg: (creados.append(reg) or {**reg, "id": "g1"}))
    monkeypatch.setattr(presupuesto_ia, "registrar_cierre", lambda pub: cierres.append(pub))

    actividad_pool.registrar_actividad_pool("unotv", "Cotejar grupos — UnoTV", etapa="Cotejar", prompt="P", salida="S")

    assert len(creados) == 1
    reg = creados[0]
    assert reg["etapa"] == "Cotejar"
    assert reg["tipo"] == "pipeline"
    assert reg["proceso"] == generaciones.PROCESO_INVESTIGACION
    assert reg["estado"] == generaciones.ESTADO_COMPLETADO
    assert reg["metricas"]["tokens_in"] == 10
    assert len(cierres) == 1 and cierres[0]["id"] == "g1"


def test_registrar_sin_metricas_no_vuelca_al_ledger(monkeypatch):
    """Una sub-llamada sin métricas medibles registra la actividad pero NO ensucia el ledger."""
    monkeypatch.setattr(_trad, "tomar_metricas_acumuladas", lambda: None)
    cierres: list[dict] = []
    monkeypatch.setattr(generaciones, "crear", lambda reg: {**reg, "id": "g2"})
    monkeypatch.setattr(presupuesto_ia, "registrar_cierre", lambda pub: cierres.append(pub))

    actividad_pool.registrar_actividad_pool("unotv", "Traducir en el acto", etapa="Traducir")

    assert cierres == []


def test_registrar_es_best_effort_ante_fallo(monkeypatch):
    """Un fallo al crear la generación nunca propaga (la actividad es best-effort)."""
    monkeypatch.setattr(_trad, "tomar_metricas_acumuladas", lambda: {"tokens_in": 1, "tokens_out": 1})

    def _revienta(_reg):
        raise RuntimeError("db caída")

    monkeypatch.setattr(generaciones, "crear", _revienta)
    actividad_pool.registrar_actividad_pool("unotv", "Subtema — UnoTV", etapa="Subtema")  # no lanza
