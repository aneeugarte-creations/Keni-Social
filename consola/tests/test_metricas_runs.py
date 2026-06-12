"""Tests de la monitorizacion de runs IA: parseo de metricas + persistencia + endpoints.

TODO OFFLINE: NUNCA se llama a `claude` real. `parsear_resultado_json` es una funcion
PURA (se prueba con fixtures del JSON que devuelve `claude -p ... --output-format json`);
los endpoints corren con `generaciones._runner` parcheado a un runner que devuelve `(texto,
MetricasRun)`.

Fixtures de stdout cubiertos:
  - exito con `modelUsage` (tokens preferentes por modelo) + `usage` (cache/fallback)
  - exito SIN `modelUsage` (fallback a `usage`)
  - error de presupuesto (`subtype == "error_max_budget"`) -> GeneracionError en espanol
  - stdout NO-JSON -> se trata como texto y `metricas is None`
"""

from __future__ import annotations

import json

import pytest

from keni_consola import agentes
from keni_consola.dominio import stream

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
    texto, m = stream.parsear_resultado_json(_JSON_EXITO_MODELUSAGE)
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
    texto, m = stream.parsear_resultado_json(_JSON_EXITO_SOLO_USAGE)
    assert texto == "Copy con fallback a usage."
    assert m is not None
    assert m.tokens_in == 77
    assert m.tokens_out == 33
    assert m.num_turns == 1
    # sin modelUsage, el modelo cae al campo `model`
    assert m.modelo == "claude-sonnet-4-6"


def test_parsear_error_presupuesto_lanza_generacionerror_en_espanol():
    with pytest.raises(stream.GeneracionError) as exc:
        stream.parsear_resultado_json(_JSON_ERROR_PRESUPUESTO)
    assert "presupuesto" in str(exc.value).lower()


def test_parsear_error_generico_lanza_generacionerror():
    with pytest.raises(stream.GeneracionError) as exc:
        stream.parsear_resultado_json(_JSON_ERROR_GENERICO)
    assert "error" in str(exc.value).lower()


def test_parsear_stdout_no_json_devuelve_texto_y_metricas_none():
    texto, m = stream.parsear_resultado_json(_STDOUT_NO_JSON)
    assert texto == _STDOUT_NO_JSON
    assert m is None


def test_parsear_json_que_no_es_objeto_result_es_texto():
    # JSON valido pero NO el objeto result esperado: se trata como texto plano.
    crudo = '{"type": "system", "foo": 1}'
    texto, m = stream.parsear_resultado_json(crudo)
    assert texto == crudo
    assert m is None


def test_parsear_vacio_devuelve_texto_vacio_sin_metricas():
    texto, m = stream.parsear_resultado_json("")
    assert texto == ""
    assert m is None


# --------------------------------------------------------------------------- #
# _arg_presupuesto: --max-budget-usd desde KENI_CLAUDE_MAX_USD                #
# --------------------------------------------------------------------------- #


def test_arg_presupuesto_valido(monkeypatch):
    monkeypatch.setenv("KENI_CLAUDE_MAX_USD", "0.50")
    assert stream.arg_presupuesto() == ["--max-budget-usd", "0.5"]


def test_arg_presupuesto_invalido_o_ausente_se_ignora(monkeypatch):
    monkeypatch.delenv("KENI_CLAUDE_MAX_USD", raising=False)
    assert stream.arg_presupuesto() == []
    monkeypatch.setenv("KENI_CLAUDE_MAX_USD", "no-numero")
    assert stream.arg_presupuesto() == []
    monkeypatch.setenv("KENI_CLAUDE_MAX_USD", "0")
    assert stream.arg_presupuesto() == []


# --------------------------------------------------------------------------- #
# arg_max_turns: --max-turns desde KENI_CLAUDE_MAX_TURNS (#103, F-T-01)         #
# --------------------------------------------------------------------------- #


def test_arg_max_turns_valido(monkeypatch):
    from keni_consola.dominio import stream

    monkeypatch.setenv("KENI_CLAUDE_MAX_TURNS", "12")
    assert stream.arg_max_turns() == ["--max-turns", "12"]


def test_arg_max_turns_invalido_o_ausente_se_ignora(monkeypatch):
    from keni_consola.dominio import stream

    monkeypatch.delenv("KENI_CLAUDE_MAX_TURNS", raising=False)
    assert stream.arg_max_turns() == []
    monkeypatch.setenv("KENI_CLAUDE_MAX_TURNS", "no-numero")
    assert stream.arg_max_turns() == []
    monkeypatch.setenv("KENI_CLAUDE_MAX_TURNS", "0")
    assert stream.arg_max_turns() == []
    monkeypatch.setenv("KENI_CLAUDE_MAX_TURNS", "1.5")  # float no es entero de turnos
    assert stream.arg_max_turns() == []


# --------------------------------------------------------------------------- #
# metricas_a_dict: solo el subconjunto persistido, sin claves None            #
# --------------------------------------------------------------------------- #


def test_metricas_a_dict_omite_none_y_extras():
    m = stream.MetricasRun(
        tokens_in=10, tokens_out=20, cache_read=5, num_turns=2,
        total_cost_usd=0.01, duration_ms=100, session_id="s", modelo="mod",
    )
    d = stream.metricas_a_dict(m)
    # cache_read/session_id NO se persisten; las claves None se omiten.
    assert d == {
        "tokens_in": 10, "tokens_out": 20, "num_turns": 2,
        "total_cost_usd": 0.01, "duration_ms": 100, "modelo": "mod",
    }
    assert stream.metricas_a_dict(None) is None


# --------------------------------------------------------------------------- #
# Metricas de prueba (subconjunto persistido de un run/generacion)            #
# --------------------------------------------------------------------------- #


_METRICAS_DEMO = stream.MetricasRun(
    tokens_in=130, tokens_out=50, num_turns=3, total_cost_usd=0.0123,
    duration_ms=4200, session_id="sess-abc-123", modelo="claude-opus-4-7",
)


# --------------------------------------------------------------------------- #
# Persistencia: metricas en el historial de prompts                            #
# --------------------------------------------------------------------------- #


_SALIDA_PROMPT = """✅ Copy listo.

```json
{"piezas": [{"red": "x", "texto": "Tweet."}]}
```
"""


def test_historial_prompt_guarda_y_expone_metricas(entorno):
    """Una generacion de COPY (Texto, prompt salida=piezas) registra historial+metricas.

    Tras retirar el motor de skills, el copy se lanza desde la Texto: un prompt con
    `salida: piezas` lanzado con redes usa el post-procesado de COPY (mismo `procesar` que la
    prompt antiguo: parsea piezas, registra historial con sus metricas, crea borradores). El
    historial se persiste en su registro duradero (se lee via `repos`).
    """
    from keni_consola import libtexto

    # Prompt de copy (salida=piezas) en el store.
    prompt = libtexto.crear("Copy desde nota", tipo="prompt", cuerpo="Convierte la nota en copy.")
    ruta = libtexto._ruta_de_id(prompt.id)
    ruta.write_text(
        ruta.read_text(encoding="utf-8").replace("tipo: prompt", "tipo: prompt\nsalida: piezas"),
        encoding="utf-8",
    )

    c = _cliente(lanzar_generacion=lanzador_generacion_completa(_SALIDA_PROMPT, _METRICAS_DEMO))
    gen = c.post(
        "/api/texto/lanzar",
        json={"prompt_id": prompt.id, "marca": _MARCA, "redes": ["x"],
              "target": {"tipo": "contenido", "valor": "una nota"}},
    ).json()
    hid = gen["generacion"]["resultado"]["historial_id"]

    # El registro persistido lleva las metricas (el historial ya no se sirve por HTTP:
    # se lee del almacen duradero via `repos`).
    from keni_consola import repos

    entrada = repos.obtener_historial_prompt(hid)
    assert entrada["metricas"]["tokens_out"] == 50
    assert entrada["metricas"]["total_cost_usd"] == pytest.approx(0.0123)
    assert entrada["metricas"]["modelo"] == "claude-opus-4-7"


def test_historial_prompt_sin_metricas_devuelve_none(entorno):
    from keni_consola import repos

    hid = repos.registrar_historial_prompt("copy-desde-nota", _MARCA, "texto plano")
    entrada = repos.obtener_historial_prompt(hid)
    assert entrada["metricas"] is None


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
