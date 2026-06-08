"""Tests de PAGINACION real de los listados + indice de runs (#121).

OFFLINE, todo aislado en tmp (raiz de datos + indice + almacenes via env vars). Cubre:
  - indice: `listar(limite/desplazamiento)` (LIMIT/OFFSET) respeta el ORDER BY y
    `contar()` ignora la paginacion (probado contra el historial, unica entidad YAML viva).
  - ficheros: `_listar_validado` solo lee los cuerpos YAML de la PAGINA, no de todo.
  - agentes: los runs se INDEXAN al crear/actualizar; `listar_runs_globales` pagina via
    el indice; `agregados_runs` agrega con SQL.
  - PARIDAD CRITICA: la nueva agregacion indexada == el viejo full-scan (mismos
    coste/tokens/runs, por agente y por dia), incl. tras un backfill desde disco.
  - retrocompat del envelope: sin params se devuelve el conjunto completo.
"""

from __future__ import annotations

import pytest

from keni_consola import agentes, ficheros, indice, repos


@pytest.fixture
def base(monkeypatch, tmp_path):
    """Aisla raiz de datos, indice y almacen de generaciones en tmp."""
    monkeypatch.setenv("KENI_CONSOLA_RAIZ", str(tmp_path / "datos"))
    monkeypatch.setenv("KENI_CONSOLA_INDICE", str(tmp_path / "indice.sqlite"))
    monkeypatch.setenv("KENI_CONSOLA_GENERACIONES", str(tmp_path / "generaciones"))
    return tmp_path


# --------------------------------------------------------------------------- #
# indice.listar: LIMIT/OFFSET + contar()                                      #
# --------------------------------------------------------------------------- #


def test_indice_paginacion_respeta_orden_y_pagina(base):
    # 5 entradas de historial; el indice ordena por fecha_creacion DESC, fecha DESC, id DESC.
    creadas = [repos.registrar_historial_prompt("p", "unotv", f"R{i}") for i in range(5)]
    todas = indice.listar("historial")
    assert len(todas) == 5

    pagina1 = indice.listar("historial", limite=2, desplazamiento=0)
    pagina2 = indice.listar("historial", limite=2, desplazamiento=2)
    pagina3 = indice.listar("historial", limite=2, desplazamiento=4)
    # Las paginas son cortes consecutivos del orden completo (sin solapes ni huecos).
    assert [e["id"] for e in pagina1] == [e["id"] for e in todas[:2]]
    assert [e["id"] for e in pagina2] == [e["id"] for e in todas[2:4]]
    assert [e["id"] for e in pagina3] == [e["id"] for e in todas[4:]]
    assert len(pagina3) == 1
    # contar() ignora la paginacion: es el total real.
    assert indice.contar("historial") == 5
    assert set(creadas) == {e["id"] for e in todas}


def test_indice_contar_aplica_filtros(base):
    repos.registrar_historial_prompt("p", "unotv", "a")
    repos.registrar_historial_prompt("p", "unotv", "b")
    repos.registrar_historial_prompt("p", "claro-sports", "c")
    assert indice.contar("historial") == 3
    assert indice.contar("historial", {"marca": "unotv"}) == 2
    assert indice.contar("historial", {"marca": "claro-sports"}) == 1


# --------------------------------------------------------------------------- #
# ficheros: paginacion solo lee los cuerpos de la pagina                      #
# --------------------------------------------------------------------------- #


def test_listar_historial_paginado_solo_lee_la_pagina(base, monkeypatch):
    for i in range(6):
        repos.registrar_historial_prompt("p", "unotv", f"R{i}")

    # Contamos cuantos cuerpos YAML se leen al pedir una pagina de 2.
    original = ficheros._leer_yaml
    llamadas = {"n": 0}

    def _contado(ruta, *, tipo):  # noqa: ANN001
        llamadas["n"] += 1
        return original(ruta, tipo=tipo)

    monkeypatch.setattr(ficheros, "_leer_yaml", _contado)
    pagina = repos.listar_historial_prompts(limite=2, desplazamiento=0)
    assert len(pagina) == 2
    # Solo se leyeron los 2 cuerpos de la pagina, no los 6.
    assert llamadas["n"] == 2


def test_listar_historial_sin_params_devuelve_todo(base):
    for i in range(4):
        repos.registrar_historial_prompt("p", "unotv", f"R{i}")
    assert len(repos.listar_historial_prompts()) == 4
    assert repos.contar_historial_prompts() == 4


def test_listar_historial_paginas_consecutivas_cubren_todo(base):
    ids = {repos.registrar_historial_prompt("p", "unotv", f"R{i}") for i in range(5)}
    vistos: list[str] = []
    for off in (0, 2, 4):
        vistos += [h["id"] for h in repos.listar_historial_prompts(limite=2, desplazamiento=off)]
    assert set(vistos) == ids
    assert len(vistos) == 5  # sin duplicados


# --------------------------------------------------------------------------- #
# Indice de runs: alta al crear/actualizar + paginacion                       #
# --------------------------------------------------------------------------- #


def _run(agente, fecha, *, coste=0.0, tin=0, tout=0, estado="completado"):
    """Crea un run con metricas en el indice (via agentes.guardar_run)."""
    return agentes.guardar_run(
        agente,
        {
            "prompt": "p", "modo": "headless", "estado": estado, "salida": "s",
            "fecha_inicio": fecha, "fecha_fin": fecha,
            "metricas": {"tokens_in": tin, "tokens_out": tout, "total_cost_usd": coste},
        },
    )


def test_guardar_run_indexa(base):
    _run("unotv", "2026-05-24T10:00:00", coste=0.01, tin=10, tout=5)
    assert indice.contar("run") == 1
    fila = indice.listar("run")[0]
    assert fila["agente"] == "unotv"
    assert fila["coste_usd"] == pytest.approx(0.01)
    assert fila["tokens_in"] == 10 and fila["tokens_out"] == 5
    assert fila["dia"] == "2026-05-24"


def test_actualizar_run_reindexa_metricas(base):
    run = _run("unotv", "2026-05-24T10:00:00", coste=0.01, tin=10, tout=5)
    agentes.actualizar_run(
        "unotv", run["id"],
        {"metricas": {"tokens_in": 100, "tokens_out": 40, "total_cost_usd": 0.05}},
    )
    # Sigue habiendo UNA fila (upsert por id), con las metricas nuevas.
    assert indice.contar("run") == 1
    fila = indice.listar("run")[0]
    assert fila["coste_usd"] == pytest.approx(0.05)
    assert fila["tokens_in"] == 100


def test_listar_runs_globales_paginado(base):
    _run("unotv", "2026-05-24T10:00:00")
    _run("unotv", "2026-05-24T11:00:00")
    _run("claro-sports", "2026-05-24T12:00:00")
    todos = agentes.listar_runs_globales()
    assert len(todos) == 3
    # Recientes primero (fecha_inicio desc).
    assert todos[0]["fecha_inicio"] == "2026-05-24T12:00:00"
    pagina = agentes.listar_runs_globales(limite=2, desplazamiento=0)
    assert [r["id"] for r in pagina] == [r["id"] for r in todos[:2]]
    assert agentes.contar_runs_globales() == 3
    # El nombre legible del agente se resuelve (no se denormaliza).
    assert pagina[0]["agente_nombre"]


def test_runs_globales_indice_vacio_se_reconstruye(base):
    _run("unotv", "2026-05-24T10:00:00", coste=0.02, tin=3, tout=2)
    # Borramos el indice en caliente: el listado debe reconstruirlo desde disco.
    indice.ruta_indice().unlink()
    todos = agentes.listar_runs_globales()
    assert len(todos) == 1
    assert agentes.agregados_runs()["total"]["runs"] == 1


# --------------------------------------------------------------------------- #
# PARIDAD CRITICA: agregacion indexada == full-scan                           #
# --------------------------------------------------------------------------- #


def _agregados_full_scan() -> dict:
    """Reimplementacion del VIEJO agregados_runs (full-scan de todos los cuerpos).

    Itera TODOS los runs en disco (sin indice) y suma coste/tokens global, por agente
    y por dia, EXACTAMENTE como lo hacia agentes.agregados_runs antes de #121. Es la
    referencia con la que comparamos la nueva agregacion en SQL.
    """
    runs: list[dict] = []
    for agente_id, nombre in agentes._agentes_para_runs():
        carpeta = agentes.carpeta_agente(agente_id, crear=False) / agentes._DIR_RUNS
        if not carpeta.is_dir():
            continue
        for r in agentes.listar_runs(agente_id):
            runs.append({**r, "agente": agente_id, "agente_nombre": nombre})
    runs.sort(key=lambda r: (r["fecha_inicio"], r["id"]), reverse=True)

    total_coste = 0.0
    total_tokens = 0.0
    por_agente: dict[str, dict] = {}
    por_dia: dict[str, dict] = {}
    for run in runs:
        m = run.get("metricas")
        coste = agentes._sumar_metrica(m, "total_cost_usd")
        tokens = agentes._sumar_metrica(m, "tokens_in") + agentes._sumar_metrica(m, "tokens_out")
        total_coste += coste
        total_tokens += tokens
        ag = run["agente"]
        e = por_agente.setdefault(
            ag, {"agente": ag, "agente_nombre": run["agente_nombre"], "coste_usd": 0.0,
                 "tokens": 0, "runs": 0},
        )
        e["coste_usd"] += coste
        e["tokens"] += int(tokens)
        e["runs"] += 1
        dia = (run["fecha_inicio"] or "")[:10]
        d = por_dia.setdefault(dia, {"dia": dia, "coste_usd": 0.0, "tokens": 0, "runs": 0})
        d["coste_usd"] += coste
        d["tokens"] += int(tokens)
        d["runs"] += 1
    agentes_lista = sorted(por_agente.values(), key=lambda e: e["coste_usd"], reverse=True)
    dias_lista = sorted(por_dia.values(), key=lambda e: e["dia"], reverse=True)
    return {
        "total": {"coste_usd": round(total_coste, 6), "tokens": int(total_tokens),
                  "runs": len(runs)},
        "por_agente": [{**e, "coste_usd": round(e["coste_usd"], 6)} for e in agentes_lista],
        "por_dia": [{**e, "coste_usd": round(e["coste_usd"], 6)} for e in dias_lista],
    }


def _sembrar_runs_variados():
    """Varios runs con costes/tokens/dias/agentes distintos (costes unicos por agente)."""
    _run("unotv", "2026-05-24T10:00:00", coste=0.0123, tin=130, tout=50)
    _run("unotv", "2026-05-24T11:00:00", coste=0.0050, tin=77, tout=33)
    _run("unotv", "2026-05-25T09:00:00", coste=0.0200, tin=10, tout=5)
    _run("claro-sports", "2026-05-24T12:00:00", coste=0.0070, tin=40, tout=10)
    _run("claro-sports", "2026-05-25T08:00:00", coste=0.0010, tin=5, tout=2)
    # Un run SIN metricas (no debe contar coste/tokens pero si runs).
    agentes.guardar_run(
        "piso-15",
        {"prompt": "p", "modo": "headless", "estado": "error", "salida": "x",
         "fecha_inicio": "2026-05-25T07:00:00", "fecha_fin": "2026-05-25T07:00:01"},
    )


def _como_mapas(agg: dict) -> dict:
    """Normaliza un agregado a forma comparable independiente del orden de listas."""
    return {
        "total": agg["total"],
        "por_agente": {e["agente"]: {k: e[k] for k in ("coste_usd", "tokens", "runs")}
                       for e in agg["por_agente"]},
        "por_dia": {e["dia"]: {k: e[k] for k in ("coste_usd", "tokens", "runs")}
                    for e in agg["por_dia"]},
    }


def test_agregados_paridad_full_scan_vs_indexado(base):
    """La agregacion SQL indexada == el full-scan, numero a numero (total/agente/dia)."""
    _sembrar_runs_variados()
    esperado = _agregados_full_scan()
    obtenido = agentes.agregados_runs()
    # Numeros identicos (comparados como mapas, orden-independiente).
    assert _como_mapas(obtenido) == _como_mapas(esperado)
    # Y el ORDEN de por_agente coincide (mayor coste primero) con costes unicos.
    assert [e["agente"] for e in obtenido["por_agente"]] == [
        e["agente"] for e in esperado["por_agente"]
    ]
    # Sanidad de totales: 0.0123+0.0050+0.0200+0.0070+0.0010 = 0.0453; tokens = 0 + ...
    assert obtenido["total"]["runs"] == 6
    assert obtenido["total"]["coste_usd"] == pytest.approx(0.0453)
    assert obtenido["total"]["tokens"] == (130 + 50 + 77 + 33 + 10 + 5 + 40 + 10 + 5 + 2)


def test_agregados_paridad_tras_backfill_desde_disco(base):
    """Tras borrar el indice, el backfill desde disco reproduce los MISMOS agregados."""
    _sembrar_runs_variados()
    esperado = _agregados_full_scan()
    # Indice borrado: agregados_runs debe reconstruirlo y NO sub-contar.
    indice.ruta_indice().unlink()
    obtenido = agentes.agregados_runs()
    assert _como_mapas(obtenido) == _como_mapas(esperado)


def test_reindexar_runs_explicito(base):
    _sembrar_runs_variados()
    indice.reemplazar_tipo("run", [])  # vacia el indice de runs sin tocar disco
    assert indice.contar("run") == 0
    agentes.reindexar_runs()
    assert indice.contar("run") == 6
