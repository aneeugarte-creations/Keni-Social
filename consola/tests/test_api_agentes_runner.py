"""Tests del ENDURECIMIENTO del runner para los runs de agente (#152, reutiliza #137).

#137 endurecio el runner de las GENERACIONES de copy (grupo de procesos con
`start_new_session=True`, `matar_arbol()` con `os.killpg(SIGKILL)`, cancelacion,
admision con tope de cola). #152 lleva ese MISMO endurecimiento a la otra via, los runs
de agente (`/api/agentes/{id}/runs`), que antes usaban un `Popen` crudo sin grupo de
proceso, sin cancelacion y sin admision previa.

Cubre, espejando los tests de `test_generaciones.py`:
  - GRUPO DE PROCESOS + KILL DEL ARBOL: un run real spawnea un padre que lanza un HIJO en
    su propio grupo; al cancelar, el ARBOL entero (incluido el hijo) muere -> sin zombis.
  - ADMISION: con la cola al tope, lanzar otro run rechaza con `ColaLlenaError` (la API lo
    traduce a 429) en vez de apilar otro hilo daemon bloqueado.
  - CANCELACION (endpoint): `POST .../runs/{id}/cancelar` cancela tanto un run EN VUELO
    como uno aun PENDIENTE (que se finaliza como cancelado sin spawnear `claude`).

Igual que el resto de la suite de agentes: aislado en tmp (`entorno`); NUNCA se llama a
`claude` real (parcheamos `runner.lanzar_proc`/`shutil.which`); la admision se libera en
`finally` para no contaminar el `_admitidos` global entre tests.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import time

import pytest

from keni_consola import agentes
from keni_consola.api import agentes as api_agentes
from keni_consola.dominio import runner

from .conftest import _cliente

# Una marca real del catalogo para las pruebas.
_MARCA = "unotv"

# El lanzador REAL, capturado AL IMPORTAR (antes de que cualquier `crear_app`/`_cliente` de
# otro test reasigne `api_agentes.lanzar_run_background` por un fake). Los tests que ejercitan
# el spawn/grupo/cancelacion reales lo inyectan EXPLICITAMENTE para no heredar el fake que
# dejo un test anterior (la reasignacion es a nivel de modulo y es pegajosa entre tests).
_LANZAR_RUN_REAL = api_agentes.lanzar_run_background

pytestmark = pytest.mark.timeout(30)


def _vivo(pid: int) -> bool:
    """True si el proceso `pid` sigue vivo (kill 0 no senaliza, solo comprueba)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # existe pero no es nuestro (no deberia pasar en el test)
    return True


def _esperar_terminal(marca_id: str, run_id: str, timeout: float = 10.0) -> str:
    """Espera a que el run alcance un estado TERMINAL (no `ejecutando`).

    Mas robusto que mirar el handle: el handle se registra DENTRO del slot (puede tardar) y
    se suelta tras fijar el estado, asi que esperar el estado terminal evita carreras.
    """
    fin = time.monotonic() + timeout
    while time.monotonic() < fin:
        run = agentes.obtener_run(marca_id, run_id)
        if run is not None and run["estado"] != "ejecutando":
            return run["estado"]
        time.sleep(0.05)
    return (agentes.obtener_run(marca_id, run_id) or {}).get("estado", "")


# --------------------------------------------------------------------------- #
# Grupo de procesos + kill del arbol (#152): cancelar NO deja hijos huerfanos. #
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(os.name != "posix", reason="grupos de procesos POSIX")
def test_run_spawnea_en_su_grupo_y_cancelar_mata_el_arbol(entorno, monkeypatch):
    """Un run real arranca en SU PROPIO grupo; cancelar mata el ARBOL (padre + hijo).

    Espeja `test_cancelar_mata_el_arbol_y_marca_cancelado` de las generaciones: sustituimos
    `runner.lanzar_proc` por uno que arranca un arbol REAL (padre python + hijo que duerme,
    en su propio grupo) que emite una linea NDJSON y se queda vivo. Cancelamos via el
    dominio: el hijo NO debe quedar huerfano/zombi (el bug que motivaba #152), y el run
    queda terminal con `motivo="cancelado"`.
    """
    monkeypatch.setattr(api_agentes.shutil, "which", lambda _n: "/usr/bin/claude")

    pids: dict[str, int] = {}
    # El padre imprime el PID del hijo (por stderr), emite una linea NDJSON valida (por
    # stdout, que es lo que lee el hilo lector) y se queda vivo. El hijo duerme 300 s.
    guion = (
        "import subprocess, sys, time\n"
        "h = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'])\n"
        "sys.stderr.write(str(h.pid) + '\\n'); sys.stderr.flush()\n"
        '''print('{"type": "stream_event", "event": {"type": "message_start", "message": {}}}', flush=True)\n'''
        "time.sleep(300)\n"
    )

    def _fake_lanzar(argv, *, cwd, env=None):  # noqa: ANN001
        # Mismo grupo de proceso que el real (`start_new_session=True`); abrimos stderr
        # para leer el PID del nieto. stdout sigue el contrato del lector (NDJSON).
        proc = subprocess.Popen(  # noqa: S603 -- argv lista controlada por el test
            [sys.executable, "-c", guion],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        pids["hijo"] = int(proc.stderr.readline().strip())
        return proc

    monkeypatch.setattr(api_agentes.runner, "lanzar_proc", _fake_lanzar)

    # Usamos el lanzador REAL (no el noop del cliente) para ejercitar el spawn/grupo/kill.
    c = _cliente(lanzar_run=_LANZAR_RUN_REAL)
    try:
        run_id = c.post(
            f"/api/agentes/{_MARCA}/runs", json={"prompt": "haz algo", "modo": "headless"}
        ).json()["run"]["id"]

        # Esperamos a que el proceso/hijo esten registrados.
        fin = time.monotonic() + 5
        while time.monotonic() < fin and "hijo" not in pids:
            time.sleep(0.05)
        assert "hijo" in pids and _vivo(pids["hijo"]), "el hijo deberia estar vivo antes de cancelar"

        assert api_agentes.cancelar_run(_MARCA, run_id) is True
        assert _esperar_terminal(_MARCA, run_id) == "error"

        # El ARBOL (incluido el hijo) debe haber muerto: NO quedan huerfanos.
        for _ in range(50):
            if not _vivo(pids["hijo"]):
                break
            time.sleep(0.1)
        assert not _vivo(pids["hijo"]), "cancelar debio matar el arbol entero (incluido el hijo)"

        run = agentes.obtener_run(_MARCA, run_id)
        assert run["estado"] == "error"
        assert run["motivo"] == "cancelado"
    finally:
        # Defensa: si algo quedo vivo, mata el grupo del nieto.
        if "hijo" in pids and _vivo(pids["hijo"]):
            with contextlib.suppress(Exception):
                os.killpg(os.getpgid(pids["hijo"]), 9)


# --------------------------------------------------------------------------- #
# Admision con tope de cola (#152): backpressure -> 429, no apilar hilos.       #
# --------------------------------------------------------------------------- #


def test_lanzar_run_rechaza_cuando_la_cola_esta_llena(entorno, monkeypatch):
    """Cola al tope -> `lanzar_run_background` lanza ColaLlenaError SINCRONAMENTE.

    La admision se decide ANTES de arrancar el hilo: con el cupo agotado, el llamante recibe
    la excepcion (que la API traduce a 429) en vez de apilar otro hilo daemon bloqueado.
    """
    monkeypatch.setenv("KENI_MAX_JOBS", "1")
    monkeypatch.setenv("KENI_MAX_COLA", "0")
    # Saturamos la admision manualmente (1 slot, 0 cola -> tope 1).
    runner.admitir()
    try:
        run = agentes.guardar_run(
            _MARCA,
            {"id": agentes.nuevo_run_id(), "prompt": "p", "modo": "headless",
             "estado": "ejecutando", "salida": "", "fecha_inicio": agentes.ahora_iso(),
             "fecha_fin": ""},
        )
        with pytest.raises(runner.ColaLlenaError):
            _LANZAR_RUN_REAL(
                _MARCA, run["id"], "hola", cwd=agentes.carpeta_agente(_MARCA)
            )
        # NO se creo ningun hilo de run extra para este id (no se admitio de mas).
        with api_agentes._HANDLES_LOCK:
            assert run["id"] not in api_agentes._HANDLES
    finally:
        runner.liberar_admision()


def test_crear_run_endpoint_responde_429_si_la_cola_esta_llena(entorno, monkeypatch):
    """El endpoint `POST .../runs` responde 429 cuando la cola esta al tope (#152).

    El lanzador REAL admite sincronicamente: con el cupo agotado propaga `ColaLlenaError`,
    que el manejador central de la app traduce a 429 (backpressure). El run queda marcado
    con `motivo="cola_llena"` para que la UI lo distinga.
    """
    monkeypatch.setenv("KENI_MAX_JOBS", "1")
    monkeypatch.setenv("KENI_MAX_COLA", "0")
    runner.admitir()  # saturamos el cupo (tope 1)
    try:
        c = _cliente(lanzar_run=_LANZAR_RUN_REAL)
        r = c.post(f"/api/agentes/{_MARCA}/runs", json={"prompt": "p", "modo": "headless"})
        assert r.status_code == 429
        # El run se persistio marcado como cola_llena (estado terminal, no "ejecutando").
        runs = agentes.listar_runs(_MARCA)
        assert runs and runs[0]["estado"] == "error"
        assert runs[0]["motivo"] == "cola_llena"
    finally:
        runner.liberar_admision()


# --------------------------------------------------------------------------- #
# Endpoint de cancelacion (#152): mata el arbol; pendiente y en vuelo.          #
# --------------------------------------------------------------------------- #


def test_cancelar_run_endpoint_marca_inexistente_404(entorno):
    r = _cliente().post("/api/agentes/no-existe/runs/algo/cancelar")
    assert r.status_code == 404


def test_cancelar_run_endpoint_run_inexistente_404(entorno):
    r = _cliente().post(f"/api/agentes/{_MARCA}/runs/noexiste/cancelar")
    assert r.status_code == 404


def test_cancelar_run_endpoint_idempotente_si_ya_termino(entorno):
    """Cancelar un run YA terminado (sin proceso en vuelo) devuelve el run tal cual (200)."""
    from .test_api_agentes import _lanzador_que_completa

    c = _cliente(lanzar_run=_lanzador_que_completa("listo"))
    run_id = c.post(f"/api/agentes/{_MARCA}/runs", json={"prompt": "p"}).json()["run"]["id"]
    r = c.post(f"/api/agentes/{_MARCA}/runs/{run_id}/cancelar")
    assert r.status_code == 200
    run = r.json()["run"]
    assert run["id"] == run_id
    # Sigue completado: no hay nada en vuelo que cancelar (idempotente).
    assert run["estado"] == "completado"


@pytest.mark.skipif(os.name != "posix", reason="grupos de procesos POSIX")
def test_cancelar_run_pendiente_no_spawnea_claude(entorno, monkeypatch):
    """Un run aun PENDIENTE (esperando slot, sin proceso) se cancela sin spawnear `claude`.

    Saturamos el unico slot con un job ficticio (sin liberar el semaforo) para que el run
    quede ESPERANDO en `slot()`. Cancelamos: el evento `cancelado` se arma; cuando el run
    logre entrar al slot, `lanzar_proc` NUNCA debe llamarse (matamos el arbol del proceso ya
    spawneado o, si aun no spawneo, el run finaliza como cancelado). Comprobamos que el run
    queda terminal con `motivo="cancelado"` y que `lanzar_proc` no produjo procesos vivos.
    """
    monkeypatch.setenv("KENI_MAX_JOBS", "1")
    monkeypatch.setenv("KENI_MAX_COLA", "4")
    monkeypatch.setattr(api_agentes.shutil, "which", lambda _n: "/usr/bin/claude")

    spawneos: list[int] = []

    def _fake_lanzar(argv, *, cwd, env=None):  # noqa: ANN001 -- registra y arranca un sleeper
        proc = subprocess.Popen(  # noqa: S603 -- argv controlada por el test
            [sys.executable, "-c", "import time; time.sleep(300)"],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        spawneos.append(proc.pid)
        return proc

    monkeypatch.setattr(api_agentes.runner, "lanzar_proc", _fake_lanzar)

    # Ocupamos el unico slot a mano (admision + adquirir el semaforo) y NO lo soltamos hasta
    # despues de cancelar: el run de prueba quedara ESPERANDO en `slot()`.
    runner.admitir()
    sem = runner._semaforo()
    assert sem.acquire(blocking=False), "el semaforo deberia estar libre al inicio del test"
    try:
        c = _cliente(lanzar_run=_LANZAR_RUN_REAL)
        run_id = c.post(
            f"/api/agentes/{_MARCA}/runs", json={"prompt": "p", "modo": "headless"}
        ).json()["run"]["id"]
        # El run esta admitido pero ATASCADO esperando el slot: aun sigue "ejecutando".
        time.sleep(0.3)
        assert agentes.obtener_run(_MARCA, run_id)["estado"] == "ejecutando"
        assert spawneos == [], "no debio spawnear `claude` mientras espera el slot"

        # Cancelamos el run PENDIENTE: arma el evento (no hay proceso aun -> False).
        api_agentes.cancelar_run(_MARCA, run_id)
    finally:
        # Soltamos el slot para que el run pueda entrar (y descubra que ya esta cancelado).
        sem.release()
        runner.liberar_admision()

    # Al entrar al slot con el evento ya armado, mata el arbol (si llego a spawnear) y
    # finaliza como cancelado. El run queda terminal con motivo cancelado.
    assert _esperar_terminal(_MARCA, run_id) == "error"
    run = agentes.obtener_run(_MARCA, run_id)
    assert run["motivo"] == "cancelado"
    # Si spawneo algo, debe estar muerto (matar_arbol); nunca un sleeper huerfano.
    for pid in spawneos:
        for _ in range(50):
            if not _vivo(pid):
                break
            time.sleep(0.1)
        assert not _vivo(pid), "el proceso spawneado debio morir (matar_arbol)"
