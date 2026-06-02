"""WORKER de generacion: clava jobs de la cola y corre `claude -p` (#130 Fase 2 / ADR 0002 Fase B).

DOS modos de ejecucion (se elige por entorno; ver `config.worker_externo`):

  - LOCAL / un solo proceso (def): el back arranca ESTE worker EN PROCESO, en un hilo de
    fondo (`iniciar_worker_inproceso`), llamado desde `__main__` (NO desde `crear_app`, para
    no arrancarlo en los tests). La UX de una sola maquina NO cambia: no hace falta un
    servicio aparte y `claude` esta en el mismo entorno que el back.

  - HOSTED: un servicio `worker` SEPARADO corre `python -m keni_consola.worker` (este
    modulo como entry-point). Consume la MISMA cola (Postgres compartido). El back arranca
    con `KENI_WORKER_EXTERNO=1` para NO arrancar su worker in-proceso. La imagen del worker
    SI lleva Node + `claude`; la del back ya NO (ADR 0002 Fase B).

POR QUE REUSA `generaciones.lanzar_job_claude`: ahi vive TODO el endurecimiento #137 que
hay que PRESERVAR (grupo de procesos propio, kill del ARBOL al timeout/cancel, tope de
concurrencia con `slot`, sin huerfanos, log correlacionado por job-id). El worker NO
reimplementa nada de eso: clava el job, reconstruye prompt+post-procesado+cwd desde el
`spec` (`dominio.jobspec`) y delega en `lanzar_job_claude(ya_admitido=True)` (el cupo de
admision ya lo tomo `encolar_job_claude`). Asi el comportamiento de ejecucion es identico
antes y despues del desacoplo.

CANCELACION CROSS-PROCESO: el back marca el job en la cola (`cola.cancelar`). Un hilo
vigia por job sondea `cola.cancelado(job_id)` y, al verlo, llama a `generaciones.cancelar`
(que arma el evento in-memoria y mata el arbol). Asi cancelar funciona aunque el job corra
en otro proceso. Un job AUN pendiente cancelado se finaliza como cancelado al clavarse, sin
lanzar `claude`.

REINICIAR EL BACK NO MATA LOS JOBS DEL WORKER: en hosted el worker es otro contenedor;
reiniciar el back no toca sus procesos. En local el worker es un hilo daemon del back: un
reinicio del back si lo para (un solo proceso), pero el registro queda persistido y el job
no se pierde (queda reclamado; se puede reaprovechar). El criterio de ADR 0002 ("reiniciar
el gateway no mata los jobs") lo cumple el modo hosted, que es el del servicio compartido.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid

from . import cola, config, generaciones
from .dominio import jobspec

_log = logging.getLogger("keni_consola.worker")

# Cuanto sondea el vigia de cancelacion el flag de la cola (s). Bajo para que cancelar
# se sienta inmediato sin martillear la BD.
_SONDEO_CANCELACION_S = 0.4


def _finalizar_cancelado(gen_id: str) -> None:
    """Deja el registro de un job (aun no lanzado) en estado terminal cancelado."""
    generaciones.actualizar(
        gen_id,
        {
            "estado": generaciones.ESTADO_ERROR,
            "motivo": generaciones.MOTIVO_CANCELADO,
            "error": "La generación fue cancelada.",
            "fecha_fin": generaciones.ahora_iso(),
        },
    )


def _finalizar_error(gen_id: str, mensaje: str) -> None:
    """Deja el registro de un job en error (spec corrupto / fallo de arranque)."""
    generaciones.actualizar(
        gen_id,
        {"estado": generaciones.ESTADO_ERROR, "error": mensaje, "fecha_fin": generaciones.ahora_iso()},
    )


def _vigilar_cancelacion(job_id: str, gen_id: str, parar: threading.Event) -> None:
    """Hilo vigia: sondea el flag de cancelacion de la cola y propaga al runner local.

    Mientras el job corre, mira `cola.cancelado(job_id)`; al verlo, llama a
    `generaciones.cancelar(gen_id)` (arma el evento in-memoria + mata el arbol) y termina.
    `parar` lo corta cuando el job ya alcanzo un estado terminal (no seguir sondeando).
    """
    while not parar.wait(_SONDEO_CANCELACION_S):
        try:
            if cola.cancelado(job_id):
                generaciones.cancelar(gen_id)
                return
        except Exception:  # noqa: BLE001 -- el vigia nunca debe romper el procesado del job
            _log.warning("worker: fallo al sondear cancelacion del job %s", job_id, exc_info=True)
            return


def procesar_job(job: dict, worker_id: str = "") -> None:
    """Ejecuta UN job ya clavado: reconstruye el trabajo y corre `claude -p` (con #137).

    `job` es `{id, gen_id, spec}` (spec ya deserializado, o None si estaba corrupto).
    Espera a que el registro alcance un estado TERMINAL antes de marcar el job terminado
    (asi el cupo de admision se libera ordenadamente y la cola refleja el fin real).
    """
    job_id = job["id"]
    gen_id = job["gen_id"]
    spec = job.get("spec")

    # Job ya cancelado (lo marcaron antes de clavarlo) o spec corrupto: finalizar SIN claude.
    if cola.cancelado(job_id):
        _finalizar_cancelado(gen_id)
        generaciones.runner.liberar_admision()  # el cupo lo tomo el encolado; liberar
        cola.terminar(job_id)
        return
    if not isinstance(spec, dict):
        _log.error("worker: job %s (gen %s) con spec invalido; no se ejecuta", job_id, gen_id)
        _finalizar_error(gen_id, "No se pudo iniciar la generación.")
        generaciones.runner.liberar_admision()
        cola.terminar(job_id)
        return

    try:
        procesar = jobspec.reconstruir_procesar(spec)
        cwd = jobspec.cwd(spec)
        dir_temporal = jobspec.dir_temporal(spec)
        prompt = spec.get("prompt", "")
        endurecer = jobspec.endurecer(spec)
    except Exception:  # noqa: BLE001 -- spec mal formado: error claro, sin traceback al cliente
        _log.exception("worker: no se pudo reconstruir el job %s (gen %s)", job_id, gen_id)
        _finalizar_error(gen_id, "No se pudo iniciar la generación.")
        generaciones.runner.liberar_admision()
        cola.terminar(job_id)
        return

    # Vigia de cancelacion cross-proceso, activo mientras el job corre.
    parar = threading.Event()
    vigia = threading.Thread(
        target=_vigilar_cancelacion, args=(job_id, gen_id, parar),
        name=f"cancel-{job_id}", daemon=True,
    )
    vigia.start()

    try:
        # El runner real (con TODO el #137). `ya_admitido=True`: el cupo lo tomo el
        # encolado; `slot` lo libera al terminar el hilo del job. Esto arranca el hilo y
        # vuelve; esperamos al estado terminal del registro para marcar el job terminado.
        generaciones.lanzar_job_claude(
            gen_id, prompt=prompt, cwd=cwd, procesar=procesar,
            dir_temporal=dir_temporal, ya_admitido=True, endurecer=endurecer,
        )
        _esperar_terminal(gen_id)
    finally:
        parar.set()
        cola.terminar(job_id)


# Margen extra sobre el wall-timeout del job para esperar el estado terminal (cierre +
# post-procesado). Si se excede (no deberia), dejamos de esperar y marcamos terminado.
_MARGEN_TERMINAL_S = 60


def _esperar_terminal(gen_id: str) -> None:
    """Espera a que el registro `gen_id` alcance un estado terminal (no `ejecutando`)."""
    limite = time.monotonic() + config.claude_timeout() + _MARGEN_TERMINAL_S
    while time.monotonic() < limite:
        g = generaciones.obtener(gen_id)
        if g is not None and g["estado"] != generaciones.ESTADO_EJECUTANDO:
            return
        time.sleep(0.2)
    _log.warning("worker: el job de la generacion %s no alcanzo estado terminal a tiempo", gen_id)


def _bucle(parar: threading.Event, worker_id: str) -> None:
    """Bucle del worker: clava un job y lo procesa; duerme si la cola esta vacia."""
    sondeo = config.worker_sondeo_segundos()
    while not parar.is_set():
        try:
            job = cola.reclamar(worker_id)
        except Exception:  # noqa: BLE001 -- un fallo de la cola no debe matar el worker
            _log.exception("worker: fallo al reclamar un job de la cola")
            if parar.wait(sondeo):
                return
            continue
        if job is None:
            if parar.wait(sondeo):
                return
            continue
        try:
            procesar_job(job, worker_id)
        except Exception:  # noqa: BLE001 -- un fallo de UN job no debe matar el worker
            _log.exception("worker: fallo al procesar el job %s", job.get("id"))


def iniciar_worker_inproceso() -> threading.Thread:
    """Arranca el worker EN PROCESO (hilo daemon) — perfil LOCAL / un solo proceso.

    Lo llama `__main__` (servidor real), NO `crear_app` (tests). El hilo es daemon: muere
    al cerrar el back. Asi la UX de una sola maquina no cambia: el mismo proceso encola y
    ejecuta, sin servicio aparte. Si hay un worker EXTERNO (`KENI_WORKER_EXTERNO`), NO se
    arranca el in-proceso (lo hace el contenedor `worker`).
    """
    parar = threading.Event()
    worker_id = f"inproc-{uuid.uuid4().hex[:8]}"
    hilo = threading.Thread(
        target=_bucle, args=(parar, worker_id), name="worker-generacion", daemon=True
    )
    hilo.start()
    hilo._parar = parar  # type: ignore[attr-defined]  # para pararlo en tests
    _log.info("Worker de generacion in-proceso activo (perfil local).")
    return hilo


def main() -> int:
    """Entry-point del servicio `worker` (hosted): corre el bucle hasta SIGTERM/Ctrl-C.

        python -m keni_consola.worker

    Consume la MISMA cola que el back (Postgres compartido). Bloqueante a proposito (es el
    proceso principal del contenedor). El back arranca con `KENI_WORKER_EXTERNO=1` para no
    duplicar el worker in-proceso.
    """
    from .observabilidad import configurar_logging

    configurar_logging()
    # Crea el esquema de la cola on-demand (idempotente) en el backend compartido.
    from . import repos

    repos.arrancar_persistencia()

    parar = threading.Event()
    worker_id = f"svc-{uuid.uuid4().hex[:8]}"
    _log.info("Worker de generacion (servicio) iniciado: %s", worker_id)
    try:
        _bucle(parar, worker_id)
    except KeyboardInterrupt:
        parar.set()
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
