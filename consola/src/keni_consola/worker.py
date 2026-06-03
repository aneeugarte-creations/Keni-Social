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
import signal
import threading
import time
import uuid

from . import cola, config, generaciones
from .dominio import jobspec

_log = logging.getLogger("keni_consola.worker")

# Job (id, gen_id) que el worker está EJECUTANDO ahora mismo (claude en vuelo), o None.
# Lo usa el manejador de apagado: si el worker muere a mitad (deploy/SIGTERM), marca esa
# generación como INTERRUMPIDA al instante (en vez de dejarla "ejecutando" fantasma hasta el
# reaper) y saca el job de la cola para que NO se re-ejecute en bucle reiniciando el run.
_JOB_EN_CURSO: dict[str, str] | None = None
_JOB_EN_CURSO_LOCK = threading.Lock()


def _marcar_job_en_curso(job: dict[str, str] | None) -> None:
    global _JOB_EN_CURSO
    with _JOB_EN_CURSO_LOCK:
        _JOB_EN_CURSO = job


def _job_en_curso() -> dict[str, str] | None:
    with _JOB_EN_CURSO_LOCK:
        return _JOB_EN_CURSO

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


def _prefetch_s3(job_id: str, gen_id: str, prefetch: dict[str, str]) -> bool:
    """Baja el objeto S3 `clave` a la ruta local `destino` (lo usa la importacion de parrilla).

    El worker tiene las credenciales S3 (a diferencia del back, no compartimos los bytes por
    disco). Crea el dir padre del destino y escribe los bytes de `media.leer_objeto(clave)`.
    Best-effort: si el objeto ya no esta o algo falla al escribirlo, marca el job en error y
    devuelve False (el caller NO debe lanzar claude). True si el documento quedo en su sitio.
    """
    from pathlib import Path

    from . import media

    clave = prefetch["clave"]
    destino = Path(prefetch["destino"])
    try:
        datos = media.leer_objeto(clave)
    except Exception:  # noqa: BLE001 -- fallo de S3: error claro, sin traceback al cliente
        _log.exception("worker: prefetch S3 falló al leer %s (job %s)", clave, job_id)
        datos = None
    if datos is None:
        _finalizar_error(gen_id, "El documento subido ya no está disponible.")
        generaciones.runner.liberar_admision()
        cola.terminar(job_id)
        return False
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(datos)
    except OSError:
        _log.exception("worker: prefetch S3 no pudo escribir %s (job %s)", destino, job_id)
        _finalizar_error(gen_id, "No se pudo preparar el documento para leerlo.")
        generaciones.runner.liberar_admision()
        cola.terminar(job_id)
        return False
    return True


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
        prefetch = jobspec.prefetch_s3(spec)
    except Exception:  # noqa: BLE001 -- spec mal formado: error claro, sin traceback al cliente
        _log.exception("worker: no se pudo reconstruir el job %s (gen %s)", job_id, gen_id)
        _finalizar_error(gen_id, "No se pudo iniciar la generación.")
        generaciones.runner.liberar_admision()
        cola.terminar(job_id)
        return

    # PREFETCH S3: si el spec lo pide (importacion de parrilla), bajamos el documento de S3 a
    # la ruta destino ANTES de lanzar claude. El worker tiene las credenciales S3; el back NO
    # comparte los bytes via disco (back y worker son contenedores distintos). Si el objeto ya
    # no esta, marcamos el job en error sin lanzar claude (no tendria nada que leer).
    if prefetch is not None and not _prefetch_s3(job_id, gen_id, prefetch):
        return

    # Vigia de cancelacion cross-proceso, activo mientras el job corre.
    parar = threading.Event()
    vigia = threading.Thread(
        target=_vigilar_cancelacion, args=(job_id, gen_id, parar),
        name=f"cancel-{job_id}", daemon=True,
    )
    vigia.start()

    # Marca este job como "en curso" mientras corre claude: si el worker recibe SIGTERM
    # (deploy) durante este tramo, el manejador de apagado lo marca interrumpido al instante.
    _marcar_job_en_curso({"id": job_id, "gen_id": gen_id})
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
        _marcar_job_en_curso(None)
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

    def _al_apagar(signum: int, _frame: object) -> None:
        """SIGTERM/SIGINT (apagado por deploy): detecta el job EN CURSO y lo deja en estado
        honesto en vez de "ejecutando" fantasma. Lo marca INTERRUMPIDO y lo SACA de la cola
        (no se re-ejecuta en bucle, que reiniciaría el razonamiento desde cero). El reaper
        cubre las muertes NO graciosas (SIGKILL/OOM), donde este manejador no llega a correr."""
        parar.set()
        job = _job_en_curso()
        if job:
            gid, jid = job.get("gen_id", ""), job.get("id", "")
            _log.warning(
                "worker: apagado (señal %s) con job en curso gen=%s; lo marco interrumpido", signum, gid
            )
            try:
                generaciones.actualizar(gid, {
                    "estado": generaciones.ESTADO_ERROR,
                    "motivo": generaciones.MOTIVO_INTERRUMPIDO,
                    "error": "Interrumpida por un reinicio del worker (despliegue). Vuelve a intentarla.",
                    "fecha_fin": generaciones.ahora_iso(),
                })
            except Exception:  # noqa: BLE001 -- en apagado, best-effort
                pass
            try:
                cola.terminar(jid)  # fuera de la cola: NO re-ejecutar (evita reinicio en bucle)
            except Exception:  # noqa: BLE001
                pass
            try:
                generaciones.cancelar(gid)  # mata el árbol de claude si sigue vivo
            except Exception:  # noqa: BLE001
                pass
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _al_apagar)
    signal.signal(signal.SIGINT, _al_apagar)
    _log.info("Worker de generacion (servicio) iniciado: %s", worker_id)
    try:
        _bucle(parar, worker_id)
    except (KeyboardInterrupt, SystemExit):
        parar.set()
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
