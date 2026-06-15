"""Tests PUROS del dominio ACTIVIDAD (normalizacion + agregados).

Sin I/O ni Postgres: `consola.actividad` recibe listas ya leidas (generaciones +
runs) y las normaliza y agrega. Aqui pasamos dicts con la forma que emiten
`generaciones._publico` y `agentes.listar_runs_globales`.
"""

from __future__ import annotations

import pytest

from keni_consola import actividad, generaciones

# --------------------------------------------------------------------------- #
# Datos de ejemplo                                                            #
# --------------------------------------------------------------------------- #


def _gen(**campos):
    base = {
        "id": "g1",
        "tipo": "copy",
        "marca": "unotv",
        "etiqueta": "Copy de nota",
        "estado": "completado",
        "fecha_inicio": "2026-05-30T10:00:00",
        "metricas": {
            "tokens_in": 100, "tokens_out": 40, "total_cost_usd": 0.01,
            "duration_ms": 1200, "num_turns": 2,
        },
    }
    base.update(campos)
    return base


def _run(**campos):
    base = {
        "id": "r1",
        "agente": "claro-sports",
        "agente_nombre": "Claro Sports",
        "prompt": "Resume la jornada de hoy",
        "modo": "headless",
        "estado": "completado",
        "fecha_inicio": "2026-05-31T09:00:00",
        "metricas": {
            "tokens_in": 130, "tokens_out": 50, "total_cost_usd": 0.0123,
            "duration_ms": 4200, "num_turns": 3,
        },
    }
    base.update(campos)
    return base


# --------------------------------------------------------------------------- #
# normalizar_generacion                                                       #
# --------------------------------------------------------------------------- #


def test_normalizar_generacion():
    item = actividad.normalizar_generacion(_gen())
    assert item == {
        "id": "g1",
        "fuente": "generacion",
        "tipo": "copy",
        "etiqueta": "Copy de nota",
        "marca": "unotv",
        "estado": "completado",
        "fecha": "2026-05-30T10:00:00",
        "metricas": {
            "tokens": 140, "coste_usd": 0.01, "duration_ms": 1200, "num_turns": 2,
        },
        "resultado_url": "/operacion/feed/lista",
        "contenido_id": "",
        "proceso": "produccion",
    }


def test_normalizar_generacion_proceso_sellado_y_default():
    # Prefiere el proceso ya sellado en la generacion; sin sellar (no valido) -> produccion.
    assert actividad.normalizar_generacion(_gen(proceso="investigacion"))["proceso"] == (
        "investigacion"
    )
    assert actividad.normalizar_generacion(_gen())["proceso"] == "produccion"
    assert actividad.normalizar_generacion(_gen(proceso="basura"))["proceso"] == "produccion"


def test_normalizar_generacion_lleva_contenido_id():
    """Una generacion nacida del pipeline expone el tema que la origino (cruce a Pipelines)."""
    assert actividad.normalizar_generacion(_gen(contenido_id="c1"))["contenido_id"] == "c1"


def test_normalizar_generacion_resultado_url_por_tipo():
    # Cada tipo COMPLETADO con pagina de resultado enlaza a su superficie.
    casos = {
        "copy": "/operacion/feed/lista",
        "rss": "/operacion/feed/lista",
        "imagen": "/contenido/estudio",
        "verificacion": "/operacion/feed",
        "qa-editorial": "/operacion/feed",
    }
    for tipo, url in casos.items():
        item = actividad.normalizar_generacion(_gen(tipo=tipo))
        assert item["resultado_url"] == url


def test_normalizar_generacion_resultado_url_none_si_no_completado_o_sin_pagina():
    # En curso / error: aun no hay resultado al que ir.
    assert actividad.normalizar_generacion(_gen(estado="ejecutando"))["resultado_url"] is None
    assert actividad.normalizar_generacion(_gen(estado="error"))["resultado_url"] is None
    # Tipos sin pagina de resultado propia: sin enlace.
    assert actividad.normalizar_generacion(_gen(tipo="hashtags"))["resultado_url"] is None
    assert actividad.normalizar_generacion(_gen(tipo="prompt"))["resultado_url"] is None
    # "insumos" (cajones) NO enlaza a propósito: la fila abre el visor en vivo (popup con el
    # resultado del parseo), en vez de navegar al cajón y perder el resultado.
    assert actividad.normalizar_generacion(_gen(tipo="insumos"))["resultado_url"] is None


def test_normalizar_generacion_sin_metricas():
    item = actividad.normalizar_generacion(_gen(metricas=None))
    assert item["metricas"] == {
        "tokens": None, "coste_usd": None, "duration_ms": None, "num_turns": None,
    }


# --------------------------------------------------------------------------- #
# normalizar_run                                                              #
# --------------------------------------------------------------------------- #


def test_normalizar_run():
    item = actividad.normalizar_run(_run())
    assert item == {
        "id": "r1",
        "fuente": "run",
        "tipo": "run",
        "etiqueta": "Resume la jornada de hoy",
        "marca": "claro-sports",
        "estado": "completado",
        "fecha": "2026-05-31T09:00:00",
        "metricas": {
            "tokens": 180, "coste_usd": 0.0123, "duration_ms": 4200, "num_turns": 3,
        },
        "resultado_url": None,
        "contenido_id": "",
    }


def test_normalizar_run_etiqueta_recorta_prompt_largo():
    largo = "x" * 200
    item = actividad.normalizar_run(_run(prompt=largo))
    assert len(item["etiqueta"]) <= 80
    assert item["etiqueta"].endswith("…")


def test_normalizar_run_sin_prompt_cae_al_nombre_del_agente():
    item = actividad.normalizar_run(_run(prompt=""))
    assert item["etiqueta"] == "Claro Sports"


# --------------------------------------------------------------------------- #
# agregados                                                                   #
# --------------------------------------------------------------------------- #


def test_agregados_total_por_tipo_y_por_dia():
    gens = [
        _gen(id="g1", tipo="copy", fecha_inicio="2026-05-30T10:00:00"),
        _gen(id="g2", tipo="rss", fecha_inicio="2026-05-30T11:00:00",
             metricas={"tokens_in": 10, "tokens_out": 5, "total_cost_usd": 0.002}),
    ]
    runs = [_run(id="r1", fecha_inicio="2026-05-31T09:00:00")]
    agg = actividad.agregados(gens, runs)

    assert agg["total"]["items"] == 3
    assert agg["total"]["tokens"] == 140 + 15 + 180
    assert agg["total"]["coste_usd"] == pytest.approx(0.01 + 0.002 + 0.0123)
    # Tiempo de computo IA sumado (g2 no trae duration_ms: suma 0).
    assert agg["total"]["duration_ms"] == 1200 + 4200

    tipos = {f["tipo"]: f for f in agg["por_tipo"]}
    assert set(tipos) == {"copy", "rss", "run"}
    assert tipos["copy"]["items"] == 1
    assert tipos["run"]["coste_usd"] == pytest.approx(0.0123)
    # por_tipo ordenado por coste desc: run (0.0123) > copy (0.01) > rss (0.002).
    assert [f["tipo"] for f in agg["por_tipo"]] == ["run", "copy", "rss"]

    dias = {f["dia"]: f for f in agg["por_dia"]}
    assert dias["2026-05-30"]["items"] == 2
    assert dias["2026-05-31"]["items"] == 1
    # por_dia trae tokens (columna del desglose en la economia unificada): g1 (140) + g2 (15).
    assert dias["2026-05-30"]["tokens"] == 140 + 15
    assert dias["2026-05-31"]["tokens"] == 180
    # por_dia recientes primero.
    assert [f["dia"] for f in agg["por_dia"]] == ["2026-05-31", "2026-05-30"]


def test_agregados_vacio():
    agg = actividad.agregados([], [])
    assert agg["total"] == {"items": 0, "coste_usd": 0, "tokens": 0, "duration_ms": 0}
    assert agg["por_tipo"] == []
    assert agg["por_dia"] == []
    # por_proceso siempre presente, ambos procesos con bloques vacios.
    assert set(agg["por_proceso"]) == {"investigacion", "produccion"}
    for proc in ("investigacion", "produccion"):
        bloque = agg["por_proceso"][proc]
        assert bloque["total"] == {"items": 0, "coste_usd": 0, "tokens": 0, "duration_ms": 0}
        assert bloque["por_tipo"] == [] and bloque["por_dia"] == []


def test_agregados_por_proceso_split():
    """`por_proceso` desglosa SOLO generaciones por loop; los runs quedan fuera."""
    gens = [
        _gen(id="g1", tipo="pipeline", proceso="investigacion",
             fecha_inicio="2026-05-30T10:00:00",
             metricas={"tokens_in": 100, "tokens_out": 40, "total_cost_usd": 0.01}),
        _gen(id="g2", tipo="copy", proceso="produccion",
             fecha_inicio="2026-05-30T11:00:00",
             metricas={"tokens_in": 10, "tokens_out": 5, "total_cost_usd": 0.002}),
        _gen(id="g3", tipo="imagen", proceso="produccion",
             fecha_inicio="2026-05-31T08:00:00",
             metricas={"tokens_in": 0, "tokens_out": 0, "total_cost_usd": 0.05}),
    ]
    runs = [_run(id="r1", fecha_inicio="2026-05-31T09:00:00")]
    agg = actividad.agregados(gens, runs)

    # El total global SIGUE incluyendo los runs (contrato existente intacto).
    assert agg["total"]["items"] == 4

    inv = agg["por_proceso"]["investigacion"]
    assert inv["total"]["items"] == 1
    assert inv["total"]["tokens"] == 140
    assert [f["tipo"] for f in inv["por_tipo"]] == ["pipeline"]
    assert {f["dia"] for f in inv["por_dia"]} == {"2026-05-30"}

    prod = agg["por_proceso"]["produccion"]
    # g2 + g3 (los runs NO entran en por_proceso).
    assert prod["total"]["items"] == 2
    assert prod["total"]["tokens"] == 15
    assert prod["total"]["coste_usd"] == pytest.approx(0.002 + 0.05)
    # por_dia trae tokens por proceso (g2=15 el 30; g3=0 el 31), recientes primero.
    dias = {f["dia"]: f for f in prod["por_dia"]}
    assert dias["2026-05-30"]["tokens"] == 15
    assert dias["2026-05-31"]["tokens"] == 0
    assert [f["dia"] for f in prod["por_dia"]] == ["2026-05-31", "2026-05-30"]


def test_agregados_proceso_default_produccion():
    """Una generacion sin proceso sellado cae en produccion (default del dominio)."""
    gens = [_gen(id="g1", tipo="copy")]  # _gen no trae `proceso`
    agg = actividad.agregados(gens, [])
    assert agg["por_proceso"]["produccion"]["total"]["items"] == 1
    assert agg["por_proceso"]["investigacion"]["total"]["items"] == 0


# --------------------------------------------------------------------------- #
# API `/api/actividad/agregados`: filtro por marca (switch global de marca)   #
# --------------------------------------------------------------------------- #


def _crear_gen(marca: str, etiqueta: str) -> dict:
    """Crea una generacion REAL en el almacen aislado del entorno (estado completado)."""
    return generaciones.crear(
        {"tipo": "copy", "marca": marca, "etiqueta": etiqueta, "estado": "completado"}
    )


def test_agregados_filtra_por_marca(cliente):
    """`marca=unotv` deja solo los agregados de UnoTV; otras marcas se excluyen."""
    _crear_gen("unotv", "Copy UnoTV")
    _crear_gen("claro-sports", "Copy Claro")

    ragg = cliente.get("/api/actividad/agregados?marca=unotv")
    assert ragg.status_code == 200
    assert ragg.json()["total"]["items"] == 1


def test_agregados_sin_marca_devuelve_todo(cliente):
    """Sin `marca` (caso admin "todas"): agregados de TODAS las marcas."""
    _crear_gen("unotv", "Copy UnoTV")
    _crear_gen("claro-sports", "Copy Claro")

    ragg = cliente.get("/api/actividad/agregados")
    assert ragg.status_code == 200
    assert ragg.json()["total"]["items"] == 2


def test_agregados_marca_invalida_400(cliente):
    """Una `marca` que no es del catalogo se rechaza con 400 (igual que pipelines)."""
    assert cliente.get("/api/actividad/agregados?marca=inventada").status_code == 400


def test_agregados_api_sella_proceso_y_desglosa(cliente):
    """La API sella el proceso de cada generacion y abre `por_proceso` (copy->produccion;
    una criba 'Verificar · …' del pipeline -> investigacion)."""
    _crear_gen("unotv", "Copy UnoTV")  # tipo copy -> produccion
    generaciones.crear({
        "tipo": "pipeline", "marca": "unotv",
        "etiqueta": "Verificar · fuente", "estado": "completado",
    })
    pp = cliente.get("/api/actividad/agregados").json()["por_proceso"]
    assert pp["produccion"]["total"]["items"] == 1
    assert pp["investigacion"]["total"]["items"] == 1
