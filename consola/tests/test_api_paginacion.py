"""Tests de la API del envelope de PAGINACION (#121). OFFLINE, todo en tmp.

Verifica que los listados pesados devuelven el envelope ADITIVO retrocompatible:
mantienen su clave de lista (`publicaciones`/`generaciones`/`runs`) y AÑADEN
`paginacion:{total, limite, desplazamiento}`. Sin `?limite=` se devuelve el conjunto
completo (comportamiento previo) con `total` exacto; con `?limite=&desplazamiento=`
se pagina. Un cliente viejo que solo lee la clave de lista sigue funcionando.
"""

from __future__ import annotations

import pytest

from .conftest import _cliente
from .test_metricas_runs import _METRICAS_DEMO, _lanzador_con_metricas


def _crear_pub(cliente, titulo):
    return cliente.post(
        "/api/publicaciones", json={"marca": "unotv", "red": "x", "titulo": titulo, "contenido": "C"}
    )


# --------------------------------------------------------------------------- #
# Publicaciones                                                               #
# --------------------------------------------------------------------------- #


def test_publicaciones_sin_params_devuelve_todo_y_paginacion(cliente):
    for i in range(3):
        _crear_pub(cliente, f"P{i}")
    datos = cliente.get("/api/publicaciones").json()
    assert "publicaciones" in datos  # clave de lista intacta (retrocompat)
    assert len(datos["publicaciones"]) == 3
    pag = datos["paginacion"]
    assert pag["total"] == 3
    assert pag["desplazamiento"] == 0
    # Sin paginar, `limite` reportado abarca todo el conjunto.
    assert pag["limite"] == 3


def test_publicaciones_paginado(cliente):
    for i in range(5):
        _crear_pub(cliente, f"P{i}")
    p1 = cliente.get("/api/publicaciones?limite=2&desplazamiento=0").json()
    p2 = cliente.get("/api/publicaciones?limite=2&desplazamiento=2").json()
    assert len(p1["publicaciones"]) == 2
    assert len(p2["publicaciones"]) == 2
    assert p1["paginacion"] == {"total": 5, "limite": 2, "desplazamiento": 0}
    assert p2["paginacion"] == {"total": 5, "limite": 2, "desplazamiento": 2}
    # Paginas distintas (sin solape).
    ids1 = {p["id"] for p in p1["publicaciones"]}
    ids2 = {p["id"] for p in p2["publicaciones"]}
    assert not (ids1 & ids2)


def test_publicaciones_paginacion_respeta_filtros(cliente):
    for i in range(3):
        _crear_pub(cliente, f"U{i}")  # unotv
    cliente.post(
        "/api/publicaciones",
        json={"marca": "claro-sports", "red": "x", "titulo": "C", "contenido": "C"},
    )
    datos = cliente.get("/api/publicaciones?marca=unotv&limite=2").json()
    assert datos["paginacion"]["total"] == 3  # total filtrado, no 4
    assert len(datos["publicaciones"]) == 2


# --------------------------------------------------------------------------- #
# Generaciones                                                                #
# --------------------------------------------------------------------------- #


def test_generaciones_envelope(cliente):
    # Sin generaciones: lista vacia + paginacion 0.
    datos = cliente.get("/api/generaciones").json()
    assert datos["generaciones"] == []
    assert datos["paginacion"]["total"] == 0


# --------------------------------------------------------------------------- #
# Runs globales (monitor)                                                     #
# --------------------------------------------------------------------------- #


def test_runs_globales_envelope_sin_params(entorno):
    c = _cliente(lanzar_run=_lanzador_con_metricas("ok", _METRICAS_DEMO))
    c.post("/api/agentes/unotv/runs", json={"prompt": "uno"})
    c.post("/api/agentes/claro-sports/runs", json={"prompt": "dos"})
    datos = c.get("/api/runs").json()
    assert "runs" in datos and len(datos["runs"]) == 2  # clave intacta
    assert datos["paginacion"]["total"] == 2


def test_runs_globales_paginado(entorno):
    c = _cliente(lanzar_run=_lanzador_con_metricas("ok", _METRICAS_DEMO))
    c.post("/api/agentes/unotv/runs", json={"prompt": "uno"})
    c.post("/api/agentes/unotv/runs", json={"prompt": "dos"})
    c.post("/api/agentes/claro-sports/runs", json={"prompt": "tres"})
    datos = c.get("/api/runs?limite=2&desplazamiento=0").json()
    assert len(datos["runs"]) == 2
    assert datos["paginacion"] == {"total": 3, "limite": 2, "desplazamiento": 0}


def test_runs_agregados_sigue_exacto_via_api(entorno):
    c = _cliente(lanzar_run=_lanzador_con_metricas("ok", _METRICAS_DEMO))
    c.post("/api/agentes/unotv/runs", json={"prompt": "uno"})
    c.post("/api/agentes/unotv/runs", json={"prompt": "dos"})
    c.post("/api/agentes/claro-sports/runs", json={"prompt": "tres"})
    agg = c.get("/api/runs/agregados").json()
    assert agg["total"]["runs"] == 3
    assert agg["total"]["coste_usd"] == pytest.approx(3 * 0.0123)
    assert agg["total"]["tokens"] == 3 * 180
    por_agente = {e["agente"]: e for e in agg["por_agente"]}
    assert por_agente["unotv"]["runs"] == 2
    assert por_agente["claro-sports"]["runs"] == 1
    # `agente_nombre` se resuelve en el agregado.
    assert all(e["agente_nombre"] for e in agg["por_agente"])


def test_runs_invalid_limite_se_ignora(entorno):
    c = _cliente(lanzar_run=_lanzador_con_metricas("ok", _METRICAS_DEMO))
    c.post("/api/agentes/unotv/runs", json={"prompt": "uno"})
    # limite no numerico / 0 / negativo => sin paginar (conjunto completo).
    for q in ("limite=abc", "limite=0", "limite=-3"):
        datos = c.get(f"/api/runs?{q}").json()
        assert len(datos["runs"]) == 1
        assert datos["paginacion"]["total"] == 1
