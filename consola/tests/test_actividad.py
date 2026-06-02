"""Tests PUROS del dominio ACTIVIDAD (normalizacion + combinar + agregados).

Sin I/O ni Postgres: `consola.actividad` recibe listas ya leidas (generaciones +
runs) y las normaliza, combina (filtros + paginacion) y agrega. Aqui pasamos dicts
con la forma que emiten `generaciones._publico` y `agentes.listar_runs_globales`.
"""

from __future__ import annotations

import pytest

from keni_consola import actividad

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
        "resultado_url": "/parrilla/pendientes",
    }


def test_normalizar_generacion_resultado_url_por_tipo():
    # Cada tipo COMPLETADO con pagina de resultado enlaza a su superficie.
    casos = {
        "copy": "/parrilla/pendientes",
        "rss": "/parrilla/pendientes",
        "imagen": "/estudio",
        "verificacion": "/revision/verificacion",
        "qa-editorial": "/revision/editorial",
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
# combinar: mezcla, orden, filtros, paginacion                               #
# --------------------------------------------------------------------------- #


def test_combinar_mezcla_y_ordena_por_fecha_desc():
    items, total = actividad.combinar([_gen()], [_run()], offset=0, limite=50)
    assert total == 2
    # El run (2026-05-31) es mas reciente que la generacion (2026-05-30).
    assert [i["fuente"] for i in items] == ["run", "generacion"]


def test_combinar_filtra_por_fuente():
    items, total = actividad.combinar([_gen()], [_run()], fuente="run")
    assert total == 1
    assert items[0]["fuente"] == "run"


def test_combinar_filtra_por_tipo():
    items, total = actividad.combinar(
        [_gen(tipo="copy"), _gen(id="g2", tipo="rss")], [_run()], tipo="copy"
    )
    assert total == 1
    assert items[0]["tipo"] == "copy"


def test_combinar_filtra_tipo_run():
    items, total = actividad.combinar([_gen()], [_run()], tipo="run")
    assert total == 1
    assert items[0]["fuente"] == "run"


def test_combinar_pagina_y_total_es_antes_de_paginar():
    gens = [_gen(id=f"g{i}", fecha_inicio=f"2026-05-{10 + i:02d}T00:00:00") for i in range(5)]
    items, total = actividad.combinar(gens, [], offset=1, limite=2)
    assert total == 5  # total tras filtrar, ANTES de paginar
    assert len(items) == 2
    # offset=1 salta el mas reciente (g4); orden desc por fecha.
    assert [i["id"] for i in items] == ["g3", "g2"]


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

    tipos = {f["tipo"]: f for f in agg["por_tipo"]}
    assert set(tipos) == {"copy", "rss", "run"}
    assert tipos["copy"]["items"] == 1
    assert tipos["run"]["coste_usd"] == pytest.approx(0.0123)
    # por_tipo ordenado por coste desc: run (0.0123) > copy (0.01) > rss (0.002).
    assert [f["tipo"] for f in agg["por_tipo"]] == ["run", "copy", "rss"]

    dias = {f["dia"]: f for f in agg["por_dia"]}
    assert dias["2026-05-30"]["items"] == 2
    assert dias["2026-05-31"]["items"] == 1
    # por_dia recientes primero.
    assert [f["dia"] for f in agg["por_dia"]] == ["2026-05-31", "2026-05-30"]


def test_agregados_vacio():
    agg = actividad.agregados([], [])
    assert agg["total"] == {"items": 0, "coste_usd": 0, "tokens": 0}
    assert agg["por_tipo"] == []
    assert agg["por_dia"] == []
