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

ENDURECIMIENTO PERMANENTE (#137): la generacion se hace —y se SEGUIRA haciendo— con el
subprocess `claude -p` (ahora en un sandbox por usuario; ver ADR 0001), NO con la API de
Claude. Por tanto este runner de subprocesos NO desaparece: las medidas de robustez son
deuda PERMANENTE, no contencion transitoria. Hay que tenerlas bien:
  - Cola con TOPE (`KENI_MAX_COLA`): antes `slot()` solo limitaba procesos CONCURRENTES,
    no la COLA. N peticiones = N hilos daemon bloqueados en `sem.acquire()` sin limite
    superior. Ahora `slot()` rechaza con `ColaLlenaError` cuando ya hay demasiados jobs
    esperando (el llamante lo traduce a 429) en vez de apilar hilos indefinidamente.
  - GRUPO DE PROCESOS: `lanzar_proc()` arranca `claude` con `start_new_session=True`
    (lider de su propio grupo). Al timeout/cancel `matar_arbol()` mata el GRUPO entero,
    no solo el padre: evita herramientas hijas zombis que `claude` haya lanzado.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from .. import config
from . import stream

_log = logging.getLogger("keni_consola.runner")

# Máximo de líneas de stderr que retenemos del subproceso (las ÚLTIMAS): para loguear el
# motivo de un fallo sin crecer sin límite. El stderr se DRENA en un hilo daemon desde el
# arranque (ver `_DrenadorStderr` / `lanzar_proc`); si no, `claude --verbose` puede llenar
# el buffer de la tubería (~64 KB) y BLOQUEARSE escribiendo en stderr → deja de producir
# stdout → `leer_stream` espera para siempre (deadlock). Drenar en paralelo lo evita.
_MAX_STDERR_LINEAS = 2000


class _DrenadorStderr:
    """Drena el stderr de un subproceso en un hilo daemon, reteniendo las últimas líneas.

    Evita el deadlock por buffer de tubería lleno (claude bloqueado escribiendo en stderr
    mientras `leer_stream` espera stdout). `texto()` espera brevemente al hilo y devuelve lo
    capturado (acotado a `_MAX_STDERR_LINEAS`)."""

    def __init__(self, pipe: object) -> None:
        self._lineas: deque[str] = deque(maxlen=_MAX_STDERR_LINEAS)
        self._hilo = threading.Thread(target=self._drenar, args=(pipe,), daemon=True)
        self._hilo.start()

    def _drenar(self, pipe: object) -> None:
        if pipe is None:
            return
        try:
            for linea in pipe:  # iteración línea a línea (text mode, bufsize=1)
                self._lineas.append(linea)
        except Exception:  # noqa: BLE001 -- drenar stderr nunca debe romper nada
            pass

    def texto(self, *, timeout: float = 1.0) -> str:
        self._hilo.join(timeout=timeout)
        return "".join(self._lineas)


class ColaLlenaError(RuntimeError):
    """La cola de jobs `claude` esta al tope: rechazar (429) en vez de encolar mas.

    PERMANENTE (#137): como la generacion es subprocess `claude -p` (ADR 0001), un pico
    de peticiones no debe traducirse en una pila ilimitada de hilos bloqueados. El
    llamante captura esta excepcion y devuelve una respuesta clara (429) al cliente.
    """

# Cada cuanto (s) se persiste el avance: con parciales llegan muchos eventos por
# segundo; throttlear evita martillear el disco sin perder la sensacion de "en vivo".
THROTTLE_S = 0.4


def argv_claude(prompt: str, *, dirs_permitidos: list[Path] | None = None) -> list[str]:
    """argv de `claude -p <prompt> --output-format stream-json --verbose
    --include-partial-messages [--disallowed-tools ...] [--effort N]
    [--max-budget-usd N] [--max-turns N] [--add-dir D ...]`. Sin shell (prompt como
    argumento de la lista).

    Es la fuente UNICA del argv para los dos lanzadores: asi ambos aplican SIEMPRE
    `--max-turns`/`--max-budget-usd` (antes los runs de agente no los ponian) Y la
    restriccion de herramientas (`arg_tools_restringidas`), defensa frente a inyeccion.
    """
    from .. import preferencias  # import perezoso: evita ciclo dominio<-paquete

    extra: list[str] = []
    for d in dirs_permitidos or []:
        extra += ["--add-dir", str(d)]
    return [
        "claude", "-p", prompt,
        "--output-format", "stream-json", "--verbose", "--include-partial-messages",
        # Headless: sin esto `claude` se cuelga al usar una tool (WebFetch/Read) porque no
        # hay forma de aprobar el permiso en `-p`. NO es "el flag de skills": no usamos el
        # motor de skills; el contexto se inyecta en el prompt. Acotado por cwd neutro + topes.
        *stream.arg_skip_permisos(),
        # Defensa contra prompt-injection: aunque corramos con skip-permissions, vetamos
        # por defecto `Bash`/`Write`/`Edit` (comandos/escritura), que ningun flujo de
        # generacion necesita. Web/Read quedan para investigacion y verificacion (corroborar).
        # Ver `arg_tools_restringidas` y `config.claude_disallowed_tools`.
        *stream.arg_tools_restringidas(),
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
    except Exception:  # noqa: BLE001 -- el lector nunca propaga, pero deja rastro
        _log.warning("error leyendo el stream de claude (ignorado)", exc_info=True)


def lanzar_proc(
    argv: list[str],
    *,
    cwd: str,
    env: dict[str, str] | None = None,
) -> subprocess.Popen:
    """Arranca `claude` en SU PROPIO grupo de procesos (lider de sesion).

    PERMANENTE (#137): `start_new_session=True` hace al hijo lider de un grupo nuevo, asi
    `matar_arbol()` puede senalizar al GRUPO entero (padre + herramientas hijas que
    `claude` lance). Sin esto, un `proc.kill()` mataba SOLO el padre y dejaba zombis.
    En Windows no hay grupos POSIX, pero el piloto corre en macOS/Linux. argv como lista
    (sin shell). El llamante elige stdout/stderr/text via los kwargs fijos de aqui.

    `stderr=PIPE` (antes DEVNULL): los errores de `claude` (auth, flag invalido, crash) se
    capturan para loguearlos si returncode != 0. CRÍTICO: el stderr se DRENA EN PARALELO
    desde el arranque (hilo daemon `_DrenadorStderr`), NO solo al cerrar. Con `--verbose` y
    un prompt grande, `claude` puede escribir > 64 KB en stderr; si nadie lo drena, el buffer
    de la tubería se llena, `claude` se BLOQUEA escribiendo en stderr y deja de producir
    stdout → `leer_stream` espera para siempre (deadlock observado en imports grandes). El
    drenador retiene las últimas líneas para `_loguear_stderr`.
    """
    proc = subprocess.Popen(  # noqa: S603 -- argv lista, sin shell
        argv,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    # Drena stderr YA (hilo daemon): evita el deadlock por buffer de tubería lleno.
    proc._keni_stderr = _DrenadorStderr(proc.stderr)  # type: ignore[attr-defined]
    return proc


def matar_arbol(proc: subprocess.Popen, *, espera: float = 10.0) -> None:
    """Mata el ARBOL COMPLETO del subproceso (su grupo de procesos), no solo el padre.

    PERMANENTE (#137): manda SIGKILL al GRUPO (`os.killpg(getpgid(pid), SIGKILL)`) para
    arrastrar a las herramientas hijas que `claude` haya lanzado. Si el grupo ya no
    existe (carrera con la salida) o la plataforma no soporta `killpg`, degrada a
    `proc.kill()`. Best-effort: nunca propaga. Tras matar, espera al padre para reapear.
    """
    try:
        pgid = os.getpgid(proc.pid)
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError, AttributeError):
        # Sin grupo (ya muerto) o plataforma sin killpg: matar al menos el padre.
        try:
            proc.kill()
        except Exception:  # noqa: BLE001 -- best-effort; ya intentamos el grupo
            pass
    try:
        proc.wait(timeout=espera)
    except Exception:  # noqa: BLE001 -- best-effort; reapeo del padre
        pass


# Tope de chars del stderr que logueamos (un crash de `claude` puede volcar mucho).
_MAX_STDERR_LOG = 4096


def _loguear_stderr(proc: subprocess.Popen) -> None:
    """Si el proceso acabo con returncode != 0/None, loguea su stderr (truncado).

    El stderr lo capturó EN PARALELO el `_DrenadorStderr` que monta `lanzar_proc` (no se
    lee aquí del pipe: a estas alturas el drenador ya lo agotó). Best-effort: nunca rompe el
    cierre. Antes iba a DEVNULL y un fallo de `claude` (auth, flag inválido, crash) era mudo.
    """
    rc = proc.returncode
    if rc is None or rc == 0:
        return
    dren = getattr(proc, "_keni_stderr", None)
    try:
        if dren is not None:
            err = dren.texto()
        elif proc.stderr is not None:
            err = proc.stderr.read() or ""
        else:
            return
    except Exception:  # noqa: BLE001 -- leer el stderr nunca debe romper la finalizacion
        return
    err = err.strip()
    if not err:
        return
    if len(err) > _MAX_STDERR_LOG:
        err = err[:_MAX_STDERR_LOG] + "…"
    _log.warning("claude terminó con returncode=%s; stderr: %s", rc, err)


def esperar(proc: subprocess.Popen, timeout: int) -> bool:
    """Espera al proceso con wall-timeout; si lo supera mata el ARBOL y devuelve True.

    PERMANENTE (#137): el timeout ahora mata el GRUPO de procesos (via `matar_arbol`), no
    solo el padre, para no dejar herramientas hijas huerfanas. Al cerrar, si el proceso
    acabo con returncode != 0, loguea su stderr (`_loguear_stderr`) para no perder el
    motivo del fallo (antes iba a DEVNULL).
    """
    try:
        proc.wait(timeout=timeout)
        _loguear_stderr(proc)
        return False
    except subprocess.TimeoutExpired:
        matar_arbol(proc)
        _loguear_stderr(proc)
        return True


# --------------------------------------------------------------------------- #
# Limite de concurrencia (semaforo por valor de KENI_MAX_JOBS)                 #
# --------------------------------------------------------------------------- #


def max_jobs() -> int:
    """Maximo de jobs `claude` simultaneos (`KENI_MAX_JOBS`, def 4, minimo 1)."""
    return config.max_jobs()


def max_cola() -> int:
    """Maximo de jobs ESPERANDO un slot (`KENI_MAX_COLA`, def 16, minimo 0).

    PERMANENTE (#137): TOPE de la cola, distinto del de concurrencia. Cuando hay este
    numero de jobs ya en espera, `slot()` rechaza el siguiente con `ColaLlenaError` en
    vez de apilar otro hilo bloqueado. 0 = no se admite NINGUN job en cola (solo los
    que entran sin esperar). El default (16) deja holgura para picos del piloto.
    """
    return config.max_cola()


# Un semaforo por VALOR de limite: en produccion el limite es constante (1 semaforo);
# en tests, cambiar `KENI_MAX_JOBS` da un semaforo distinto -> aislamiento sin estado
# global pegajoso. BoundedSemaphore: un release de mas es un bug y revienta (lo veriamos).
_sems: dict[int, threading.BoundedSemaphore] = {}
_sems_lock = threading.Lock()

# ADMISION (#137): contador de jobs ADMITIDOS (esperando un slot + corriendo). Es la
# cuenta autoritativa para el tope total = max_jobs() + max_cola(). `admitir()` lo sube
# de forma ATOMICA (rechaza si se pasaria del tope) y cada job lo baja al terminar. Asi
# el rechazo por cola llena es SINCRONO (el llamante responde 429) y NO se apilan hilos
# daemon bloqueados sin limite, que era el bug original.
_admitidos = 0
_admision_lock = threading.Lock()


def _semaforo() -> threading.BoundedSemaphore:
    n = max_jobs()
    with _sems_lock:
        sem = _sems.get(n)
        if sem is None:
            sem = threading.BoundedSemaphore(n)
            _sems[n] = sem
        return sem


def admitir() -> None:
    """Admite SINCRONAMENTE un job en el sistema, o lo rechaza con `ColaLlenaError`.

    PERMANENTE (#137): se llama ANTES de lanzar el hilo del job. El tope total es
    `max_jobs()` (procesos concurrentes) + `max_cola()` (espera). Si admitir este job
    superaria ese tope, lanza `ColaLlenaError` (-> 429) y NO se encola otro hilo. Si
    admite, incrementa el contador; el job DEBE llamar a `liberar_admision()` al
    terminar (lo hace `slot()` por el, ver abajo).
    """
    global _admitidos
    tope = max_jobs() + max_cola()
    with _admision_lock:
        if _admitidos >= tope:
            raise ColaLlenaError(
                "La cola de generaciones está llena; inténtalo de nuevo en unos segundos."
            )
        _admitidos += 1


def liberar_admision() -> None:
    """Libera la admision de un job (lo decrementa). Idempotencia: nunca baja de 0."""
    global _admitidos
    with _admision_lock:
        if _admitidos > 0:
            _admitidos -= 1


def admitidos() -> int:
    """Jobs admitidos ahora mismo (esperando + corriendo). Para tests/inspeccion."""
    with _admision_lock:
        return _admitidos


@contextmanager
def slot(
    on_encolado: Callable[[], None] | None = None,
    *,
    ya_admitido: bool = False,
) -> Iterator[None]:
    """Reserva un hueco de ejecucion; si no hay, ESPERA (job en cola).

    `on_encolado()` (opcional) se llama UNA vez si hubo que esperar (para reflejar la
    cola en el estado). La espera no es infinita: cada job tiene wall-timeout, asi que
    los slots siempre acaban liberandose.

    TOPE DE COLA PERMANENTE (#137): la admision se decide ANTES en `admitir()` (rechazo
    sincrono -> 429). Aqui `slot()` solo bloquea hasta tener un proceso concurrente
    libre. `ya_admitido=True` indica que el llamante YA pidio `admitir()` (asi `slot()`
    se encarga de `liberar_admision()` al salir, pase lo que pase). Si `ya_admitido` es
    False (camino legado/tests del semaforo puro), `slot()` admite el job el mismo: si
    la cola esta al tope, rechaza con `ColaLlenaError`.
    """
    if not ya_admitido:
        admitir()  # puede lanzar ColaLlenaError
    sem = _semaforo()
    try:
        if not sem.acquire(blocking=False):
            if on_encolado is not None:
                try:
                    on_encolado()
                except Exception:  # noqa: BLE001 -- reflejar la cola nunca rompe el job
                    pass
            sem.acquire()  # espera acotada por el wall-timeout de los jobs en curso
        try:
            yield
        finally:
            sem.release()
    finally:
        liberar_admision()
