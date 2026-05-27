"""dominio.runner: argv unico (con --max-turns) + semaforo de concurrencia (#116).

Antes habia dos lanzadores `claude -p` duplicados; los runs de agente NO aplicaban
`--max-turns` y nada topaba la concurrencia. Estos tests fijan ese contrato.

ANTI-CUELGUE: todo acotado (Barrier/Event/Timer/join con timeout) + `pytest-timeout`
de backstop. Nada puede esperar para siempre.
"""

from __future__ import annotations

import os
import sys
import threading
import time

import pytest

from keni_consola.dominio import runner


@pytest.mark.timeout(15)
def test_argv_incluye_max_turns_y_presupuesto(monkeypatch):
    monkeypatch.setenv("KENI_CLAUDE_MAX_TURNS", "5")
    monkeypatch.setenv("KENI_CLAUDE_MAX_USD", "1.5")
    argv = runner.argv_claude("hola mundo")
    assert argv[:3] == ["claude", "-p", "hola mundo"]
    assert "--max-turns" in argv and argv[argv.index("--max-turns") + 1] == "5"
    assert "--max-budget-usd" in argv
    assert "--output-format" in argv and "stream-json" in argv and "--verbose" in argv


@pytest.mark.timeout(15)
def test_argv_add_dir_por_cada_permitido():
    argv = runner.argv_claude("p", dirs_permitidos=[__import__("pathlib").Path("/tmp/a")])
    assert "--add-dir" in argv and "/tmp/a" in argv


@pytest.mark.timeout(20)
def test_slot_nunca_supera_el_limite(monkeypatch):
    monkeypatch.setenv("KENI_MAX_JOBS", "2")
    activos = 0
    pico = 0
    lock = threading.Lock()
    suelta = threading.Event()
    arranque = threading.Barrier(3, timeout=5)

    def trabajo():
        nonlocal activos, pico
        arranque.wait()
        with runner.slot():
            with lock:
                activos += 1
                pico = max(pico, activos)
            assert suelta.wait(timeout=5)  # mantiene ocupado el slot
            with lock:
                activos -= 1

    hilos = [threading.Thread(target=trabajo) for _ in range(3)]
    for h in hilos:
        h.start()
    time.sleep(0.5)  # margen para que 2 entren y el 3o quede en cola
    with lock:
        assert pico <= 2, f"se superó el limite de concurrencia: {pico}"
        assert activos == 2, f"esperaba 2 dentro y 1 en cola, hay {activos}"
    suelta.set()  # liberamos: el 3o ya puede entrar
    for h in hilos:
        h.join(timeout=5)
        assert not h.is_alive(), "hilo colgado"
    assert pico == 2  # llegó a 2, nunca a 3


@pytest.mark.timeout(15)
def test_on_encolado_se_llama_si_hay_cola(monkeypatch):
    monkeypatch.setenv("KENI_MAX_JOBS", "1")
    encolado: list[int] = []
    dentro = threading.Event()
    suelta = threading.Event()

    def ocupa():
        with runner.slot():
            dentro.set()
            suelta.wait(timeout=5)

    h = threading.Thread(target=ocupa)
    h.start()
    assert dentro.wait(timeout=5)  # el unico slot esta ocupado
    # Liberamos el slot tras un instante, MIENTRAS el main espera en slot().
    threading.Timer(0.3, suelta.set).start()
    with runner.slot(on_encolado=lambda: encolado.append(1)):
        pass  # entra cuando `ocupa` suelta
    h.join(timeout=5)
    assert not h.is_alive()
    assert encolado == [1], "on_encolado debia llamarse una vez (habia cola)"


# --------------------------------------------------------------------------- #
# Tope de COLA (#137): cuando la cola esta al tope, se RECHAZA con ColaLlena.  #
# --------------------------------------------------------------------------- #


@pytest.mark.timeout(20)
def test_cola_al_tope_rechaza_con_cola_llena(monkeypatch):
    """Con 1 slot + 1 de cola (tope total = 2), el 3o NO se encola: ColaLlenaError.

    Antes `slot()` solo limitaba CONCURRENTES: N peticiones = N hilos daemon esperando
    sin limite. Ahora la admision (running + en cola) tiene tope y rechaza el exceso.
    """
    monkeypatch.setenv("KENI_MAX_JOBS", "1")
    monkeypatch.setenv("KENI_MAX_COLA", "1")
    suelta = threading.Event()
    corriendo = threading.Event()
    en_cola_ev = threading.Event()

    def corre():  # ocupa el unico slot
        with runner.slot():
            corriendo.set()
            assert suelta.wait(timeout=10)

    def encola():  # admitido, pero ESPERA el slot (ocupa el unico hueco de cola)
        with runner.slot(on_encolado=en_cola_ev.set):
            pass

    a = threading.Thread(target=corre)
    a.start()
    assert corriendo.wait(timeout=5)
    b = threading.Thread(target=encola)
    b.start()
    assert en_cola_ev.wait(timeout=5), "el 2o debia quedar en cola"
    # Margen para que `b` incremente el contador de admision antes de medir.
    time.sleep(0.2)
    assert runner.admitidos() == 2, f"esperaba 2 admitidos (1 corre + 1 en cola), hay {runner.admitidos()}"

    # El 3o: la cola esta al tope -> RECHAZO sincrono.
    with pytest.raises(runner.ColaLlenaError):
        runner.admitir()
    # `slot()` (que admite por dentro) tambien debe rechazar.
    with pytest.raises(runner.ColaLlenaError):
        with runner.slot():
            pass

    suelta.set()  # liberamos: ambos hilos terminan y se libera la admision
    a.join(timeout=5)
    b.join(timeout=5)
    assert not a.is_alive() and not b.is_alive()
    # Tras drenar, vuelve a haber sitio.
    assert runner.admitidos() == 0
    runner.admitir()
    runner.liberar_admision()


@pytest.mark.timeout(15)
def test_admitir_se_libera_en_finally_del_slot(monkeypatch):
    """`slot()` libera SIEMPRE la admision al salir (no se fuga el cupo)."""
    monkeypatch.setenv("KENI_MAX_JOBS", "1")
    monkeypatch.setenv("KENI_MAX_COLA", "0")
    assert runner.admitidos() == 0
    with runner.slot():
        assert runner.admitidos() == 1
    assert runner.admitidos() == 0  # liberado en el finally


# --------------------------------------------------------------------------- #
# Grupo de procesos (#137): matar_arbol mata el ARBOL, no solo el padre.       #
# --------------------------------------------------------------------------- #


def _vivo(pid: int) -> bool:
    """True si el proceso `pid` sigue vivo (kill 0 no senaliza, solo comprueba)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # existe pero no es nuestro (no deberia pasar en el test)
    return True


@pytest.mark.timeout(20)
@pytest.mark.skipif(os.name != "posix", reason="grupos de procesos POSIX")
def test_matar_arbol_mata_el_hijo_no_solo_el_padre():
    """`lanzar_proc` arranca en su propio grupo; `matar_arbol` mata padre + nieto.

    El padre (python) lanza un HIJO (otro python que duerme) en el MISMO grupo, imprime
    su PID y espera. `matar_arbol` debe matar el grupo entero: tras el kill, el HIJO ya
    no debe estar vivo (antes, un `proc.kill()` del padre lo dejaba huerfano/zombi).
    """
    # El padre imprime el PID del hijo y se queda esperando; el hijo duerme 300s.
    guion = (
        "import subprocess, sys, time\n"
        "h = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'])\n"
        "print(h.pid, flush=True)\n"
        "time.sleep(300)\n"
    )
    proc = runner.lanzar_proc([sys.executable, "-c", guion], cwd=os.getcwd())
    try:
        linea = proc.stdout.readline()  # PID del nieto
        hijo_pid = int(linea.strip())
        assert _vivo(hijo_pid), "el hijo deberia estar vivo antes de matar"
        runner.matar_arbol(proc)
        # Damos un instante a que el SO reape al grupo.
        for _ in range(50):
            if not _vivo(hijo_pid):
                break
            time.sleep(0.1)
        assert not _vivo(hijo_pid), "matar_arbol debio matar tambien al hijo (todo el grupo)"
        assert proc.poll() is not None, "el padre tambien debe estar muerto"
    finally:
        runner.matar_arbol(proc)  # best-effort por si algo quedo vivo


@pytest.mark.timeout(20)
@pytest.mark.skipif(os.name != "posix", reason="grupos de procesos POSIX")
def test_esperar_timeout_mata_el_arbol():
    """`esperar` con timeout=0-ish mata el arbol y devuelve True (timeout)."""
    proc = runner.lanzar_proc(
        [sys.executable, "-c", "import time; time.sleep(300)"], cwd=os.getcwd()
    )
    try:
        timed_out = runner.esperar(proc, timeout=1)
        assert timed_out is True
        assert proc.poll() is not None, "el proceso debio morir por timeout"
    finally:
        runner.matar_arbol(proc)
