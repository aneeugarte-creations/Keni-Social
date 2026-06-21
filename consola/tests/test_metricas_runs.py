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


def test_parsear_refusal_por_stop_reason_lanza_generacionerror():
    # Rechazo del modelo: `is_error` puede venir false, pero `stop_reason == "refusal"` marca
    # el run como fallo terminal -> GeneracionError (no pasa como exito con result vacio).
    crudo = json.dumps({
        "type": "result", "subtype": "success", "is_error": False,
        "stop_reason": "refusal", "result": "",
    })
    with pytest.raises(stream.GeneracionError) as exc:
        stream.parsear_resultado_json(crudo)
    assert "rehus" in str(exc.value).lower()


def test_parsear_refusal_por_subtype_lanza_generacionerror():
    crudo = json.dumps({"type": "result", "subtype": "refusal", "result": ""})
    with pytest.raises(stream.GeneracionError):
        stream.parsear_resultado_json(crudo)


def test_parsear_exito_normal_no_es_refusal():
    # `stop_reason: end_turn` (o ausente) sigue siendo exito: sin regresion.
    crudo = json.dumps({
        "type": "result", "subtype": "success", "is_error": False,
        "stop_reason": "end_turn", "result": "Copy ok.",
        "usage": {"input_tokens": 1, "output_tokens": 1},
    })
    texto, m = stream.parsear_resultado_json(crudo)
    assert texto == "Copy ok."
    assert m is not None


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
# arg_max_turns: --max-turns desde KENI_CLAUDE_MAX_TURNS                        #
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
        tokens_in=10, tokens_out=20, cache_read=5, cache_creation=2, num_turns=2,
        total_cost_usd=0.01, duration_ms=100, session_id="s", modelo="mod",
        ttft_ms=350, tokens_por_s=12.5,
    )
    d = stream.metricas_a_dict(m)
    # cache_read/cache_creation SI se persisten (prompt caching, para medir el ahorro);
    # ttft_ms/tokens_por_s SI (rendimiento); session_id NO; las claves None se omiten.
    assert d == {
        "tokens_in": 10, "tokens_out": 20, "cache_read": 5, "cache_creation": 2,
        "num_turns": 2, "total_cost_usd": 0.01, "duration_ms": 100, "modelo": "mod",
        "ttft_ms": 350, "tokens_por_s": 12.5,
    }
    # Un run que NO cachea ni reporta rendimiento: esas claves (None) se omiten, no se fuerzan.
    sin_cache = stream.MetricasRun(tokens_in=10, tokens_out=20)
    assert stream.metricas_a_dict(sin_cache) == {"tokens_in": 10, "tokens_out": 20}
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
    from keni_consola import libprompts

    # Prompt de copy (salida=piezas) en el store.
    prompt = libprompts.crear("Copy desde nota", tipo="prompt", cuerpo="Convierte la nota en copy.")
    ruta = libprompts._ruta_de_id(prompt.id)
    ruta.write_text(
        ruta.read_text(encoding="utf-8").replace("tipo: prompt", "tipo: prompt\nsalida: piezas"),
        encoding="utf-8",
    )

    c = _cliente(lanzar_generacion=lanzador_generacion_completa(_SALIDA_PROMPT, _METRICAS_DEMO))
    gen = c.post(
        "/api/prompts/lanzar",
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


# --------------------------------------------------------------------------- #
# M3: TTFT (ttft_ms) + tokens/s derivados del `result` (sin tocar esquema BD)  #
# --------------------------------------------------------------------------- #

_JSON_CON_TTFT = json.dumps(
    {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "Copy con ttft.",
        "duration_ms": 2000,
        "ttft_ms": 420,
        "usage": {"input_tokens": 50, "output_tokens": 100},
    }
)

_JSON_TTFT_FALLBACK = json.dumps(
    {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "Copy con ttft_stream.",
        "duration_ms": 0,
        "ttft_stream_ms": 510,
        "usage": {"input_tokens": 10, "output_tokens": 20},
    }
)


def test_parsear_lee_ttft_ms_y_deriva_tokens_por_s():
    _, m = stream.parsear_resultado_json(_JSON_CON_TTFT)
    assert m is not None
    assert m.ttft_ms == 420
    # 100 output_tokens / (2000ms / 1000) = 50.0 tok/s
    assert m.tokens_por_s == pytest.approx(50.0)


def test_parsear_ttft_usa_ttft_stream_ms_como_fallback():
    _, m = stream.parsear_resultado_json(_JSON_TTFT_FALLBACK)
    assert m is not None
    # ttft_ms ausente -> cae a ttft_stream_ms
    assert m.ttft_ms == 510


def test_parsear_tokens_por_s_none_si_duration_cero():
    # duration_ms=0 -> no se puede derivar tok/s (no se divide por cero).
    _, m = stream.parsear_resultado_json(_JSON_TTFT_FALLBACK)
    assert m is not None
    assert m.tokens_por_s is None


def test_parsear_sin_ttft_deja_campos_none():
    # Los fixtures clasicos no traen ttft -> ttft_ms None; con duration y out, tok/s derivado.
    _, m = stream.parsear_resultado_json(_JSON_EXITO_SOLO_USAGE)
    assert m is not None
    assert m.ttft_ms is None
    # 33 out / (1000ms / 1000) = 33.0 tok/s
    assert m.tokens_por_s == pytest.approx(33.0)


# --------------------------------------------------------------------------- #
# Constructores de args nuevos (M5/M4/M1): default + override por env          #
# --------------------------------------------------------------------------- #


def test_arg_excluir_secciones_dinamicas_default_on(monkeypatch):
    monkeypatch.delenv("KENI_CLAUDE_EXCLUDE_DYNAMIC_SECTIONS", raising=False)
    assert stream.arg_excluir_secciones_dinamicas() == [
        "--exclude-dynamic-system-prompt-sections"
    ]
    monkeypatch.setenv("KENI_CLAUDE_EXCLUDE_DYNAMIC_SECTIONS", "0")
    assert stream.arg_excluir_secciones_dinamicas() == []


def test_arg_session_persistence_default_no_persiste(monkeypatch):
    monkeypatch.delenv("KENI_CLAUDE_SESSION_PERSISTENCE", raising=False)
    assert stream.arg_session_persistence() == ["--no-session-persistence"]
    monkeypatch.setenv("KENI_CLAUDE_SESSION_PERSISTENCE", "1")
    assert stream.arg_session_persistence() == []


def test_arg_fallback_model_default_y_override(monkeypatch):
    monkeypatch.delenv("KENI_CLAUDE_FALLBACK_MODEL", raising=False)
    assert stream.arg_fallback_model() == []
    monkeypatch.setenv("KENI_CLAUDE_FALLBACK_MODEL", "a, b ,a")
    # Normaliza (trim, sin duplicados, orden) y va en UN solo flag.
    assert stream.arg_fallback_model() == ["--fallback-model", "a,b"]
    # omitir=True (el job fija su modelo): no se añade aunque haya env.
    assert stream.arg_fallback_model(omitir=True) == []
