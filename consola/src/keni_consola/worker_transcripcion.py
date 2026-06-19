"""WORKER de TRANSCRIPCION (ASR faster-whisper): carril `transcripcion` de la cola.

Servicio DEDICADO (imagen lean, SIN Node/claude/gh): reclama SOLO los jobs cuyo
`jobspec.carril(spec) == "transcripcion"` (`PROC_TRANSCRIBIR` / `PROC_TRANSCRIBIR_AUDIO`) y los
despacha por el camino de PROCESO (`worker.procesar_job` -> `_procesar_job_proceso` -> el motor
`keni_consola.transcripcion`, faster-whisper). Así el motor (wheel) + el modelo (~1.6 GB) NO
contaminan la imagen del worker de contenido: viven en una imagen propia (`deploy/transcriptor/`).
El worker de contenido EXCLUYE este carril.

Son jobs de PROCESO: NO gastan tokens de la suscripción claude (exentos del corte por presupuesto);
solo el kill switch PAUSADO los detiene, igual que el carril `proceso` del worker de contenido.

Pool de `KENI_MAX_JOBS_TRANSCRIPCION` hilos (def 2). Entry-point: `python -m keni_consola.worker_transcripcion`.
"""

from __future__ import annotations

import logging
import os
import signal
import threading
import uuid

from . import cola, config, presupuesto_ia, transcripcion, worker
from .dominio import jobspec

_log = logging.getLogger("keni_consola.worker_transcripcion")

# Carriles que ESTE worker reclama: solo transcripción (jamás contenido ni dev).
_CARRILES_TRANSCRIPCION: set[str] = {jobspec.CARRIL_TRANSCRIPCION}

# Tope del backoff del sondeo de la cola cuando lleva vacía / cortada (s).
_SONDEO_MAX_S = 5.0


def _max_jobs() -> int:
    """Cupo de hilos del servicio de transcripción (`KENI_MAX_JOBS_TRANSCRIPCION`, def 2, mín 1)."""
    crudo = os.environ.get("KENI_MAX_JOBS_TRANSCRIPCION")
    if crudo is None:
        return 2
    try:
        return max(1, int(str(crudo).strip()))
    except (TypeError, ValueError):
        return 2


def _bucle(parar: threading.Event, worker_id: str) -> None:
    """Bucle de un hilo: reclama un job del carril `transcripcion` y lo despacha como PROCESO.

    GATE: los jobs de proceso (ASR) NO gastan tokens, así que solo el kill switch PAUSADO los
    frena (`gasta_tokens=False`); el resto de niveles de presupuesto no les aplica.
    """
    sondeo = config.worker_sondeo_segundos()
    espera = sondeo
    while not parar.is_set():
        try:
            nivel = presupuesto_ia.nivel()
        except Exception:  # noqa: BLE001 -- ante un fallo del gate, preferimos NO cortar
            _log.warning("worker_transcripcion: fallo el gate de presupuesto; sigo", exc_info=True)
            nivel = presupuesto_ia.NIVEL_NORMAL
        if presupuesto_ia.bloqueo_admision(nivel, gasta_tokens=False, es_fondo=False) is not None:
            # PAUSADO (kill switch): no reclama nada hasta que se reanude.
            if parar.wait(espera):
                return
            espera = min(espera * 1.5, max(sondeo, _SONDEO_MAX_S))
            continue
        try:
            job = cola.reclamar(worker_id, carriles=_CARRILES_TRANSCRIPCION)
        except Exception:  # noqa: BLE001 -- un fallo de la cola no debe matar el worker
            _log.exception("worker_transcripcion: fallo al reclamar un job de transcripción")
            if parar.wait(espera):
                return
            continue
        if job is None:
            if parar.wait(espera):
                return
            espera = min(espera * 1.5, max(sondeo, _SONDEO_MAX_S))
            continue
        espera = sondeo
        if parar.is_set():
            return
        try:
            worker.procesar_job(job, worker_id=worker_id)
        except Exception:  # noqa: BLE001 -- un fallo de UN job no debe matar el worker
            _log.exception("worker_transcripcion: fallo al procesar el job %s", job.get("id"))


def main() -> int:
    """Entry-point del servicio `transcriptor`: corre el POOL hasta SIGTERM/Ctrl-C."""
    from .observabilidad import configurar_logging

    configurar_logging()
    from . import repos

    repos.arrancar_persistencia()

    # PRE-CALENTADO del modelo en SEGUNDO PLANO: lo descarga (la 1ª vez, al cache persistente /data)
    # y lo carga en memoria sin bloquear el arranque, para que la primera transcripción no espere.
    # Best-effort: si falla (deps/disco/red), se reintentará cuando llegue el primer job real.
    def _precalentar() -> None:
        try:
            transcripcion._cargar_modelo()
            _log.info("worker_transcripcion: modelo whisper pre-cargado.")
        except Exception:  # noqa: BLE001 -- el warm-up nunca debe tumbar el servicio
            _log.warning("worker_transcripcion: no se pudo pre-cargar el modelo (se reintenta)", exc_info=True)

    threading.Thread(target=_precalentar, name="warm-whisper", daemon=True).start()

    parar = threading.Event()
    hilos = [
        threading.Thread(
            target=_bucle, args=(parar, f"trans-{uuid.uuid4().hex[:8]}"),
            name=f"worker-transcripcion-{i}", daemon=True,
        )
        for i in range(_max_jobs())
    ]

    def _al_apagar(signum: int, _frame: object) -> None:
        _log.warning("worker_transcripcion: señal de apagado %s recibida; deteniendo el pool", signum)
        parar.set()

    signal.signal(signal.SIGTERM, _al_apagar)
    signal.signal(signal.SIGINT, _al_apagar)
    for h in hilos:
        h.start()
    _log.info("worker_transcripcion iniciado: pool de %d hilos (carril transcripcion).", len(hilos))
    try:
        while not parar.wait(timeout=1.0):
            pass
    except (KeyboardInterrupt, SystemExit):
        parar.set()
    for h in hilos:
        h.join(timeout=5.0)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
