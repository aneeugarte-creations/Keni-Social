"""API Producción del día: el admision de los N contenidos diarios de una marca, en un sitio.

PROBLEMA QUE RESUELVE
=====================
El objetivo editorial es un puñado de contenidos AL DÍA por marca (p.ej. 13 de UnoTV),
pero su seguimiento estaba repartido: la cola de generación en Actividad, las runs en
Pipelines, la cola de aprobación en el feed y lo programado en el calendario. Nadie veía
de un vistazo "¿cómo van los 13 de hoy?". Este endpoint junta las CUATRO vistas para la
ventana de producción del día:

  GET /api/produccion/dia?marca=unotv ->
    {
      "marca", "ventana": {desde, hasta},
      "objetivo": {"plan": plan_dia|None},
      "admision": {"total", "generando", "en_borrador", "en_revision",
                  "programado", "publicado"},
      "por_categoria_etiqueta": [{"categoria", "total", "en_revision", "programado", "publicado"}],
      "por_origen": {"pipeline": n, "historia": n, ...},
      "cola_generacion": {"pendientes", "en_curso"},
      "programacion": {"programadas": [{id, titulo, red, fecha_programada}],
                        "proximos_huecos": [{"red", "hueco"}]},
      "piezas": [{"id", "titulo", "categoria", "estado", "redes", "creado"}],
    }

El ADMISION cuenta TEMAS (contenido padre), no filas por red: el objetivo diario se mide en
contenidos, y cada tema se clasifica por su pieza MÁS AVANZADA (publicado > programado >
en_revision > borrador con copy > generando). `objetivo.plan` es el PLAN EDITORIAL por marca
(`KENI_PLAN_DIA::marca`) que regula Admitir: la fuente de verdad de "cuántos al día y de qué".

Lo consumen la UI (panel de producción) y el MCP operativo (`keni_produccion_dia`), para
que tanto el equipo como los agentes monitoricen la generación del día sin sumar a mano.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import bootstrap_categorias, config, marcas, pipeline_estado, redes, repos
from ..tiempo import ahora_iso, inicio_dia_cdmx_iso_utc

_log = logging.getLogger("keni_consola.api.produccion")

# Escalera de estados de plataforma, de menos a más avanzado: el tema se clasifica por el
# MÁXIMO que alcanza cualquiera de sus redes (una pieza publicada en X ya "cuenta" aunque
# la de Instagram siga en revisión).
_ESCALERA = ("borrador", "en_revision", "programado", "publicado")
_RANGO = {e: i for i, e in enumerate(_ESCALERA)}

# Redes sociales candidatas para el cálculo de próximos huecos de programación.
_REDES_HUECO = ("x", "instagram", "facebook", "tiktok", "youtube")


def _estado_max(filas: list[dict[str, Any]]) -> str:
    """Estado de plataforma MÁS AVANZADO de un tema ('' si no tiene filas)."""
    mejor = -1
    for f in filas:
        mejor = max(mejor, _RANGO.get(str(f.get("estado") or ""), -1))
    return _ESCALERA[mejor] if mejor >= 0 else ""


def _peldano_admision(filas: list[dict[str, Any]]) -> str:
    """Peldaño del admision de un tema: estados editoriales o 'generando'/'en_borrador'.

    'generando' = tiene redes pero NINGUNA con copy todavía (la IA trabaja);
    'en_borrador' = hay copy pero ninguna red pasó de `borrador` (reposo del
    avance o pieza incompleta de asset).
    """
    estado = _estado_max(filas)
    if estado in ("", "borrador"):
        con_copy = any(str(f.get("copy") or "").strip() for f in filas)
        return "en_borrador" if con_copy else "generando"
    return estado


def _categoria_de(etiquetas: list[str], categorias: set[str]) -> str:
    """Primera etiqueta del tema que sea una categoría de la marca ('' si ninguna)."""
    for nombre in etiquetas:
        if nombre in categorias:
            return nombre
    return ""


async def dia(request: Request) -> Response:
    """GET /api/produccion/dia?marca=: producción de la JORNADA MX (parrilla del día) de una marca."""
    marca = (request.query_params.get("marca") or "").strip()
    if marca and not marcas.es_marca(marca):
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    return JSONResponse(await run_in_threadpool(_dia, marca))


def _dia(marca: str) -> dict:
    ahora = datetime.fromisoformat(ahora_iso())
    # JORNADA MX (la parrilla del día), no ventana móvil de 24 h: a medianoche de México
    # el monitor vuelve a 0, igual que el contador del plan de la Mesa y Admitir.
    desde_iso = inicio_dia_cdmx_iso_utc(ahora)

    # Temas (contenido padre) CREADOS en la ventana + sus filas por red. El corte por `creado`
    # se empuja a SQL (`creado_desde`): la jornada trae solo lo del día, no el histórico.
    items = repos.listar_publicacion(
        clase="contenido", marca=marca or None, creado_desde=desde_iso
    )
    filas = repos.listar_piezas_fila(marca=marca or None)
    filas_por_item: dict[str, list[dict[str, Any]]] = {}
    for f in filas:
        filas_por_item.setdefault(str(f.get("publicacion_id") or ""), []).append(f)

    etiquetas_por_item = repos.etiquetas_por_contenido()
    categorias_marca = {
        e.get("nombre", "")
        for e in repos.listar_etiquetas(marca=marca or None, clase="categoria")
        if e.get("nombre")
    }

    # Admisión + detalle por tema.
    admision = {
        "total": len(items),
        "generando": 0,
        "en_borrador": 0,
        "en_revision": 0,
        "programado": 0,
        "publicado": 0,
    }
    por_categoria_etiqueta: dict[str, dict[str, int]] = {}
    por_origen: dict[str, int] = {}
    piezas: list[dict[str, Any]] = []
    for it in items:
        iid = str(it.get("id") or "")
        sus_filas = filas_por_item.get(iid, [])
        peldano = _peldano_admision(sus_filas)
        admision[peldano] = admision.get(peldano, 0) + 1
        origen = str(it.get("origen") or "") or "manual"
        por_origen[origen] = por_origen.get(origen, 0) + 1
        categoria = _categoria_de(etiquetas_por_item.get(iid, []), categorias_marca)
        v = por_categoria_etiqueta.setdefault(
            categoria or "(sin categoría)",
            {"total": 0, "en_revision": 0, "programado": 0, "publicado": 0},
        )
        v["total"] += 1
        if peldano in ("en_revision", "programado", "publicado"):
            v[peldano] = v.get(peldano, 0) + 1
        piezas.append(
            {
                "id": iid,
                "titulo": it.get("titulo") or "",
                "categoria": categoria,
                "estado": peldano,
                "redes": sorted({str(f.get("red") or "") for f in sus_filas if f.get("red")}),
                "creado": it.get("creado") or "",
            }
        )
    piezas.sort(key=lambda p: p["creado"], reverse=True)

    # Objetivo: el PLAN EDITORIAL por marca que regula Admitir ({} = sin plan -> None, esa marca
    # no auto-produce).
    objetivo = {
        "plan": config.plan_dia(marca) or None,
    }

    # CANTIDADES POR LÍNEA del plan (monitor): GENERADOS y PUBLICADOS en la ventana vs
    # OBJETIVO, por categoría — el MISMO conteo que usa Admitir (contenido.categoria).
    # Incluye las categorías del plan aunque vayan a 0 y las generadas fuera de plan.
    por_categoria: list[dict[str, Any]] = []
    if marca:
        plan = config.plan_dia(marca)
        try:
            resumen = repos.resumen_plan_por_categoria(marca, desde_iso)
        except Exception:  # noqa: BLE001 -- el panel no falla por un contador
            _log.exception("produccion: fallo el conteo por categoría (%s).", marca)
            resumen = {}
        categorias = sorted(set(plan) | set(resumen))

        def _etiqueta_clave(clave: str) -> str:
            """Nombre legible de una clave de plan: id de línea -> su nombre; señales con su rótulo."""
            rotulo = bootstrap_categorias.ETIQUETAS_CLAVE_NO_LINEA.get(clave)
            if rotulo is not None:
                return rotulo
            et = repos.obtener_etiqueta(clave)
            return (et or {}).get("nombre") or clave

        por_categoria = [
            {
                "categoria": cat,
                "etiqueta": _etiqueta_clave(cat),
                "generados": resumen.get(cat, {}).get("generados", 0),
                "publicados": resumen.get(cat, {}).get("publicados", 0),
                "objetivo": plan.get(cat) or None,
            }
            for cat in categorias
            if cat  # sin categoría ('') no es una línea del plan
        ]

    # Cola de generación (conteo global; el detalle vive en /api/actividad/cola).
    estados_jobs = repos.contar_jobs_por_estado()
    cola = {
        "pendientes": estados_jobs.get(repos.JOB_PENDIENTE, 0),
        "en_curso": estados_jobs.get(repos.JOB_RECLAMADO, 0),
    }

    # Cola de programación: lo programado (futuro primero) + el próximo hueco por red.
    programadas = [
        {
            "id": p["id"],
            "titulo": p.get("titulo") or "",
            "red": p.get("red") or "",
            "fecha_programada": p.get("fecha_programada") or "",
        }
        for p in repos.listar_piezas(marca=marca or None, estado="programado")
    ]
    programadas.sort(key=lambda p: p["fecha_programada"])
    proximos_huecos: list[dict[str, str]] = []
    if marca:
        # Import perezoso: reusa el cálculo del encolado manual (franjas de horario).
        from .piezas import calcular_hueco_para

        for red in _REDES_HUECO:
            if not redes.es_red(red):
                continue
            try:
                hueco = calcular_hueco_para({"id": "", "marca": marca, "red": red}, ahora)
            except Exception:  # noqa: BLE001 -- un fallo de franjas no tumba el panel
                _log.exception("produccion: fallo el cálculo de hueco (%s/%s).", marca, red)
                hueco = None
            if hueco:
                proximos_huecos.append({"red": red, "hueco": hueco})

    return {
        "marca": marca,
        "ventana": {"desde": desde_iso, "hasta": ahora.isoformat(timespec="seconds")},
        "objetivo": objetivo,
        "por_categoria": por_categoria,
        "admision": admision,
        "por_categoria_etiqueta": [
            {"categoria": k, **v}
            for k, v in sorted(por_categoria_etiqueta.items(), key=lambda kv: -kv[1]["total"])
        ],
        "por_origen": por_origen,
        "cola_generacion": cola,
        "programacion": {
            "programadas": programadas,
            "proximos_huecos": proximos_huecos,
        },
        "piezas": piezas,
    }


# --------------------------------------------------------------------------- #
# Backlog de la CADENA completa (no la jornada): el embalse oculto por marca    #
# --------------------------------------------------------------------------- #
# Claves de `etapas` en orden de la cadena (entrada -> salida). El front depende de que
# SIEMPRE estén las seis, a 0 si no hay nada en esa etapa.
_BACKLOG_ETAPAS = (
    "pool_sin_admitir",     # [A] clusters de noticia `nuevo` aún sin admitir (pool de redacción)
    "pipeline_en_proceso",  # [B] temas admitidos en proceso (sin verificar / verificado sin copy)
    "esperando_copy",       # [C] autogen en el tablero priorizado, sin copy aún (= ETAPA_PRIORIZADA)
    "generando_copy",       # [D1] copy ya encolado (etiqueta autogen), sin copy listo
    "generando_arte",       # [D2] tiene copy pero le falta el arte
    "lista_para_revisar",   # [E] copy + arte listos / ya en el gate humano
)

# Estimación APROXIMADA de cuánto costará vaciar el backlog: cada etapa pendiente factura el
# coste de la PRÓXIMA generación de IA que disparará (no la que ya consumió). Mapea la clave de
# `etapas` a la ETAPA legible del ledger (`gasto_ia`) cuya media histórica se aplica por pieza:
#   - pool_sin_admitir   -> Verificar (al admitirse se verificará la fuente; trabajo upstream que SÍ estimamos)
#   - pipeline_en_proceso-> Verificar (lo que falta es verificar/decidir antes del copy)
#   - esperando_copy     -> Redactar  (término dominante: la siguiente generación es el copy)
#   - generando_arte     -> Ilustrar  (copy hecho, falta el arte)
# Las etapas que NO disparan nueva generación de IA se omiten (cuestan 0):
#   - generando_copy     (su copy ya está encolado/en curso) · lista_para_revisar (ya completas)
_BACKLOG_ESTIMADO_ETAPA = {
    "pool_sin_admitir": "Verificar",
    "pipeline_en_proceso": "Verificar",
    "esperando_copy": "Redactar",
    "generando_arte": "Ilustrar",
}


def _pool_sin_admitir(marca: str) -> int:
    """[A] Clusters de noticia en `nuevo` (pool sin admitir) de una marca. 0 best-effort."""
    try:
        _, total = repos.listar_noticia_clusters(marca=marca, estado="nuevo", limite=1)
        return int(total)
    except Exception:  # noqa: BLE001 -- una sub-cuenta que falla cae a 0, no tumba el panel
        _log.exception("backlog: fallo el conteo del pool sin admitir (%s).", marca)
        return 0


def _pipeline_en_proceso(marca: str) -> int:
    """[B] Temas admitidos del pipeline EN PROCESO de una marca. 0 best-effort."""
    try:
        from ..pipeline_contenido import temas_en_proceso

        return temas_en_proceso(marca)
    except Exception:  # noqa: BLE001 -- una sub-cuenta que falla cae a 0, no tumba el panel
        _log.exception("backlog: fallo el conteo del pipeline en proceso (%s).", marca)
        return 0


async def backlog(request: Request) -> Response:
    """GET /api/produccion/backlog: el backlog HISTÓRICO de la cadena por marca × etapa."""
    return JSONResponse(await run_in_threadpool(_backlog))


def _backlog() -> dict:
    """Recuento del backlog COMPLETO (todo el embalse, no solo la jornada) por marca × etapa.

    A diferencia de `_dia` (que recorta a la JORNADA MX), aquí se cuenta TODO lo pendiente a lo
    largo de la cadena: el pool de noticias sin admitir [A], el pipeline admitido en proceso [B]
    y el backlog del tablero autogen por etapa [C-E]. Las tres lecturas globales del tablero se
    hacen UNA vez y se agrupan por marca en Python (no una query por marca); el pool [A] y el
    pipeline en proceso [B] sí se cuentan por marca (no hay lectura global por marca para ellos)
    y caen a 0 best-effort si su fuente falla.
    """
    # Tablero (autogen [C-E]): los tres insumos PUROS de `pipeline_estado.contar_por_etapa`,
    # leídos globales y agrupados por marca.
    items = repos.listar_publicacion(clase="contenido")
    items_por_marca: dict[str, list[dict[str, Any]]] = {}
    for it in items:
        items_por_marca.setdefault(str(it.get("marca") or ""), []).append(it)

    filas_por_item: dict[str, list[dict[str, Any]]] = {}
    for f in repos.listar_piezas_fila():
        filas_por_item.setdefault(str(f.get("publicacion_id") or ""), []).append(f)
    etiquetas_por_item = repos.etiquetas_por_contenido()

    # Medias históricas por etapa (una sola lectura del ledger), para estimar el coste de vaciar
    # el backlog. Etapas sin muestra histórica no están en el dict -> cuentan 0 (sin cascar).
    tokens_medios = repos.tokens_promedio_por_etapa()
    coste_medio = repos.coste_promedio_por_etapa()

    salida: list[dict[str, Any]] = []
    estimado_total = {"tokens": 0, "coste_usd": 0.0}
    for marca in sorted(marcas.ids()):
        etapas_tablero = pipeline_estado.contar_por_etapa(
            items_por_marca.get(marca, []),
            plataformas_por_item=filas_por_item,
            etiquetas_por_item=etiquetas_por_item,
        )
        etapas = {
            "pool_sin_admitir": _pool_sin_admitir(marca),
            "pipeline_en_proceso": _pipeline_en_proceso(marca),
            "esperando_copy": etapas_tablero.get(pipeline_estado.ETAPA_PRIORIZADA, 0),
            "generando_copy": etapas_tablero.get(pipeline_estado.ETAPA_GENERANDO_COPY, 0),
            "generando_arte": etapas_tablero.get(pipeline_estado.ETAPA_GENERANDO_ARTE, 0),
            "lista_para_revisar": etapas_tablero.get(pipeline_estado.ETAPA_LISTA_REVISAR, 0),
        }
        estimado = _estimar_backlog(etapas, tokens_medios, coste_medio)
        estimado_total["tokens"] += estimado["tokens"]
        estimado_total["coste_usd"] += estimado["coste_usd"]
        salida.append(
            {
                "marca": marca,
                "nombre": marcas.etiqueta_de(marca),
                "etapas": etapas,
                "total": sum(etapas.values()),
                "estimado": estimado,
            }
        )
    return {"marcas": salida, "estimado_total": estimado_total}


def _estimar_backlog(
    etapas: dict[str, int],
    tokens_medios: dict[str, int],
    coste_medio: dict[str, float],
) -> dict[str, Any]:
    """Coste APROXIMADO de generar lo pendiente: conteo de cada etapa × media histórica de la
    PRÓXIMA generación que dispara (`_BACKLOG_ESTIMADO_ETAPA`). Las etapas sin media histórica o
    sin mapeo aportan 0. Es una estimación a-priori, no un gasto real."""
    tokens = 0
    coste_usd = 0.0
    for clave, etapa_ledger in _BACKLOG_ESTIMADO_ETAPA.items():
        n = etapas.get(clave, 0)
        tokens += n * tokens_medios.get(etapa_ledger, 0)
        coste_usd += n * coste_medio.get(etapa_ledger, 0.0)
    return {"tokens": tokens, "coste_usd": coste_usd}


RUTAS = [
    Route("/api/produccion/dia", dia, methods=["GET"]),
    Route("/api/produccion/backlog", backlog, methods=["GET"]),
]
