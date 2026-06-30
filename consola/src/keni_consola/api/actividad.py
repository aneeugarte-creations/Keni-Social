"""API ACTIVIDAD: agregados de la actividad de IA + monitor de la cola de generacion.

Reune los DOS registros donde vive la "verdad" de lo que la IA produce —las
GENERACIONES (`generaciones.py`: copy, rss, autogen, hashtags, imagen, verificacion,
revision, prompt) y los RUNS de agente (`agentes.py`)— y sirve sus AGREGADOS. La normalizacion/mezcla/agregacion es DOMINIO PURO
(`consola.actividad`); aqui solo se LEEN ambos orígenes (via `generaciones.listar(...)`
y el dominio `agentes`, NUNCA por HTTP) y se sirven.

Endpoints:
  - `GET /api/actividad/agregados`
      -> `{"total": {...}, "por_tipo": [...], "por_dia": [...]}`
  - `GET /api/actividad/economia?dias=`
      -> desglose economico GLOBAL (sin marca) por proceso DESDE el ledger `gasto_ia` (la misma
         fuente que el presupuesto), para que la pagina Economia cuadre:
         `{"dias": int, "por_proceso": {"investigacion"|"produccion": {"total": {...},
         "por_dia": [...], "por_tipo": [...]}}}`.
  - `GET /api/actividad/cola`
      -> MONITOR EN VIVO de la cola de generacion: capacidad (`max_jobs`: la cola NO tiene tope,
         R-NO-LIMIT), conteo (pendientes/reclamados/terminados/activos), `procesando` (claude -p en proceso), slots
         libres, workers activos, listas `en_curso`/`esperando` (con etiqueta/tipo/marca/edad),
         desglose `por_proceso` (investigacion/produccion sobre la MISMA cola, ADR 0011), el
         `admision_verificacion` (lo unico que Investigacion acota aparte) y el estado de los daemons de
         fondo. Para "que ocurre AHORA en la cola".
  - `GET /api/actividad/cola/series?dias=`
      -> series por dia: `encolados` (de la tabla de jobs) y `resultados` (completados/errores/
         cola_llena + desglose por proceso con tokens/coste, de las generaciones REALES; los
         MARCADORES de etapa quedan excluidos). Throughput de entrada vs salida de la cola.
  - `GET /api/actividad/cola/desglose`
      -> la cola en vuelo agrupada por marca x proceso x estado + bloque `huerfanos` (jobs sin
         registro de generacion). Desglose AUTORITATIVO de en que se reparte el conteo global.
  - `GET /api/actividad/cola/preview?marca=`
      -> cuantas piezas ENTRARIAN a cada etapa autogenerable (hoy `redactar`) SI se activara, sin
         encolar nada: `{"marcas": [{"marca", "redactar"}]}`. Para anticipar la avalancha.
  - `POST /api/actividad/cola/limpiar-huerfanos` (admin)
      -> saca de la cola los jobs PENDIENTES huerfanos (gen_id sin registro). `{huerfanos_limpiados}`.
  - `POST /api/actividad/cola/eliminar` (admin)
      -> saca UN job concreto de la cola por `{gen_id}` (cancela su arbol si corria). `{eliminado, gen_id}`.

Solo LECTURA. Errores en espanol; sin tracebacks crudos.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import (
    actividad,
    agentes,
    ajustes_catalogo,
    config,
    gate_diario,
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
    """True si la generación es un MARCADOR de etapa del pipeline (CI/CD/verificación) — fuera de Actividad.

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


def _agregados(marca: str | None) -> dict:
    gens, runs = _origenes(marca)
    # SELLA el proceso (ADR 0011) de cada generacion (prefiere el sellado, deduce de
    # tipo/etiqueta) antes de agregar: el dominio `actividad` es PURO y solo LEE el campo
    # para abrir el desglose `por_proceso`. Los runs no llevan proceso (no son de la maquina).
    for g in gens:
        g["proceso"] = generaciones.proceso_de(g)
    return actividad.agregados(gens, runs)


async def agregados(request: Request) -> Response:
    """Agregados de la actividad: total + por_tipo (incluye 'run') + por_dia.

    Query: `marca` (""=todas, o un id de marca valido — acota los agregados a esa marca).
    """
    qp = request.query_params
    marca = (qp.get("marca") or "").strip()
    if marca and not marcas.es_marca(marca):
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    return JSONResponse(await run_in_threadpool(_agregados, marca or None))


_ECONOMIA_DIAS_MAX = 31


async def economia(request: Request) -> Response:
    """GET /api/actividad/economia?dias=&marca=: desglose economico por proceso del ledger.

    Fuente UNICA del desglose de la pagina Economia: el ledger `gasto_ia` (el mismo de la
    tarjeta de presupuesto), para que KPIs/series/tablas cuadren. `marca` ("" = AGREGADO de
    todas, o un id de marca valido = acota a esa marca). `dias` default 7, minimo 1, clampado a
    `_ECONOMIA_DIAS_MAX`.
    """
    dias = _entero_query(request.query_params.get("dias"), minimo=1) or 7
    dias = min(dias, _ECONOMIA_DIAS_MAX)
    marca = (request.query_params.get("marca") or "").strip()
    if marca and not marcas.es_marca(marca):
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    return JSONResponse(await run_in_threadpool(_economia, dias, marca))


def _economia(dias: int, marca: str) -> dict:
    return {"dias": dias, "por_proceso": repos.gasto_ia_economia_por_proceso(dias, marca)}


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
# TOGGLE REAL (PUT /api/ajustes) en vez de un badge de solo lectura. "" => sin toggle (limpiador).
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
     "Recoge media suelta (no borra salvo toggle).", config.ENV_MEDIA_GC),
    ("noticias_gc", "GC de noticias", "noticias_gc_activo",
     "Purga el pool de noticias por relevancia/inactividad.", config.ENV_NOTICIAS_GC),
    ("alertas", "Alertas de rendimiento", "alertas_rendimiento_activas",
     "Lee métricas y emite eventos de alerta.", config.ENV_ALERTAS_ACTIVAS),
    ("patrones", "Patrones de marca", "patrones_auto_activo",
     "Re-deriva los patrones editoriales por marca desde sus métricas.", config.ENV_PATRONES_AUTO),
    ("publicar_real", "Publicación real", "publicar_real",
     "Si está OFF, el botón de publicar solo previsualiza (no publica).", config.ENV_PUBLICAR_REAL),
    ("limpiador", "Limpiador de generaciones", None,
     "Siempre activo: cierra como error las generaciones atascada.", ""),
]


def _edad_s(iso: str | None, ahora: datetime) -> int | None:
    """Segundos transcurridos desde el instante ISO `iso` hasta `ahora` (None si no parsea)."""
    if not iso:
        return None
    try:
        return max(0, int((ahora - datetime.fromisoformat(iso)).total_seconds()))
    except (TypeError, ValueError):
        return None


def _tokens_vivo(reg: dict) -> tuple[int, int, float] | None:
    """`(tokens_in, tokens_out, coste_usd)` reales del run desde `reg.metricas` (None si no reporta).

    Solo aplica a un job EN CURSO cuyo run ya emitio metricas: hasta entonces no hay tokens reales.
    """
    m = reg.get("metricas")
    if not isinstance(m, dict):
        return None
    try:
        return (
            int(m.get("tokens_in") or 0),
            int(m.get("tokens_out") or 0),
            float(m.get("total_cost_usd") or 0.0),
        )
    except (TypeError, ValueError):
        return None


def _item_job(
    job: dict, ahora: datetime, promedios: dict[str, int] | None = None
) -> dict:
    """Normaliza un job en proceso + su registro de generacion para el monitor (sin `spec`).

    `promedios` (etapa -> tokens medios historicos) se calcula UNA vez por peticion y se pasa para
    estimar el gasto de un job que aun ESPERA (no hay metricas en vivo hasta que corre)."""
    reg = generaciones.obtener(job["gen_id"])
    # HUERFANO: el job sobrevive en la cola pero su registro de generacion ya no existe (gen
    # borrada/purgada). Sin registro no hay marca/proceso real: nunca aparece en una lista por
    # marca y solo infla el conteo global. Se marca para poder aislarlo (desglose / limpieza).
    huerfano = reg is None
    reg = reg or {}
    corriendo = job["estado"] == repos.JOB_RECLAMADO
    tipo = reg.get("tipo") or ""
    # Proceso (ADR 0011): investigacion (verificación) | produccion (copy/arte). La cola es
    # COMPARTIDA; esto solo clasifica cada job para desglosar el pool por proceso.
    proceso = generaciones.proceso_de(reg)
    # Etapa LEGIBLE (fase del pipeline: Verificar/Redactar/Ilustrar/…): la explicita del registro
    # si la trae (fases inline), si no la derivada de proceso+tipo. `tipo`/`proceso` siguen como
    # origen crudo.
    etapa = reg.get("etapa") or repos.etapa_economia(proceso, tipo)
    # Tokens estimados (a-priori): media historica de la etapa, para el job que aun espera.
    tokens_estimados = (promedios or {}).get(etapa)
    # Tokens REALES en vivo: solo de un job EN CURSO cuyo run ya reporto metricas; si no, null.
    vivo = _tokens_vivo(reg) if corriendo else None
    return {
        "job_id": job["id"],
        "gen_id": job["gen_id"],
        "estado": job["estado"],
        "huerfano": huerfano,
        "worker": job.get("worker") or "",
        "etiqueta": reg.get("etiqueta") or "",
        "tipo": tipo,
        "marca": reg.get("marca") or "",
        "proceso": proceso,
        # Etapa legible derivada (origen para la columna del Monitor); `tipo`/`proceso` crudos arriba.
        "etapa": etapa,
        "gen_estado": reg.get("estado") or "",
        "fase": reg.get("fase") or "",
        # Prioridad de cola (mayor = adelanta): los lanzamientos manuales van por delante
        # del lote de fondo del pipeline; el Monitor lo señala en la lista de espera.
        "prioridad": int(job.get("prioridad") or 0),
        # Intentos gastados (anti crash-loop): >1 delata un job que ya mato a un worker.
        "intentos": int(job.get("intentos") or 0),
        "encolado_hace_s": _edad_s(job.get("creado"), ahora),
        "corriendo_hace_s": _edad_s(job.get("claimed_at"), ahora) if corriendo else None,
        # Tokens: `prompt_chars` (tamano exacto del prompt encolado), `tokens_estimados` (a-priori
        # por etapa) y, para un job en curso que ya reporta, los tokens/coste REALES (si no, null).
        "prompt_chars": int(job.get("prompt_chars") or 0),
        "tokens_estimados": tokens_estimados,
        "tokens_in": vivo[0] if vivo else None,
        "tokens_out": vivo[1] if vivo else None,
        "coste_usd": vivo[2] if vivo else None,
    }


def _daemons_estado() -> list[dict]:
    """Estado ON/OFF de cada daemon de fondo (lee los toggles de `config`, best-effort).

    Cada daemon reporta su `clave_ajuste` (env var del catálogo) y si es `editable`: el Monitor
    pinta un TOGGLE REAL (PUT /api/ajustes) cuando la clave está en el catálogo y NO es peligrosa;
    si no (limpiador sin toggle, o `publicar_real` que es peligroso y vive en su flujo propio), pinta
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
    return JSONResponse(await run_in_threadpool(_cola, marca))


def _cola(marca: str) -> dict:
    snap = snapshot_cola()
    pendientes = snap["pendientes"]
    reclamados = snap["reclamados"]
    terminados = snap["terminados"]
    max_jobs = snap["max_jobs"]
    activos = snap["activos"]

    ahora = datetime.now()
    promedios = repos.tokens_promedio_por_etapa()
    filas = repos.jobs_activos(limite=200)
    en_proceso = [_item_job(j, ahora, promedios) for j in filas]
    # Desglose del pool COMPARTIDO por proceso (ADR 0011): se calcula sobre TODOS los jobs en
    # vuelo (global, como los KPIs de capacidad), ANTES de acotar las listas por marca. La cola y
    # el pool son UNICOS; esto solo dice cuanto del trabajo en proceso es Investigacion (verificación/verificación)
    # y cuanto Produccion (copy/arte), para poder vigilar los dos loops sobre la misma cola.
    por_proceso = {
        proc: {
            "procesando": sum(
                1 for j in en_proceso
                if j["proceso"] == proc and j["estado"] == repos.JOB_RECLAMADO
            ),
            "pendientes": sum(
                1 for j in en_proceso
                if j["proceso"] == proc and j["estado"] == repos.JOB_PENDIENTE
            ),
        }
        for proc in (generaciones.PROCESO_INVESTIGACION, generaciones.PROCESO_PRODUCCION)
    }
    # ADMISION de verificación: el unico limite que Investigacion acota aparte de la cola compartida (cuanta
    # verificación cabe en proceso por marca). Lazy import del helper del pipeline (evita acoplar la API al
    # orquestador) y best-effort: un fallo deja el admision vacio, nunca tumba el snapshot.
    try:
        from ..pipeline_contenido import admision_verificacion as _admision_verificacion

        admision = _admision_verificacion()
    except Exception:  # noqa: BLE001 -- el admision es observabilidad; su fallo no rompe el Monitor
        admision = {"en_proceso": 0, "tope_por_marca": 0, "marcas": []}
    # Jobs HUERFANOS (sin registro de generacion): inflan el conteo GLOBAL pero no caen en
    # ninguna marca. Se cuentan ANTES de acotar por marca para que el Monitor explique el hueco
    # entre el conteo global y lo que suman las marcas. El desglose completo va en `/cola/desglose`.
    huerfanos = {
        "pendientes": sum(
            1 for j in en_proceso if j["huerfano"] and j["estado"] == repos.JOB_PENDIENTE
        ),
        "reclamados": sum(
            1 for j in en_proceso if j["huerfano"] and j["estado"] == repos.JOB_RECLAMADO
        ),
    }
    # Listas para mostrar: respetan el switch GLOBAL de marca (la capacidad/los conteos no).
    if marca:
        en_proceso = [j for j in en_proceso if j["marca"] == marca]
    en_curso = [j for j in en_proceso if j["estado"] == repos.JOB_RECLAMADO]
    esperando = [j for j in en_proceso if j["estado"] == repos.JOB_PENDIENTE]
    # Conteo POR LA MARCA filtrada, derivado de los mismos jobs enriquecidos: CUADRA con las
    # listas (`pendientes == len(esperando)`, `reclamados == len(en_curso)`) para que la UI no
    # mezcle el KPI global con listas por marca. Sin filtro de marca queda None (manda `conteo`).
    conteo_marca = (
        {"pendientes": len(esperando), "reclamados": len(en_curso)} if marca else None
    )
    workers = sorted({j.get("worker") for j in filas if j["estado"] == repos.JOB_RECLAMADO and j.get("worker")})

    return {
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
        # Conteo de la marca filtrada (None sin filtro): cuadra con `en_curso`/`esperando`.
        "conteo_marca": conteo_marca,
        # Jobs sin registro de generacion (parte del conteo global que no cae en ninguna marca).
        "huerfanos": huerfanos,
        "procesando": reclamados,  # claude -p en proceso (acotado por max_jobs)
        "slots_libres": max(0, max_jobs - reclamados),
        "workers_activos": workers,
        # Desglose del pool compartido por proceso + admision de verificación (Investigacion). La cola es
        # UNA; estos dos campos dejan ver los dos loops (ADR 0011) sobre esa misma cola.
        "por_proceso": por_proceso,
        "admision_verificacion": admision,
        "en_curso": en_curso,
        "esperando": esperando,
        "daemons": _daemons_estado(),
        # Economia de tokens (presupuesto_ia): presupuesto diario, gasto del dia UTC,
        # nivel de corte vigente (normal/solo_manual/agotado/pausado) y kill switch.
        # CONTRATO de visibilidad para humanos (Monitor) y agentes (observabilidad).
        # Respeta el switch de marca: con marca activa, el presupuesto/parada PROPIOS de esa
        # marca; "" = el control GLOBAL.
        "presupuesto": presupuesto_ia.estado(marca),
    }


def _desglose_jobs(en_proceso: list[dict]) -> dict:
    """Agrupa los jobs en vuelo YA enriquecidos por marca x proceso x estado + bloque huerfanos.

    `en_proceso` son items de `_item_job` SIN filtrar por marca. Un job HUERFANO (su `gen_id` ya
    no tiene registro: `huerfano=True`) no cae en ninguna marca —se agrega en `huerfanos`—; el
    resto se agrupa por la marca de su registro ('' = feed compartido sin marca). Cada celda cuenta
    `pendientes` (en cola) y `reclamados` (corriendo); ambos procesos van SIEMPRE presentes a cero.
    """
    procs = (generaciones.PROCESO_INVESTIGACION, generaciones.PROCESO_PRODUCCION)
    por_marca: dict[str, dict] = {}
    huerfanos = {"pendientes": 0, "reclamados": 0}
    for j in en_proceso:
        clave = "pendientes" if j["estado"] == repos.JOB_PENDIENTE else "reclamados"
        if j["huerfano"]:
            huerfanos[clave] += 1
            continue
        bloque = por_marca.setdefault(j["marca"], {
            "marca": j["marca"],
            "por_proceso": {p: {"pendientes": 0, "reclamados": 0} for p in procs},
            "total": {"pendientes": 0, "reclamados": 0},
        })
        proc = j["proceso"] if j["proceso"] in bloque["por_proceso"] else generaciones.PROCESO_PRODUCCION
        bloque["por_proceso"][proc][clave] += 1
        bloque["total"][clave] += 1
    return {
        "marcas": [por_marca[m] for m in sorted(por_marca)],
        "huerfanos": huerfanos,
    }


def _cola_desglose() -> dict:
    ahora = datetime.now()
    promedios = repos.tokens_promedio_por_etapa()
    en_proceso = [
        _item_job(j, ahora, promedios) for j in repos.jobs_activos(limite=10_000)
    ]
    return _desglose_jobs(en_proceso)


async def cola_desglose(request: Request) -> Response:
    """GET /api/actividad/cola/desglose: la cola en vuelo agrupada por marca x proceso x estado.

    Desglose AUTORITATIVO del pool en curso (todos los jobs, no acotado por marca): por cada marca
    su `por_proceso` (investigacion/produccion -> pendientes/reclamados) y su `total`, mas un bloque
    `huerfanos` con los jobs sin registro de generacion (lo que infla el conteo global y no cae en
    ninguna marca). Solo lectura; sin filtro de marca (es la foto completa).
    """
    return JSONResponse(await run_in_threadpool(_cola_desglose))


def _cola_preview(marca: str) -> dict:
    from ..pipeline_contenido import preview_redactar_por_marca

    try:
        por_marca = preview_redactar_por_marca()
    except Exception:  # noqa: BLE001 -- el preview es observabilidad; su fallo no rompe el panel
        por_marca = {}
    if marca:
        filas = [(marca, int(por_marca.get(marca, 0)))]
    else:
        filas = sorted(por_marca.items())
    return {"marcas": [{"marca": m, "redactar": n} for m, n in filas]}


async def cola_preview(request: Request) -> Response:
    """GET /api/actividad/cola/preview?marca=: cuantas piezas ENTRARIAN a cada etapa autogenerable.

    Responde, SIN encolar nada, cuanto trabajo pondria en cola activar cada etapa autogenerable de
    una marca. Hoy expone `redactar` (la etapa de copy, la de la avalancha): el MISMO computo de
    seleccion que la etapa de Redactar PERO ignorando su gate por marca, asi se ve el volumen antes
    de encender el toggle. `marca` ("" = todas) acota el resultado a esa marca.
    """
    marca = (request.query_params.get("marca") or "").strip()
    if marca and not marcas.es_marca(marca):
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    return JSONResponse(await run_in_threadpool(_cola_preview, marca))


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

    EXCLUYE los MARCADORES de etapa (`pipeline_etapa`, CI/verificación/CD a coste 0): son trazabilidad, no
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


def _cola_series(dias: int) -> dict:
    return {
        "dias": dias,
        "encolados": repos.encolados_por_dia(dias),
        "resultados": _resultados_por_dia(dias),
        # Lado de CONSUMO (ledger gasto_ia): tokens/coste/generaciones cerradas por dia,
        # para correlacionar el volumen de la cola con el gasto real de la suscripcion.
        "gasto": repos.gasto_ia_por_dia(dias),
    }


async def cola_series(request: Request) -> Response:
    """GET /api/actividad/cola/series?dias=: encolados (jobs) vs resultados (generaciones) por dia."""
    dias = _entero_query(request.query_params.get("dias"), minimo=1) or 14
    return JSONResponse(await run_in_threadpool(_cola_series, dias))


# --------------------------------------------------------------------------- #
# ACCIONES ADMIN sobre la cola (mutan estado -> exigen SESION admin real)       #
# --------------------------------------------------------------------------- #


async def cola_purgar(request: Request) -> Response:
    """POST /api/actividad/cola/purgar: libera la cola (cancela+termina TODO lo activo). Admin.

    Para cada job en proceso: marca el flag `cancelado` (un worker que lo este corriendo mata el
    arbol de `claude`), saca el job de la cola (`terminar`, libera el slot de inmediato) y cierra
    el registro de generacion si seguia `ejecutando`. Es el boton de "destrabar / resetear
    capacidad". Devuelve cuantos jobs purgo.
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    return JSONResponse(await run_in_threadpool(_cola_purgar))


def _cola_purgar() -> dict:
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
    return {"purgados": purgados}


async def cola_eliminar(request: Request) -> Response:
    """POST /api/actividad/cola/eliminar {gen_id}: saca UN job concreto de la cola. Admin.

    A diferencia de `purgar` (vacia toda la cola), borra solo el job del `gen_id` dado. Si estaba
    RECLAMADO (corriendo), primero cancela su arbol (igual que `purgar`: marca `cancelado` para que
    un worker vivo mate su `claude` y cierra el registro `ejecutando` como error); luego lo saca de
    la cola (`terminar`, libera el cupo). 400 sin `gen_id`; 404 si no hay job activo para ese
    `gen_id`. Devuelve `{eliminado, gen_id}`.
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
    status, cuerpo_resp = await run_in_threadpool(_cola_eliminar, gen_id)
    return JSONResponse(cuerpo_resp, status_code=status)


def _cola_eliminar(gen_id: str) -> tuple[int, dict]:
    job = next(
        (j for j in repos.jobs_activos(limite=10_000) if j["gen_id"] == gen_id), None
    )
    if job is None:
        return 404, {"error": "No hay un job activo para esa generación."}
    if job["estado"] == repos.JOB_RECLAMADO:
        repos.cancelar_job(gen_id)  # cross-proceso: un worker vivo mata su claude
        g = generaciones.obtener(gen_id)
        if g and g.get("estado") == generaciones.ESTADO_EJECUTANDO:
            generaciones.actualizar(
                gen_id,
                {
                    "estado": generaciones.ESTADO_ERROR,
                    "motivo": generaciones.MOTIVO_CANCELADO,
                    "error": "Eliminada de la cola (administrador).",
                    "fecha_fin": generaciones.ahora_iso(),
                },
            )
    repos.terminar_job(job["id"])  # fuera de la cola: libera el cupo
    return 200, {"eliminado": True, "gen_id": gen_id}


async def cola_limpiar_huerfanos(request: Request) -> Response:
    """POST /api/actividad/cola/limpiar-huerfanos: saca de la cola los jobs PENDIENTES huerfanos. Admin.

    Un job huerfano (su `gen_id` ya no tiene registro de generacion) jamas se procesa con sentido y
    solo infla el conteo global. Solo se tocan los PENDIENTES (nunca corrieron: no hay arbol de
    `claude` que matar ni post-procesado que duplicar); se marcan `terminado` (salen de la cola
    activa; la retencion borra la fila despues). Devuelve cuantos limpio.
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    return JSONResponse(await run_in_threadpool(_cola_limpiar_huerfanos))


def _cola_limpiar_huerfanos() -> dict:
    filas = repos.jobs_activos(limite=10_000)
    limpiados = 0
    for j in filas:
        if j["estado"] != repos.JOB_PENDIENTE:
            continue
        if generaciones.obtener(j["gen_id"]) is not None:
            continue
        try:
            repos.terminar_job(j["id"])
            limpiados += 1
        except Exception:  # noqa: BLE001 -- un fallo por job no aborta la limpieza del resto
            continue
    return {"huerfanos_limpiados": limpiados}


_PRIORIDAD_MIN = 0
_PRIORIDAD_MAX = 100


async def cola_priorizar(request: Request) -> Response:
    """POST /api/actividad/cola/priorizar {gen_id, prioridad?, a_tope?}: adelanta un job ESPERANDO. Admin.

    Sin `prioridad` ni `a_tope` sube su despacho al de un lanzamiento manual (`PRIORIDAD_MANUAL`).
    Con `prioridad` (entero 0..100) clava ESE valor. Con `a_tope=true` lo deja un escalon por
    encima de todo lo pendiente (lo primero del proximo claim). Solo aplica a jobs aún `pendiente`
    (los reclamados ya corren); 404 si no hay job pendiente para ese `gen_id`; 400 si `prioridad`
    no es un entero del rango.
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    try:
        cuerpo = await request.json()
    except Exception:  # noqa: BLE001 -- body no-JSON
        cuerpo = {}
    if not isinstance(cuerpo, dict):
        cuerpo = {}
    gen_id = (cuerpo.get("gen_id") or "").strip()
    if not gen_id:
        return JSONResponse({"error": "Falta el identificador de la generación."}, status_code=400)
    a_tope = bool(cuerpo.get("a_tope"))
    prioridad: int | None = None
    crudo = cuerpo.get("prioridad")
    if not a_tope and crudo is not None:
        try:
            prioridad = int(crudo)
        except (TypeError, ValueError):
            return JSONResponse({"error": "La prioridad debe ser un número entero."}, status_code=400)
        if not (_PRIORIDAD_MIN <= prioridad <= _PRIORIDAD_MAX):
            return JSONResponse(
                {"error": f"La prioridad debe estar entre {_PRIORIDAD_MIN} y {_PRIORIDAD_MAX}."},
                status_code=400,
            )
    status, cuerpo_resp = await run_in_threadpool(_cola_priorizar, gen_id, prioridad, a_tope)
    return JSONResponse(cuerpo_resp, status_code=status)


def _cola_priorizar(
    gen_id: str, prioridad: int | None = None, a_tope: bool = False
) -> tuple[int, dict]:
    from ..dominio import jobspec

    if a_tope:
        objetivo = repos.max_prioridad_pendiente() + 1
    elif prioridad is not None:
        objetivo = prioridad
    else:
        objetivo = jobspec.PRIORIDAD_MANUAL
    if not repos.priorizar_job(gen_id, objetivo):
        return 404, {"error": "No hay un job esperando para esa generación."}
    return 200, {"priorizado": True, "gen_id": gen_id, "prioridad": objetivo}


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
    status, cuerpo_resp = await run_in_threadpool(_cola_reencolar, gen_id)
    return JSONResponse(cuerpo_resp, status_code=status)


def _cola_reencolar(gen_id: str) -> tuple[int, dict]:
    if not repos.reencolar_job(gen_id):
        return 404, {"error": "No hay un job para esa generación."}
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
    return 200, {"reencolado": True, "gen_id": gen_id}


async def gate_diario_aceptar(request: Request) -> Response:
    """POST /api/actividad/cola/gate-diario/aceptar?cuenta=a|b: sube +10% el umbral del dia de ESA
    cuenta. Admin.

    El gate DIARIO pausa la generacion de las marcas de UNA cuenta cuando el consumo del dia de esa
    cuenta alcanza su umbral vigente (un % de SU limite SEMANAL). Aceptar +10% sube el umbral del dia
    de la cuenta indicada y reanuda sus marcas; al cruzar el nuevo umbral vuelve a pausar. `cuenta`
    es obligatoria y debe ser una cuenta valida (`jobspec.CUENTAS`). Devuelve el estado del gate de
    esa cuenta ya actualizado (la misma forma que un bloque de `presupuesto.gate_diario_cuentas` de
    `/api/actividad/cola`). El estado se LEE de ahi; este endpoint solo MUTA, por eso es admin.
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    from ..dominio import jobspec

    cuenta = (request.query_params.get("cuenta") or "").strip().lower()
    if cuenta not in jobspec.CUENTAS:
        return JSONResponse(
            {"error": f"Cuenta no valida; usa una de {list(jobspec.CUENTAS)}."}, status_code=400
        )
    return JSONResponse(await run_in_threadpool(gate_diario.aceptar_mas, cuenta))


RUTAS = [
    Route("/api/actividad/agregados", agregados, methods=["GET"]),
    Route("/api/actividad/economia", economia, methods=["GET"]),
    # Mas especificas ANTES que la generica para que Starlette case bien.
    Route("/api/actividad/cola/series", cola_series, methods=["GET"]),
    Route("/api/actividad/cola/desglose", cola_desglose, methods=["GET"]),
    Route("/api/actividad/cola/preview", cola_preview, methods=["GET"]),
    Route("/api/actividad/cola/limpiar-huerfanos", cola_limpiar_huerfanos, methods=["POST"]),
    Route("/api/actividad/cola/purgar", cola_purgar, methods=["POST"]),
    Route("/api/actividad/cola/eliminar", cola_eliminar, methods=["POST"]),
    Route("/api/actividad/cola/priorizar", cola_priorizar, methods=["POST"]),
    Route("/api/actividad/cola/reencolar", cola_reencolar, methods=["POST"]),
    Route("/api/actividad/cola/gate-diario/aceptar", gate_diario_aceptar, methods=["POST"]),
    Route("/api/actividad/cola", cola, methods=["GET"]),
]
