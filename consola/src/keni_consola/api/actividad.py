"""API ACTIVIDAD: vista UNIFICADA de la actividad de IA (generaciones + runs).

Reune los DOS registros donde vive la "verdad" de lo que la IA produce —las
GENERACIONES (`generaciones.py`: copy, rss, autogen, hashtags, imagen, verificacion,
qa-editorial, prompt) y los RUNS de agente (`agentes.py`)— en una sola lista de
items normalizados, con filtros, paginacion y agregados. La normalizacion/mezcla/
agregacion es DOMINIO PURO (`consola.actividad`); aqui solo se LEEN ambos orígenes
(via `generaciones.listar(...)` y el dominio `agentes`, NUNCA por HTTP) y se sirven.

Endpoints:
  - `GET /api/actividad?limite=&offset=&fuente=&tipo=`
      -> `{"items": [...], "total": <int>}`
  - `GET /api/actividad/agregados`
      -> `{"total": {...}, "por_tipo": [...], "por_dia": [...]}`
  - `GET /api/actividad/cola`
      -> MONITOR EN VIVO de la cola de generacion: capacidad (max_jobs/max_cola/tope), conteo
         (pendientes/reclamados/terminados/activos), `procesando` (claude -p en vuelo), slots
         libres, workers activos, listas `en_curso`/`esperando` (con etiqueta/tipo/marca/edad) y
         estado de los daemons de fondo. Para "que ocurre AHORA en la cola".
  - `GET /api/actividad/cola/series?dias=`
      -> series por dia: `encolados` (de la tabla de jobs) y `resultados` (completados/errores/
         cola_llena, de las generaciones). Throughput de entrada vs salida de la cola.

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

# Tope por defecto de items por pagina (alineado con el contrato del frontend).
_LIMITE_DEF = 50

# Fuentes y tipos validos para filtrar (un filtro vacio no filtra por ese eje). El `tipo`
# admite los tipos de generacion + "run" + "pipeline" (la generación de copy que lanza el
# pipeline de contenido: trabajo real `claude -p` CON tokens/coste/tiempo). Los MARCADORES
# de etapa (CI/CD/QA, `tipo='pipeline_etapa'`, SIN coste) NO se listan ni se muestran aquí:
# son para la pestaña Pipelines y se EXCLUYEN del feed (ver `_es_marcador_pipeline`), para no
# ensuciar Actividad con filas a 0.
_FUENTES = frozenset({"generacion", "run"})
_TIPOS = frozenset({*generaciones.TIPOS, "autogen", "run", "pipeline"})


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
        return (gen.get("etiqueta", "") or "").startswith(("CI · ", "CD · ", "QA · "))
    return False


def _filtro(valor: str | None, validos: frozenset[str]) -> str:
    """Normaliza un filtro de query: devuelve el valor si es valido, "" si no."""
    v = (valor or "").strip()
    return v if v in validos else ""


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


async def listar(request: Request) -> Response:
    """Actividad unificada (generaciones + runs), filtrada, ordenada y paginada.

    Query: `limite` (def 50), `offset` (def 0), `fuente` (""|generacion|run),
    `tipo` (""|copy|rss|autogen|hashtags|imagen|verificacion|qa-editorial|prompt|run),
    `marca` (""=todas, o un id de marca valido — acota la actividad a esa marca).
    """
    qp = request.query_params
    marca = (qp.get("marca") or "").strip()
    if marca and not marcas.es_marca(marca):
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    limite = _entero_query(qp.get("limite"), minimo=1)
    offset = _entero_query(qp.get("offset"), minimo=0) or 0
    fuente = _filtro(qp.get("fuente"), _FUENTES)
    tipo = _filtro(qp.get("tipo"), _TIPOS)

    gens, runs = _origenes(marca or None)
    items, total = actividad.combinar(
        gens, runs,
        fuente=fuente, tipo=tipo, offset=offset,
        limite=_LIMITE_DEF if limite is None else limite,
    )
    return JSONResponse({"items": items, "total": total})


async def agregados(request: Request) -> Response:
    """Agregados de la actividad: total + por_tipo (incluye 'run') + por_dia.

    Query: `marca` (""=todas, o un id de marca valido — acota los agregados a esa marca).
    """
    qp = request.query_params
    marca = (qp.get("marca") or "").strip()
    if marca and not marcas.es_marca(marca):
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    gens, runs = _origenes(marca or None)
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
# El interruptor general (`maquina`), la Selección (`ingesta`) y el Copy (`pipeline`) NO están aquí:
# son ETAPAS de la máquina y se controlan en la sección «Máquina de contenido» del Monitor (toggles
# del catálogo: maquina_global + maestros_etapa + topes). Aquí quedan los daemons de fondo restantes.
_DAEMONS: list[tuple[str, str, str | None, str, str]] = [
    ("trends", "Google Trends", "trends_activo",
     "Ingiere tendencias (con sus noticias) al pool.", config.ENV_TRENDS),
    ("algoritmos", "Feeds de algoritmo", "algoritmos_auto_activo",
     "Refresca los feeds de algoritmo por marca.", config.ENV_ALGORITMOS_AUTO),
    ("sugerencias", "Sugerencias editoriales", "sugerencias_editoriales_activo",
     "Digest diario de sugerencias editoriales.", config.ENV_SUGERENCIAS_EDITORIALES),
    ("media_gc", "GC de media", "media_gc_activo",
     "Recoge media huérfana (no borra salvo toggle).", config.ENV_MEDIA_GC),
    ("noticias_gc", "GC de noticias", "noticias_gc_activo",
     "Poda el pool de noticias por relevancia/inactividad.", config.ENV_NOTICIAS_GC),
    ("alertas", "Alertas de rendimiento", "alertas_rendimiento_activas",
     "Lee métricas y emite eventos de alerta.", config.ENV_ALERTAS_ACTIVAS),
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

    estados = repos.contar_jobs_por_estado()
    pendientes = estados.get(repos.JOB_PENDIENTE, 0)
    reclamados = estados.get(repos.JOB_RECLAMADO, 0)
    terminados = estados.get(repos.JOB_TERMINADO, 0)
    max_jobs, max_cola = config.max_jobs(), config.max_cola()
    tope = max_jobs + max_cola
    activos = pendientes + reclamados

    ahora = datetime.now()
    filas = repos.jobs_activos(limite=200)
    en_vuelo = [_item_job(j, ahora) for j in filas]
    if marca:
        en_vuelo = [j for j in en_vuelo if j["marca"] == marca]
    en_curso = [j for j in en_vuelo if j["estado"] == repos.JOB_RECLAMADO]
    esperando = [j for j in en_vuelo if j["estado"] == repos.JOB_PENDIENTE]
    workers = sorted({j.get("worker") for j in filas if j["estado"] == repos.JOB_RECLAMADO and j.get("worker")})

    return JSONResponse(
        {
            # Eco del filtro aplicado a las listas ("" = todas): la UI lo usa para etiquetar.
            "marca": marca,
            "capacidad": {"max_jobs": max_jobs, "max_cola": max_cola, "tope": tope},
            "conteo": {
                "pendientes": pendientes,
                "reclamados": reclamados,
                "terminados": terminados,
                "activos": activos,
            },
            "cola_llena": activos >= tope,
            "procesando": reclamados,  # claude -p en vuelo (acotado por max_jobs)
            "slots_libres": max(0, max_jobs - reclamados),
            "workers_activos": workers,
            "en_curso": en_curso,
            "esperando": esperando,
            "daemons": _daemons_estado(),
            # Economia de tokens (presupuesto_ia): presupuesto diario, gasto del dia UTC,
            # nivel de corte vigente (normal/solo_manual/agotado/pausado) y kill switch.
            # CONTRATO de visibilidad para humanos (Monitor) y agentes (observabilidad).
            "presupuesto": presupuesto_ia.estado(),
        }
    )


def _resultados_por_dia(dias: int) -> list[dict]:
    """Generaciones por dia clasificadas en completados / errores (y cuantos por cola llena).

    Escanea el almacen de generaciones (YAML) una vez y agrupa por `fecha_inicio[:10]`. Es el
    lado de SALIDA de la cola; el endpoint que lo usa se sondea con poca frecuencia (no es el
    snapshot en vivo), asi que el escaneo completo es aceptable.
    """
    corte = (hoy_utc() - timedelta(days=max(0, dias - 1))).isoformat()
    buckets: dict[str, dict] = {}
    for g in generaciones.listar(limite=None):
        dia = (g.get("fecha_inicio") or "")[:10]
        if not dia or dia < corte:
            continue
        b = buckets.setdefault(dia, {"completados": 0, "errores": 0, "cola_llena": 0})
        est = g.get("estado")
        if est == generaciones.ESTADO_COMPLETADO:
            b["completados"] += 1
        elif est == generaciones.ESTADO_ERROR:
            b["errores"] += 1
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

    if not repos.priorizar_job(gen_id, jobspec.PRIORIDAD_MANUAL):
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
    Route("/api/actividad", listar, methods=["GET"]),
    Route("/api/actividad/agregados", agregados, methods=["GET"]),
    # Mas especificas ANTES que la generica para que Starlette case bien.
    Route("/api/actividad/cola/series", cola_series, methods=["GET"]),
    Route("/api/actividad/cola/purgar", cola_purgar, methods=["POST"]),
    Route("/api/actividad/cola/priorizar", cola_priorizar, methods=["POST"]),
    Route("/api/actividad/cola/reencolar", cola_reencolar, methods=["POST"]),
    Route("/api/actividad/cola", cola, methods=["GET"]),
]
