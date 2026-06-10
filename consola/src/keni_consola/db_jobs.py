"""Persistencia — dominio jobs. Implementación de db.py (ver barrel `db.py`)."""
from __future__ import annotations

from ._db_comun import (
    UTC,
    Any,
    _conectar,
    config,
    datetime,
    timedelta,
    uuid,
)
from .tiempo import ahora_iso, iso_utc

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

# Margen sobre el wall-timeout tras el cual un job `reclamado` se considera HUERFANO (su
# worker murio a mitad: reinicio/deploy/OOM) y OTRO worker lo RE-RECLAMA para que el trabajo
# complete solo, sin que el usuario relance. Debe SUPERAR el wall-timeout + el margen terminal
# del worker (~60 s), asi un worker VIVO que aun esta cerrando su job nunca pierde la fila
# (a esa edad la fila ya seria `terminado`, no `reclamado`). El reaper de generaciones (TTL
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
    fallo). Antes el `ON CONFLICT DO NOTHING` devolvia el job viejo (terminado) y el nuevo no
    corria jamas. El `ON CONFLICT ... DO UPDATE` REVIVE la fila a `pendiente` (spec/prioridad
    nuevos, flags de despacho limpios) SOLO si estaba `terminado` (el `WHERE jobs.estado = ?`);
    una fila VIVA no se toca (idempotencia intacta: el RETURNING viene vacio y se relee su id
    real con un SELECT, como antes).
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
            "prioridad = EXCLUDED.prioridad, cancelado = 0, worker = '', claimed_at = '' "
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
    """Nº de jobs EN VUELO en la cola COMPARTIDA: `pendiente` (esperando) + `reclamado` (corriendo).

    Es la cuenta AUTORITATIVA del backpressure (#130 Fase 2): vive en Postgres, asi que la ven
    TODOS los procesos que encolan (back, daemons) y se AUTOLIBERA cuando un worker marca el job
    `terminado`. Reemplaza al contador en memoria por-proceso de `runner` (que en hosted —back y
    worker son contenedores distintos— solo subia y nunca bajaba, saturando el back tras
    `max_jobs+max_cola` generaciones). El gate de admision (`cola.encolar`) compara este valor con
    el tope antes de insertar.
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
    """Jobs EN VUELO (`pendiente` + `reclamado`) con sus metadatos de despacho, mas antiguos primero.

    Para el monitor de cola: cada fila lleva `id`, `gen_id`, `estado`, `worker` (quien lo clavo),
    `creado` (cuando se encolo), `claimed_at` (cuando empezo a correr) y `prioridad` (mayor =
    adelanta en la cola; el Monitor distingue los manuales del lote de fondo). El front deriva
    la EDAD y enriquece con el registro de generacion (etiqueta/tipo/marca). Sin `spec` (pesado).
    """
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT id, gen_id, estado, worker, creado, claimed_at, prioridad FROM jobs "
            "WHERE estado <> ? ORDER BY creado ASC, id ASC LIMIT ?",
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
            "creado": f["creado"],
            "claimed_at": f["claimed_at"],
            "prioridad": int(f["prioridad"] or 0),
        }
        for f in filas
    ]


def encolados_por_dia(dias: int = 14) -> list[dict[str, Any]]:
    """Jobs ENCOLADOS por dia (de `jobs.creado`) en la ventana `dias`, dia ascendente.

    Throughput de ENTRADA de la cola: cuanto se pidio cada dia (incluye los ya `terminado`,
    que se conservan). El dia se deriva con `substr(creado,1,10)` (ISO `YYYY-MM-DD`), portable
    SQLite/Postgres. El corte se compara lexicograficamente (ISO ordena por texto)."""
    corte = iso_utc(datetime.now(UTC) - timedelta(days=max(0, int(dias))))
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT substr(creado, 1, 10) AS dia, count(*) AS n FROM jobs "
            "WHERE creado >= ? GROUP BY substr(creado, 1, 10) ORDER BY dia ASC",
            (corte,),
        ).fetchall()
    finally:
        con.close()
    return [{"dia": f["dia"], "n": int(f["n"])} for f in filas]


def reclamar_job(worker: str = "", *, prioridad_minima: int | None = None) -> dict[str, Any] | None:
    """Clava UN job de forma CONCURRENTE-SEGURA y lo devuelve (None si no hay).

    `SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1` dentro de la transaccion + UPDATE a
    `reclamado`: otro worker que corra a la vez SALTA esa fila (no la doble-ejecuta).
    Devuelve `{id, gen_id, spec}` del job clavado.

    `prioridad_minima` (corte del presupuesto, ver `presupuesto_ia`): si viene, solo se
    consideran filas con `prioridad >= prioridad_minima` (el fondo cortado queda `pendiente`
    en la cola, listo para cuando el presupuesto vuelva; lo manual sigue saliendo).

    RE-RECLAMO DE HUERFANOS: ademas de los `pendiente`, clava los `reclamado` cuyo
    `claimed_at` es mas viejo que `wall-timeout + _RECLAIM_STALE_MARGEN_S` — su worker murio
    a mitad (reinicio/deploy/OOM) y nadie lo sacaria adelante (antes quedaba `reclamado` para
    siempre y el registro `ejecutando` -> la UI mostraba "Generando..." sin fin). El umbral
    supera el tiempo maximo que un worker VIVO retiene la fila, asi nunca se roba un job en
    curso. El UPDATE re-sella `worker`/`claimed_at`, asi un segundo abandono se vuelve a cubrir.

    GUARDIA ANTI-DUPLICADO (re-reclamo de huerfanos): un worker puede haber MUERTO DESPUES de
    fijar el estado terminal del registro (y de correr su post-procesado: `crear_borrador` es un
    INSERT fresco, NO idempotente) pero ANTES de llamar a `terminar_job` — el job queda
    `reclamado`. Re-ejecutarlo DUPLICARIA el borrador. Por eso, al re-reclamar un HUERFANO,
    consultamos el registro de generaciones: si su `gen_id` YA esta en un estado TERMINAL
    (`completado`/`error`), NO se relanza: se marca el job `terminado` y se pasa al siguiente
    (su trabajo ya se hizo). Solo afecta al re-reclamo de huerfanos; un `pendiente` nunca corrio.
    """
    ahora = ahora_iso()
    limite_huerfano = iso_utc(
        datetime.now(UTC) - timedelta(seconds=config.claude_timeout() + _RECLAIM_STALE_MARGEN_S)
    )
    filtro_prioridad = "" if prioridad_minima is None else "AND prioridad >= ? "
    params_prio: tuple[int, ...] = () if prioridad_minima is None else (int(prioridad_minima),)
    con = _conectar()
    try:
        # Acotamos los saltos: descartamos huerfanos ya-terminados (terminando su job) y
        # seguimos buscando, sin reintentar para siempre.
        for _ in range(_MAX_SALTOS_RECLAMO):
            fila = con.execute(
                "SELECT id, gen_id, spec, estado FROM jobs "
                "WHERE (estado = ? OR (estado = ? AND claimed_at IS NOT NULL AND claimed_at < ?)) "
                + filtro_prioridad +
                # Prioridad primero (manual > pipeline/autogen), luego FIFO por antiguedad.
                "ORDER BY prioridad DESC, creado ASC, id ASC LIMIT 1 FOR UPDATE SKIP LOCKED",
                (JOB_PENDIENTE, JOB_RECLAMADO, limite_huerfano, *params_prio),
            ).fetchone()
            if fila is None:
                con.commit()
                return None
            # Solo un HUERFANO (estado `reclamado`) pudo haber corrido ya su post-procesado.
            if fila["estado"] == JOB_RECLAMADO and _gen_ya_terminal(fila["gen_id"]):
                # El registro ya alcanzo estado terminal: el trabajo se hizo. Cerramos el job
                # SIN relanzarlo (evita el borrador duplicado) y buscamos el siguiente.
                con.execute(
                    "UPDATE jobs SET estado = ? WHERE id = ?", (JOB_TERMINADO, fila["id"])
                )
                con.commit()
                continue
            con.execute(
                "UPDATE jobs SET estado = ?, worker = ?, claimed_at = ? WHERE id = ?",
                (JOB_RECLAMADO, worker, ahora, fila["id"]),
            )
            con.commit()
            return {"id": fila["id"], "gen_id": fila["gen_id"], "spec": fila["spec"]}
        con.commit()
        return None
    finally:
        con.close()


# Tope de huerfanos-ya-terminados que `reclamar_job` descarta de una tirada antes de rendirse
# (cota dura para que el barrido nunca gire indefinidamente). Si hubiera mas, el siguiente
# `reclamar` los sigue limpiando.
_MAX_SALTOS_RECLAMO = 50


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

    "Limpio" aqui es '' (no NULL): ambas columnas son NOT NULL DEFAULT '' en el esquema,
    el mismo convenio que usa el encolado."""
    con = _conectar()
    try:
        cur = con.execute(
            "UPDATE jobs SET estado = ?, worker = '', claimed_at = '', cancelado = 0 "
            "WHERE gen_id = ?",
            (JOB_PENDIENTE, gen_id),
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
) -> None:
    """UPSERT del gasto de UNA generacion cerrada (idempotente por `gen_id`).

    `dia` es el dia UTC (YYYY-MM-DD) en que se CERRO la generacion (cuando se gasto). Un
    re-cierre sobreescribe tokens/coste con los ultimos valores (nunca suma dos veces).
    """
    if not gen_id:
        return
    ahora = ahora_iso()
    con = _conectar()
    try:
        con.execute(
            "INSERT INTO gasto_ia (gen_id, dia, tipo, marca, tokens_in, tokens_out, "
            "coste_usd, actualizado) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (gen_id) DO UPDATE SET "
            "dia = EXCLUDED.dia, tipo = EXCLUDED.tipo, marca = EXCLUDED.marca, "
            "tokens_in = EXCLUDED.tokens_in, tokens_out = EXCLUDED.tokens_out, "
            "coste_usd = EXCLUDED.coste_usd, actualizado = EXCLUDED.actualizado",
            (gen_id, dia, tipo, marca, int(tokens_in), int(tokens_out), float(coste_usd), ahora),
        )
        con.commit()
    finally:
        con.close()


def gasto_ia_del_dia(dia: str) -> dict[str, Any]:
    """Gasto AGREGADO de un dia UTC: `{tokens, tokens_in, tokens_out, coste_usd, generaciones}`.

    Es la lectura del corte automatico (`presupuesto_ia.nivel()`): tokens = in + out del dia.
    """
    con = _conectar()
    try:
        fila = con.execute(
            "SELECT COALESCE(SUM(tokens_in), 0) AS tin, COALESCE(SUM(tokens_out), 0) AS tout, "
            "COALESCE(SUM(coste_usd), 0) AS coste, COUNT(*) AS n "
            "FROM gasto_ia WHERE dia = ?",
            (dia,),
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


def gasto_ia_por_dia(dias: int = 14) -> list[dict[str, Any]]:
    """Serie de gasto por dia (ventana `dias`, dia ascendente): tokens/coste/generaciones.

    Para el monitor y el agente de observabilidad (lado de CONSUMO de la cola, en tokens).
    El corte se compara lexicograficamente (ISO ordena por texto), como `encolados_por_dia`.
    """
    corte = iso_utc(datetime.now(UTC) - timedelta(days=max(0, int(dias))))[:10]
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT dia, COALESCE(SUM(tokens_in), 0) AS tin, "
            "COALESCE(SUM(tokens_out), 0) AS tout, COALESCE(SUM(coste_usd), 0) AS coste, "
            "COUNT(*) AS n FROM gasto_ia WHERE dia >= ? GROUP BY dia ORDER BY dia ASC",
            (corte,),
        ).fetchall()
    finally:
        con.close()
    return [
        {
            "dia": f["dia"],
            "tokens": int(f["tin"]) + int(f["tout"]),
            "tokens_in": int(f["tin"]),
            "tokens_out": int(f["tout"]),
            "coste_usd": float(f["coste"]),
            "generaciones": int(f["n"]),
        }
        for f in filas
    ]
