"""WORKER de generacion: clava jobs de la cola y corre `claude -p` (ADR 0002).

DOS modos de ejecucion (se elige por entorno; ver `config.worker_externo`):

  - LOCAL / un solo proceso (def): el back arranca ESTE worker EN PROCESO, como un POOL de
    `config.max_jobs()` hilos de fondo (`iniciar_worker_inproceso`), llamado desde `__main__`
    (NO desde `crear_app`, para no arrancarlo en los tests). La UX de una sola maquina NO
    cambia: no hace falta un servicio aparte y `claude` esta en el mismo entorno que el back.

  - HOSTED: un servicio `worker` SEPARADO corre `python -m keni_consola.worker` (este
    modulo como entry-point), tambien con un POOL de `config.max_jobs()` hilos. Consume la
    MISMA cola (Postgres compartido). El back arranca con `KENI_WORKER_EXTERNO=1` para NO
    arrancar su worker in-proceso. La imagen del worker SI lleva Node + `claude`; la del
    back ya NO (ADR 0002).

CONCURRENCIA (KENI_MAX_JOBS): el worker corre HASTA `config.max_jobs()` jobs `claude` EN
PARALELO. Cada hilo del POOL corre su propio bucle reclama->procesa->termina, bloqueando en
SU job (`_esperar_terminal`); el POOL da el paralelismo de N vias. Reclamar es concurrente-
seguro (`FOR UPDATE SKIP LOCKED`: dos hilos nunca cogen el mismo job). El semaforo de
`runner.slot` (BoundedSemaphore(max_jobs)) es un tope adicional al numero de procesos.

POR QUE REUSA `generaciones.lanzar_job_claude`: ahi vive TODO el endurecimiento que
hay que PRESERVAR (grupo de procesos propio, kill del ARBOL al timeout/cancel, tope de
concurrencia con `slot`, sin procesos sueltos, log correlacionado por job-id). El worker NO
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
import os
import signal
import threading
import time
import uuid

from . import cola, config, generaciones, presupuesto_ia
from .dominio import jobspec

_log = logging.getLogger("keni_consola.worker")

# Jobs (id -> {id, gen_id}) que el worker está EJECUTANDO ahora mismo (claude en curso).
# Con el pool de hilos (KENI_MAX_JOBS) puede haber VARIOS a la vez, asi que es un MAPA, no
# un solo job. Lo usa el manejador de apagado: si el worker muere a mitad (deploy/SIGTERM),
# marca TODAS esas generaciones como INTERRUMPIDAS al instante (en vez de dejarlas
# "ejecutando" fantasma hasta el limpiador) y saca cada job de la cola para que NO se
# re-ejecute en bucle reiniciando el run. Cada hilo del pool registra y des-registra SU job.
_JOBS_EN_CURSO: dict[str, dict[str, str]] = {}
_JOBS_EN_CURSO_LOCK = threading.Lock()


def _marcar_job_en_curso(job: dict[str, str]) -> None:
    """Registra un job (por su id) como en curso en ESTE worker (lo llama su hilo del pool)."""
    with _JOBS_EN_CURSO_LOCK:
        _JOBS_EN_CURSO[job["id"]] = job


def _desmarcar_job_en_curso(job_id: str) -> None:
    """Saca un job del registro de en-curso (su hilo terminó de procesarlo)."""
    with _JOBS_EN_CURSO_LOCK:
        _JOBS_EN_CURSO.pop(job_id, None)


def _reset_estado_para_tests() -> None:
    """Vacia el registro GLOBAL de jobs en curso (solo tests).

    `_JOBS_EN_CURSO` es estado de MODULO (proceso): si un test arranca un pool y por lo que
    sea no lo detiene del todo, su entrada contaminaria el siguiente test (que veria jobs
    "en curso" fantasma). `_Pool.detener()` ya lo deja vacio; este helper es la red de
    seguridad del teardown para garantizar aislamiento entre tests pase lo que pase.
    """
    with _JOBS_EN_CURSO_LOCK:
        _JOBS_EN_CURSO.clear()


def _jobs_en_curso() -> list[dict[str, str]]:
    """Copia de los jobs en curso ahora mismo (para el apagado): lista, sin el lock fuera."""
    with _JOBS_EN_CURSO_LOCK:
        return list(_JOBS_EN_CURSO.values())

# Cuanto sondea el vigia de cancelacion el flag de la cola (s). Equilibrio: cancelar se
# siente casi inmediato (~1.5 s) sin martillear la BD con un SELECT por job cada 0.4 s
# (con N jobs en curso el sondeo de cancelacion era la mayor fuente de QPS de fondo).
_SONDEO_CANCELACION_S = 1.5


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


def _limpiar_si_fallo(gen_id: str, spec: dict) -> None:
    """Si el job terminó en ERROR, ejecuta la limpieza `al_fallar` del spec (best-effort).

    Para una pieza evergreen lanzada desde una idea: la generación falla (o se cancela) y la
    pieza queda sin copy. Borramos esa pieza huérfana y revertimos la idea a `aprobada` para
    poder reintentar (ver `jobspec.reconstruir_al_fallar`). Sin `al_fallar` en el spec —el caso
    del resto de generaciones— es un no-op. Nunca rompe el cierre del job.
    """
    limpiar = jobspec.reconstruir_al_fallar(spec)
    if limpiar is None:
        return
    reg = generaciones.obtener(gen_id)
    if not reg or reg.get("estado") != generaciones.ESTADO_ERROR:
        return
    try:
        limpiar()
    except Exception:  # noqa: BLE001 -- limpieza best-effort; nunca rompe el cierre del job
        _log.exception("worker: falló la limpieza al_fallar del job (gen %s)", gen_id)


def _vigilar_cancelacion(job_id: str, gen_id: str, parar: threading.Event) -> None:
    """Hilo vigia: sondea el flag de cancelacion de la cola y propaga al runner local.

    Mientras el job corre, mira `cola.cancelado(job_id)`; al verlo, llama a
    `generaciones.cancelar(gen_id)` (arma el evento in-memoria + mata el arbol) y termina.
    `parar` lo corta cuando el job ya alcanzo un estado terminal (no seguir sondeando).

    TOLERANTE A FALLOS TRANSITORIOS: un error al sondear (p. ej. un blip de la BD) se loguea
    y se SIGUE sondeando. Antes el vigia hacia `return` ante cualquier excepcion y el job
    quedaba INCANCELABLE durante el resto de su ejecucion (hasta 10 min de wall-timeout).
    """
    while not parar.wait(_SONDEO_CANCELACION_S):
        try:
            if cola.cancelado(job_id):
                generaciones.cancelar(gen_id)
                return
        except Exception:  # noqa: BLE001 -- el vigia nunca debe romper el procesado del job
            _log.warning("worker: fallo al sondear cancelacion del job %s", job_id, exc_info=True)


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


def _procesar_job_proceso(job_id: str, gen_id: str, spec: dict) -> None:
    """Despacha un job de PROCESO (no-claude) a su EJECUTOR y cierra el ciclo (Ola VIDEO).

    SEAM del motor de video: render con ffmpeg / transcripcion ASR. Reutiliza la cola/worker
    para colgarse de Actividad IA, pero NO usa `claude` ni el slot de concurrencia de claude.
    El ejecutor (`jobspec.resolver_ejecutor_proceso(kind)`) tiene firma `ejecutar(gen_id, spec)`
    y reporta progreso/estado/errores via `generaciones.actualizar(...)`; este wrapper SOLO
    garantiza el cierre ordenado pase lo que pase:
      - si el ejecutor revienta (excepcion no controlada), marca el registro en error;
      - SIEMPRE libera el cupo de admision (lo tomo `encolar_job_proceso`) y saca el job de la
        cola, igual que el camino claude lo hace via `slot`/`cola.terminar`.

    NO arranca el vigia de cancelacion cross-proceso del camino claude (que mata el ARBOL de un
    subprocess `claude`): cada ejecutor de proceso es responsable de su propia cancelacion/
    timeout (p. ej. el render pasa su propio `-t`/timeout a ffmpeg). El registro se marca
    `en curso` para que el apagado del pool lo deje INTERRUMPIDO, igual que un job claude.
    """
    kind = spec.get("kind", "")
    _marcar_job_en_curso({"id": job_id, "gen_id": gen_id})
    try:
        ejecutar = jobspec.resolver_ejecutor_proceso(kind)
        ejecutar(gen_id, spec)
    except Exception:  # noqa: BLE001 -- fallo del ejecutor: error claro, sin traceback al cliente
        _log.exception("worker: el ejecutor del job de proceso %s (gen %s) falló", job_id, gen_id)
        _finalizar_error(gen_id, "No se pudo completar el trabajo.")
    finally:
        _desmarcar_job_en_curso(job_id)
        generaciones.runner.liberar_admision()
        cola.terminar(job_id)


def procesar_job(job: dict, worker_id: str = "") -> None:
    """Ejecuta UN job ya clavado: reconstruye el trabajo y corre `claude -p` (con el endurecimiento).

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

    # DISPATCH GENERICO (Ola VIDEO): un job de PROCESO (no-claude) — render de video, ASR —
    # NO reconstruye un `procesar` de claude ni lanza `claude -p`: lo despacha a su EJECUTOR.
    # El camino claude de abajo queda INTACTO (sus tests siguen verdes).
    if jobspec.es_kind_proceso(spec):
        _procesar_job_proceso(job_id, gen_id, spec)
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
    # (deploy) durante esta fase, el manejador de apagado lo marca interrumpido al instante.
    _marcar_job_en_curso({"id": job_id, "gen_id": gen_id})
    try:
        # El runner real (con TODO el endurecimiento). `ya_admitido=True`: el cupo lo tomo el
        # encolado; `slot` lo libera al terminar el hilo del job. Esto arranca el hilo y
        # vuelve; esperamos al estado terminal del registro para marcar el job terminado.
        generaciones.lanzar_job_claude(
            gen_id, prompt=prompt, cwd=cwd, procesar=procesar,
            dir_temporal=dir_temporal, ya_admitido=True, endurecer=endurecer,
        )
        _esperar_terminal(gen_id)
        # Si terminó en error/cancelado, limpia lo que el spec declare desechable (pieza
        # evergreen huérfana + revertir su idea). No-op para el resto de generaciones.
        _limpiar_si_fallo(gen_id, spec)
    finally:
        _desmarcar_job_en_curso(job_id)
        parar.set()
        cola.terminar(job_id)


# Margen extra sobre el wall-timeout del job para esperar el estado terminal (cierre +
# post-procesado). Si se excede (no deberia), dejamos de esperar y marcamos terminado.
_MARGEN_TERMINAL_S = 60

# Tope del BACKOFF del sondeo de la cola cuando lleva vacia varios ciclos (s). El sondeo
# arranca en `config.worker_sondeo_segundos()` (def 0.5) y crece x1.5 por ciclo vacio hasta
# este maximo; un job lo resetea al ritmo base. Reduce el QPS de fondo del pool contra la BD.
_SONDEO_MAX_S = 5.0

# FALLBACK acotado del `_esperar_terminal` cuando la señal in-proceso no llega (s). El camino
# normal NO sondea disco: el hilo que fija el estado terminal (mismo proceso) despierta al que
# espera via `generaciones.evento_terminal`. Este intervalo es solo la RED DE SEGURIDAD por si
# la señal no llegara (p.ej. el job lo cerrara otro proceso, o un test que fija el terminal sin
# pasar por `actualizar`): cada tanto re-leemos el registro para no colgarnos. Mas alto que el
# viejo 0.2 s a proposito: el evento da la latencia baja; esto solo evita un cuelgue.
_FALLBACK_TERMINAL_S = 2.0


def _esperar_terminal(gen_id: str) -> None:
    """Espera a que el registro `gen_id` alcance un estado terminal (no `ejecutando`).

    SEÑAL IN-PROCESO (no sondeo de disco): el hilo que ejecuta el job corre en ESTE mismo
    proceso y, al fijar el estado terminal (`generaciones.actualizar`), despierta este Event.
    El camino normal bloquea en el Event y se reactiva al instante, sin re-parsear el YAML cada
    200 ms. El Event se obtiene ANTES de la primera lectura para no perder una señal que llegue
    entre medias. Un `_FALLBACK_TERMINAL_S` acotado re-lee el registro por si la señal no llega.

    Si el registro DESAPARECE (obtener -> None) tambien dejamos de esperar: no queda nada
    que vigilar, y seguir esperando hasta el timeout retiene la entrada de `_JOBS_EN_CURSO`
    durante minutos (en la suite, el TRUNCATE entre tests borra la fila y ese hilo fugado
    contaminaba el siguiente test del pool con un job fantasma).
    """
    ev = generaciones.evento_terminal(gen_id)
    limite = time.monotonic() + config.claude_timeout() + _MARGEN_TERMINAL_S
    try:
        while True:
            g = generaciones.obtener(gen_id)
            if g is None:
                _log.warning(
                    "worker: la generacion %s desaparecio del registro; dejo de esperar", gen_id
                )
                return
            if g["estado"] != generaciones.ESTADO_EJECUTANDO:
                return
            restante = limite - time.monotonic()
            if restante <= 0:
                break
            # Bloquea en la señal (latencia baja del camino normal); el fallback acota la espera
            # por si la señal no llega. `wait` devuelve True si ya esta `set`: si el terminal se
            # fijo justo tras `obtener`, el Event ya quedo señalizado y re-leemos sin demora.
            ev.wait(min(_FALLBACK_TERMINAL_S, restante))
        _log.warning(
            "worker: el job de la generacion %s no alcanzo estado terminal a tiempo", gen_id
        )
    finally:
        generaciones.descartar_evento_terminal(gen_id)


def _bucle(
    parar: threading.Event,
    worker_id: str,
    *,
    solo_proceso: bool | None = None,
    carriles: set[str] | None = None,
) -> None:
    """Bucle de UN hilo del pool: clava un job y lo procesa; duerme si la cola esta vacia.

    CONCURRENCIA (KENI_MAX_JOBS): este bucle lo corren EN PARALELO los hilos del pool (ver
    `_Pool`/`iniciar_worker_inproceso`). Cada hilo reclama, procesa (bloqueando en SU job via
    `_esperar_terminal`) y reclama el siguiente. La reclamacion concurrente es SEGURA:
    `cola.reclamar` usa `FOR UPDATE SKIP LOCKED`, asi que dos hilos NUNCA se llevan el mismo job.

    CARRIL (`solo_proceso`): separa el trabajo CPU-bound (render de video / transcripcion ASR,
    `solo_proceso=True`) del de INFERENCIA (`claude -p`, I/O-bound, `solo_proceso=False`), cada
    uno con su cupo de hilos independiente, para que un video largo no acapare un slot del copy
    manual prioritario (head-of-line). `None` = cualquiera (pool unico legado). Los jobs de
    proceso NO gastan tokens de la suscripcion: su carril queda EXENTO del corte por presupuesto
    (solo lo detiene el kill switch PAUSADO), como el gate de encolado (`cola.encolar`).

    POOL DE CARRILES (`carriles`): el conjunto de carriles que este worker reclama. Reparte las DOS
    cuentas de Claude entre workers: el worker A incluye `cuenta-a` y el worker B solo `cuenta-b`.
    Los carriles de cuenta llevan `claude` (investigacion) que SI gasta tokens, asi que se reclaman
    por el camino de inferencia (`gasta_tokens=True`), nunca por el exento de proceso. `None` =
    `{inferencia, proceso}` (retrocompatible).
    """
    if carriles is None:
        carriles = {jobspec.CARRIL_INFERENCIA, jobspec.CARRIL_PROCESO}
    sondeo = config.worker_sondeo_segundos()
    espera = sondeo
    # Un carril CPU-bound (proceso) NO gasta tokens IA: el corte por presupuesto (AGOTADO/
    # SOLO_MANUAL) no le aplica; solo el kill switch PAUSADO lo detiene. El carril de inferencia
    # (y el pool unico legado, None) si gasta tokens.
    gasta_tokens = solo_proceso is not True
    while not parar.is_set():
        # GATE DE ECONOMIA (presupuesto_ia): se decide ANTES de reclamar, asi una ráfaga
        # YA ENCOLADA tambien se corta (el gate de admision solo limita lo nuevo). Pausado
        # (kill switch) o agotado (presupuesto + margen): no se reclama NADA (lo encolado
        # queda `pendiente`, listo para la reanudacion). Solo-manual: se reclama unicamente
        # prioridad >= MANUAL (el fondo espera). El gate es barato (lectura cacheada ~3 s).
        try:
            nivel = presupuesto_ia.nivel()
        except Exception:  # noqa: BLE001 -- ante un fallo del gate, preferimos NO cortar
            _log.warning("worker: fallo el gate de presupuesto; sigo sin corte", exc_info=True)
            nivel = presupuesto_ia.NIVEL_NORMAL
        # El gate de reclamo DERIVA del MISMO helper de admisión (`presupuesto_ia.bloqueo_admision`,
        # fuente única de la regla): si ni un job MANUAL que gasta tokens pasaría (PAUSADO/AGOTADO),
        # no reclamamos NADA (lo encolado queda pendiente). Si un job de FONDO no pasaría pero el
        # manual sí (SOLO_MANUAL), reclamamos solo prioridad >= MANUAL (el fondo espera). Con
        # `gasta_tokens=False` (carril proceso) solo PAUSADO bloquea (exento del presupuesto).
        if presupuesto_ia.bloqueo_admision(nivel, gasta_tokens=gasta_tokens, es_fondo=False) is not None:
            if parar.wait(espera):
                return
            espera = min(espera * 1.5, max(sondeo, _SONDEO_MAX_S))
            continue
        solo_manual = (
            gasta_tokens
            and presupuesto_ia.bloqueo_admision(nivel, gasta_tokens=True, es_fondo=True) is not None
        )
        prioridad_minima = jobspec.PRIORIDAD_MANUAL if solo_manual else None
        try:
            job = cola.reclamar(
                worker_id,
                prioridad_minima=prioridad_minima,
                solo_proceso=solo_proceso,
                carriles=carriles,
            )
        except Exception:  # noqa: BLE001 -- un fallo de la cola no debe matar el worker
            _log.exception("worker: fallo al reclamar un job de la cola")
            if parar.wait(espera):
                return
            continue
        if job is None:
            # BACKOFF con cola vacia: tras cada sondeo sin trabajo la espera crece (x1.5)
            # hasta `_SONDEO_MAX_S`, y se RESETEA al sondeo base en cuanto hay un job. Con
            # N hilos del pool sondeando, esto recorta el QPS de fondo contra Postgres sin
            # afectar la latencia bajo carga (con cola activa se sondea al ritmo base).
            if parar.wait(espera):
                return
            espera = min(espera * 1.5, max(sondeo, _SONDEO_MAX_S))
            continue
        espera = sondeo
        # CARRERA DE APAGADO: `parar` pudo activarse DESPUES de pasar el `while` y ANTES (o
        # durante) este `reclamar`. Sin esta re-comprobacion el hilo procesaria un job nuevo
        # tras el apagado, sobreviviendo al `detener()` (atascado luego en `_esperar_terminal`)
        # y FUGANDOSE al siguiente test/deploy. Si ya hay que parar, NO lanzamos `claude`:
        # registramos el job como en-curso (para que `detener()` lo cierre INTERRUMPIDO y lo
        # saque de la cola), liberamos su cupo de admision (lo tomo el encolado; sin esto se
        # fugaria) y salimos limpio. Asi el hilo muere SIEMPRE y no queda cupo colgado.
        if parar.is_set():
            _marcar_job_en_curso({"id": job["id"], "gen_id": job["gen_id"]})
            try:
                generaciones.runner.liberar_admision()
            except Exception:  # noqa: BLE001 -- en apagado, best-effort
                pass
            return
        try:
            procesar_job(job, worker_id)
        except Exception:  # noqa: BLE001 -- un fallo de UN job no debe matar el worker
            _log.exception("worker: fallo al procesar el job %s", job.get("id"))


def _max_jobs_proceso() -> int:
    """Cupo de hilos del CARRIL CPU-bound (render/transcripcion): `KENI_MAX_JOBS_PROCESO`.

    Carril SEPARADO del de inferencia (`claude -p`, `config.max_jobs()`): asi un video largo no
    agota los slots del copy manual. Default 2, minimo 0 (0 = sin carril dedicado: los jobs de
    proceso esperarian a que el carril de inferencia los tomara, head-of-line otra vez — por eso
    el default es >=1). Se lee INLINE de `os.environ` (no por `config.py`, de otro agente).
    """
    crudo = os.environ.get("KENI_MAX_JOBS_PROCESO")
    if crudo is None:
        return 2
    try:
        valor = int(str(crudo).strip())
    except (TypeError, ValueError):
        return 2
    return max(0, valor)


class _Pool:
    """Pool de hilos worker en DOS CARRILES corriendo el bucle de reclamacion.

    - INFERENCIA (`config.max_jobs()` hilos): jobs de `claude -p` (I/O-bound). Da el paralelismo
      de copy/arte (hasta N jobs `claude` a la vez, acotado tambien por `runner.slot`).
    - PROCESO (`KENI_MAX_JOBS_PROCESO` hilos): jobs CPU-bound (render de video / transcripcion).

    Separar los carriles evita el HEAD-OF-LINE: un video largo ya no acapara un slot del copy
    manual prioritario. Cada hilo reclama y procesa de forma independiente, filtrando por su
    carril (`cola.reclamar(solo_proceso=...)`). Comparten el mismo `parar` (Event): `detener()`
    lo activa, cancela TODOS los jobs en curso y hace join con timeout (apagado determinista).
    """

    def __init__(
        self,
        n: int,
        prefijo_id: str,
        *,
        n_proceso: int | None = None,
        carriles: set[str] | None = None,
    ) -> None:
        self._parar = threading.Event()
        self._hilos: list[threading.Thread] = []
        n_inferencia = max(1, n)
        n_proc = _max_jobs_proceso() if n_proceso is None else max(0, n_proceso)
        # Carriles que este worker reclama (reparto de cuentas A/B entre workers). Por defecto, los
        # del entorno (`config.worker_carriles()`): el worker A monta `cuenta-a` y el worker B solo
        # `cuenta-b`. Los hilos de inferencia y proceso comparten el conjunto; la separacion
        # CPU-bound vs inferencia la hace `solo_proceso` (los carriles de cuenta caen siempre del
        # lado de inferencia, que gasta tokens).
        if carriles is None:
            from . import config

            carriles = config.worker_carriles()
        # SIN carril de proceso dedicado (n_proc == 0): el de inferencia toma TODO (`None`, pool
        # unico legado), para no dejar jobs de proceso sin quien los reclame. Con carril dedicado,
        # el de inferencia EXCLUYE los kinds de proceso (False).
        carril_inferencia = False if n_proc > 0 else None
        # INFERENCIA primero (`_hilos[0]` queda como hilo-fachada de inferencia).
        for i in range(n_inferencia):
            worker_id = f"{prefijo_id}-inf-{uuid.uuid4().hex[:8]}"
            self._hilos.append(threading.Thread(
                target=_bucle, args=(self._parar, worker_id),
                kwargs={"solo_proceso": carril_inferencia, "carriles": set(carriles)},
                name=f"worker-generacion-inf-{i}", daemon=True,
            ))
        # PROCESO (CPU-bound): carril aparte para que no compita por los slots de inferencia.
        for i in range(n_proc):
            worker_id = f"{prefijo_id}-proc-{uuid.uuid4().hex[:8]}"
            self._hilos.append(threading.Thread(
                target=_bucle, args=(self._parar, worker_id),
                kwargs={"solo_proceso": True, "carriles": set(carriles)},
                name=f"worker-generacion-proc-{i}", daemon=True,
            ))

    @property
    def parar(self) -> threading.Event:
        return self._parar

    def arrancar(self) -> None:
        for hilo in self._hilos:
            hilo.start()

    def detener(self, *, timeout: float = 10.0) -> None:
        """Apagado DETERMINISTA: para el bucle, cancela TODOS los jobs en curso y hace join.

        GARANTIA: al volver, NINGUN hilo del pool sigue vivo y `_JOBS_EN_CURSO` esta vacio
        (ni un job procesandose, ni un hilo en su bucle de reclamacion). No quedan hilos
        fugados que reclamen un job nuevo en el siguiente test/deploy.

        ORDEN:
        1) Activa `parar`: tras esto NINGUN hilo entra a procesar un job nuevo (el bucle
           re-comprueba `parar` JUSTO despues de reclamar; si esta puesto, devuelve el job a
           la cola y sale en vez de procesarlo).
        2) BUCLE de cancelacion+join: repetidamente captura los jobs en curso, MATA EL ARBOL
           de cada `claude` (`generaciones.cancelar` -> desbloquea su hilo `gen-<id>`, que fija
           terminal y libera el slot -> desbloquea al hilo del pool en `_esperar_terminal`) y
           hace join. Se REPITE porque un hilo pudo haber reclamado un job en la ventana de
           carrera justo antes de ver `parar`: ese job aparece en una pasada posterior y se
           cancela tambien. Se acota por `timeout` global (defensa: nunca colgar el apagado).
        3) RE-ENCOLA cada job capturado (`cola.reencolar` -> `pendiente`) para que el worker
           POST-DEPLOY lo retome solo, y deja su registro `ejecutando` otra vez (revive el
           `cancelado` que escribio el hilo del job: el usuario no cancelo nada; la UI sigue
           mostrando "Generando..." y el run se reanuda sin intervencion). ANTES se marcaba
           INTERRUMPIDO y se sacaba de la cola "para que se re-reclame mas tarde (limpiador)",
           pero NINGUN limpiador relanzaba jobs terminados: cada deploy PERDIA los jobs en curso
           y exigia relanzarlos a mano. Excepcion: un registro que YA llego a `completado`
           (su post-procesado corrio) NO se re-encola (re-ejecutarlo duplicaria borradores).
        4) Limpia `_JOBS_EN_CURSO` (defensa final): si un hilo quedo colgado pasado el timeout
           (no deberia), su entrada no debe contaminar el registro global.

        El limpiador cubre las muertes NO graciosas (SIGKILL/OOM), donde esto no llega a correr
        (ahi actua el re-reclamo de los sueltos de `reclamar_job` por `claimed_at` viejo).
        """
        self._parar.set()
        limite = time.monotonic() + timeout
        capturados: dict[str, dict[str, str]] = {}
        # 2) Cancelar + join, repetido hasta que todos los hilos mueran (o se agote el timeout).
        while True:
            for job in _jobs_en_curso():
                capturados[job["id"]] = job  # acumula (no se pierde ninguno entre pasadas)
                try:
                    generaciones.cancelar(job.get("gen_id", ""))
                except Exception:  # noqa: BLE001 -- en apagado, best-effort por job
                    pass
            vivos = [h for h in self._hilos if h.is_alive()]
            if not vivos:
                break
            restante = limite - time.monotonic()
            if restante <= 0:
                _log.warning(
                    "worker: %d hilo(s) del pool no salieron en %.0fs; sigo el apagado",
                    len(vivos), timeout,
                )
                break
            # Join CORTO por pasada: si un hilo clava un job en la ventana de carrera, volvemos
            # a la cabeza del bucle para capturarlo+cancelarlo (no nos quedamos ciegos 10s).
            vivos[0].join(timeout=min(0.2, restante))
        # Barrido FINAL: un hilo pudo registrar su job (en `_bucle`, antes de morir) DESPUES de
        # la ultima captura del bucle. Como ya esta muerto, el bucle no lo recapturaria; lo
        # recogemos aqui para que reciba estado honesto (y no quede en `_JOBS_EN_CURSO`).
        for job in _jobs_en_curso():
            if job["id"] not in capturados:
                capturados[job["id"]] = job
                try:
                    generaciones.cancelar(job.get("gen_id", ""))
                except Exception:  # noqa: BLE001 -- en apagado, best-effort por job
                    pass
        # 3) RE-DESPACHO: devolver cada job a `pendiente` para que el worker post-deploy lo
        #    retome SOLO (el trabajo no se pierde). Un registro YA `completado` no se re-encola
        #    (su post-procesado corrio: re-ejecutarlo duplicaria borradores); se cierra su job.
        for job in capturados.values():
            gid, jid = job.get("gen_id", ""), job.get("id", "")
            try:
                g = generaciones.obtener(gid)
            except Exception:  # noqa: BLE001 -- sin registro legible, mejor re-encolar (pendiente nunca corrio su post-procesado dos veces: la guardia anti-duplicado del reclamo lo cubre)
                g = None
            if g is not None and g.get("estado") == generaciones.ESTADO_COMPLETADO:
                _log.info("worker: apagado con job gen=%s ya completado; cierro su job", gid)
                try:
                    cola.terminar(jid)
                except Exception:  # noqa: BLE001 -- en apagado, best-effort
                    pass
                continue
            _log.warning(
                "worker: apagado con job en curso gen=%s; lo devuelvo a la cola (pendiente)", gid
            )
            try:
                # Revive el registro (el hilo del job lo dejo `cancelado`/error al matar el
                # arbol): vuelve a `ejecutando` SIN motivo/error, para que la UI siga en
                # "Generando..." hasta que el worker post-deploy lo retome y lo complete.
                generaciones.actualizar(gid, {
                    "estado": generaciones.ESTADO_EJECUTANDO,
                    "motivo": "",
                    "error": "",
                    "fecha_fin": "",
                })
            except Exception:  # noqa: BLE001 -- en apagado, best-effort
                pass
            try:
                cola.reencolar(gid)  # de regreso a `pendiente`: el proximo worker lo clava
            except Exception:  # noqa: BLE001
                pass
        # 4) Defensa: vaciar el registro global por si un hilo quedo colgado (no debe ocurrir).
        with _JOBS_EN_CURSO_LOCK:
            _JOBS_EN_CURSO.clear()


def iniciar_worker_inproceso() -> threading.Thread:
    """Arranca el worker EN PROCESO (pool de hilos daemon) — perfil LOCAL / un solo proceso.

    Lo llama `__main__` (servidor real), NO `crear_app` (tests). Arranca un POOL de
    `config.max_jobs()` hilos daemon (mueren al cerrar el back): asi el mismo proceso
    encola y ejecuta HASTA N jobs `claude` en paralelo, sin servicio aparte. Si hay un
    worker EXTERNO (`KENI_WORKER_EXTERNO`), NO se arranca el in-proceso (lo hace `worker`).

    Devuelve un hilo "fachada" (el primero del pool) con `_parar`/`_pool` adjuntos para
    compatibilidad con el arranque y para pararlo en tests (parar el pool entero).
    """
    pool = _Pool(config.max_jobs(), "inproc")
    pool.arrancar()
    fachada = pool._hilos[0]
    fachada._parar = pool.parar  # type: ignore[attr-defined]  # para pararlo en tests
    fachada._pool = pool  # type: ignore[attr-defined]  # acceso al pool (detener con cancelacion)
    _log.info(
        "Worker de generacion in-proceso activo (perfil local; pool de %d hilos).",
        len(pool._hilos),
    )
    return fachada


def main() -> int:
    """Entry-point del servicio `worker` (hosted): corre el POOL hasta SIGTERM/Ctrl-C.

        python -m keni_consola.worker

    Consume la MISMA cola que el back (Postgres compartido). Arranca un POOL de
    `config.max_jobs()` hilos (cada uno reclama+procesa), asi corre HASTA N jobs `claude`
    en paralelo. El proceso principal se queda BLOQUEADO esperando la señal de apagado; al
    recibirla, para el pool y cancela TODOS los jobs en curso. El back arranca con
    `KENI_WORKER_EXTERNO=1` para no duplicar el worker in-proceso.
    """
    from .observabilidad import configurar_logging

    configurar_logging()
    # Crea el esquema de la cola on-demand (idempotente) en el backend compartido.
    from . import repos

    repos.arrancar_persistencia()

    pool = _Pool(config.max_jobs(), "svc")
    # Señal de "apagar el proceso principal": el manejador la activa y el hilo principal,
    # que espera en ella, detiene el pool (cancelando TODOS los jobs en curso) y sale.
    apagar = threading.Event()

    def _al_apagar(signum: int, _frame: object) -> None:
        """SIGTERM/SIGINT (apagado por deploy): NO hace trabajo pesado en el manejador (corre
        en el hilo principal y debe ser breve/reentrante-seguro). Solo activa los eventos; el
        hilo principal hace el apagado real (parar el pool + cancelar todos los jobs en curso,
        dejandolos INTERRUMPIDOS y re-reclamables). El limpiador cubre las muertes NO graciosas."""
        _log.warning("worker: señal de apagado %s recibida; deteniendo el pool", signum)
        pool.parar.set()  # corta YA la reclamacion de jobs nuevos en todos los hilos
        apagar.set()

    signal.signal(signal.SIGTERM, _al_apagar)
    signal.signal(signal.SIGINT, _al_apagar)
    pool.arrancar()
    _log.info(
        "Worker de generacion (servicio) iniciado: pool de %d hilos.", len(pool._hilos)
    )
    try:
        # Hilo principal bloqueado hasta la señal de apagado (los hilos del pool trabajan).
        while not apagar.wait(timeout=1.0):
            pass
    except (KeyboardInterrupt, SystemExit):
        pool.parar.set()
    finally:
        # Apagado determinista: cancela los jobs en curso y hace join con timeout del pool.
        pool.detener()
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
