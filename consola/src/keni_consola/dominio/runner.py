"""Runner UNICO de `claude -p` en streaming para los jobs en segundo plano (#116).

Antes habia DOS lanzadores casi identicos —`generaciones.lanzar_job_claude` y
`api/agentes.lanzar_run_background`— que ademas DIVERGIAN: los runs de agente no
aplicaban `--max-turns` (sin tope de turnos => sin tope de coste por turnos) y
dependian de `api.skills` (acoplamiento api->api). Aqui viven las MECANICAS
compartidas (argv, lectura de stream con throttle, espera con wall-timeout y kill);
cada llamante conserva SU finalizacion (generaciones post-procesa y guarda
`resultado`; los runs solo guardan el texto).

CONCURRENCIA (#116 / R-NO-LIMIT): sin tope, N peticiones lanzaban N procesos `claude`
a la vez (CPU/RAM/rate-limit/coste). `slot()` aplica un semaforo (`KENI_MAX_JOBS`,
def 4): los jobs que no caben ESPERAN un hueco (quedan en cola). No hay espera
infinita: cada job tiene wall-timeout (mata el proceso), asi que los slots SIEMPRE
se liberan.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from . import stream

# Cada cuanto (s) se persiste el avance: con parciales llegan muchos eventos por
# segundo; throttlear evita martillear el disco sin perder la sensacion de "en vivo".
THROTTLE_S = 0.4


def argv_claude(prompt: str, *, dirs_permitidos: list[Path] | None = None) -> list[str]:
    """argv de `claude -p <prompt> --output-format stream-json --verbose
    --include-partial-messages [--effort N] [--max-budget-usd N] [--max-turns N]
    [--add-dir D ...]`. Sin shell (prompt como argumento de la lista).

    Es la fuente UNICA del argv para los dos lanzadores: asi ambos aplican SIEMPRE
    `--max-turns`/`--max-budget-usd` (antes los runs de agente no los ponian).
    """
    from .. import preferencias  # import perezoso: evita ciclo dominio<-paquete

    extra: list[str] = []
    for d in dirs_permitidos or []:
        extra += ["--add-dir", str(d)]
    return [
        "claude", "-p", prompt,
        "--output-format", "stream-json", "--verbose", "--include-partial-messages",
        *preferencias.arg_esfuerzo(),
        *stream.arg_presupuesto(),
        *stream.arg_max_turns(),
        *extra,
    ]


def leer_stream(
    proc: subprocess.Popen,
    acumulador: stream.AcumuladorStream,
    on_avance: Callable[[], None],
    *,
    throttle: float = THROTTLE_S,
) -> None:
    """Hilo lector: alimenta el acumulador con el NDJSON y persiste el avance (throttled).

    Persiste al cambiar de turno (hito) o cada `throttle` s; NUNCA en la linea terminal
    (`result`), porque el cierre fija el estado final. Tolerante: una linea no JSON se
    ignora y cualquier fallo se traga (el lector nunca propaga; el cierre fija el estado).
    """
    if proc.stdout is None:
        return
    ultimo = 0.0
    ultimo_turno = -1
    try:
        for linea in proc.stdout:
            acumulador.procesar_linea(linea)
            if acumulador.terminado:
                continue
            ahora = time.monotonic()
            if acumulador.turnos != ultimo_turno or (ahora - ultimo) >= throttle:
                ultimo, ultimo_turno = ahora, acumulador.turnos
                try:
                    on_avance()
                except Exception:  # noqa: BLE001 -- el avance nunca debe romper el hilo
                    pass
    except Exception:  # noqa: BLE001 -- el lector nunca propaga
        pass


def esperar(proc: subprocess.Popen, timeout: int) -> bool:
    """Espera al proceso con wall-timeout; si lo supera lo MATA y devuelve True (timeout)."""
    try:
        proc.wait(timeout=timeout)
        return False
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=10)
        except Exception:  # noqa: BLE001 -- best-effort; ya marcamos timeout
            pass
        return True


# --------------------------------------------------------------------------- #
# Limite de concurrencia (semaforo por valor de KENI_MAX_JOBS)                 #
# --------------------------------------------------------------------------- #


def max_jobs() -> int:
    """Maximo de jobs `claude` simultaneos (`KENI_MAX_JOBS`, def 4, minimo 1)."""
    try:
        n = int(os.environ.get("KENI_MAX_JOBS", "4"))
    except (TypeError, ValueError):
        n = 4
    return max(1, n)


# Un semaforo por VALOR de limite: en produccion el limite es constante (1 semaforo);
# en tests, cambiar `KENI_MAX_JOBS` da un semaforo distinto -> aislamiento sin estado
# global pegajoso. BoundedSemaphore: un release de mas es un bug y revienta (lo veriamos).
_sems: dict[int, threading.BoundedSemaphore] = {}
_sems_lock = threading.Lock()


def _semaforo() -> threading.BoundedSemaphore:
    n = max_jobs()
    with _sems_lock:
        sem = _sems.get(n)
        if sem is None:
            sem = threading.BoundedSemaphore(n)
            _sems[n] = sem
        return sem


@contextmanager
def slot(on_encolado: Callable[[], None] | None = None) -> Iterator[None]:
    """Reserva un hueco de ejecucion; si no hay, ESPERA (job en cola).

    `on_encolado()` (opcional) se llama UNA vez si hubo que esperar (para reflejar la
    cola en el estado). La espera no es infinita: cada job tiene wall-timeout, asi que
    los slots siempre acaban liberandose.
    """
    sem = _semaforo()
    if not sem.acquire(blocking=False):
        if on_encolado is not None:
            try:
                on_encolado()
            except Exception:  # noqa: BLE001 -- reflejar la cola nunca debe romper el job
                pass
        sem.acquire()
    try:
        yield
    finally:
        sem.release()
