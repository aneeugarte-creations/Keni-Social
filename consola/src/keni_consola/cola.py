"""Cola de jobs de generacion: el back ENCOLA, un WORKER CLAVA y ejecuta (#130 Fase 2).

Capa fina sobre `repos` (persistencia SQLite local / Postgres hosted) + `dominio.jobspec`
(serializacion del trabajo). Separa el "qué se encola/clava" (aquí) del "cómo se ejecuta"
(`worker.py`) y del "qué post-procesado" (`dominio.jobspec`). El back llama a `encolar`
dentro de la peticion (y vuelve al instante); el worker llama a `reclamar`/`terminar`.

ESTADO DE LA COLA vs ESTADO DEL REGISTRO: la fila de `jobs` es el sobre de DESPACHO
(pendiente|reclamado|terminado, + flag de cancelacion); el registro de generacion
(`generaciones`) sigue siendo la FUENTE DE VERDAD del sondeo de la UI. El worker avanza el
registro igual que antes; la cola solo coordina quién ejecuta qué.
"""

from __future__ import annotations

import logging
from typing import Any

from . import config, presupuesto_ia, repos
from .dominio import jobspec, runner

_log = logging.getLogger("keni_consola.cola")


def tope_cola() -> int:
    """Tope TOTAL de jobs en vuelo admitidos: `max_jobs` (corriendo) + `max_cola` (esperando)."""
    return config.max_jobs() + config.max_cola()


def encolar(gen_id: str, spec: dict[str, Any]) -> str:
    """Encola el job de `gen_id` con su `spec` (dict). Devuelve el job id. NO bloquea.

    BACKPRESSURE SOLO PARA EL TRABAJO DE FONDO: el gate de admision se decide contra el conteo
    REAL de la cola en Postgres (`repos.contar_jobs_activos`), compartido por todos los procesos
    que encolan (back, daemons) y autoliberado cuando un worker marca un job `terminado`. Pero el
    tope SOLO frena a los jobs de FONDO (prioridad pipeline: la maquina): su llamante (el tick del
    pipeline) trata `ColaLlenaError` como backpressure y reintenta solo en unos segundos.

    Un lanzamiento MANUAL (una persona pulsando un boton) SIEMPRE encola: para eso existe la
    cola. Rechazarlo con "intentalo en unos segundos" era pedirle a un humano que hiciera de
    reintentador del sistema mientras la maquina (flujo continuo) mantenia la cola llena. Ademas
    los manuales van PRIMERO (`jobs.prioridad`, `reclamar_job` ordena por ella): aunque la cola
    este cargada de pipeline, lo manual se despacha en cuanto un worker queda libre.

    POR QUE el gate vive aqui (y no en `runner.admitir`): el contador en memoria solo funcionaba
    en el perfil LOCAL (back y worker en el MISMO proceso). En hosted son contenedores distintos
    y el contador del back solo subia — rechazaba TODO para siempre con la cola real vacia.
    """
    # La PRIORIDAD de despacho viaja DENTRO del spec (`jobspec.prioridad`): manual > pipeline.
    # Asi los seams inyectables de encolado no cambian de firma y `reclamar_job` puede ordenar
    # por prioridad (un copy manual del equipo no espera detras del lote del pipeline/autogen).
    prio = jobspec.prioridad(spec)
    es_fondo = prio < jobspec.PRIORIDAD_MANUAL

    # ECONOMIA DE TOKENS (presupuesto_ia): el kill switch y el corte automatico se deciden
    # ANTES que el tope de capacidad. Pausado (humano): NADA entra, ni manual ni procesos
    # (es el freno de mano de toda la maquinaria IA). Agotado (presupuesto + margen): no
    # entra nada QUE GASTE TOKENS (un job de PROCESO —render ffmpeg/ASR— no toca la
    # suscripcion y queda exento del corte por presupuesto). Solo-manual: el FONDO se corta
    # y lo manual del equipo sigue entrando hasta el margen. La REGLA vive en
    # `presupuesto_ia.bloqueo_admision` (fuente única, compartida con el gate de reclamo del
    # worker); aquí solo mapeamos el nivel que BLOQUEA a su excepción. Todas son subclase de
    # ColaLlenaError -> 429 claro en API y backpressure normal en el pipeline.
    gasta_tokens = not jobspec.es_kind_proceso(spec)
    bloqueo = presupuesto_ia.bloqueo_admision(
        presupuesto_ia.nivel(), gasta_tokens=gasta_tokens, es_fondo=es_fondo
    )
    if bloqueo == presupuesto_ia.NIVEL_PAUSADO:
        raise runner.GeneracionPausadaError(
            "La generación con IA está pausada por un administrador."
        )
    if bloqueo == presupuesto_ia.NIVEL_AGOTADO:
        raise runner.PresupuestoAgotadoError(
            "El presupuesto diario de IA está agotado; la generación se reanuda al rotar el día."
        )
    if bloqueo == presupuesto_ia.NIVEL_SOLO_MANUAL:
        raise runner.PresupuestoAgotadoError(
            "El presupuesto diario de IA está agotado para el trabajo automático; "
            "los lanzamientos manuales siguen disponibles."
        )

    # ECONOMIA DE CONTEXTO: el tamano del prompt se gobierna AQUI (embudo unico de admision).
    # Tope DURO (`KENI_PROMPT_MAX_CHARS`): un prompt patologico (feeds concatenados sin criba,
    # un documento gigante) se rechaza ANTES de gastar tokens, con el remedio en el mensaje.
    # Umbral de AVISO (`KENI_PROMPT_AVISO_CHARS`): no corta, deja rastro correlacionado para
    # ver la deriva del contexto antes de chocar con el tope.
    prompt_chars = len(spec.get("prompt") or "")
    tope_prompt = config.prompt_max_chars()
    if tope_prompt and prompt_chars > tope_prompt:
        raise runner.PromptExcesivoError(
            f"El contexto de esta generación es demasiado grande ({prompt_chars:,} caracteres; "
            f"máximo {tope_prompt:,}). Recorta el material de entrada e inténtalo de nuevo."
        )
    aviso = config.prompt_aviso_chars()
    if aviso and prompt_chars > aviso:
        _log.warning(
            "cola: prompt grande en la generacion %s (%d chars > aviso %d); revisa el contexto",
            gen_id, prompt_chars, aviso,
        )

    if es_fondo and repos.contar_jobs_activos() >= tope_cola():
        raise runner.ColaLlenaError(
            "Hay demasiadas generaciones en curso; inténtalo en unos segundos."
        )
    return repos.encolar_job(gen_id, jobspec.serializar(spec), prio)


def reclamar(
    worker: str = "",
    *,
    prioridad_minima: int | None = None,
    solo_proceso: bool | None = None,
) -> dict[str, Any] | None:
    """Clava UN job pendiente (concurrente-seguro) y devuelve `{id, gen_id, spec}` o None.

    `spec` se devuelve YA DESERIALIZADO (dict). Si el JSON guardado estuviera corrupto, el
    job se devuelve con `spec=None` para que el worker lo marque en error (no lo ejecuta).

    `prioridad_minima` (corte del presupuesto, ver `presupuesto_ia`): si viene, SOLO se
    clavan jobs con `prioridad >= prioridad_minima`. Asi una avalancha de fondo YA ENCOLADA
    deja de ejecutarse al agotarse el presupuesto (queda `pendiente`, no se pierde) mientras
    lo manual sigue saliendo.

    `solo_proceso` (CARRIL CPU-bound vs inferencia): separa los jobs de PROCESO (render de
    video / transcripcion ASR, CPU-bound) de los de INFERENCIA (`claude -p`, I/O-bound), para
    que un video largo no acapare un slot del copy manual prioritario (head-of-line). True =
    solo CPU-bound; False = solo inferencia; None = cualquiera. La lista de kinds CPU-bound sale
    de `jobspec.KINDS_PROCESO` (aqui, para no acoplar la persistencia al dominio).
    """
    kinds_proceso = () if solo_proceso is None else tuple(jobspec.KINDS_PROCESO)
    fila = repos.reclamar_job(
        worker, prioridad_minima=prioridad_minima,
        solo_proceso=solo_proceso, kinds_proceso=kinds_proceso,
    )
    if fila is None:
        return None
    try:
        spec = jobspec.deserializar(fila["spec"])
    except (ValueError, TypeError):
        spec = None
    return {"id": fila["id"], "gen_id": fila["gen_id"], "spec": spec}


def terminar(job_id: str) -> None:
    """Marca un job como terminado (el worker ya fijo el estado terminal del registro)."""
    repos.terminar_job(job_id)


def reencolar(gen_id: str) -> bool:
    """Devuelve el job de `gen_id` a `pendiente` (apagado gracioso): otro worker lo re-reclama."""
    return repos.reencolar_job(gen_id)


def cancelar(gen_id: str) -> bool:
    """Marca el job de `gen_id` como cancelado (cross-proceso). True si habia un job."""
    return repos.cancelar_job(gen_id)


def cancelado(job_id: str) -> bool:
    """True si el job esta marcado como cancelado (lo sondea el worker en ejecucion)."""
    return repos.job_cancelado(job_id)
