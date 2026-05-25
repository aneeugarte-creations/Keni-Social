"""Tests de la monitorizacion de runs IA: parseo de metricas + persistencia + endpoints.

TODO OFFLINE: NUNCA se llama a `claude` real. `parsear_resultado_json` es una funcion
PURA (se prueba con fixtures del JSON que devuelve `claude -p ... --output-format json`);
los endpoints corren con `skills._runner` parcheado a un runner que devuelve `(texto,
MetricasRun)`.

Fixtures de stdout cubiertos:
  - exito con `modelUsage` (tokens preferentes por modelo) + `usage` (cache/fallback)
  - exito SIN `modelUsage` (fallback a `usage`)
  - error de presupuesto (`subtype == "error_max_budget"`) -> SkillError en espanol
  - stdout NO-JSON -> se trata como texto y `metricas is None`
"""

from __future__ import annotations

import json

import pytest

from keni_consola import agentes
from keni_consola.api import skills

from .conftest import _cliente, lanzador_generacion_completa

_MARCA = "unotv"


# --------------------------------------------------------------------------- #
# Fixtures: el JSON real de `claude -p ... --output-format json`              #
# --------------------------------------------------------------------------- #

_JSON_EXITO_MODELUSAGE = json.dumps(
    {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "Copy generado por el asistente.",
        "num_turns": 3,
        "total_cost_usd": 0.0123,
        "duration_ms": 4200,
        "duration_api_ms": 3900,
        "session_id": "sess-abc-123",
        "usage": {
            "input_tokens": 10,
            "output_tokens": 20,
            "cache_read_input_tokens": 5,
            "cache_creation_input_tokens": 2,
        },
        "modelUsage": {
            "claude-opus-4-7": {"inputTokens": 100, "outputTokens": 40, "costUSD": 0.01},
            "claude-haiku-4": {"inputTokens": 30, "outputTokens": 10, "costUSD": 0.0023},
        },
    }
)

_JSON_EXITO_SOLO_USAGE = json.dumps(
    {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "Copy con fallback a usage.",
        "num_turns": 1,
        "total_cost_usd": 0.005,
        "duration_ms": 1000,
        "session_id": "sess-xyz",
        "model": "claude-sonnet-4-6",
        "usage": {"input_tokens": 77, "output_tokens": 33},
    }
)

_JSON_ERROR_PRESUPUESTO = json.dumps(
    {
        "type": "result",
        "subtype": "error_max_budget",
        "is_error": True,
        "result": "Budget exceeded",
        "total_cost_usd": 0.5,
    }
)

_JSON_ERROR_GENERICO = json.dumps(
    {
        "type": "result",
        "subtype": "error_during_execution",
        "is_error": True,
        "result": "algo falló a mitad",
    }
)

_STDOUT_NO_JSON = "✅ Copy listo.\n\n## X\nUn texto plano, no es JSON."


# --------------------------------------------------------------------------- #
# parsear_resultado_json (funcion pura)                                       #
# --------------------------------------------------------------------------- #


def test_parsear_exito_con_modelusage_suma_tokens_por_modelo():
    texto, m = skills.parsear_resultado_json(_JSON_EXITO_MODELUSAGE)
    assert texto == "Copy generado por el asistente."
    assert m is not None
    # tokens preferentes de modelUsage: 100+30 in, 40+10 out
    assert m.tokens_in == 130
    assert m.tokens_out == 50
    # cache viene de usage
    assert m.cache_read == 5
    assert m.cache_creation == 2
    assert m.num_turns == 3
    assert m.total_cost_usd == pytest.approx(0.0123)
    assert m.duration_ms == 4200
    assert m.session_id == "sess-abc-123"
    # modelo = los modelos usados (coma-separados)
    assert "claude-opus-4-7" in m.modelo and "claude-haiku-4" in m.modelo


def test_parsear_exito_fallback_a_usage_sin_modelusage():
    texto, m = skills.parsear_resultado_json(_JSON_EXITO_SOLO_USAGE)
    assert texto == "Copy con fallback a usage."
    assert m is not None
    assert m.tokens_in == 77
    assert m.tokens_out == 33
    assert m.num_turns == 1
    # sin modelUsage, el modelo cae al campo `model`
    assert m.modelo == "claude-sonnet-4-6"


def test_parsear_error_presupuesto_lanza_skillerror_en_espanol():
    with pytest.raises(skills.SkillError) as exc:
        skills.parsear_resultado_json(_JSON_ERROR_PRESUPUESTO)
    assert "presupuesto" in str(exc.value).lower()


def test_parsear_error_generico_lanza_skillerror():
    with pytest.raises(skills.SkillError) as exc:
        skills.parsear_resultado_json(_JSON_ERROR_GENERICO)
    assert "error" in str(exc.value).lower()


def test_parsear_stdout_no_json_devuelve_texto_y_metricas_none():
    texto, m = skills.parsear_resultado_json(_STDOUT_NO_JSON)
    assert texto == _STDOUT_NO_JSON
    assert m is None


def test_parsear_json_que_no_es_objeto_result_es_texto():
    # JSON valido pero NO el objeto result esperado: se trata como texto plano.
    crudo = '{"type": "system", "foo": 1}'
    texto, m = skills.parsear_resultado_json(crudo)
    assert texto == crudo
    assert m is None


def test_parsear_vacio_devuelve_texto_vacio_sin_metricas():
    texto, m = skills.parsear_resultado_json("")
    assert texto == ""
    assert m is None


# --------------------------------------------------------------------------- #
# _arg_presupuesto: --max-budget-usd desde KENI_CLAUDE_MAX_USD                #
# --------------------------------------------------------------------------- #


def test_arg_presupuesto_valido(monkeypatch):
    monkeypatch.setenv("KENI_CLAUDE_MAX_USD", "0.50")
    assert skills._arg_presupuesto() == ["--max-budget-usd", "0.5"]


def test_arg_presupuesto_invalido_o_ausente_se_ignora(monkeypatch):
    monkeypatch.delenv("KENI_CLAUDE_MAX_USD", raising=False)
    assert skills._arg_presupuesto() == []
    monkeypatch.setenv("KENI_CLAUDE_MAX_USD", "no-numero")
    assert skills._arg_presupuesto() == []
    monkeypatch.setenv("KENI_CLAUDE_MAX_USD", "0")
    assert skills._arg_presupuesto() == []


# --------------------------------------------------------------------------- #
# metricas_a_dict: solo el subconjunto persistido, sin claves None            #
# --------------------------------------------------------------------------- #


def test_metricas_a_dict_omite_none_y_extras():
    m = skills.MetricasRun(
        tokens_in=10, tokens_out=20, cache_read=5, num_turns=2,
        total_cost_usd=0.01, duration_ms=100, session_id="s", modelo="mod",
    )
    d = skills.metricas_a_dict(m)
    # cache_read/session_id NO se persisten; las claves None se omiten.
    assert d == {
        "tokens_in": 10, "tokens_out": 20, "num_turns": 2,
        "total_cost_usd": 0.01, "duration_ms": 100, "modelo": "mod",
    }
    assert skills.metricas_a_dict(None) is None


# --------------------------------------------------------------------------- #
# Runner de prueba (devuelve metricas reales)                                 #
# --------------------------------------------------------------------------- #


_METRICAS_DEMO = skills.MetricasRun(
    tokens_in=130, tokens_out=50, num_turns=3, total_cost_usd=0.0123,
    duration_ms=4200, session_id="sess-abc-123", modelo="claude-opus-4-7",
)


def _lanzador_con_metricas(texto: str, metricas: skills.MetricasRun):
    """Fake del lanzador background: completa el run con `texto` + metricas (sin Popen)."""

    def lanzar(marca_id, run_id, prompt, *, cwd):  # noqa: ANN001
        agentes.actualizar_run(
            marca_id, run_id,
            {
                "estado": "completado",
                "salida": texto,
                "metricas": skills.metricas_a_dict(metricas),
                "fecha_fin": agentes.ahora_iso(),
            },
        )

    return lanzar


# --------------------------------------------------------------------------- #
# Persistencia: metricas en el run YAML del agente                            #
# --------------------------------------------------------------------------- #


def test_run_headless_guarda_metricas_en_yaml(entorno):
    c = _cliente(lanzar_run=_lanzador_con_metricas("salida con metricas", _METRICAS_DEMO))
    run = c.post(f"/api/agentes/{_MARCA}/runs", json={"prompt": "p"}).json()["run"]
    # El run devuelto trae las metricas (el lanzador fake ya completo el run).
    assert run["estado"] == "completado"
    assert run["metricas"]["tokens_in"] == 130
    assert run["metricas"]["total_cost_usd"] == pytest.approx(0.0123)
    assert run["metricas"]["modelo"] == "claude-opus-4-7"
    # Persistido en el YAML del run.
    detalle = c.get(f"/api/agentes/{_MARCA}/runs/{run['id']}").json()["run"]
    assert detalle["metricas"]["num_turns"] == 3
    assert detalle["metricas"]["duration_ms"] == 4200


def test_run_headless_error_no_tiene_metricas(entorno):
    def lanzar(marca_id, run_id, prompt, *, cwd):  # noqa: ANN001
        agentes.actualizar_run(
            marca_id, run_id,
            {"estado": "error", "salida": "El asistente terminó con error: x",
             "fecha_fin": agentes.ahora_iso()},
        )

    c = _cliente(lanzar_run=lanzar)
    run = c.post(f"/api/agentes/{_MARCA}/runs", json={"prompt": "p"}).json()["run"]
    assert run["estado"] == "error"
    assert run["metricas"] is None


# --------------------------------------------------------------------------- #
# Persistencia: metricas en el historial de skills                            #
# --------------------------------------------------------------------------- #


_SALIDA_SKILL = """✅ Copy listo.

```json
{"piezas": [{"red": "x", "texto": "Tweet."}]}
```
"""


def test_historial_skill_guarda_y_expone_metricas(entorno):
    c = _cliente(lanzar_generacion=lanzador_generacion_completa(_SALIDA_SKILL, _METRICAS_DEMO))
    gen = c.post(
        "/api/skills/ejecutar",
        json={"skill": "copy-desde-nota", "marca": _MARCA, "texto": "una nota", "redes": ["x"]},
    ).json()
    hid = gen["generacion"]["resultado"]["historial_id"]

    # Listado expone metricas.
    lista = c.get("/api/skills/historial").json()["historial"]
    assert lista[0]["metricas"]["tokens_out"] == 50
    # Detalle tambien.
    detalle = c.get(f"/api/skills/historial/{hid}").json()
    assert detalle["metricas"]["total_cost_usd"] == pytest.approx(0.0123)
    assert detalle["metricas"]["modelo"] == "claude-opus-4-7"


def test_historial_skill_sin_metricas_devuelve_none(entorno):
    from keni_consola import repos

    hid = repos.registrar_historial_skill("copy-desde-nota", _MARCA, "texto plano")
    c = _cliente()
    detalle = c.get(f"/api/skills/historial/{hid}").json()
    assert detalle["metricas"] is None


# --------------------------------------------------------------------------- #
# GET /api/runs (global) + /api/runs/agregados                                #
# --------------------------------------------------------------------------- #


def test_runs_globales_agrega_de_varios_agentes(entorno):
    c = _cliente(lanzar_run=_lanzador_con_metricas("ok", _METRICAS_DEMO))
    c.post(f"/api/agentes/{_MARCA}/runs", json={"prompt": "uno"})
    c.post("/api/agentes/claro-sports/runs", json={"prompt": "dos"})

    datos = c.get("/api/runs").json()
    runs = datos["runs"]
    assert len(runs) == 2
    agentes_vistos = {r["agente"] for r in runs}
    assert agentes_vistos == {_MARCA, "claro-sports"}
    primero = runs[0]
    assert set(primero) == {
        "id", "agente", "agente_nombre", "prompt", "modo", "estado", "motivo",
        "fecha_inicio", "metricas",
    }
    assert primero["metricas"]["tokens_in"] == 130


def test_runs_agregados_totales_por_agente_y_dia(entorno):
    c = _cliente(lanzar_run=_lanzador_con_metricas("ok", _METRICAS_DEMO))
    c.post(f"/api/agentes/{_MARCA}/runs", json={"prompt": "uno"})
    c.post(f"/api/agentes/{_MARCA}/runs", json={"prompt": "dos"})
    c.post("/api/agentes/claro-sports/runs", json={"prompt": "tres"})

    agg = c.get("/api/runs/agregados").json()
    assert agg["total"]["runs"] == 3
    # 3 runs * 0.0123
    assert agg["total"]["coste_usd"] == pytest.approx(0.0369)
    # 3 runs * (130+50) tokens
    assert agg["total"]["tokens"] == 3 * 180

    por_agente = {e["agente"]: e for e in agg["por_agente"]}
    assert por_agente[_MARCA]["runs"] == 2
    assert por_agente["claro-sports"]["runs"] == 1
    # por_dia agrupa por fecha (un solo dia en el test).
    assert sum(d["runs"] for d in agg["por_dia"]) == 3


def test_runs_agregados_vacio_sin_runs(entorno):
    agg = _cliente().get("/api/runs/agregados").json()
    assert agg["total"] == {"coste_usd": 0, "tokens": 0, "runs": 0}
    assert agg["por_agente"] == []
    assert agg["por_dia"] == []


def test_runs_globales_no_materializa_carpetas(entorno):
    """Listar runs globales sin ningun run no debe crear carpetas de agente."""
    _cliente().get("/api/runs")
    raiz = entorno / "datos"
    assert not raiz.exists() or not any(raiz.iterdir())


# --------------------------------------------------------------------------- #
# Dominio: agregados directos (sin pasar por la API)                          #
# --------------------------------------------------------------------------- #


def test_dominio_agregados_suma_tokens_in_y_out(entorno):
    agentes.guardar_run(
        _MARCA,
        {"prompt": "p", "modo": "headless", "estado": "completado", "salida": "s",
         "fecha_inicio": "2026-05-24T10:00:00", "fecha_fin": "2026-05-24T10:00:05",
         "metricas": {"tokens_in": 10, "tokens_out": 5, "total_cost_usd": 0.02}},
    )
    agg = agentes.agregados_runs()
    assert agg["total"]["tokens"] == 15
    assert agg["total"]["coste_usd"] == pytest.approx(0.02)
    assert agg["total"]["runs"] == 1
