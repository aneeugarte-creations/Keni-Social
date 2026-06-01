"""Tests del progreso EN VIVO de los runs headless (stream-json + background).

TODO OFFLINE: NUNCA se llama a `claude` real. Cubre dos niveles:

  - `AcumuladorStream` (PURO): parseo de eventos NDJSON `system/init`, `assistant`
    (tokens/turnos PARCIALES) y `result` (metricas finales + texto + estado).
  - El ciclo del lector/finalizador (`_leer_stream` + `_finalizar_run`) con un
    Popen FAKE (un stub con `stdout` iterable, `wait`, `kill`, `returncode`), que
    avanza el YAML del run de forma incremental y fija el estado terminal. Tambien
    el wall-timeout (mata el proceso, `estado="error", motivo="timeout"`) y la
    degradacion cuando `claude` no esta (run en error, sin Popen).
"""

from __future__ import annotations

import json
import subprocess

import pytest

from keni_consola import agentes
from keni_consola.api import agentes as api_agentes
from keni_consola.dominio import stream as skills  # stream reúne lo que era la fachada api.skills

_MARCA = "unotv"

# Referencia GENUINA al lanzador real. Otros tests crean la app con un lanzador FAKE
# inyectado (crear_app reasigna el atributo de modulo `lanzar_run_background`), lo que
# dejaria el modulo con una fake al ejecutar la suite completa. Los tests que ejercitan
# el lanzador REAL restauran este atributo (con monkeypatch, asi se revierte solo).
_LANZADOR_REAL = api_agentes.lanzar_run_background


# --------------------------------------------------------------------------- #
# Lineas NDJSON del stream `--output-format stream-json --verbose`            #
# --------------------------------------------------------------------------- #

_INIT = json.dumps({"type": "system", "subtype": "init", "model": "claude-opus-4-7",
                    "session_id": "sess-1"})
_ASSISTANT_1 = json.dumps({"type": "assistant",
                           "message": {"usage": {"input_tokens": 100, "output_tokens": 20}}})
_ASSISTANT_2 = json.dumps({"type": "assistant",
                           "message": {"usage": {"input_tokens": 30, "output_tokens": 30}}})
_RESULT = json.dumps({
    "type": "result", "subtype": "success", "is_error": False,
    "result": "Texto final del run.",
    "num_turns": 2, "total_cost_usd": 0.0123, "duration_ms": 4200,
    "usage": {"input_tokens": 130, "output_tokens": 50},
    "modelUsage": {"claude-opus-4-7": {"inputTokens": 130, "outputTokens": 50}},
})
_RESULT_ERROR = json.dumps({
    "type": "result", "subtype": "error_max_budget", "is_error": True,
    "result": "Budget exceeded",
})


# --------------------------------------------------------------------------- #
# AcumuladorStream (puro)                                                     #
# --------------------------------------------------------------------------- #


def test_acumulador_arranque_y_turnos_parciales():
    acc = skills.AcumuladorStream()
    acc.procesar_linea(_INIT)
    assert acc.iniciado is True
    assert acc.modelo == "claude-opus-4-7"
    assert acc.session_id == "sess-1"
    # aun no hay metricas parciales (ningun assistant)
    assert acc.metricas_parciales() is None

    acc.procesar_linea(_ASSISTANT_1)
    parc = acc.metricas_parciales()
    assert parc is not None
    assert parc.num_turns == 1
    assert parc.tokens_in == 100 and parc.tokens_out == 20

    acc.procesar_linea(_ASSISTANT_2)
    parc = acc.metricas_parciales()
    assert parc.num_turns == 2
    assert parc.tokens_in == 130 and parc.tokens_out == 50


def test_acumulador_evento_result_fija_final_y_texto():
    acc = skills.AcumuladorStream()
    acc.procesar_linea(_INIT)
    acc.procesar_linea(_RESULT)
    assert acc.terminado is True
    assert acc.error is False
    assert acc.texto == "Texto final del run."
    assert acc.final is not None
    assert acc.final.num_turns == 2
    assert acc.final.total_cost_usd == pytest.approx(0.0123)


def test_acumulador_result_error_marca_error_en_espanol():
    acc = skills.AcumuladorStream()
    acc.procesar_linea(_RESULT_ERROR)
    assert acc.terminado is True
    assert acc.error is True
    assert "presupuesto" in acc.mensaje_error.lower()


def test_acumulador_ignora_lineas_basura():
    acc = skills.AcumuladorStream()
    acc.procesar_linea("")
    acc.procesar_linea("no es json {{{")
    acc.procesar_linea(json.dumps([1, 2, 3]))  # JSON valido pero no un objeto
    assert acc.iniciado is False
    assert acc.terminado is False
    assert acc.metricas_parciales() is None


# --------------------------------------------------------------------------- #
# Popen FAKE para ejercitar _leer_stream + _finalizar_run sin claude          #
# --------------------------------------------------------------------------- #


class _FakePopen:
    """Stub minimo de subprocess.Popen: stdout iterable + wait/kill/returncode."""

    def __init__(self, lineas, *, returncode=0, cuelga=False):
        # `stdout` debe iterar lineas con salto, como el text-mode real.
        self.stdout = iter(f"{linea}\n" for linea in lineas)
        self.returncode = returncode
        self._cuelga = cuelga
        self.matado = False

    def wait(self, timeout=None):
        if self._cuelga and not self.matado:
            raise subprocess.TimeoutExpired(cmd="claude", timeout=timeout)
        return self.returncode

    def kill(self):
        self.matado = True
        self.returncode = -9


def _siembra_run(marca_id: str) -> str:
    """Crea un run 'ejecutando' en el YAML y devuelve su id (como hace crear_run)."""
    run = agentes.guardar_run(
        marca_id,
        {"prompt": "p", "modo": "headless", "estado": "ejecutando", "salida": "",
         "fecha_inicio": agentes.ahora_iso(), "fecha_fin": ""},
    )
    return run["id"]


def test_lector_y_finalizador_completan_el_run(entorno):
    run_id = _siembra_run(_MARCA)
    acc = skills.AcumuladorStream()
    proc = _FakePopen([_INIT, _ASSISTANT_1, _ASSISTANT_2, _RESULT])

    api_agentes._leer_stream(_MARCA, run_id, proc, acc)
    api_agentes._finalizar_run(_MARCA, run_id, proc, acc)

    run = agentes.obtener_run(_MARCA, run_id)
    assert run["estado"] == "completado"
    assert run["salida"] == "Texto final del run."
    assert run["metricas"]["num_turns"] == 2
    assert run["metricas"]["total_cost_usd"] == pytest.approx(0.0123)
    assert run["fecha_fin"]


def test_lector_persiste_metricas_parciales_mientras_corre(entorno):
    """Tras consumir un assistant (sin result aun), el YAML refleja 'ejecutando' + parciales."""
    run_id = _siembra_run(_MARCA)
    acc = skills.AcumuladorStream()
    # Solo init + un assistant: no hay evento result.
    proc = _FakePopen([_INIT, _ASSISTANT_1])
    api_agentes._leer_stream(_MARCA, run_id, proc, acc)

    run = agentes.obtener_run(_MARCA, run_id)
    assert run["estado"] == "ejecutando"
    assert run["metricas"]["num_turns"] == 1
    assert run["metricas"]["tokens_in"] == 100


def test_finalizador_timeout_marca_error_con_motivo(entorno):
    run_id = _siembra_run(_MARCA)
    acc = skills.AcumuladorStream()
    acc.procesar_linea(_INIT)
    acc.procesar_linea(_ASSISTANT_1)  # algo de progreso parcial antes del corte
    proc = _FakePopen([], cuelga=True)

    api_agentes._finalizar_run(_MARCA, run_id, proc, acc)

    assert proc.matado is True
    run = agentes.obtener_run(_MARCA, run_id)
    assert run["estado"] == "error"
    assert run["motivo"] == "timeout"
    # conserva las metricas parciales que alcanzo a acumular
    assert run["metricas"]["num_turns"] == 1


def test_finalizador_result_de_error_marca_error(entorno):
    run_id = _siembra_run(_MARCA)
    acc = skills.AcumuladorStream()
    acc.procesar_linea(_RESULT_ERROR)
    proc = _FakePopen([], returncode=1)

    api_agentes._finalizar_run(_MARCA, run_id, proc, acc)
    run = agentes.obtener_run(_MARCA, run_id)
    assert run["estado"] == "error"
    assert "presupuesto" in run["salida"].lower()


def test_finalizador_sin_result_y_rc_no_cero_es_error(entorno):
    run_id = _siembra_run(_MARCA)
    acc = skills.AcumuladorStream()  # nunca llego un result
    proc = _FakePopen([], returncode=2)

    api_agentes._finalizar_run(_MARCA, run_id, proc, acc)
    run = agentes.obtener_run(_MARCA, run_id)
    assert run["estado"] == "error"


def _esperar_hasta(cond, *, timeout=5.0, intervalo=0.02):
    """Sondea `cond()` hasta True o `timeout`. Los lanzadores ahora spawnean ASYNC
    (Popen dentro del slot de concurrencia, #116), asi que no se puede leer el estado
    justo tras llamar. Acotado: nunca espera para siempre."""
    import time

    fin = time.monotonic() + timeout
    while time.monotonic() < fin:
        if cond():
            return True
        time.sleep(intervalo)
    return bool(cond())


def test_lanzar_background_degrada_si_no_hay_claude(entorno, monkeypatch):
    """Si `claude` no esta en el PATH, el run se marca en error (en espanol), sin Popen."""
    monkeypatch.setattr(api_agentes.shutil, "which", lambda _: None)
    # Si intentara abrir Popen, fallaria el test (no debe llegar ahi).
    monkeypatch.setattr(
        api_agentes.subprocess, "Popen",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debe abrir Popen")),
    )
    carpeta = agentes.carpeta_agente(_MARCA)
    run_id = _siembra_run(_MARCA)

    # Llamamos a la implementacion REAL (otros tests pudieron inyectar una fake en el modulo).
    _LANZADOR_REAL(_MARCA, run_id, "p", cwd=carpeta)

    # Spawn async (dentro del slot): sondeamos el estado terminal.
    _esperar_hasta(lambda: (agentes.obtener_run(_MARCA, run_id) or {}).get("estado") == "error")
    run = agentes.obtener_run(_MARCA, run_id)
    assert run["estado"] == "error"
    assert "asistente" in run["salida"].lower()


def test_lanzar_background_usa_stream_json_y_verbose(entorno, monkeypatch):
    """El argv del Popen incluye --output-format stream-json --verbose (sin claude real)."""
    capturado = {}

    monkeypatch.setattr(api_agentes.shutil, "which", lambda _: "/usr/bin/claude")

    class _PopenInerte:
        def __init__(self, argv, **kwargs):
            capturado["argv"] = argv
            capturado["cwd"] = kwargs.get("cwd")
            self.stdout = iter(())  # sin lineas: el lector no hace nada
            self.returncode = 0

        def wait(self, timeout=None):
            return 0

        def kill(self):
            pass

    monkeypatch.setattr(api_agentes.subprocess, "Popen", _PopenInerte)
    carpeta = agentes.carpeta_agente(_MARCA)
    run_id = _siembra_run(_MARCA)

    # Implementacion REAL (otros tests pudieron inyectar una fake en el atributo de modulo).
    _LANZADOR_REAL(_MARCA, run_id, "haz algo", cwd=carpeta)
    # Spawn async (dentro del slot): sondeamos a que el Popen se haya invocado.
    _esperar_hasta(lambda: "argv" in capturado)

    argv = capturado["argv"]
    assert argv[:2] == ["claude", "-p"]
    assert "haz algo" in argv
    assert "--output-format" in argv and "stream-json" in argv
    assert "--verbose" in argv
    assert capturado["cwd"] == str(carpeta)
