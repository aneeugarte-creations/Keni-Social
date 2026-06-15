"""API ACTIVIDAD: agregados de la actividad de IA + monitor de la cola de generacion.

Reune los DOS registros donde vive la "verdad" de lo que la IA produce —las
GENERACIONES (`generaciones.py`: copy, rss, autogen, hashtags, imagen, verificacion,
qa-editorial, prompt) y los RUNS de agente (`agentes.py`)— y sirve sus AGREGADOS. La normalizacion/mezcla/agregacion es DOMINIO PURO
(`consola.actividad`); aqui solo se LEEN ambos orígenes (via `generaciones.listar(...)`
y el dominio `agentes`, NUNCA por HTTP) y se sirven.

Endpoints:
  - `GET /api/actividad/agregados`
      -> `{"total": {...}, "por_tipo": [...], "por_dia": [...]}`
  - `GET /api/actividad/cola`
      -> MONITOR EN VIVO de la cola de generacion: capacidad (`max_jobs`: la cola NO tiene tope,
         R-NO-LIMIT), conteo (pendientes/reclamados/terminados/activos), `procesando` (claude -p en vuelo), slots
         libres, workers activos, listas `en_curso`/`esperando` (con etiqueta/tipo/marca/edad),
         desglose `por_proceso` (investigacion/produccion sobre la MISMA cola, ADR 0011), el
         `embudo_qa` (lo unico que Investigacion acota aparte) y el estado de los daemons de
         fondo. Para "que ocurre AHORA en la cola".
  - `GET /api/actividad/cola/series?dias=`
      -> series por dia: `encolados` (de la tabla de jobs) y `resultados` (completados/errores/
         cola_llena + desglose por proceso con tokens/coste, de las generaciones REALES; los
         MARCADORES de etapa quedan excluidos). Throughput de entrada vs salida de la cola.

Solo LECTURA. Errores en espanol; sin tracebacks crudos.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import (
    actividad,
    agentes,
    ajustes_catalogo,
    config,
    generaciones,
    marcas,
    permisos,
    presupuesto_ia,
    repos,
)
from .._http_json import _entero_query
from ..tiempo import hoy_utc

_MSG_SOLO_ADMIN = "Solo un administrador puede operar la cola de generación."


def _es_marcador_pipeline(gen: dict) -> bool:
    """True si la generación es un MARCADOR de etapa del pipeline (CI/CD/QA) — fuera de Actividad.

    Los marcadores no son trabajo con coste (el trabajo real es la generación de copy
    `tipo='pipeline'`, que SÍ se muestra). Excluye el tipo propio `pipeline_etapa` y, por
    retrocompat, los marcadores VIEJOS (`tipo='pipeline'` con `etiqueta` de etapa, anteriores
    a separar el tipo).
    """
    tipo = gen.get("tipo")
    if tipo == "pipeline_etapa":
        return True
    if tipo == "pipeline":
        return (gen.get("etiqueta", "") or "").startswith(("ADMITIR · ", "REDACTAR · ", "VERIFICAR · "))
    return False


def _origenes(marca: str | None = None) -> tuple[list, list]:
    """Lee TODAS las generaciones y TODOS los runs (sin recortar) para combinar/agregar.

    Las generaciones se piden con `limite=None` (conjunto completo; la paginacion la
    aplica el dominio sobre la mezcla). Los runs vienen del dominio `agentes`
    (`listar_runs_globales`) con sus metricas y su agente denormalizado.

    `marca` (opcional): si viene NO vacia, acota AMBOS origenes a esa marca —las
    generaciones filtran por su campo `marca` (en la fuente, `generaciones.listar`); los
    runs por su `agente` (que, para los agentes-marca, ES el id de marca). El default
    `None`/"" NO filtra (caso admin "todas las marcas").
    """
    gens = [
        g
        for g in generaciones.listar(limite=None, marca=marca or None)
        if not _es_marcador_pipeline(g)
    ]
    runs = agentes.listar_runs_globales()
    if marca:
        runs = [r for r in runs if (r.get("agente") or r.get("marca") or "") == marca]
    return gens, runs


async def agregados(request: Request) -> Response:
    """Agregados de la actividad: total + por_tipo (incluye 'run') + por_dia.

    Query: `marca` (""=todas, o un id de marca valido — acota los agregados a esa marca).
    """
    qp = request.query_params
    marca = (qp.get("marca") or "").strip()
    if marca and not marcas.es_marca(marca):
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    gens, runs = _origenes(marca or None)
    # SELLA el proceso (ADR 0011) de cada generacion (prefiere el sellado, deduce de
    # tipo/etiqueta) antes de agregar: el dominio `actividad` es PURO y solo LEE el campo
    # para abrir el desglose `por_proceso`. Los runs no llevan proceso (no son de la maquina).
    for g in gens:
        g["proceso"] = generaciones.proceso_de(g)
    return JSONResponse(actividad.agregados(gens, runs))


# --------------------------------------------------------------------------- #
# MONITOR DE COLA: que ocurre AHORA en la cola de generacion (jobs + workers)  #
# --------------------------------------------------------------------------- #
#
# La cola la sirve `repos` (tabla de jobs, infra compartida); el registro de cada generacion
# (etiqueta/tipo/marca/estado) vive en `generaciones` (app A, ya importado aqui). Shaping
# LIGERO de lectura: la agregacion pesada (combinar/agregados) sigue en el dominio `actividad`.

# Daemons de fondo a reportar: (clave, etiqueta, accesor de toggle en `config`, descripcion,
# clave_ajuste). `accesor`=None => SIEMPRE activo (sin toggle). `clave_ajuste` es la env var
# del catálogo de ajustes (`KENI_*`) que lo enciende/apaga; el Monitor la usa para pintar un
# TOGGLE REAL (PUT /api/ajustes) en vez de un badge de solo lectura. "" => sin toggle (reaper).
# El estado se lee best-effort: si el accesor no existe en `config`, el daemon sale con
# `activo=None` (desconocido) en vez de romper el panel.
# El interruptor general (`maquina`), la Recolección (`ingesta`) y la Redacción (`pipeline`) NO están aquí:
# son ETAPAS de la máquina y se controlan en la sección «Máquina de contenido» del Monitor (toggles
# del catálogo: maquina_global + maestros_etapa + topes). Aquí quedan los daemons de fondo restantes.
_DAEMONS: list[tuple[str, str, str | None, str, str]] = [
    ("trends", "Google Trends", "trends_activo",
     "Ingiere tendencias (con sus noticias) al pool.", config.ENV_TRENDS),
    ("algoritmos", "Feeds de algoritmo", "algoritmos_auto_activo",
     "Refresca los feeds de algoritmo por marca.", config.ENV_ALGORITMOS_AUTO),
    ("media_gc", "GC de media", "media_gc_activo",
     "Recoge media huérfana (no borra salvo toggle).", config.ENV_MEDIA_GC),
    ("noticias_gc", "GC de noticias", "noticias_gc_activo",
     "Poda el pool de noticias por relevancia/inactividad.", config.ENV_NOTICIAS_GC),
    ("alertas", "Alertas de rendimiento", "alertas_rendimiento_activas",
     "Lee métricas y emite eventos de alerta.", config.ENV_ALERTAS_ACTIVAS),
    ("patrones", "Patrones de marca", "patrones_auto_activo",
     "Re-deriva los patrones editoriales por marca desde sus métricas.", config.ENV_PATRONES_AUTO),
    ("publicar_real", "Publicación real", "publicar_real",
     "Si está OFF, el programador corre en DRY-RUN (no publica).", config.ENV_PUBLICAR_REAL),
    ("reaper", "Reaper de generaciones", None,
     "Siempre activo: cierra como error las generaciones zombi.", ""),
]


def _edad_s(iso: str | None, ahora: datetime) -> int | None:
    """Segundos transcurridos desde el instante ISO `iso` hasta `ahora` (None si no parsea)."""
    if not iso:
        return None
    try:
        return max(0, int((ahora - datetime.fromisoformat(iso)).total_seconds()))
    except (TypeError, ValueError):
        return None


def _item_job(job: dict, ahora: datetime) -> dict:
    """Normaliza un job en vuelo + su registro de generacion para el monitor (sin `spec`)."""
    reg = generaciones.obtener(job["gen_id"]) or {}
    corriendo = job["estado"] == repos.JOB_RECLAMADO
    return {
        "job_id": job["id"],
        "gen_id": job["gen_id"],
        "estado": job["estado"],
        "worker": job.get("worker") or "",
        "etiqueta": reg.get("etiqueta") or "",
        "tipo": reg.get("tipo") or "",
        "marca": reg.get("marca") or "",
        # Proceso (ADR 0011): investigacion (criba/QA) | produccion (copy/arte). La cola es
        # COMPARTIDA; esto solo clasifica cada job para desglosar el pool por proceso.
        "proceso": generaciones.proceso_de(reg),
        "gen_estado": reg.get("estado") or "",
        "fase": reg.get("fase") or "",
        # Prioridad de cola (mayor = adelanta): los lanzamientos manuales van por delante
        # del lote de fondo del pipeline; el Monitor lo señala en la lista de espera.
        "prioridad": int(job.get("prioridad") or 0),
        # Intentos quemados (anti crash-loop): >1 delata un job que ya mato a un worker.
        "intentos": int(job.get("intentos") or 0),
        "encolado_hace_s": _edad_s(job.get("creado"), ahora),
        "corriendo_hace_s": _edad_s(job.get("claimed_at"), ahora) if corriendo else None,
    }


def _daemons_estado() -> list[dict]:
    """Estado ON/OFF de cada daemon de fondo (lee los toggles de `config`, best-effort).

    Cada daemon reporta su `clave_ajuste` (env var del catálogo) y si es `editable`: el Monitor
    pinta un TOGGLE REAL (PUT /api/ajustes) cuando la clave está en el catálogo y NO es peligrosa;
    si no (reaper sin toggle, o `publicar_real` que es peligroso y vive en su flujo propio), pinta
    un badge de solo lectura. Así los toggles del Monitor son los MISMOS que los de Configuración.
    """
    items: list[dict] = []
    for clave, etiqueta, accesor, desc, clave_ajuste in _DAEMONS:
        if accesor is None:
            activo: bool | None = True
        else:
            fn = getattr(config, accesor, None)
            try:
                activo = bool(fn()) if callable(fn) else None
            except Exception:  # noqa: BLE001 -- un toggle que falle no debe tumbar el panel
                activo = None
        cat = ajustes_catalogo.por_clave(clave_ajuste) if clave_ajuste else None
        editable = cat is not None and not cat.peligroso
        items.append({
            "clave": clave,
            "etiqueta": etiqueta,
            "activo": activo,
            "descripcion": desc,
            "clave_ajuste": clave_ajuste,
            "editable": editable,
        })
    return items


def snapshot_cola() -> dict:
    """Snapshot PLANO de capacidad y conteo de la cola de jobs (sin listas ni workers).

    Una sola sonda compartida por el monitor (`GET /api/actividad/cola`) y el doctor
    (`GET /api/estado`, chequeo `maquina:cola`): no duplicar el calculo. Forma:
    `{max_jobs, pendientes, reclamados, terminados, activos}`. La cola NO tiene tope
    (R-NO-LIMIT): el unico limite es la concurrencia (`max_jobs`); el exceso ESPERA, nada
    se rechaza por tamano de cola. Puede propagar un fallo de BD: cada consumidor degrada.
    """
    estados = repos.contar_jobs_por_estado()
    pendientes = estados.get(repos.JOB_PENDIENTE, 0)
    reclamados = estados.get(repos.JOB_RECLAMADO, 0)
    terminados = estados.get(repos.JOB_TERMINADO, 0)
    return {
        "max_jobs": config.max_jobs(),
        "pendientes": pendientes,
        "reclamados": reclamados,
        "terminados": terminados,
        "activos": pendientes + reclamados,
    }


async def cola(request: Request) -> Response:
    """GET /api/actividad/cola?marca=: snapshot EN VIVO de la cola de generacion + workers + daemons.

    `marca` (""=todas, o un id de marca valido): acota las LISTAS `en_curso`/`esperando` a los
    jobs de esa marca (la del registro de generacion), igual que el resto del hub Actividad IA
    respeta el switch global de marca. Los KPIs de CAPACIDAD/conteo siguen siendo GLOBALES a
    proposito: la cola es infraestructura compartida (un slot ocupado por otra marca tambien
    te bloquea) y mentiria mostrar capacidad "por marca".
    """
    qp = request.query_params
    marca = (qp.get("marca") or "").strip()
    if marca and not marcas.es_marca(marca):
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)

    snap = snapshot_cola()
    pendientes = snap["pendientes"]
    reclamados = snap["reclamados"]
    terminados = snap["terminados"]
    max_jobs = snap["max_jobs"]
    activos = snap["activos"]

    ahora = datetime.now()
    filas = repos.jobs_activos(limite=200)
    en_vuelo = [_item_job(j, ahora) for j in filas]
    # Desglose del pool COMPARTIDO por proceso (ADR 0011): se calcula sobre TODOS los jobs en
    # vuelo (global, como los KPIs de capacidad), ANTES de acotar las listas por marca. La cola y
    # el pool son UNICOS; esto solo dice cuanto del trabajo en vuelo es Investigacion (criba/QA)
    # y cuanto Produccion (copy/arte), para poder vigilar los dos loops sobre la misma cola.
    por_proceso = {
        proc: {
            "procesando": sum(
                1 for j in en_vuelo
                if j["proceso"] == proc and j["estado"] == repos.JOB_RECLAMADO
            ),
            "pendientes": sum(
                1 for j in en_vuelo
                if j["proceso"] == proc and j["estado"] == repos.JOB_PENDIENTE
            ),
        }
        for proc in (generaciones.PROCESO_INVESTIGACION, generaciones.PROCESO_PRODUCCION)
    }
    # EMBUDO de QA: el unico limite que Investigacion acota aparte de la cola compartida (cuanta
    # criba cabe en vuelo por marca). Lazy import del helper del pipeline (evita acoplar la API al
    # orquestador) y best-effort: un fallo deja el embudo vacio, nunca tumba el snapshot.
    try:
        from ..pipeline_contenido import embudo_qa as _embudo_qa

        embudo = _embudo_qa()
    except Exception:  # noqa: BLE001 -- el embudo es observabilidad; su fallo no rompe el Monitor
        embudo = {"en_vuelo": 0, "tope_por_marca": 0, "marcas": []}
    # Listas para mostrar: respetan el switch GLOBAL de marca (la capacidad/los conteos no).
    if marca:
        en_vuelo = [j for j in en_vuelo if j["marca"] == marca]
    en_curso = [j for j in en_vuelo if j["estado"] == repos.JOB_RECLAMADO]
    esperando = [j for j in en_vuelo if j["estado"] == repos.JOB_PENDIENTE]
    workers = sorted({j.get("worker") for j in filas if j["estado"] == repos.JOB_RECLAMADO and j.get("worker")})

    return JSONResponse(
        {
            # Eco del filtro aplicado a las listas ("" = todas): la UI lo usa para etiquetar.
            "marca": marca,
            # La cola NO tiene tope (R-NO-LIMIT): la capacidad es solo la CONCURRENCIA.
            "capacidad": {"max_jobs": max_jobs},
            "conteo": {
                "pendientes": pendientes,
                "reclamados": reclamados,
                "terminados": terminados,
                "activos": activos,
            },
            "procesando": reclamados,  # claude -p en vuelo (acotado por max_jobs)
            "slots_libres": max(0, max_jobs - reclamados),
            "workers_activos": workers,
            # Desglose del pool compartido por proceso + embudo de QA (Investigacion). La cola es
            # UNA; estos dos campos dejan ver los dos loops (ADR 0011) sobre esa misma cola.
            "por_proceso": por_proceso,
            "embudo_qa": embudo,
            "en_curso": en_curso,
            "esperando": esperando,
            "daemons": _daemons_estado(),
            # Economia de tokens (presupuesto_ia): presupuesto diario, gasto del dia UTC,
            # nivel de corte vigente (normal/solo_manual/agotado/pausado) y kill switch.
            # CONTRATO de visibilidad para humanos (Monitor) y agentes (observabilidad).
            "presupuesto": presupuesto_ia.estado(),
        }
    )


def _metricas_tokens(g: dict) -> tuple[int, float]:
    """(tokens, coste_usd) de una generacion desde sus `metricas` (0,0.0 si no las trae)."""
    m = g.get("metricas")
    if not isinstance(m, dict):
        return 0, 0.0
    try:
        return int(m.get("tokens_in") or 0) + int(m.get("tokens_out") or 0), float(
            m.get("total_cost_usd") or 0.0
        )
    except (TypeError, ValueError):
        return 0, 0.0


def _bucket_dia() -> dict:
    """Bucket vacio de un dia: totales + desglose por proceso (ADR 0011)."""
    return {
        "completados": 0,
        "errores": 0,
        "cola_llena": 0,
        "por_proceso": {
            generaciones.PROCESO_INVESTIGACION: {
                "completados": 0, "errores": 0, "tokens": 0, "coste_usd": 0.0,
            },
            generaciones.PROCESO_PRODUCCION: {
                "completados": 0, "errores": 0, "tokens": 0, "coste_usd": 0.0,
            },
        },
    }


def _resultados_por_dia(dias: int) -> list[dict]:
    """Generaciones REALES por dia: completados/errores (+cola_llena) y desglose por proceso.

    Escanea el almacen de generaciones (YAML) una vez y agrupa por `fecha_inicio[:10]`. Es el
    lado de SALIDA de la cola; el endpoint que lo usa se sondea con poca frecuencia (no es el
    snapshot en vivo), asi que el escaneo completo es aceptable.

    EXCLUYE los MARCADORES de etapa (`pipeline_etapa`, CI/QA/CD a coste 0): son trazabilidad, no
    trabajo con tokens, y antes inflaban "completados" a miles (la serie no cuadraba ni con los
    encolados ni con el gasto). Igual que el feed de Actividad, aqui solo cuentan generaciones
    REALES. Cada generacion se clasifica en su proceso (investigacion/produccion) con su gasto.
    """
    corte = (hoy_utc() - timedelta(days=max(0, dias - 1))).isoformat()
    buckets: dict[str, dict] = {}
    for g in generaciones.listar(limite=None):
        if _es_marcador_pipeline(g):
            continue  # marcador de etapa (coste 0): no es trabajo real, no infla la serie
        dia = (g.get("fecha_inicio") or "")[:10]
        if not dia or dia < corte:
            continue
        b = buckets.setdefault(dia, _bucket_dia())
        proc = b["por_proceso"][generaciones.proceso_de(g)]
        est = g.get("estado")
        tokens, coste = _metricas_tokens(g)
        proc["tokens"] += tokens
        proc["coste_usd"] += coste
        if est == generaciones.ESTADO_COMPLETADO:
            b["completados"] += 1
            proc["completados"] += 1
        elif est == generaciones.ESTADO_ERROR:
            b["errores"] += 1
            proc["errores"] += 1
            if g.get("motivo") == generaciones.MOTIVO_COLA_LLENA:
                b["cola_llena"] += 1
    return [{"dia": d, **v} for d, v in sorted(buckets.items())]


async def cola_series(request: Request) -> Response:
    """GET /api/actividad/cola/series?dias=: encolados (jobs) vs resultados (generaciones) por dia."""
    dias = _entero_query(request.query_params.get("dias"), minimo=1) or 14
    return JSONResponse(
        {
            "dias": dias,
            "encolados": repos.encolados_por_dia(dias),
            "resultados": _resultados_por_dia(dias),
            # Lado de CONSUMO (ledger gasto_ia): tokens/coste/generaciones cerradas por dia,
            # para correlacionar el volumen de la cola con el gasto real de la suscripcion.
            "gasto": repos.gasto_ia_por_dia(dias),
        }
    )


# --------------------------------------------------------------------------- #
# ACCIONES ADMIN sobre la cola (mutan estado -> exigen SESION admin real)       #
# --------------------------------------------------------------------------- #


async def cola_purgar(request: Request) -> Response:
    """POST /api/actividad/cola/purgar: libera la cola (cancela+termina TODO lo activo). Admin.

    Para cada job en vuelo: marca el flag `cancelado` (un worker que lo este corriendo mata el
    arbol de `claude`), saca el job de la cola (`terminar`, libera el slot de inmediato) y cierra
    el registro de generacion si seguia `ejecutando`. Es el boton de "destrabar / resetear
    capacidad". Devuelve cuantos jobs purgo.
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    filas = repos.jobs_activos(limite=10_000)
    purgados = 0
    for j in filas:
        try:
            repos.cancelar_job(j["gen_id"])  # cross-proceso: un worker vivo mata su claude
            repos.terminar_job(j["id"])  # fuera de la cola: libera el cupo YA
            g = generaciones.obtener(j["gen_id"])
            if g and g.get("estado") == generaciones.ESTADO_EJECUTANDO:
                generaciones.actualizar(
                    j["gen_id"],
                    {
                        "estado": generaciones.ESTADO_ERROR,
                        "motivo": generaciones.MOTIVO_CANCELADO,
                        "error": "Cancelada al purgar la cola (administrador).",
                        "fecha_fin": generaciones.ahora_iso(),
                    },
                )
            purgados += 1
        except Exception:  # noqa: BLE001 -- un fallo por job no debe abortar la purga del resto
            continue
    return JSONResponse({"purgados": purgados})


async def cola_priorizar(request: Request) -> Response:
    """POST /api/actividad/cola/priorizar {gen_id}: adelanta un job ESPERANDO. Admin.

    Sube su prioridad de despacho a la de un lanzamiento manual (`PRIORIDAD_MANUAL`): el
    worker lo clavará antes que todo el lote de fondo pendiente. Solo aplica a jobs aún
    `pendiente` (los reclamados ya corren); 404 si no hay job pendiente para ese `gen_id`.
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    try:
        cuerpo = await request.json()
    except Exception:  # noqa: BLE001 -- body no-JSON
        cuerpo = {}
    gen_id = (cuerpo.get("gen_id") or "").strip() if isinstance(cuerpo, dict) else ""
    if not gen_id:
        return JSONResponse({"error": "Falta el identificador de la generación."}, status_code=400)
    from ..dominio import jobspec

    if not repos.priorizar_job(gen_id, jobspec.PRIORIDAD_URGENTE):
        return JSONResponse(
            {"error": "No hay un job esperando para esa generación."}, status_code=404
        )
    return JSONResponse({"priorizado": True, "gen_id": gen_id})


async def cola_reencolar(request: Request) -> Response:
    """POST /api/actividad/cola/reencolar {gen_id}: reintenta un job atascado/fallido. Admin.

    Devuelve la fila del job a `pendiente` (mismo `spec`) y reabre el registro a `ejecutando`,
    para que un worker lo vuelva a clavar y correr. 404 si no hay job para ese `gen_id`.
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    try:
        cuerpo = await request.json()
    except Exception:  # noqa: BLE001 -- body no-JSON
        cuerpo = {}
    gen_id = (cuerpo.get("gen_id") or "").strip() if isinstance(cuerpo, dict) else ""
    if not gen_id:
        return JSONResponse({"error": "Falta el identificador de la generación."}, status_code=400)
    if not repos.reencolar_job(gen_id):
        return JSONResponse({"error": "No hay un job para esa generación."}, status_code=404)
    # Reabrir el registro: si quedara terminal, el guardia anti-duplicado de `reclamar_job` lo
    # cerraria sin correr. Lo dejamos `ejecutando` (y limpiamos motivo/error de la vez anterior).
    generaciones.actualizar(
        gen_id,
        {
            "estado": generaciones.ESTADO_EJECUTANDO,
            "motivo": "",
            "error": "",
            "fase": "",
            "fecha_fin": "",
        },
    )
    return JSONResponse({"reencolado": True, "gen_id": gen_id})


RUTAS = [
    Route("/api/actividad/agregados", agregados, methods=["GET"]),
    # Mas especificas ANTES que la generica para que Starlette case bien.
    Route("/api/actividad/cola/series", cola_series, methods=["GET"]),
    Route("/api/actividad/cola/purgar", cola_purgar, methods=["POST"]),
    Route("/api/actividad/cola/priorizar", cola_priorizar, methods=["POST"]),
    Route("/api/actividad/cola/reencolar", cola_reencolar, methods=["POST"]),
    Route("/api/actividad/cola", cola, methods=["GET"]),
]
