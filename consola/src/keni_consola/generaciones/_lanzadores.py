"""GENERACIONES · LANZADORES: encolado/ejecución de trabajos de `claude -p`, de IMAGEN y de
PROCESO (render/transcripción), más la cancelación del árbol de subprocesos.

Submódulo interno del paquete `generaciones`. Aquí vive TODO el endurecimiento #137: grupo de
procesos + kill del árbol, backpressure de admisión por presupuesto/pausa (`ColaLlenaError`; la
cola NO tiene tope, R-NO-LIMIT), cancelación y logging correlacionado
por job-id. El `__init__.py` re-exporta los lanzadores INYECTABLES (`encolar_job_claude`,
`encolar_job_proceso`, `lanzar_job_claude`, `lanzar_job_imagen`) y `cancelar`.

LANZADORES INYECTABLES: `crear_app(...)` REASIGNA `generaciones.encolar_job_claude` y
`generaciones.lanzar_job_imagen` (a nivel del paquete barrel) por fakes que NO usan Popen ni red;
ningún módulo del paquete los llama internamente, así que la reasignación del barrel basta. El
`procesar` (callback que parsea la salida y crea los artefactos) SÍ corre en los tests.

DESACOPLO (#130 Fase 2 / ADR 0002 Fase B): el back ENCOLA (`encolar_job_claude`) y el WORKER
EJECUTA (`lanzar_job_claude`). `lanzar_job_claude` NO desaparece: es la primitiva de ejecución
del worker (con todo el #137).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .. import preferencias
from ..dominio import runner, stream
from ..observabilidad import request_id_actual
from ._almacen import actualizar, crear, obtener
from ._comun import (
    _HANDLES,
    _HANDLES_LOCK,
    ESTADO_COMPLETADO,
    ESTADO_EJECUTANDO,
    ESTADO_ERROR,
    FASE_COMPLETADO,
    MOTIVO_CANCELADO,
    MOTIVO_TIMEOUT,
    Procesar,
    _log,
    _timeout,
    ahora_iso,
    nuevo_id,
)

__all__ = [
    "cancelar",
    "encolar_job_claude",
    "encolar_job_proceso",
    "lanzar_job_claude",
    "lanzar_job_imagen",
    "_ENV_DENYLIST_EXACTOS",
    "_ENV_DENYLIST_PREFIJOS",
    "_argv_claude",
    "_entorno_generacion",
    "_es_secreto_infra",
]


# --------------------------------------------------------------------------- #
# REINTENTO de fallos TRANSITORIOS del modelo/CLI (529/overloaded, blip, crash) #
# --------------------------------------------------------------------------- #

# Backoff exponencial corto entre reintentos (s). Monkeypatcheable en tests (->0 para no esperar).
_BACKOFF_BASE_S = 2.0
_BACKOFF_MAX_S = 10.0

# Señales de error TRANSITORIO en el mensaje del `result` de claude (busqueda en minusculas).
# El tope de PRESUPUESTO ("tope de presupuesto") NO esta aqui: no es transitorio (no reintentar).
_SENALES_TRANSITORIAS: tuple[str, ...] = (
    "overloaded", "rate limit", "rate_limit", "429", "529", "502", "503", "504",
    "timed out", "timeout", "temporarily unavailable", "service unavailable",
    "connection", "network", "internal server error", "econnreset",
)


def _reintentos_maximos() -> int:
    """Reintentos EXTRA ante un fallo transitorio (`KENI_GEN_REINTENTOS`, def 2, min 0).

    Inline de `os.environ` (no por `config.py`, de otro agente). 0 = sin reintento (comportamiento
    previo: un transitorio va directo a error).
    """
    crudo = os.environ.get("KENI_GEN_REINTENTOS")
    if crudo is None:
        return 2
    try:
        return max(0, int(str(crudo).strip()))
    except (TypeError, ValueError):
        return 2


def _backoff_s(intento: int) -> float:
    """Backoff (s) antes del `intento`-esimo reintento (1-indexado): base * 2^(intento-1), topado."""
    return min(_BACKOFF_MAX_S, _BACKOFF_BASE_S * (2 ** max(0, intento - 1)))


def _es_fallo_transitorio(acumulador: Any, returncode: int | None) -> bool:
    """True si el cierre fue un fallo TRANSITORIO (reintentable): 529/overloaded, blip, crash CLI.

    NO transitorio (no reintentar): exito real; error de MODELO/CONTENIDO o de PRESUPUESTO
    reportado en el `result` (su mensaje no casa con `_SENALES_TRANSITORIAS`); el `terminó sin
    resultado` limpio (returncode 0). SI transitorio: un `result` de error con señal transitoria,
    o la CLI que MURIO sin entregar result (returncode != 0/None: crash/kill/blip).
    """
    if acumulador.terminado and not acumulador.error:
        return False  # exito real
    if acumulador.error:
        m = (acumulador.mensaje_error or "").lower()
        return any(s in m for s in _SENALES_TRANSITORIAS)
    if returncode not in (0, None):
        return True  # la CLI murio sin entregar result (crash/blip): reintentable
    return False


def _presupuesto_permite_reintento() -> bool:
    """True si el presupuesto IA permite gastar otro intento (no AGOTADO/PAUSADO).

    Reusa el helper UNICO de la regla (`presupuesto_ia.bloqueo_admision`). Ante un fallo del gate
    NO bloqueamos (mismo criterio que el worker: preferir no cortar por un blip de lectura).
    """
    try:
        from .. import presupuesto_ia

        return presupuesto_ia.bloqueo_admision(
            presupuesto_ia.nivel(), gasta_tokens=True, es_fondo=False
        ) is None
    except Exception:  # noqa: BLE001 -- ante un fallo del gate, no bloqueamos el reintento
        return True


# --------------------------------------------------------------------------- #
# Lanzador de trabajos de CLAUDE (stream-json + parciales) — INYECTABLE        #
# --------------------------------------------------------------------------- #


def _argv_claude(
    prompt: str,
    dirs_permitidos: list[Path] | None = None,
    *,
    endurecer: dict[str, Any] | None = None,
) -> list[str]:
    """argv de `claude -p <prompt> --output-format stream-json --verbose
    --include-partial-messages [--effort N] [--max-budget-usd N] [--max-turns N]
    [--add-dir D ...]`.

    `--include-partial-messages` es lo que habilita el STREAMING token a token (eventos
    `stream_event`/`text_delta`). `--verbose` es obligatorio para stream-json. `--effort`
    se añade solo si hay un nivel guardado en preferencias (si no, el predeterminado del
    modelo). `--max-budget-usd`/`--max-turns` se añaden solo si hay un tope valido en el
    entorno (`KENI_CLAUDE_MAX_USD`/`KENI_CLAUDE_MAX_TURNS`): topan el run por coste y por
    turnos de agente (complementan al wall-timeout, que topa por tiempo). Por cada dir en
    `dirs_permitidos` se añade `--add-dir <dir>` para que claude pueda LEER archivos fuera
    de su cwd (p.ej. la foto subida, que vive en un temporal del SO). El default `None`
    mantiene la retrocompat (sin `--add-dir`). Sin shell.

    El presupuesto/max-turns salen del DOMINIO (`dominio.stream`), no de `api.skills`:
    asi `generaciones` ya no necesita el import perezoso que rompia el ciclo dominio↔API.

    ENDURECIMIENTO POR JOB (`endurecer`): un job READ-ONLY (p.ej. la importacion de parrilla)
    pasa overrides que ENDURECEN el argv para ESE run sin tocar la config global:
      - `disallowed_tools`: lista de herramientas EXTRA a vetar (se UNE a la global; sirve
        para prohibir Write/Edit/MCP de escritura en un job que solo debe LEER).
      - `max_turns` / `max_budget_usd`: topes especificos (mas bajos) que SUSTITUYEN a los
        globales para ese run. Se aplican solo si vienen; si no, se usan los globales.
      - `modelo`: nombre de modelo para ESE run (`--model <modelo>`). Lo usan los parseos de
        insumos / investigacion (Haiku via `config.insumos_modelo()`). "" / ausente = default.
    Los overrides de seguridad solo pueden ENDURECER (vetar mas, topar mas bajo); `modelo`
    solo SELECCIONA el modelo del run (no relaja nada).
    """
    endurecer = endurecer or {}
    extra: list[str] = []
    for d in dirs_permitidos or []:
        extra += ["--add-dir", str(d)]

    # Herramientas vetadas: global (config) UNIDA a las extra del job (orden estable, sin dups).
    vetadas_global = stream.arg_tools_restringidas()
    tools_global = vetadas_global[1:] if vetadas_global else []
    extra_tools = [str(t) for t in (endurecer.get("disallowed_tools") or []) if str(t)]
    todas_tools: list[str] = []
    for t in (*tools_global, *extra_tools):
        if t not in todas_tools:
            todas_tools.append(t)
    arg_tools = ["--disallowed-tools", *todas_tools] if todas_tools else []

    # Topes: override del job si viene; si no, el global del dominio.
    if "max_turns" in endurecer and endurecer["max_turns"]:
        arg_turns = ["--max-turns", str(int(endurecer["max_turns"]))]
    else:
        arg_turns = stream.arg_max_turns()
    if "max_budget_usd" in endurecer and endurecer["max_budget_usd"]:
        texto = f"{float(endurecer['max_budget_usd']):.10f}".rstrip("0").rstrip(".")
        arg_budget = ["--max-budget-usd", texto]
    else:
        arg_budget = stream.arg_presupuesto()

    # Esfuerzo (thinking): override del job si viene y es un nivel válido; si no, el global
    # de preferencias. Un job mecánico (p.ej. importar parrilla = transcribir filas a JSON)
    # pasa `esfuerzo="low"` para no "pensar" de más (3× más rápido, misma cobertura) SIN
    # tocar la preferencia global de copy/otros.
    nivel = str(endurecer.get("esfuerzo") or "")
    if nivel in preferencias.ESFUERZOS_VALIDOS:
        arg_effort = ["--effort", nivel]
    else:
        arg_effort = preferencias.arg_esfuerzo()

    # Modelo del job (`endurecer["modelo"]`): si viene un nombre no vacio, se anade `--model
    # <modelo>` para que ESE run use un modelo concreto (p.ej. los parseos de insumos /
    # investigacion usan Haiku via `config.insumos_modelo()`). Ausente/"" = el modelo por
    # defecto de `claude`. Solo SELECCIONA el modelo del run; no relaja seguridad.
    modelo = str(endurecer.get("modelo") or "").strip()
    arg_modelo = ["--model", modelo] if modelo else []

    return [
        "claude", "-p", prompt,
        "--output-format", "stream-json", "--verbose", "--include-partial-messages",
        # Headless: sin esto `claude` se cuelga al usar una tool (WebFetch/Read), no hay forma
        # de aprobar el permiso en `-p`. NO es el flag de skills: no usamos el motor de skills,
        # el contexto se inyecta en el prompt; el cwd es neutro. Acotado por topes.
        *stream.arg_skip_permisos(),
        # Defensa en profundidad anti prompt-injection: veta herramientas peligrosas (por
        # defecto `Bash`/`Write`/`Edit`, mas las extra del job). Va DESPUES de skip-permisos.
        *arg_tools,
        *arg_effort,
        *arg_modelo,
        *arg_budget,
        *arg_turns,
        *extra,
    ]


# Prefijos/nombres de variables de entorno que NUNCA deben llegar al subproceso `claude -p`
# (case-insensitive). Defensa contra EXFILTRACION de secretos: la generacion corre con
# skip-permissions y el prompt incluye contenido de usuario/RSS NO confiable; si el modelo
# fuese prompt-injectado y tuviera una herramienta de salida (Web, MCP), no debe poder leer
# del entorno credenciales de la INFRA (Postgres, S3/Garage, Metricool/agencias) y filtrarlas.
# La generacion NO las necesita: solo precisa PATH/HOME/locale/XDG, el token de Claude
# (`CLAUDE_CODE_OAUTH_TOKEN`/`ANTHROPIC_API_KEY`) y, en su caso, la clave del proveedor de
# imagen (que `_entorno_generacion` inyecta explicitamente). Usamos DENYLIST (no allowlist) para no
# romper variables legitimas que `claude` pueda necesitar y que no preveamos. CRITICO: estos
# prefijos NO deben cazar `PATH`/`HOME`/`CLAUDE_*` (`PG` es prefijo, no caza `PATH`: empieza
# por `PA`, no `PG`).
_ENV_DENYLIST_PREFIJOS: tuple[str, ...] = (
    "S3_", "GARAGE_", "POSTGRES_", "APP_DB_", "PG", "METRICOOL", "MC_",
)
_ENV_DENYLIST_EXACTOS: frozenset[str] = frozenset({"DATABASE_URL"})


def _es_secreto_infra(nombre: str) -> bool:
    """True si `nombre` es una var de secreto de INFRA que no debe llegar al subproceso.

    Case-insensitive. Caza por PREFIJO (`S3_`, `POSTGRES_`, `PG`, `METRICOOL`, ...) o por
    nombre EXACTO (`DATABASE_URL`). Nunca caza el token de Claude ni `PATH`/`HOME`.
    """
    arriba = nombre.upper()
    if arriba in _ENV_DENYLIST_EXACTOS:
        return True
    return any(arriba.startswith(p) for p in _ENV_DENYLIST_PREFIJOS)


def _entorno_generacion() -> dict[str, str]:
    """Entorno del subproceso de la generacion.

    Hereda `os.environ` PERO con un SCRUB de los secretos de infra (`_es_secreto_infra`):
    Postgres/S3/Garage/Metricool no deben viajar al subproceso `claude -p` (defensa contra
    exfiltracion si el modelo es prompt-injectado). Se conserva todo lo demas que la
    generacion necesita (PATH/HOME/locale/XDG, `CLAUDE_CODE_OAUTH_TOKEN`/`ANTHROPIC_API_KEY`).
    Si hay una clave de imagen en el ALMACEN (secretos.toml, la UNICA fuente de verdad) y la
    variable correspondiente no esta ya puesta, la inyecta: el motor de imagen es un proceso
    independiente que solo lee variables de entorno, asi que este es el canal por el que recibe la clave. NO
    duplica el almacen: solo lo transporta al subproceso. Una variable ya presente en el
    entorno tiene prioridad (no se pisa).
    """
    import os

    from .. import secretos

    entorno = {k: v for k, v in os.environ.items() if not _es_secreto_infra(k)}
    clave = secretos.obtener_clave_imagen()
    if not clave:
        return entorno
    var = {
        "openrouter": "OPENROUTER_API_KEY",
        "openai": "OPENAI_API_KEY",
        "gemini": "GEMINI_API_KEY",
    }.get(secretos.obtener_proveedor_imagen())
    if var and not entorno.get(var):
        entorno[var] = clave
    return entorno


def encolar_job_claude(
    gen_id: str,
    *,
    prompt: str,
    cwd: Path,
    procesar: Procesar,
    dir_temporal: Path | None = None,
    spec: dict[str, Any] | None = None,
) -> None:
    """ENCOLA un trabajo de claude (#130 Fase 2): persiste el `spec` y vuelve de INMEDIATO.

    Es el NUEVO seam de lanzamiento que usan los endpoints/dominio en lugar de ejecutar
    `claude -p` en la peticion. El back solo ENCOLA; un WORKER (in-proceso en local,
    servicio aparte en hosted) clava el job y corre `lanzar_job_claude` (el runner real
    con todo el #137). `spec` es la forma serializable (prompt + post-procesado + cwd) que
    el worker usa para reconstruir el trabajo; `procesar`/`cwd`/`dir_temporal` SOLO los
    necesita un lanzador INYECTADO (tests), que recibe la MISMA firma que el viejo
    `lanzar_job_claude` y por eso sigue funcionando sin cambios.

    INYECTABLE: `crear_app(lanzar_generacion=...)` reasigna ESTA funcion; los tests pasan
    fakes que NO tocan `claude` ni la cola (ejecutan `procesar` sincronicamente o dejan el
    registro `ejecutando`). En produccion, el default encola el `spec`.

    SIN TOPE DE COLA (R-NO-LIMIT): `cola.encolar` SIEMPRE acepta; nada se rechaza por tamano de
    cola. El unico limite es la concurrencia (`max_jobs`), que el worker/`runner.slot` aplican
    más adelante en el flujo (el exceso ESPERA). `cola.encolar` aun puede rechazar por el límite VOLUNTARIO de
    presupuesto/pausa (subclases de `ColaLlenaError` -> 429), que se conserva.
    """
    if spec is None:
        # Defensa: sin spec no se puede reconstruir el job en el worker. El llamante real
        # SIEMPRE pasa spec; un test que inyecte su fake no llega aqui (reasigna la funcion).
        raise ValueError("encolar_job_claude requiere un spec serializable")
    from .. import cola

    cola.encolar(gen_id, spec)  # SIEMPRE encola (sin tope); solo presupuesto/pausa rechaza (ColaLlenaError -> 429)
    # Visibilidad/control: persistimos el prompt EXACTO que recibirá `claude -p` y su TAMAÑO
    # (`prompt_chars`, economía de contexto: lo vuelca el ledger `gasto_ia` al cerrar, para
    # ver la deriva del contexto por día). El prompt se expone SOLO en el detalle
    # (`GET /api/generaciones/{id}`), nunca en el listado (lo quita `_todas_ordenadas`).
    # Best-effort: el job ya está encolado; un fallo al persistir esto no debe tumbarlo.
    if prompt:
        try:
            actualizar(gen_id, {"prompt": prompt, "prompt_chars": len(prompt)})
        except Exception:  # noqa: BLE001 -- best-effort
            pass


def encolar_job_proceso(
    gen_id: str | None = None,
    *,
    kind: str,
    params: dict[str, Any] | None = None,
    etiqueta: str | None = None,
    marca: str | None = None,
) -> dict[str, Any]:
    """ENCOLA un job de PROCESO (no-claude): render de video / transcripcion ASR (Ola VIDEO).

    Analogo a `encolar_job_claude` pero para los KINDS de proceso (`jobspec.KINDS_PROCESO`): el
    back/daemon CREA el registro de generacion con `tipo=kind` (asi sale en Actividad IA) y
    ENCOLA un job con `spec={"version":1, "kind":kind, **params}`. Un WORKER lo reclama y, al ver
    un kind de proceso, despacha al EJECUTOR correspondiente (`jobspec.resolver_ejecutor_proceso`)
    en vez de correr `claude` (ver `worker.procesar_job`). El ejecutor reporta progreso/estado/
    errores via `actualizar(...)`.

    Reutiliza el MISMO camino de admision que el camino claude (`cola.encolar`): la cola NO tiene
    tope (R-NO-LIMIT), asi que SIEMPRE encola; solo el límite voluntario de presupuesto/pausa puede
    rechazar (subclase de `ColaLlenaError` -> 429). Si `gen_id` no se pasa, se crea uno.
    Devuelve el registro publico de la generacion (incluye su `id`).
    """
    from ..dominio import jobspec

    if kind not in jobspec.KINDS_PROCESO:
        raise ValueError(f"'{kind}' no es un kind de proceso valido (KINDS_PROCESO).")
    reg = crear({
        "id": gen_id or nuevo_id(),
        "tipo": kind,
        "marca": marca or "",
        "etiqueta": etiqueta or kind,
    })
    spec = jobspec.construir_proceso(kind, params or {})
    from .. import cola

    cola.encolar(reg["id"], spec)  # SIEMPRE encola (sin tope); solo presupuesto/pausa rechaza (ColaLlenaError -> 429)
    return reg


def lanzar_job_claude(
    gen_id: str,
    *,
    prompt: str,
    cwd: Path,
    procesar: Procesar,
    dir_temporal: Path | None = None,
    ya_admitido: bool = False,
    endurecer: dict[str, Any] | None = None,
) -> None:
    """Lanza un trabajo de claude EN SEGUNDO PLANO (Popen + hilo lector). NO bloquea.

    El hilo lee el NDJSON (stream-json + parciales), persiste `salida` (texto en vivo) y
    metricas parciales en el registro, y al cerrar fija el estado terminal:
      - exito  -> `completado`, `resultado = procesar(texto_final, metricas_finales)`.
      - error/budget/timeout -> `error` (mensaje en espanol).
    Si `dir_temporal` viene (archivo subido), se borra al terminar. INYECTABLE: los tests
    reemplazan esta funcion por una fake que llama a `procesar` con una salida canned.

    LO LLAMA EL WORKER (#130 Fase 2) tras clavar un job, NO la peticion HTTP. `ya_admitido`
    es True cuando el cupo de admision ya lo tomo `encolar_job_claude` (el caso normal del
    worker): asi NO se vuelve a admitir (evita doble cuenta), pero `slot` SIGUE liberandolo.

    SIN TOPE DE COLA (R-NO-LIMIT): `runner.admitir()` SIEMPRE acepta (solo lleva la cuenta de
    jobs en curso); nada se rechaza por tamano de cola. Con `ya_admitido` la admision la hizo ya
    el encolado (el worker no re-admite). El hilo hereda la admision (`slot(ya_admitido=True)`) y
    la libera al terminar. La concurrencia (`max_jobs`) la impone `slot` haciendo ESPERAR.
    """
    acumulador = stream.AcumuladorStream()
    # Wall-timeout del run: el global (`KENI_CLAUDE_TIMEOUT`, def 600 s) salvo que el job
    # traiga un override en `endurecer["timeout"]` (timeout POR ETAPA: p. ej. la verificación verificación de
    # la fuente corre con ~180 s). Solo puede ENDURECER (acortar): se topa con `min(...)`,
    # nunca alarga el global (misma filosofia que el resto de overrides de `endurecer`).
    timeout = _timeout()
    try:
        timeout_job = int((endurecer or {}).get("timeout") or 0)
    except (TypeError, ValueError):
        timeout_job = 0
    if timeout_job > 0:
        timeout = min(timeout, timeout_job)

    # CORRELACION (#123 + #137): capturamos AQUI (sincronicamente, dentro de la peticion)
    # el request-id de quien lanzo el job. El hilo de trabajo corre fuera del contexto de
    # la peticion, asi que el ContextVar ya no estara puesto; por eso lo guardamos ahora y
    # lo incluimos en TODOS los logs del job. Asi un fallo del job se rastrea hasta la
    # peticion que lo origino (y hasta el id que el usuario pudo haber reportado).
    rid = request_id_actual()
    etq = f"generacion {gen_id}" + (f" (req {rid})" if rid else "")

    # Admision: la cola NO tiene tope (R-NO-LIMIT), asi que `admitir()` SIEMPRE acepta (solo
    # cuenta el job en curso). El hilo, ya admitido, libera el cupo al terminar via `slot`. Si el
    # cupo ya lo tomo `encolar_job_claude` (worker, #130 Fase 2), NO re-admitimos.
    if not ya_admitido:
        runner.admitir()

    def _avance() -> None:
        try:
            actualizar(
                gen_id,
                {
                    "estado": ESTADO_EJECUTANDO,
                    # Etapa de progreso (en que etapa va): razonando → generando.
                    "fase": acumulador.fase(),
                    "salida": acumulador.texto,
                    # Razonamiento en vivo (cola acotada): feedback inmediato mientras piensa.
                    "razonamiento": acumulador.razonamiento,
                    "metricas": stream.metricas_a_dict(acumulador.metricas_parciales()),
                },
            )
        except Exception:  # noqa: BLE001 -- el avance nunca debe romper el hilo
            # Persistir un parcial es best-effort (el cierre fija el estado), pero ya no
            # lo silenciamos en mudo: dejamos rastro con el job-id + request-id (#123, #137).
            _log.warning("%s: fallo al persistir avance parcial", etq, exc_info=True)

    def _finalizar(timed_out: bool, returncode: int | None, cancelado: bool) -> None:
        # OJO: el `dir_temporal` se borra al FINAL (no aqui), porque el post-procesado
        # `procesar` puede necesitar los ARCHIVOS que la skill dejo ahi: las skills de
        # imagen (estudio-imagen) escriben los .png derivados junto a la foto subida y
        # `procesar` los importa al media para previsualizarlos. Borrarlo antes los
        # perderia. La limpieza va en el `finally`, asi corre pase lo que pase.
        fecha_fin = ahora_iso()
        try:
            if cancelado:
                # Cancelacion del usuario (#137): se mato el arbol; estado terminal claro.
                actualizar(gen_id, {
                    "estado": ESTADO_ERROR, "motivo": MOTIVO_CANCELADO,
                    "error": "La generación fue cancelada.",
                    "salida": acumulador.texto,
                    "metricas": stream.metricas_a_dict(acumulador.metricas_parciales()),
                    "fecha_fin": fecha_fin,
                })
                return
            if timed_out:
                actualizar(gen_id, {
                    "estado": ESTADO_ERROR, "motivo": MOTIVO_TIMEOUT,
                    "error": f"El asistente tardó demasiado (más de {timeout} s) y se canceló.",
                    "metricas": stream.metricas_a_dict(acumulador.metricas_parciales()),
                    "fecha_fin": fecha_fin,
                })
                return
            if acumulador.error:
                actualizar(gen_id, {
                    "estado": ESTADO_ERROR, "error": acumulador.mensaje_error,
                    "fecha_fin": fecha_fin,
                })
                return
            if acumulador.terminado:
                try:
                    resultado = procesar(acumulador.texto, acumulador.final)
                except Exception:  # noqa: BLE001 -- fallo del post-procesado -> error claro
                    # El cliente ve un mensaje generico (sin traceback), pero el fallo
                    # queda CORRELACIONADO al job + a la peticion en el log (#123, #137).
                    _log.exception("%s: fallo el post-procesado (procesar)", etq)
                    actualizar(gen_id, {
                        "estado": ESTADO_ERROR,
                        "error": "Se generó el contenido pero no se pudo procesar el resultado.",
                        "salida": acumulador.texto,
                        "metricas": stream.metricas_a_dict(acumulador.final),
                        "fecha_fin": fecha_fin,
                    })
                    return
                actualizar(gen_id, {
                    "estado": ESTADO_COMPLETADO, "fase": FASE_COMPLETADO,
                    "salida": acumulador.texto,
                    "metricas": stream.metricas_a_dict(acumulador.final),
                    "resultado": resultado, "fecha_fin": fecha_fin,
                })
                return
            detalle = "El asistente terminó sin devolver un resultado."
            if returncode not in (0, None):
                detalle = "El asistente terminó con error."
            actualizar(gen_id, {
                "estado": ESTADO_ERROR, "error": detalle,
                # A4: conservar el texto ya acumulado (no descartarlo en stream truncado).
                "salida": acumulador.texto,
                "metricas": stream.metricas_a_dict(acumulador.metricas_parciales()),
                "fecha_fin": fecha_fin,
            })
        except Exception:  # noqa: BLE001 -- el cierre nunca debe propagar
            # Logueamos con el job-id + request-id (#123, #137) y, best-effort, intentamos dejarlo
            # en error (no propagamos: es daemon).
            _log.exception("%s: fallo al fijar el estado terminal", etq)
            try:
                actualizar(gen_id, {
                    "estado": ESTADO_ERROR,
                    "error": "Ocurrió un error al finalizar la generación.",
                    "fecha_fin": fecha_fin,
                })
            except Exception:  # noqa: BLE001 -- ya logueamos; no hay mas que hacer
                _log.error("%s: tampoco se pudo marcar el error de cierre", etq)
        finally:
            # Limpieza del temporal de la subida: DESPUES de `procesar` (ver nota arriba).
            if dir_temporal is not None:
                shutil.rmtree(dir_temporal, ignore_errors=True)

    # Evento de cancelacion del job (lo arma `cancelar()`). Se guarda en el handle para
    # que `cancelar()` pueda matar el arbol y para que `_finalizar` sepa el porque.
    cancelado = threading.Event()

    def _ciclo() -> None:
        # `acumulador` se REASIGNA entre reintentos (estado limpio por intento); `_avance`/
        # `_finalizar` lo leen del scope de `lanzar_job_claude`, asi que el `nonlocal` hace que
        # vean siempre el del intento en curso.
        nonlocal acumulador
        # Concurrencia (#116) + admision/tope de cola (#137): el job YA fue admitido en
        # `lanzar_job_claude` (sincronicamente), asi que aqui solo esperamos un proceso
        # concurrente libre. `slot(ya_admitido=True)` libera el cupo al salir. El spawn
        # ocurre DENTRO del slot para que el tope limite procesos `claude` reales. Cada
        # job tiene wall-timeout, asi que los slots siempre se liberan. El REINTENTO de
        # transitorios ocurre DENTRO del mismo slot (no re-admite ni re-encola).
        try:
            with runner.slot(ya_admitido=True):
                if shutil.which("claude") is None:
                    if dir_temporal is not None:
                        shutil.rmtree(dir_temporal, ignore_errors=True)
                    actualizar(gen_id, {
                        "estado": ESTADO_ERROR,
                        "error": (
                            "No se encontró el asistente en este equipo. Instala Claude "
                            "Code para generar desde la consola."
                        ),
                        "fecha_fin": ahora_iso(),
                    })
                    return
                max_reintentos = _reintentos_maximos()
                intento = 0
                while True:
                    try:
                        # Subproceso en SU PROPIO grupo (#137): al timeout/cancel matamos el
                        # ARBOL entero (`runner.matar_arbol`), no solo el padre.
                        proc = runner.lanzar_proc(
                            _argv_claude(
                                prompt,
                                [dir_temporal] if dir_temporal else None,
                                endurecer=endurecer,
                            ),
                            cwd=str(cwd),
                            env=_entorno_generacion(),
                        )
                    except (OSError, ValueError):
                        if dir_temporal is not None:
                            shutil.rmtree(dir_temporal, ignore_errors=True)
                        actualizar(gen_id, {
                            "estado": ESTADO_ERROR, "error": "No se pudo iniciar la generación.",
                            "fecha_fin": ahora_iso(),
                        })
                        return
                    with _HANDLES_LOCK:
                        _HANDLES[gen_id] = {"proc": proc, "cancelado": cancelado}
                    # Si ya pidieron cancelar entre el spawn y registrar el handle, matamos ya.
                    if cancelado.is_set():
                        runner.matar_arbol(proc)
                    runner.leer_stream(proc, acumulador, _avance)
                    # `runner.esperar` mata el ARBOL si supera el wall-timeout (#137).
                    timed_out = runner.esperar(proc, timeout)
                    # ¿REINTENTAR? Solo un fallo TRANSITORIO (529/overloaded, blip, crash de la
                    # CLI), no cancelado ni timeout (ya gasto su wall-timeout), con reintentos y
                    # presupuesto disponibles. El error de modelo/contenido/presupuesto NO se
                    # reintenta (cae al `_finalizar` de error de siempre).
                    if (
                        not cancelado.is_set()
                        and not timed_out
                        and intento < max_reintentos
                        and _es_fallo_transitorio(acumulador, proc.returncode)
                        and _presupuesto_permite_reintento()
                    ):
                        intento += 1
                        espera = _backoff_s(intento)
                        _log.warning(
                            "%s: fallo transitorio (%s); reintento %d/%d tras %.1fs",
                            etq, acumulador.mensaje_error or f"rc={proc.returncode}",
                            intento, max_reintentos, espera,
                        )
                        # Backoff CANCELABLE: si el usuario cancela durante la espera, salimos a
                        # finalizar (cancelado). `cancelado.wait` devuelve True si se señalo.
                        if cancelado.wait(espera):
                            break
                        acumulador = stream.AcumuladorStream()  # estado limpio para el reintento
                        continue
                    break
                # Estado terminal ANTES de soltar el handle: un sondeo que ya no ve el
                # handle nunca lee un "ejecutando" obsoleto.
                _finalizar(timed_out, proc.returncode, cancelado.is_set())
        finally:
            with _HANDLES_LOCK:
                _HANDLES.pop(gen_id, None)

    # El hilo (via `slot(ya_admitido=True)`) libera la admision al terminar. Si el
    # arranque del hilo fallara ANTES de entrar al slot, liberamos aqui para no fugar el
    # cupo de `admitir()` (defensa; en la practica `start()` casi nunca falla).
    hilo = threading.Thread(target=_ciclo, name=f"gen-{gen_id}", daemon=True)
    try:
        hilo.start()
    except Exception:  # noqa: BLE001 -- el cupo admitido no debe quedar colgado
        runner.liberar_admision()
        raise


def cancelar(gen_id: str) -> bool:
    """Cancela un job de claude EN CURSO: mata el ARBOL del subproceso (#137, PERMANENTE).

    Devuelve True si se pudo cancelar algo (handle in-memoria del proceso O un job en la
    cola); False si no hay nada que cancelar (ya terminó). Tiene DOS vias, porque el job
    puede correr en ESTE proceso o en otro (worker hosted, #130 Fase 2):
      - IN-MEMORIA: si el job corre aqui (back local con worker in-proceso, o el propio
        worker), hay un handle con el proceso: armamos el evento y matamos el ARBOL ya.
      - CROSS-PROCESO: marcamos el job en la cola como `cancelado` (`cola.cancelar`). El
        worker que lo corre sondea ese flag y mata el arbol; un job aun pendiente se
        finaliza como cancelado al clavarse, sin lanzar `claude`.
    La limpieza del estado terminal la hace el hilo del job en `_finalizar`. La generacion
    es subprocess `claude -p` (ADR 0001): cancelar = matar el arbol del proceso.
    """
    cancelado_algo = False
    with _HANDLES_LOCK:
        handle = _HANDLES.get(gen_id)
        ev = handle.get("cancelado") if handle else None
        proc = handle.get("proc") if handle else None
    if isinstance(ev, threading.Event):
        ev.set()
        cancelado_algo = True
    if isinstance(proc, subprocess.Popen):
        runner.matar_arbol(proc)
        cancelado_algo = True
    # Cross-proceso: marca el job en la cola (lo lee el worker, esté donde esté).
    try:
        from .. import cola

        if cola.cancelar(gen_id):
            cancelado_algo = True
    except Exception:  # noqa: BLE001 -- la cancelacion in-memoria ya pudo bastar; no propagar
        _log.warning("generacion %s: fallo al marcar la cancelacion en la cola", gen_id, exc_info=True)
    return cancelado_algo


# --------------------------------------------------------------------------- #
# Lanzador de trabajos de IMAGEN (HTTP a un proveedor) — INYECTABLE            #
# --------------------------------------------------------------------------- #


def _autocatalogar_arte_ia(gen_id: str, resultado: Any) -> None:
    """Cataloga en la galería de artes las imágenes recién GENERADAS por IA, para REUTILIZARLAS
    en otros posts/redes sin re-generarlas (la foto de un post de Neymar vale para el resto de
    redes). Solo toca objetos GENERATIVOS (carpeta `generadas/`): los deterministas
    (recortes/composites/sets en `render/`) NO se catalogan. Las cataloga como GLOBALES
    (marca='') para que salgan en la galería de CUALQUIER marca (ver `api/artes` listar).

    Best-effort y AISLADO: corre tras fijar el estado terminal; cualquier fallo se loguea y NO
    afecta a la generación (ya `completada`). Idempotente por `objeto` UNIQUE en `catalogo_media`.
    """
    if not isinstance(resultado, dict):
        return
    try:
        from .. import almacen_media, media, repos
    except Exception:  # noqa: BLE001 -- si el cableado no está, no rompemos la generación
        return
    claves: list[str] = []
    pid = resultado.get("id")
    if isinstance(pid, str) and pid:
        claves.append(pid)
    for img in resultado.get("imagenes") or []:
        if isinstance(img, dict) and isinstance(img.get("id"), str) and img["id"]:
            claves.append(img["id"])
    # Solo las imágenes GENERATIVAS (carpeta `generadas/`); de-dup conservando orden.
    generadas = [k for k in dict.fromkeys(claves) if almacen_media.categoria_de(k) == "generadas"]
    if not generadas:
        return
    gen = obtener(gen_id) or {}
    titulo = (gen.get("etiqueta") or "").strip()
    autor = {"id": gen.get("autor_id", ""), "usuario": gen.get("autor_nombre", "")}
    for clave in generadas:
        try:
            if media.leer_media(clave) is None:
                continue
            # Promueve a la carpeta reusable `artes/` (igual que `POST /api/artes`): COPIA, así la
            # pieza que referencia el `generadas/` original sigue intacta.
            objeto = almacen_media.promover_objeto(clave, "artes")
            if repos.existe_media_objeto(objeto):
                continue
            repos.crear_media_catalogo(
                objeto=objeto, tipo="ia", marca="", titulo=titulo, aprobado=False, autor=autor,
            )
        except Exception:  # noqa: BLE001 -- best-effort por objeto; nunca rompe la generación
            _log.warning("auto-catálogo de arte IA falló para %r (gen %s)", clave, gen_id, exc_info=True)


def lanzar_job_imagen(gen_id: str, *, generar: Callable[[], dict[str, Any]]) -> None:
    """Lanza un trabajo de imagen EN SEGUNDO PLANO (un hilo simple; sin Popen).

    `generar()` hace la llamada al proveedor y guarda la imagen, devolviendo el
    `resultado` (`{id, url}`). No es un stream: el registro pasa de `ejecutando` a
    `completado` (con `resultado`) o `error`. INYECTABLE para tests (sin red).
    """

    def _ciclo() -> None:
        try:
            resultado = generar()
        except Exception as e:  # noqa: BLE001 -- mensaje en espanol; sin traceback al cliente
            mensaje = str(e) if str(e) else "No se pudo generar la imagen."
            actualizar(gen_id, {"estado": ESTADO_ERROR, "error": mensaje, "fecha_fin": ahora_iso()})
        else:
            actualizar(gen_id, {
                "estado": ESTADO_COMPLETADO, "resultado": resultado, "fecha_fin": ahora_iso(),
            })
            # Auto-catálogo: si generó imagen(es) por IA, las deja reutilizables en la galería.
            _autocatalogar_arte_ia(gen_id, resultado)
        # Soltamos el handle DESPUES de fijar el estado terminal (ver `lanzar_job_claude`).
        with _HANDLES_LOCK:
            _HANDLES.pop(gen_id, None)

    hilo = threading.Thread(target=_ciclo, name=f"gen-img-{gen_id}", daemon=True)
    with _HANDLES_LOCK:
        _HANDLES[gen_id] = {"hilo": hilo}
    hilo.start()
