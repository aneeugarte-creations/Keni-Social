"""Persistencia — dominio jobs. Implementación de db.py (ver barrel `db.py`)."""
from __future__ import annotations

import json

from ._db_comun import (
    UTC,
    Any,
    _conectar,
    config,
    datetime,
    timedelta,
    uuid,
)
from .tiempo import ahora_iso, hoy_utc, iso_o_vacio, iso_utc

# --------------------------------------------------------------------------- #
# Cola de jobs de generacion (#130 Fase 2 / ADR 0002 Fase B)                    #
# --------------------------------------------------------------------------- #
#
# El back ENCOLA (`encolar_job`) y devuelve de inmediato; un WORKER (in-proceso en local,
# servicio aparte en hosted) CLAVA un pendiente (`reclamar_job`) y corre `claude -p`. La
# reclamacion es CONCURRENTE-SEGURA en Postgres con `FOR UPDATE SKIP LOCKED`: varios workers
# no clavan el mismo job. La cancelacion viaja por la columna `cancelado` (el back la marca;
# el worker la lee y mata el arbol), de modo que funciona AUNQUE el worker sea otro proceso.

# Estados del ciclo de la cola (distintos de los del registro de generacion).
JOB_PENDIENTE = "pendiente"
JOB_RECLAMADO = "reclamado"
JOB_TERMINADO = "terminado"

# Margen sobre el wall-timeout tras el cual un job `reclamado` se considera SIN DUEÑO (su
# worker murio a mitad: reinicio/deploy/OOM) y OTRO worker lo RE-RECLAMA para que el trabajo
# complete solo, sin que el usuario relance. Debe SUPERAR el wall-timeout + el margen terminal
# del worker (~60 s), asi un worker VIVO que aun esta cerrando su job nunca pierde la fila
# (a esa edad la fila ya seria `terminado`, no `reclamado`). El recolector de generaciones (TTL
# 1 h) sigue como red de ultimo recurso si el re-reclamo tampoco lo saca adelante.
_RECLAIM_STALE_MARGEN_S = 300


def encolar_job(gen_id: str, spec: str, prioridad: int = 0) -> str:
    """Encola un job de generacion para el `gen_id` dado con su `spec` (JSON). Devuelve el job id.

    `spec` es el JSON serializable que el worker usa para reconstruir el trabajo (prompt +
    post-procesado + cwd). Idempotente por `gen_id` (indice UNICO): re-encolar el mismo
    registro VIVO (pendiente/reclamado) no duplica filas. El back lo llama dentro de la
    peticion y responde al instante.

    `prioridad` (entero, mayor = antes): los lanzamientos MANUALES del equipo (API/MCP) van
    con prioridad alta y los del pipeline/autogen con baja, para que un copy manual no espere
    detras del lote de fondo (`reclamar_job` ordena por prioridad DESC, creado ASC).

    RESURRECCION de filas `terminado`: re-encolar un `gen_id` cuya fila vieja ya esta
    `terminado` debe correr el trabajo NUEVO (p. ej. el reintento de un copy del pipeline que
    fallo). El `ON CONFLICT ... DO UPDATE` REVIVE la fila a `pendiente` (spec/prioridad
    nuevos, flags de despacho limpios) SOLO si estaba `terminado` (el `WHERE jobs.estado = ?`);
    una fila VIVA no se toca (idempotencia intacta).
    """
    job_id = uuid.uuid4().hex[:12]
    ahora = ahora_iso()
    con = _conectar()
    try:
        fila = con.execute(
            "INSERT INTO jobs (id, gen_id, spec, estado, creado, prioridad) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (gen_id) DO UPDATE SET "
            "spec = EXCLUDED.spec, estado = EXCLUDED.estado, creado = EXCLUDED.creado, "
            "prioridad = EXCLUDED.prioridad, cancelado = 0, worker = '', claimed_at = NULL, "
            "intentos = 0 "
            "WHERE jobs.estado = ? "
            "RETURNING id",
            (job_id, gen_id, spec, JOB_PENDIENTE, ahora, int(prioridad), JOB_TERMINADO),
        ).fetchone()
        if fila is None:
            # Hubo conflicto con una fila VIVA (gen_id ya encolado/reclamado): ni insert ni
            # update. Releemos el id REAL de la fila viva para que el llamante/worker operen
            # sobre la fila correcta.
            fila = con.execute(
                "SELECT id FROM jobs WHERE gen_id = ?", (gen_id,)
            ).fetchone()
        con.commit()
    finally:
        con.close()
    return fila["id"] if fila is not None else job_id


def contar_jobs_activos() -> int:
    """Nº de jobs EN CURSO en la cola COMPARTIDA: `pendiente` (esperando) + `reclamado` (corriendo).

    Conteo AUTORITATIVO (Postgres) de cuanto hay en curso, visible para TODOS los procesos (back,
    daemons, worker) y autoliberado al marcar un job `terminado`. Queda como señal de profundidad
    para el monitor/diagnostico y los tests.
    """
    con = _conectar()
    try:
        fila = con.execute(
            "SELECT count(*) AS n FROM jobs WHERE estado <> ?", (JOB_TERMINADO,)
        ).fetchone()
    finally:
        con.close()
    return int(fila["n"]) if fila is not None else 0


def contar_jobs_por_estado() -> dict[str, int]:
    """Conteo de jobs por estado de cola (`pendiente`/`reclamado`/`terminado`). Para el monitor."""
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT estado, count(*) AS n FROM jobs GROUP BY estado"
        ).fetchall()
    finally:
        con.close()
    return {f["estado"]: int(f["n"]) for f in filas}


def jobs_activos(limite: int = 200) -> list[dict[str, Any]]:
    """Jobs EN CURSO (`pendiente` + `reclamado`) con sus metadatos de despacho, mas antiguos primero.

    Para el monitor de cola: cada fila lleva `id`, `gen_id`, `estado`, `worker` (quien lo clavo),
    `creado` (cuando se encolo), `claimed_at` (cuando empezo a correr) y `prioridad` (mayor =
    adelanta en la cola; el Monitor distingue los manuales del lote de fondo). El front deriva
    la EDAD y enriquece con el registro de generacion (etiqueta/tipo/marca). Sin `spec` (pesado).
    `creado`/`claimed_at` son timestamptz (migracion 0033): se re-emiten al canon ISO
    ('' si `claimed_at` aun es NULL), tal como los consumia el monitor (`_edad_s`).
    """
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT id, gen_id, estado, worker, creado, claimed_at, prioridad, intentos "
            "FROM jobs WHERE estado <> ? ORDER BY creado ASC, id ASC LIMIT ?",
            (JOB_TERMINADO, int(limite)),
        ).fetchall()
    finally:
        con.close()
    return [
        {
            "id": f["id"],
            "gen_id": f["gen_id"],
            "estado": f["estado"],
            "worker": f["worker"] or "",
            "creado": iso_o_vacio(f["creado"]),
            "claimed_at": iso_o_vacio(f["claimed_at"]),
            "prioridad": int(f["prioridad"] or 0),
            "intentos": int(f["intentos"] or 0),
        }
        for f in filas
    ]


def encolados_por_dia(dias: int = 14) -> list[dict[str, Any]]:
    """Jobs ENCOLADOS por dia (de `jobs.creado`) en la ventana `dias`, dia ascendente.

    Throughput de ENTRADA de la cola: cuanto se pidio cada dia (incluye los ya `terminado`,
    que se conservan). `creado` es `timestamptz` (migracion 0033): el dia (UTC) se deriva con
    `to_char(creado AT TIME ZONE 'UTC', 'YYYY-MM-DD')`. El corte `creado >= ?` compara nativo
    (el param ISO se castea a timestamptz)."""
    corte = iso_utc(datetime.now(UTC) - timedelta(days=max(0, int(dias))))
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT to_char(creado AT TIME ZONE 'UTC', 'YYYY-MM-DD') AS dia, count(*) AS n "
            "FROM jobs WHERE creado >= ? "
            "GROUP BY to_char(creado AT TIME ZONE 'UTC', 'YYYY-MM-DD') ORDER BY dia ASC",
            (corte,),
        ).fetchall()
    finally:
        con.close()
    return [{"dia": f["dia"], "n": int(f["n"])} for f in filas]


def reclamar_job(
    worker: str = "",
    *,
    prioridad_minima: int | None = None,
    solo_proceso: bool | None = None,
    kinds_proceso: tuple[str, ...] = (),
    kinds_transcripcion: tuple[str, ...] = (),
    carriles: set[str] | None = None,
) -> dict[str, Any] | None:
    """Clava UN job de forma CONCURRENTE-SEGURA y lo devuelve (None si no hay).

    `SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1` dentro de la transaccion + UPDATE a
    `reclamado`: otro worker que corra a la vez SALTA esa fila (no la doble-ejecuta).
    Devuelve `{id, gen_id, spec}` del job clavado.

    `prioridad_minima` (corte del presupuesto, ver `presupuesto_ia`): si viene, solo se
    consideran filas con `prioridad >= prioridad_minima` (el fondo cortado queda `pendiente`
    en la cola, listo para cuando el presupuesto vuelva; lo manual sigue saliendo).

    CARRILES (CPU-bound vs inferencia): `solo_proceso` separa los KINDS de PROCESO (render de
    video / transcripcion ASR — CPU-bound: ffmpeg/whisper) de los de INFERENCIA (`claude -p` —
    I/O-bound). `kinds_proceso` es la lista de kinds CPU-bound (de `jobspec.KINDS_PROCESO`, la pasa
    el llamante para no acoplar la persistencia al dominio). El kind de proceso viaja a NIVEL RAIZ
    del spec (`spec->>'kind'`); los jobs de inferencia no lo llevan (NULL). Asi:
      - `solo_proceso=True`  -> solo jobs CPU-bound (su carril/pool propio).
      - `solo_proceso=False` -> solo jobs de inferencia (el carril de `claude`, que un video largo
        ya no puede acaparar: head-of-line eliminado).
      - `solo_proceso=None`  -> cualquiera (back-compat: el pool unico de antes).

    POOL DE WORKERS (`carriles`): si viene, solo se clavan jobs cuyo carril (replica de
    `jobspec.carril` en SQL: `carril` raiz explicito, o derivado a 'transcripcion' (kinds de
    `kinds_transcripcion`) / 'proceso' (resto de `kinds_proceso`) / 'inferencia') esté en el
    conjunto. `worker_dev` pasa {'dev'}; el `transcriptor` pasa {'transcripcion'}; el worker de
    contenido {'inferencia','proceso'} (excluye dev y transcripcion). None = cualquier carril.

    RE-RECLAMO DE JOBS SIN DUEÑO: ademas de los `pendiente`, clava los `reclamado` cuyo
    `claimed_at` es mas viejo que `wall-timeout + _RECLAIM_STALE_MARGEN_S` — su worker murio
    a mitad (reinicio/deploy/OOM) y nadie lo sacaria adelante. El umbral supera el tiempo maximo
    que un worker VIVO retiene la fila, asi nunca se roba un job en curso. El UPDATE re-sella
    `worker`/`claimed_at`, asi un segundo abandono se vuelve a cubrir.

    GUARDIA ANTI-DUPLICADO (re-reclamo de jobs sin dueño): un worker puede haber MUERTO DESPUES de
    fijar el estado terminal del registro (y de correr su post-procesado: `crear_borrador` es un
    INSERT fresco, NO idempotente) pero ANTES de llamar a `terminar_job` — el job queda
    `reclamado`. Re-ejecutarlo DUPLICARIA el borrador. Por eso, al re-reclamar un job SIN DUEÑO,
    consultamos el registro de generaciones: si su `gen_id` YA esta en un estado TERMINAL
    (`completado`/`error`), NO se relanza: se marca el job `terminado` y se pasa al siguiente
    (su trabajo ya se hizo). Solo afecta al re-reclamo de jobs sin dueño; un `pendiente` nunca corrio.

    RENDIMIENTO (la lectura del YAML va FUERA del row-lock): la guardia anti-duplicado lee y
    parsea un fichero YAML (`_gen_ya_terminal` -> `generaciones.obtener`). Hacer ese I/O de disco
    mientras se retiene el `FOR UPDATE` alargaba la contencion de la fila (y, con varios workers,
    de toda la cola). Ahora se CLAVA la fila y se hace COMMIT (suelta el lock) ANTES de tocar el
    disco; recien entonces, si era un job sin dueño, se comprueba si su registro ya es terminal y, en
    ese caso, se cierra el job sin relanzarlo. Tras clavarlo con `claimed_at` fresco, ningun otro
    worker lo ve como sin dueño, asi que cerrarlo fuera del lock es seguro (no hay carrera). El
    camino normal (un `pendiente`) NO toca el disco en absoluto.

    TOPE DE INTENTOS (anti crash-loop): cada reclamo incrementa `jobs.intentos`. Un job sin dueño
    que ya gasto `KENI_JOBS_MAX_INTENTOS` intentos NO se re-ejecuta: se cierra su job y su
    registro queda en error (motivo `interrumpido`, mensaje claro). `reencolar_job` (reintento
    admin) y la resurreccion de `encolar_job` resetean el contador (intencion humana/trabajo
    nuevo). Esta comprobacion es DB-pura (columna `intentos`), asi que permanece dentro del lock
    (sin disco).
    """
    ahora = ahora_iso()
    limite_suelto = iso_utc(
        datetime.now(UTC) - timedelta(seconds=config.claude_timeout() + _RECLAIM_STALE_MARGEN_S)
    )
    filtro_prioridad = "" if prioridad_minima is None else "AND prioridad >= ? "
    params_prio: tuple[int, ...] = () if prioridad_minima is None else (int(prioridad_minima),)
    # Carril por tipo de trabajo (CPU-bound vs inferencia): filtra por el `kind` raiz del spec.
    filtro_kind = ""
    params_kind: tuple[str, ...] = ()
    if solo_proceso is not None and kinds_proceso:
        marcadores = ", ".join("?" for _ in kinds_proceso)
        op = "IN" if solo_proceso else "NOT IN"
        # `COALESCE(spec->>'kind','')`: los jobs de inferencia no llevan kind raiz (NULL -> '').
        filtro_kind = f"AND COALESCE(spec->>'kind', '') {op} ({marcadores}) "
        params_kind = tuple(kinds_proceso)
    # CARRIL (POOL de workers): filtra por el carril del spec, replicando `jobspec.carril` en SQL:
    # un `carril` raiz EXPLICITO (lo ponen los jobs de desarrollo: 'dev') manda; si no, se DERIVA
    # ('transcripcion' si el kind raiz es de transcripcion, 'proceso' si es de otro proceso,
    # 'inferencia' en otro caso). La rama de transcripcion va ANTES que la de proceso porque sus
    # kinds son un subconjunto de `kinds_proceso`. `worker_dev` pasa {'dev'}; el `transcriptor`
    # {'transcripcion'}; el worker de contenido {'inferencia','proceso'} (excluye dev/transcripcion).
    filtro_carril = ""
    params_carril: tuple[str, ...] = ()
    if carriles:
        carril_vals = tuple(sorted(carriles))
        car_marc = ", ".join("?" for _ in carril_vals)
        ramas = "CASE WHEN COALESCE(spec->>'carril', '') <> '' THEN spec->>'carril' "
        if kinds_transcripcion:
            trans_marc = ", ".join("?" for _ in kinds_transcripcion)
            ramas += f"WHEN COALESCE(spec->>'kind', '') IN ({trans_marc}) THEN 'transcripcion' "
            params_carril += tuple(kinds_transcripcion)
        if kinds_proceso:
            kind_marc = ", ".join("?" for _ in kinds_proceso)
            ramas += f"WHEN COALESCE(spec->>'kind', '') IN ({kind_marc}) THEN 'proceso' "
            params_carril += tuple(kinds_proceso)
        expr_carril = ramas + "ELSE 'inferencia' END"
        params_carril += carril_vals
        filtro_carril = f"AND ({expr_carril}) IN ({car_marc}) "
    con = _conectar()
    try:
        # Acotamos los saltos: descartamos jobs sin dueño ya-terminados (terminando su job) y
        # seguimos buscando, sin reintentar para siempre.
        for _ in range(_MAX_SALTOS_RECLAMO):
            fila = con.execute(
                "SELECT id, gen_id, spec, estado, intentos FROM jobs "
                "WHERE (estado = ? OR (estado = ? AND claimed_at IS NOT NULL AND claimed_at < ?)) "
                + filtro_prioridad + filtro_kind + filtro_carril +
                # Prioridad primero (manual > pipeline/autogen), luego FIFO por antiguedad.
                "ORDER BY prioridad DESC, creado ASC, id ASC LIMIT 1 FOR UPDATE SKIP LOCKED",
                (JOB_PENDIENTE, JOB_RECLAMADO, limite_suelto,
                 *params_prio, *params_kind, *params_carril),
            ).fetchone()
            if fila is None:
                con.commit()
                return None
            # Solo un JOB SIN DUEÑO (estado `reclamado`) pudo haber corrido ya su post-procesado.
            es_suelto = fila["estado"] == JOB_RECLAMADO
            # TOPE DE INTENTOS (anti crash-loop): un job sin dueño que ya agoto sus intentos NO se
            # re-ejecuta. Es DB-puro (sin disco): se decide DENTRO del lock. Se cierra el job y
            # el registro queda en error claro (best-effort, ya fuera del lock tras el commit).
            if es_suelto and int(fila["intentos"] or 0) >= config.jobs_max_intentos():
                con.execute(
                    "UPDATE jobs SET estado = ? WHERE id = ?", (JOB_TERMINADO, fila["id"])
                )
                con.commit()
                _marcar_error_reintentos(fila["gen_id"], int(fila["intentos"] or 0))
                continue
            # CLAVA la fila y COMMIT: suelta el row-lock ANTES de cualquier I/O de disco.
            con.execute(
                "UPDATE jobs SET estado = ?, worker = ?, claimed_at = ?, "
                "intentos = intentos + 1 WHERE id = ?",
                (JOB_RECLAMADO, worker, ahora, fila["id"]),
            )
            con.commit()
            # GUARDIA ANTI-DUPLICADO, ya FUERA del lock: solo un job sin dueño pudo haber corrido su
            # post-procesado. Si su registro ya es terminal, el trabajo se hizo: cerramos el job
            # SIN relanzarlo (evita el borrador duplicado) y buscamos el siguiente. Con el
            # `claimed_at` fresco que acabamos de fijar, ningun otro worker lo re-reclama mientras
            # tanto, asi que esta segunda escritura es segura sin retener el lock.
            if es_suelto and _gen_ya_terminal(fila["gen_id"]):
                con.execute(
                    "UPDATE jobs SET estado = ? WHERE id = ?", (JOB_TERMINADO, fila["id"])
                )
                con.commit()
                continue
            return {"id": fila["id"], "gen_id": fila["gen_id"], "spec": fila["spec"]}
        con.commit()
        return None
    finally:
        con.close()


# Tope de jobs sin dueño ya-terminados que `reclamar_job` descarta de una tirada antes de rendirse
# (cota dura para que el barrido nunca gire indefinidamente). Si hubiera mas, el siguiente
# `reclamar` los sigue limpiando.
_MAX_SALTOS_RECLAMO = 50


def _marcar_error_reintentos(gen_id: str, intentos: int) -> None:
    """Deja el registro de generacion en ERROR claro al descartar un job sin intentos.

    Import perezoso de `generaciones` (igual que `_gen_ya_terminal`) y best-effort: si el
    registro no se puede escribir, el job igualmente quedo `terminado` (el recolector de
    generaciones acabara marcando el `ejecutando` colgado como interrumpido).
    """
    try:
        from . import generaciones

        g = generaciones.obtener(gen_id)
        if g is None or g.get("estado") != generaciones.ESTADO_EJECUTANDO:
            return  # ya tiene un terminal honesto (o no existe): no pisar nada
        generaciones.actualizar(gen_id, {
            "estado": generaciones.ESTADO_ERROR,
            "motivo": generaciones.MOTIVO_INTERRUMPIDO,
            "error": (
                f"La generación se interrumpió {intentos} veces (el proceso que la ejecutaba "
                "murió) y se descartó. Puedes relanzarla manualmente."
            ),
            "fecha_fin": ahora_iso(),
        })
    except Exception:  # noqa: BLE001 -- best-effort: el descarte del job ya esta hecho
        pass


def _gen_ya_terminal(gen_id: str) -> bool:
    """True si el registro de generacion `gen_id` ya esta en estado TERMINAL (no `ejecutando`).

    Lee el almacen de generaciones (YAML, fuente del estado terminal que fija el worker). Import
    perezoso para no acoplar `db` con `generaciones` a nivel de modulo. Best-effort: ante
    cualquier fallo de lectura devuelve False (preferimos re-ejecutar a tragarnos un job).
    """
    try:
        from . import generaciones

        g = generaciones.obtener(gen_id)
    except Exception:  # noqa: BLE001 -- si no se puede leer el registro, no bloqueamos el reclamo.
        return False
    if g is None:
        return False
    return g.get("estado") in (generaciones.ESTADO_COMPLETADO, generaciones.ESTADO_ERROR)


def terminar_job(job_id: str) -> None:
    """Marca un job como terminado (el worker ya fijo el estado terminal del registro)."""
    con = _conectar()
    try:
        con.execute("UPDATE jobs SET estado = ? WHERE id = ?", (JOB_TERMINADO, job_id))
        con.commit()
    finally:
        con.close()


def reencolar_job(gen_id: str) -> bool:
    """Devuelve a `pendiente` el job de `gen_id` (reintento admin de un job atascado).

    Limpia `worker`/`claimed_at` y el flag `cancelado`, de modo que un worker lo vuelva a clavar
    y a correr `claude` con el MISMO `spec`. El llamante (capa API) debe ademas reabrir el
    registro de generacion a `ejecutando` (si no, el guardia anti-duplicado de `reclamar_job` lo
    cerraria al verlo en estado terminal). Devuelve False si no hay fila para ese `gen_id`.

    "Limpio" aqui: `worker` vuelve a '' (TEXT) y `claimed_at` a NULL (timestamptz, migracion
    0033: el sentinel "sin reclamar" es ahora NULL, no ''), el mismo convenio que el encolado.
    `intentos` se RESETEA: el reintento es una decision humana (o un apagado gracioso), no la
    continuacion de un crash-loop."""
    con = _conectar()
    try:
        cur = con.execute(
            "UPDATE jobs SET estado = ?, worker = '', claimed_at = NULL, cancelado = 0, "
            "intentos = 0 WHERE gen_id = ?",
            (JOB_PENDIENTE, gen_id),
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def priorizar_job(gen_id: str, prioridad: int) -> bool:
    """Sube la prioridad de despacho del job PENDIENTE de `gen_id`. True si lo tocó.

    Solo actúa sobre jobs aún `pendiente` (uno reclamado ya corre; uno terminado ya salió):
    el worker ordena por (prioridad DESC, creado), así que el job adelanta a todo lo de
    prioridad menor en el siguiente claim. Decisión humana desde el Monitor ("este primero").
    """
    con = _conectar()
    try:
        cur = con.execute(
            "UPDATE jobs SET prioridad = ? WHERE gen_id = ? AND estado = ?",
            (int(prioridad), gen_id, JOB_PENDIENTE),
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def cancelar_job(gen_id: str) -> bool:
    """Marca el job de un `gen_id` como cancelado (cross-proceso). True si habia un job.

    El back lo llama al cancelar; el worker LEE `cancelado` y mata el arbol. Tambien
    cubre el caso de un job AUN pendiente (no reclamado): el worker, al clavarlo, ve el
    flag y lo finaliza como cancelado sin lanzar `claude`. Devuelve False si no hay job
    (ya terminado o nunca encolado): el llamante cae a la cancelacion in-memoria.
    """
    con = _conectar()
    try:
        cur = con.execute(
            "UPDATE jobs SET cancelado = 1 WHERE gen_id = ? AND estado <> ?",
            (gen_id, JOB_TERMINADO),
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def job_cancelado(job_id: str) -> bool:
    """True si el job esta marcado como cancelado (lo sondea el worker en ejecucion)."""
    con = _conectar()
    try:
        fila = con.execute("SELECT cancelado FROM jobs WHERE id = ?", (job_id,)).fetchone()
    finally:
        con.close()
    return bool(fila["cancelado"]) if fila is not None else False


def gen_ids_jobs_pendientes() -> set[str]:
    """`gen_id` de TODOS los jobs `pendiente` (esperando turno en la cola).

    Lo usa el recolector de generaciones: un registro `ejecutando` cuyo job sigue PENDIENTE no
    esta colgado (nada llego a correr ni a morir): esta legitimamente en cola, posiblemente
    retenido por el corte de presupuesto o el kill switch (`presupuesto_ia`), y puede
    esperar mas que el TTL. Cerrarlo lo mataria en silencio: la guardia anti-duplicado del
    reclamo veria el registro terminal y cerraria el job sin ejecutarlo.
    """
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT gen_id FROM jobs WHERE estado = ?", (JOB_PENDIENTE,)
        ).fetchall()
    finally:
        con.close()
    return {f["gen_id"] for f in filas}


# --------------------------------------------------------------------------- #
# Ledger de gasto de IA (economia de tokens; ver `presupuesto_ia.py`)          #
# --------------------------------------------------------------------------- #
#
# Una fila por generacion CERRADA (estado terminal) con sus tokens/coste. UPSERT por
# `gen_id`: re-cerrar la misma generacion (reintento, re-encolado tras deploy) ACTUALIZA la
# fila en vez de duplicar gasto. La suma del `dia` es la cuenta autoritativa del presupuesto
# diario, compartida por todos los procesos (back/worker/daemons) via Postgres.


def registrar_gasto_ia(
    gen_id: str,
    *,
    dia: str,
    tipo: str = "",
    marca: str = "",
    tokens_in: int = 0,
    tokens_out: int = 0,
    coste_usd: float = 0.0,
    prompt_chars: int = 0,
    cache_read: int = 0,
    cache_creation: int = 0,
    modelo: str = "",
    proceso: str = "produccion",
    etapa: str = "",
) -> None:
    """UPSERT del gasto de UNA generacion cerrada (idempotente por `gen_id`).

    `dia` es el dia UTC (YYYY-MM-DD) en que se CERRO la generacion (cuando se gasto). Un
    re-cierre sobreescribe tokens/coste con los ultimos valores (nunca suma dos veces).
    `prompt_chars` (economia de contexto): tamano del prompt que entro a `claude -p`.
    `cache_read`/`cache_creation` (prompt caching): tokens de cache leidos / creados, para medir
    si el caching ocurre y el ahorro (run sin caching => 0; no rompe agregados viejos).
    `modelo`: id del modelo que gasto (para el coste medio por imagen POR MODELO).
    `proceso` (ADR 0011): 'investigacion' | 'produccion', el loop de la maquina que gasto;
    lo conoce el llamante (`presupuesto_ia.registrar_cierre` via `generaciones.proceso_de`).
    Default 'produccion' (la maquina de contenido) para llamantes que aun no lo pasan.
    `etapa` (opcional): fase del pipeline EXPLICITA cuando el llamante la conoce (las fases inline
    del pool, que comparten `tipo='pipeline'`); vacio => la economia la deriva de `tipo`+`proceso`.
    """
    if not gen_id:
        return
    ahora = ahora_iso()
    con = _conectar()
    try:
        con.execute(
            "INSERT INTO gasto_ia (gen_id, dia, tipo, marca, tokens_in, tokens_out, "
            "coste_usd, prompt_chars, cache_read, cache_creation, modelo, proceso, etapa, actualizado) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (gen_id) DO UPDATE SET "
            "dia = EXCLUDED.dia, tipo = EXCLUDED.tipo, marca = EXCLUDED.marca, "
            "tokens_in = EXCLUDED.tokens_in, tokens_out = EXCLUDED.tokens_out, "
            "coste_usd = EXCLUDED.coste_usd, prompt_chars = EXCLUDED.prompt_chars, "
            "cache_read = EXCLUDED.cache_read, cache_creation = EXCLUDED.cache_creation, "
            "modelo = EXCLUDED.modelo, proceso = EXCLUDED.proceso, etapa = EXCLUDED.etapa, "
            "actualizado = EXCLUDED.actualizado",
            (gen_id, dia, tipo, marca, int(tokens_in), int(tokens_out), float(coste_usd),
             int(prompt_chars), int(cache_read), int(cache_creation), str(modelo or ""),
             str(proceso or "produccion"), str(etapa or ""), ahora),
        )
        con.commit()
    finally:
        con.close()


def coste_medio_imagen(modelo: str = "", limite: int = 50) -> dict[str, Any]:
    """Coste medio por IMAGEN (USD) de las ultimas `limite` generaciones tipo `imagen`.

    Promedia `coste_usd` de las filas `gasto_ia` con `tipo='imagen'` y coste > 0, las mas
    recientes primero. Con `modelo`, acota a ese modelo (estimacion por modelo); sin el,
    media GLOBAL de imagen. Devuelve `{por_imagen, muestras, modelo}`: `por_imagen` es None
    si no hay muestras (el front cae al fallback). La moneda la fija el endpoint (USD).
    """
    limite = max(1, min(int(limite or 1), 500))
    sql = (
        "SELECT coste_usd FROM gasto_ia "
        "WHERE tipo = 'imagen' AND coste_usd > 0"
    )
    params: list[Any] = []
    if modelo:
        sql += " AND modelo = ?"
        params.append(str(modelo))
    sql += " ORDER BY actualizado DESC LIMIT ?"
    params.append(limite)
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    costes = [float(f["coste_usd"]) for f in filas]
    por_imagen = (sum(costes) / len(costes)) if costes else None
    return {"por_imagen": por_imagen, "muestras": len(costes), "modelo": modelo or ""}


def gasto_ia_del_dia(dia: str, marca: str = "") -> dict[str, Any]:
    """Gasto AGREGADO de un dia UTC: `{tokens, tokens_in, tokens_out, coste_usd, generaciones}`.

    Es la lectura del corte automatico (`presupuesto_ia.nivel()`): tokens = in + out del dia.
    `marca` ("" = TODAS, agregado global; un id acota a esa marca) para el corte POR MARCA.
    """
    where = "WHERE dia = ?"
    params: tuple[Any, ...] = (dia,)
    if marca:
        where += " AND marca = ?"
        params = (dia, marca)
    con = _conectar()
    try:
        fila = con.execute(
            "SELECT COALESCE(SUM(tokens_in), 0) AS tin, COALESCE(SUM(tokens_out), 0) AS tout, "
            "COALESCE(SUM(coste_usd), 0) AS coste, COUNT(*) AS n "
            f"FROM gasto_ia {where}",
            params,
        ).fetchone()
    finally:
        con.close()
    tin = int(fila["tin"]) if fila is not None else 0
    tout = int(fila["tout"]) if fila is not None else 0
    return {
        "tokens": tin + tout,
        "tokens_in": tin,
        "tokens_out": tout,
        "coste_usd": float(fila["coste"]) if fila is not None else 0.0,
        "generaciones": int(fila["n"]) if fila is not None else 0,
    }


def gasto_ia_del_dia_por_proceso(dia: str, marca: str = "") -> dict[str, dict[str, Any]]:
    """Gasto del dia UTC DESGLOSADO por proceso (ADR 0011): investigacion vs produccion.

    Mismo dia que `gasto_ia_del_dia`, agrupado por la columna `proceso` del ledger. Por cada
    proceso devuelve `{tokens_in, tokens_out, tokens (=in+out), coste_usd, generaciones}`.
    GARANTIZA siempre las claves 'investigacion' y 'produccion' (a ceros si no hay filas), para
    que el desglose de la Economia tenga ambos motores sin condicionar la UI. Otros valores de
    `proceso` (legado/desconocido) tambien aparecen si existen filas.
    `marca` ("" = TODAS; un id acota a esa marca) para el corte por motor POR MARCA.
    """
    por_proceso: dict[str, dict[str, Any]] = {
        "investigacion": {"tokens_in": 0, "tokens_out": 0, "tokens": 0, "coste_usd": 0.0, "generaciones": 0},
        "produccion": {"tokens_in": 0, "tokens_out": 0, "tokens": 0, "coste_usd": 0.0, "generaciones": 0},
    }
    where = "WHERE dia = ?"
    params: tuple[Any, ...] = (dia,)
    if marca:
        where += " AND marca = ?"
        params = (dia, marca)
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT proceso, COALESCE(SUM(tokens_in), 0) AS tin, COALESCE(SUM(tokens_out), 0) AS tout, "
            "COALESCE(SUM(coste_usd), 0) AS coste, COUNT(*) AS n "
            f"FROM gasto_ia {where} GROUP BY proceso",
            params,
        ).fetchall()
    finally:
        con.close()
    for fila in filas:
        proceso = str(fila["proceso"] or "")
        if not proceso:
            continue
        tin = int(fila["tin"])
        tout = int(fila["tout"])
        por_proceso[proceso] = {
            "tokens_in": tin,
            "tokens_out": tout,
            "tokens": tin + tout,
            "coste_usd": float(fila["coste"]),
            "generaciones": int(fila["n"]),
        }
    return por_proceso


# Pestañas de la página Contexto: las 4 que agrupan TODO el gasto de prompts. La economía
# reclasifica cada fila del ledger en una de ellas al leer (espejo de las pestañas de `fases.ts`).
PESTANA_INVESTIGACION = "investigacion"
PESTANA_PRODUCCION = "produccion"
PESTANA_HERRAMIENTAS = "herramientas"
PESTANA_DESARROLLO = "desarrollo"
PESTANAS_ECONOMIA = (
    PESTANA_INVESTIGACION,
    PESTANA_PRODUCCION,
    PESTANA_HERRAMIENTAS,
    PESTANA_DESARROLLO,
)
# `tipo` -> Desarrollo (pipeline de auto-desarrollo: fases del carril + discovery).
_TIPOS_DESARROLLO = frozenset({"dev-fase", "dev-discovery"})
# `tipo` -> Herramientas (agentes sueltos de la pestaña: Recibir/Importar/Ideación/Audio).
_TIPOS_HERRAMIENTAS = frozenset(
    {"insumos", "import-calendario", "parrilla-import", "evergreen-ideas", "transcribir"}
)


def pestana_economia(proceso: str, tipo: str) -> str:
    """Pestaña de Contexto (1 de las 4) a la que pertenece una fila de gasto del ledger.

    Desarrollo y Herramientas se reconocen por su `tipo` (inequívoco); el resto cae a su MOTOR
    según la columna `proceso` sellada (investigacion|produccion), que ya resuelve la ambigüedad
    de los tipos compartidos como `pipeline` (verificación de fuente vs redacción). Default
    produccion ante un proceso desconocido o vacío.
    """
    if tipo in _TIPOS_DESARROLLO:
        return PESTANA_DESARROLLO
    if tipo in _TIPOS_HERRAMIENTAS:
        return PESTANA_HERRAMIENTAS
    if proceso == PESTANA_INVESTIGACION:
        return PESTANA_INVESTIGACION
    return PESTANA_PRODUCCION


# `tipo` del ledger -> ETAPA (fase del pipeline de Contexto). Varios tipos colapsan en una fase
# (copy/autogen/evergreen = Redactar) para que el desglose "por etapa" hable el idioma del
# pipeline (Redactar/Verificar/Ilustrar…) en vez del tipo crudo del job (pipeline/copy…). Las
# sub-fases que NO dejan fila propia en el ledger (Admitir sin IA; Fusionar/Traducir/Clasificar
# inline) no aparecen aquí: solo se listan las etapas que de verdad consumen tokens.
_ETAPA_POR_TIPO = {
    # Investigación
    "rss": "Recolectar", "noticias-ia": "Recolectar", "noticias": "Recolectar",
    "verificacion": "Verificar", "revision": "Revisión editorial",
    # Producción
    "copy": "Redactar", "autogen": "Redactar", "evergreen": "Redactar",
    "sugerir-hashtags": "Sugerir hashtags",
    "imagen": "Ilustrar",
    "critica-ia": "Crítica",
    "carrusel": "Carrusel",
    # Herramientas
    "insumos": "Recibir",
    "import-calendario": "Importar", "parrilla-import": "Importar",
    "evergreen-ideas": "Ideación",
    "transcribir": "Audio",
    # Desarrollo
    "dev-fase": "Desarrollo", "dev-discovery": "Exploración",
}


def etapa_economia(proceso: str, tipo: str) -> str:
    """ETAPA (fase del pipeline) de una fila de gasto, para el desglose "por etapa".

    El tipo `pipeline` es ambiguo: lo desambigua el `proceso` sellado (investigación = Verificar
    la fuente; producción = Redactar). El resto sale del mapa `tipo -> etapa`; un tipo desconocido
    cae a sí mismo (mejor un nombre crudo que perder la fila)."""
    if tipo == "pipeline":
        return "Verificar" if proceso == PESTANA_INVESTIGACION else "Redactar"
    return _ETAPA_POR_TIPO.get(tipo, tipo or "—")


def gasto_ia_economia_por_proceso(dias: int = 7, marca: str = "") -> dict[str, dict[str, Any]]:
    """Desglose económico de los últimos `dias` (UTC) DESDE el ledger `gasto_ia`, AGRUPADO en las
    4 PESTAÑAS de Contexto (investigacion/produccion/herramientas/desarrollo).

    Fuente ÚNICA y autoritativa de la página Economía: el mismo ledger que la tarjeta de
    presupuesto. `marca` vacía = AGREGADO de todas las marcas; una marca concreta acota el
    desglose a sus filas. Cada fila se reclasifica con `pestana_economia(proceso, tipo)`. Por cada
    pestaña devuelve:
      - `total`:    `{items, tokens, coste_usd}` (items=COUNT, tokens=SUM(in+out), coste=SUM).
      - `por_dia`:  EXACTAMENTE `dias` entradas, antiguo→reciente, ZERO-FILLED; cada una
                    `{dia, items, tokens, coste_usd, por_etapa:[{etapa, items, tokens, coste_usd}]}`
                    (el desglose por ETAPA/fase de ESE día, ordenado por coste desc).
      - `por_etapa`:`[{etapa, items, tokens, coste_usd, por_dia:[{dia, items, tokens, coste_usd}]}]`
                    ordenado por coste desc; el `por_dia` interno va zero-filled (longitud `dias`).
    La ETAPA es la fase del pipeline (Redactar/Verificar/Ilustrar…), derivada con `etapa_economia`
    (varios tipos colapsan en una fase); NO es el `tipo` crudo del job.
    GARANTIZA siempre las 4 claves (a ceros, con `por_dia` de longitud `dias`) aunque no haya filas.
    `dia` es `date` (migración 0033): el corte `dia >= ?` compara nativo y el `dia` agrupado se
    re-emite como string ISO `YYYY-MM-DD`.
    """
    n = max(1, int(dias))
    hoy = hoy_utc()
    # Eje temporal esperado, antiguo -> reciente: el corte del SELECT es su primer dia
    # (hoy_utc - (n-1)); zero-fill = sembrar estos n dias a cero y volcar encima lo agregado.
    dias_esperados = [(hoy - timedelta(days=n - 1 - i)).isoformat() for i in range(n)]
    corte = dias_esperados[0]

    def _acc_nuevo() -> dict[str, Any]:
        return {
            "items": 0,
            "tokens": 0,
            "coste_usd": 0.0,
            # dia -> {items, tokens, coste_usd, _etapas: {tipo -> {items, tokens, coste_usd}}}
            "_por_dia": {
                d: {"items": 0, "tokens": 0, "coste_usd": 0.0, "_etapas": {}}
                for d in dias_esperados
            },
            # tipo(etapa) -> {items, tokens, coste_usd, _dias: {dia -> {items, tokens, coste_usd}}}
            "_por_etapa": {},
        }

    acumulado: dict[str, dict[str, Any]] = {p: _acc_nuevo() for p in PESTANAS_ECONOMIA}
    where = "WHERE dia >= ?"
    params: tuple[Any, ...] = (corte,)
    if marca:
        where += " AND marca = ?"
        params = (corte, marca)
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT proceso, tipo, etapa, dia, COUNT(*) AS items, "
            "COALESCE(SUM(tokens_in + tokens_out), 0) AS tokens, "
            "COALESCE(SUM(coste_usd), 0) AS coste "
            f"FROM gasto_ia {where} GROUP BY proceso, tipo, etapa, dia",
            params,
        ).fetchall()
    finally:
        con.close()

    def _bump(celda: dict[str, Any], items: int, tokens: int, coste: float) -> None:
        celda["items"] += items
        celda["tokens"] += tokens
        celda["coste_usd"] += coste

    for f in filas:
        items = int(f["items"])
        tokens = int(f["tokens"])
        coste = float(f["coste"])
        proceso = str(f["proceso"] or "")
        tipo = str(f["tipo"] or "")
        acc = acumulado[pestana_economia(proceso, tipo)]
        # La ETAPA (fase del pipeline) es la unidad del desglose, no el tipo crudo: varios tipos
        # colapsan en una fase (copy/autogen -> Redactar). Si la fila trae una etapa EXPLICITA (las
        # fases inline del pool, que comparten tipo='pipeline'), manda; si no, se deriva del tipo.
        etapa_nom = str(f["etapa"] or "") or etapa_economia(proceso, tipo)
        _bump(acc, items, tokens, coste)
        dia = iso_o_vacio(f["dia"])
        celda_dia = acc["_por_dia"].get(dia)
        if celda_dia is not None:
            _bump(celda_dia, items, tokens, coste)
            _bump(
                celda_dia["_etapas"].setdefault(
                    etapa_nom, {"items": 0, "tokens": 0, "coste_usd": 0.0}
                ),
                items, tokens, coste,
            )
        etapa = acc["_por_etapa"].setdefault(
            etapa_nom, {"items": 0, "tokens": 0, "coste_usd": 0.0, "_dias": {}}
        )
        _bump(etapa, items, tokens, coste)
        if dia in acc["_por_dia"]:
            _bump(
                etapa["_dias"].setdefault(dia, {"items": 0, "tokens": 0, "coste_usd": 0.0}),
                items, tokens, coste,
            )

    def _orden_etapa(r: dict[str, Any]) -> tuple[float, str]:
        return (-r["coste_usd"], r["etapa"])

    resultado: dict[str, dict[str, Any]] = {}
    for pestana, acc in acumulado.items():
        por_dia = []
        for d in dias_esperados:
            celda = acc["_por_dia"][d]
            por_dia.append({
                "dia": d,
                "items": celda["items"],
                "tokens": celda["tokens"],
                "coste_usd": celda["coste_usd"],
                "por_etapa": sorted(
                    ({"etapa": e, **v} for e, v in celda["_etapas"].items()), key=_orden_etapa
                ),
            })
        por_etapa = sorted(
            (
                {
                    "etapa": etapa_nom,
                    "items": v["items"],
                    "tokens": v["tokens"],
                    "coste_usd": v["coste_usd"],
                    "por_dia": [
                        {"dia": d, **v["_dias"].get(d, {"items": 0, "tokens": 0, "coste_usd": 0.0})}
                        for d in dias_esperados
                    ],
                }
                for etapa_nom, v in acc["_por_etapa"].items()
            ),
            key=_orden_etapa,
        )
        resultado[pestana] = {
            "total": {
                "items": acc["items"],
                "tokens": acc["tokens"],
                "coste_usd": acc["coste_usd"],
            },
            "por_dia": por_dia,
            "por_etapa": por_etapa,
        }
    return resultado


# --------------------------------------------------------------------------- #
# Indice de GENERACIONES (rendimiento del listado; ver `generaciones._almacen`) #
# --------------------------------------------------------------------------- #
#
# El registro de cada generacion vive en un YAML (fuente de verdad del DETALLE pesado). Este
# indice replica los campos LIGEROS del listado para paginar por SQL sin parsear ~2000 YAML por
# peticion. `payload` (jsonb) guarda el dict publico ligero (sin prompt/razonamiento) que
# `listar` devuelve. UPSERT por `gen_id`: lo mantiene el almacen al crear/actualizar.


def indexar_generacion(
    gen_id: str,
    *,
    fecha_inicio: str = "",
    estado: str = "",
    tipo: str = "",
    marca: str = "",
    proceso: str = "",
    publicacion_id: str = "",
    payload: dict[str, Any] | None = None,
) -> None:
    """UPSERT de la fila de indice de una generacion (idempotente por `gen_id`).

    `payload` es el dict publico LIGERO (lo que devuelve `listar`); se guarda en la columna
    jsonb (se pasa serializado, Postgres lo castea, igual que `jobs.spec`). Las columnas sueltas
    (fecha_inicio/estado/marca/...) son las que el indice consulta/ordena.
    """
    if not gen_id:
        return
    con = _conectar()
    try:
        con.execute(
            "INSERT INTO generaciones_indice (gen_id, fecha_inicio, estado, tipo, marca, "
            "proceso, publicacion_id, payload, actualizado) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (gen_id) DO UPDATE SET "
            "fecha_inicio = EXCLUDED.fecha_inicio, estado = EXCLUDED.estado, "
            "tipo = EXCLUDED.tipo, marca = EXCLUDED.marca, proceso = EXCLUDED.proceso, "
            "publicacion_id = EXCLUDED.publicacion_id, payload = EXCLUDED.payload, "
            "actualizado = EXCLUDED.actualizado",
            (gen_id, fecha_inicio, estado, tipo, marca, proceso, publicacion_id,
             json.dumps(payload or {}, ensure_ascii=False), ahora_iso()),
        )
        con.commit()
    finally:
        con.close()


def desindexar_generacion(gen_id: str) -> None:
    """Borra la fila de indice de una generacion (al borrar/limpiar el YAML). Idempotente."""
    if not gen_id:
        return
    con = _conectar()
    try:
        con.execute("DELETE FROM generaciones_indice WHERE gen_id = ?", (gen_id,))
        con.commit()
    finally:
        con.close()


def _payload_indice(fila: dict[str, Any]) -> dict[str, Any]:
    """Reconstruye el dict publico desde una fila de indice (payload jsonb -> dict; id sellado)."""
    payload = fila.get("payload")
    if isinstance(payload, str):  # backend sin jsonb-a-dict: deserializa defensivamente
        try:
            payload = json.loads(payload)
        except (ValueError, TypeError):
            payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload.setdefault("id", fila.get("gen_id", ""))
    return payload


def listar_indice_generaciones(
    *, marca: str | None = None, limite: int | None = None, desplazamiento: int = 0
) -> list[dict[str, Any]]:
    """Listado de generaciones desde el INDICE (recientes primero), paginado por SQL.

    Devuelve los `payload` (dicts publicos ligeros) ordenados por (fecha_inicio DESC, gen_id
    DESC). `marca` no vacia filtra por marca; `limite=None` no recorta.
    """
    filtro = "WHERE marca = ? " if marca else ""
    params: list[Any] = [marca] if marca else []
    sql = (
        "SELECT gen_id, payload FROM generaciones_indice " + filtro +
        "ORDER BY fecha_inicio DESC, gen_id DESC"
    )
    if limite is not None:
        sql += " LIMIT ? OFFSET ?"
        params += [max(0, int(limite)), max(0, int(desplazamiento or 0))]
    elif desplazamiento:
        sql += " OFFSET ?"
        params.append(max(0, int(desplazamiento or 0)))
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_payload_indice(f) for f in filas]


def contar_indice_generaciones(*, marca: str | None = None) -> int:
    """Total de filas del indice de generaciones (filtrado por marca si viene)."""
    filtro = "WHERE marca = ?" if marca else ""
    params: tuple[Any, ...] = (marca,) if marca else ()
    con = _conectar()
    try:
        fila = con.execute(
            "SELECT count(*) AS n FROM generaciones_indice " + filtro, params
        ).fetchone()
    finally:
        con.close()
    return int(fila["n"]) if fila is not None else 0


def indice_generaciones_por_estado(estado: str) -> list[dict[str, Any]]:
    """Payloads de las generaciones del indice en `estado` (recientes primero). Para el recolector."""
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT gen_id, payload FROM generaciones_indice WHERE estado = ? "
            "ORDER BY fecha_inicio DESC, gen_id DESC",
            (estado,),
        ).fetchall()
    finally:
        con.close()
    return [_payload_indice(f) for f in filas]


def indice_generaciones_vacio() -> bool:
    """True si el indice no tiene filas (para decidir el backfill perezoso desde los YAML)."""
    con = _conectar()
    try:
        fila = con.execute("SELECT 1 FROM generaciones_indice LIMIT 1").fetchone()
    finally:
        con.close()
    return fila is None


def gasto_ia_por_dia(dias: int = 14) -> list[dict[str, Any]]:
    """Serie de gasto por dia (ventana `dias`, dia ascendente): tokens/coste/generaciones.

    Para el monitor y el agente de observabilidad (lado de CONSUMO de la cola, en tokens).
    `dia` es `date` (migracion 0033): el corte `dia >= ?` compara nativo (el param `YYYY-MM-DD`
    se castea a date) y el `dia` agrupado se re-emite como string ISO `YYYY-MM-DD`.
    """
    corte = iso_utc(datetime.now(UTC) - timedelta(days=max(0, int(dias))))[:10]
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT dia, COALESCE(SUM(tokens_in), 0) AS tin, "
            "COALESCE(SUM(tokens_out), 0) AS tout, COALESCE(SUM(coste_usd), 0) AS coste, "
            "COALESCE(SUM(prompt_chars), 0) AS pchars, "
            "COALESCE(SUM(cache_read), 0) AS cread, COALESCE(SUM(cache_creation), 0) AS ccreac, "
            "COUNT(*) AS n FROM gasto_ia WHERE dia >= ? GROUP BY dia ORDER BY dia ASC",
            (corte,),
        ).fetchall()
    finally:
        con.close()
    return [
        {
            "dia": iso_o_vacio(f["dia"]),
            "tokens": int(f["tin"]) + int(f["tout"]),
            "tokens_in": int(f["tin"]),
            "tokens_out": int(f["tout"]),
            "coste_usd": float(f["coste"]),
            # Economia de contexto: chars de prompt sumados del dia (la media por generacion
            # se deriva con `generaciones`); delata la deriva de prompts cada vez mas gordos.
            "prompt_chars": int(f["pchars"]),
            # Prompt caching: tokens de cache leidos/creados del dia (mide si el caching ocurre y
            # el ahorro: cache_read alto = contexto reutilizado sin re-cobrar).
            "cache_read": int(f["cread"]),
            "cache_creation": int(f["ccreac"]),
            "generaciones": int(f["n"]),
        }
        for f in filas
    ]
