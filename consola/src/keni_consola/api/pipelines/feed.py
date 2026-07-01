"""PIPELINES · `GET /api/pipelines`: el feed UNIFICADO de Producción.

Mezcla en una sola línea temporal las RUNS del pipeline (`clase="run"`) y la ACTIVIDAD SUELTA
(`clase="actividad"`: generaciones que no nacieron de una run + runs de agente), con filtros y
paginación offset. Cada item suelto se presenta con la MISMA forma que una run (una etapa) para
que la UI lo pinte con la misma tarjeta.
"""

from __future__ import annotations

import logging
import os

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ... import actividad, agentes, generaciones, marcas, repos
from ..._http_json import _entero_query, envoltura_paginacion
from ...estados import CLASE_CONTENIDO, ORIGENES_AUTOGEN
from ...pipeline_contenido import ORIGEN_PIPELINE
from ..actividad import _es_marcador_pipeline
from ._comun import (
    _CLASES,
    _ENV_FUTUROS_MAX,
    _ESTADO_ACTIVIDAD,
    _ESTADO_HECHA,
    _ESTADOS_GLOBAL,
    _ETAPA_CLAVES,
    _FUTUROS_MAX_DEF,
    _LIMITE_DEF,
    _LIMITE_MAX,
    _METRICAS_CERO,
    _ORIGENES_RUN,
    _PREFIJO_POOL_EDITORIAL,
    _PREFIJO_POOL_FUSION,
    _TIPOS_TRABAJO_PIPELINE,
    _UNIVERSO_MAX,
    _marca_nombre,
)
from ._metricas import (
    _con_pool,
    _marcas_con_pool,
    _metricas_por_run,
    _pool_por_marca,
    _runs_con_arte_ia,
    _runs_con_carrusel,
    _runs_con_critica_ia,
    _runs_con_decisor,
    _runs_con_hashtags,
)
from ._runs import _run_de

_log = logging.getLogger("keni_consola.api.pipelines.feed")


def _item_de_actividad(it: dict) -> dict:
    """Presenta un item SUELTO de actividad (generación manual / run de agente) como una
    "run" de UNA etapa, con la MISMA forma que las runs del pipeline.

    Así la UI lo pinta con la misma tarjeta (tira de etapas + métricas) y el mismo patrón de
    detalle entrada/salida. `it` es el item YA normalizado por el dominio `actividad`. La
    etapa única lleva `clave="trabajo"` y `nombre` = el tipo crudo (la UI lo etiqueta con su
    catálogo de tipos); `tipo`/`fuente` viajan para filtros y navegación.
    """
    estado = _ESTADO_ACTIVIDAD.get(it["estado"], "pendiente")
    marca = it["marca"]
    etapa = {
        "clave": "trabajo",
        "nombre": it["tipo"] or "trabajo",
        "estado": estado,
        "detalle": "",
        "ts": it["fecha"],
        "es_ia": True,
    }
    return {
        "clase": "actividad",
        "id": it["id"],
        "titulo": it["etiqueta"] or it["tipo"] or "Sin etiqueta",
        "marca": marca,
        "marca_nombre": _marca_nombre(marca) or marca,
        "origen": it["fuente"],  # "generacion" | "run" (run de agente)
        "tipo": it["tipo"],
        "descripcion": "",
        "creado": it["fecha"],
        "actualizado": it["fecha"],
        "estado_global": estado,
        "etapa_actual": "",
        "etapas": [etapa],
        "verificacion": None,
        "cluster": None,
        "metricas": {"items": 1, **{k: v for k, v in it["metricas"].items() if k != "num_turns"}},
        "piezas": [],
        # Ruta del SPA al resultado (si su tipo tiene página); la UI la ofrece en el detalle.
        "resultado_url": it["resultado_url"],
    }


def _actividad_suelta(gens: list[dict], ids_runs: set[str], marca: str | None) -> list[dict]:
    """Items SUELTOS del feed: generaciones que no pertenecen a una run listada + runs de agente.

    Excluye los marcadores de etapa (sin coste), el trabajo del POOL y de etapas del pipeline
    (`tipo='pipeline'`, y su nombre LEGADO `autogen`: ya está representado DENTRO de las runs)
    y toda generación cuyo `publicacion_id` apunte a una run de `ids_runs` (su coste ya viaja en
    la run; listarla otra vez sería la duplicación que teníamos con dos pestañas). Una
    generación correlacionada a un contenido que NO es run (p. ej. un copy manual sobre el
    tablero) SÍ sale suelta. Convertir un post en Carrusel (`tipo='carrusel'`) NO es una
    excepción: es trabajo de PRODUCCIÓN sobre la misma historia (alternativa a un post de foto
    simple), así que se pliega en su run como cualquier otra etapa (ver `_ETAPAS`), no sale
    suelta aunque su post sea una run.
    """
    sueltas = [
        actividad.normalizar_generacion(g)
        for g in gens
        if not _es_marcador_pipeline(g)
        and (g.get("tipo") or "") not in _TIPOS_TRABAJO_PIPELINE
        and (g.get("publicacion_id") or "") not in ids_runs
    ]
    runs_agente = agentes.listar_runs_globales()
    if marca:
        runs_agente = [
            r for r in runs_agente if (r.get("agente") or r.get("marca") or "") == marca
        ]
    sueltas.extend(actividad.normalizar_run(r) for r in runs_agente)
    return [_item_de_actividad(it) for it in sueltas]


def _temas_trabajados(gens: list[dict]) -> set[str]:
    """Ids de contenido con TRABAJO del pipeline correlacionado (copy/arte/verificación/decisor/marcadores).

    Es la evidencia que convierte un tema del TABLERO en run del feed: la etapa Redactar del
    pipeline también redacta los temas de `ORIGENES_AUTOGEN` (rss/equipo/historia/…); ese
    trabajo debe verse DENTRO de la run de su tema, no como entradas sueltas. El Decisor corre
    ANTES que Redactar (`_TIPOS_TRABAJO_PIPELINE` incluye `decisor`): sin esta evidencia, un tema
    cuyo ÚNICO trabajo hasta ahora fuera el Decisor no contaría como "trabajado" todavía y su
    generación saldría suelta en vez de dentro de la run de su historia.
    """
    return {
        g.get("publicacion_id") or ""
        for g in gens
        if (g.get("publicacion_id") or "") and (g.get("tipo") or "") in _TIPOS_TRABAJO_PIPELINE
    }


def _runs_del_pipeline(items: list[dict], trabajados: set[str]) -> list[dict]:
    """Temas que son RUNS del feed, más recientes primero, acotados a `_UNIVERSO_MAX`.

    Son runs: (a) todo contenido `origen='pipeline'` (recolectado por el propio pipeline) y
    (b) los temas del TABLERO (`ORIGENES_AUTOGEN`) que la máquina TRABAJÓ (`trabajados`:
    tienen generaciones del pipeline correlacionadas) — su copy/arte pertenece al pipeline
    y se muestra como run, no como entradas sueltas. Un alta manual sin trabajo IA no es
    una run TRABAJADA (sale en su lugar como tema FUTURO; ver `_temas_futuros`).

    `items` es el tablero del equipo (`listar_publicacion`, ya acotado a la marca enfocada);
    `listar_publicacion` no filtra por `origen`, así que filtramos en memoria. Reordenamos por
    recencia (`creado` desc) y acotamos al universo máximo (los filtros y la paginación se
    aplican sobre este conjunto).

    NO oculta runs por el toggle de la marca: un tema que NACIÓ del pipeline sigue siendo
    localizable aunque luego apaguen "Crear noticias" (antes se ocultaban y aparecían posts en
    el feed sin pipeline que encontrar). Con la marca apagada, la etapa CI se pinta "saltada"
    (lo refleja `_etapas_de_run`), pero la run NO desaparece de Pipelines.
    """
    pipeline = [
        it
        for it in items
        if (it.get("origen") or "") == ORIGEN_PIPELINE
        or ((it.get("origen") or "") in _ORIGENES_RUN and (it.get("id") or "") in trabajados)
    ]
    pipeline.sort(key=lambda it: (it.get("creado", "") or "", it.get("id", "")), reverse=True)
    return pipeline[:_UNIVERSO_MAX]


def _futuros_max() -> int:
    """Tope de temas FUTUROS a materializar (env `KENI_PIPELINES_FUTUROS_MAX`, def `_FUTUROS_MAX_DEF`)."""
    crudo = os.environ.get(_ENV_FUTUROS_MAX, "")
    try:
        return max(1, int(crudo))
    except (TypeError, ValueError):
        return _FUTUROS_MAX_DEF


def _temas_futuros(items: list[dict], trabajados: set[str]) -> list[dict]:
    """Temas del TABLERO que la máquina AÚN no ha trabajado: el backlog FUTURO del feed.

    Son los temas redactables (`clase='contenido'`, `origen` en `ORIGENES_AUTOGEN`, no cerrados)
    que NO tienen ninguna generación de trabajo del pipeline correlacionada (`id` fuera de
    `trabajados`). Esa misma condición GARANTIZA el dedup con las runs trabajadas: un tema que ya
    es run (vía `_runs_del_pipeline`, condición (b)) está en `trabajados` y por tanto NO sale aquí.
    Los `origen='pipeline'` tampoco caen aquí (no están en `ORIGENES_AUTOGEN`): son siempre runs.

    Orden: más recientes primero (`creado` desc) — el recorte por `_futuros_max` se queda con los
    más nuevos. El llamante los pinta DESPUÉS de los pasados/en curso (van al final del feed).
    """
    futuros = [
        it
        for it in items
        if (it.get("clase") or CLASE_CONTENIDO) == CLASE_CONTENIDO
        and (it.get("origen") or "") in ORIGENES_AUTOGEN
        and (it.get("estado") or "") != _ESTADO_HECHA
        and (it.get("id") or "") not in trabajados
    ]
    futuros.sort(key=lambda it: (it.get("creado", "") or "", it.get("id", "")), reverse=True)
    return futuros


async def listar(request: Request) -> Response:
    """GET /api/pipelines?marca=&etapa=&estado=&tipo=&clase=&limite=50&desplazamiento=0.

    Feed UNIFICADO de Producción, recientes primero: runs del pipeline (`clase="run"`) +
    actividad suelta (`clase="actividad"`), con FILTROS y PAGINACIÓN offset (envelope
    `paginacion:{total, limite, desplazamiento}`). Mantiene la clave `pipelines`
    retrocompatible. Filtros (se IGNORAN si el valor no es válido: el cliente ve el
    conjunto sin filtrar, no un 400):
      - `etapa`: la etapa del pipeline donde la run está parada (solo casa runs).
      - `estado`: el `estado_global` del item (runs y sueltos).
      - `tipo`: el tipo de trabajo de un item suelto (copy/rss/imagen/run/…; solo casa sueltos).
      - `clase`: "run" (solo pipeline) o "actividad" (solo sueltos).
    Los filtros se aplican sobre el objeto DERIVADO (etapa_actual/estado_global), por eso se
    materializa el universo y se filtra/pagina en memoria.
    """
    qp = request.query_params
    marca = (qp.get("marca") or "").strip()
    if marca and not marcas.es_marca(marca):
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    etapa = (qp.get("etapa") or "").strip()
    if etapa and etapa not in _ETAPA_CLAVES:
        etapa = ""
    estado = (qp.get("estado") or "").strip()
    if estado and estado not in _ESTADOS_GLOBAL:
        estado = ""
    tipo = (qp.get("tipo") or "").strip()
    clase = (qp.get("clase") or "").strip()
    if clase and clase not in _CLASES:
        clase = ""
    limite = _entero_query(qp.get("limite"), minimo=1)
    if limite is None:
        limite = _LIMITE_DEF
    limite = min(limite, _LIMITE_MAX)
    desplazamiento = _entero_query(qp.get("desplazamiento"), minimo=0) or 0
    cuerpo = await run_in_threadpool(
        _feed, marca, etapa, estado, tipo, clase, limite, desplazamiento
    )
    return JSONResponse(cuerpo)


def _feed(
    marca: str,
    etapa: str,
    estado: str,
    tipo: str,
    clase: str,
    limite: int,
    desplazamiento: int,
) -> dict:
    # UNA sola lectura del almacén de generaciones: alimenta el universo de runs (temas del
    # tablero TRABAJADOS por el pipeline), las métricas por run, la evidencia del pool (fix
    # "Saltada") y los items sueltos del feed.
    gens = generaciones.listar(limite=None, marca=marca or None)
    # UNA sola lectura del tablero (acotada a la marca): alimenta tanto las runs TRABAJADAS como
    # los temas FUTUROS (backlog aún sin trabajar) — ambos salen de este mismo listado.
    items_tablero = repos.listar_publicacion(marca=marca or None)
    trabajados = _temas_trabajados(gens)
    runs_items = _runs_del_pipeline(items_tablero, trabajados)
    ids_runs = {it.get("id", "") or "" for it in runs_items}
    met_por_run = _metricas_por_run(gens, ids_runs)
    pool_fusion = _marcas_con_pool(gens, _PREFIJO_POOL_FUSION)
    pool_editorial = _marcas_con_pool(gens, _PREFIJO_POOL_EDITORIAL)
    arte_ia_runs = _runs_con_arte_ia(gens)
    critica_ia_runs = _runs_con_critica_ia(gens)
    hashtags_runs = _runs_con_hashtags(gens)
    decisor_runs = _runs_con_decisor(gens)
    carrusel_runs = _runs_con_carrusel(gens)
    # Una sola lectura de las plataformas (acotada a la marca enfocada), agrupada por contenido
    # (evita N consultas). Solo se consultan piezas de las runs listadas, todas de esta marca.
    por_contenido: dict[str, list[dict]] = {}
    for plat in repos.listar_piezas_fila(marca=marca or None):
        por_contenido.setdefault(plat.get("publicacion_id", ""), []).append(plat)
    # Una sola lectura de las HISTORIAS (clusters) de estos temas (procedencia IA; evita N consultas).
    clusters = repos.clusters_por_contenidos([it.get("id", "") or "" for it in runs_items])
    pool_marca = _pool_por_marca(gens)
    todas = [
        _run_de(
            it,
            por_contenido.get(it.get("id", ""), []),
            cluster=clusters.get(it.get("id", "")),
            # La run suma sus generaciones correlacionadas + las etapas de POOL que su
            # detalle enlaza (solo temas del pipeline: al tablero el pool no le aplica).
            metricas=(
                _con_pool(
                    met_por_run.get(it.get("id", "")),
                    pool_marca.get(it.get("marca", "") or "", []),
                )
                if (it.get("origen") or "") == ORIGEN_PIPELINE
                else met_por_run.get(it.get("id", ""))
            ),
            pool_fusion=(it.get("marca", "") or "") in pool_fusion,
            pool_editorial=(it.get("marca", "") or "") in pool_editorial,
            hashtags_ia=(it.get("id", "") or "") in hashtags_runs,
            arte_ia=(it.get("id", "") or "") in arte_ia_runs,
            critica_ia=(it.get("id", "") or "") in critica_ia_runs,
            decisor_ia=(it.get("id", "") or "") in decisor_runs,
            carrusel_ia=(it.get("id", "") or "") in carrusel_runs,
        )
        for it in runs_items
    ]
    todas.extend(_actividad_suelta(gens, ids_runs, marca or None))
    # Mezcla cronológica (recientes primero) de runs + sueltos; empata por id (estable). Los
    # PASADOS/EN CURSO (con trabajo real) llevan `futuro=False`.
    todas.sort(key=lambda r: (r.get("creado", "") or "", r.get("id", "") or ""), reverse=True)
    for r in todas:
        r["futuro"] = False

    # Temas FUTUROS: backlog del tablero AÚN sin trabajar (sin generaciones de trabajo). Se
    # materializan como runs "en gris" (mismas etapas de `_ETAPAS`, todas pendientes/saltadas al derivarse de
    # un tema sin trabajo) con `futuro=True`. CAP anti-inundación: solo los `_futuros_max()` más
    # recientes (el backlog puede tener cientos); `futuros_total`/`futuros_mostrados` reportan el
    # recorte para que el front muestre "+N más".
    futuros_cand = _temas_futuros(items_tablero, trabajados)
    futuros_total = len(futuros_cand)
    cap = _futuros_max()
    if futuros_total > cap:
        _log.info(
            "Feed pipelines: %d temas futuros, recortados a %d (marca=%s)",
            futuros_total, cap, marca or "todas",
        )
    futuros = [
        {
            **_run_de(it, por_contenido.get(it.get("id", ""), [])),
            "futuro": True,
        }
        for it in futuros_cand[:cap]
    ]
    futuros_mostrados = len(futuros)

    # Los FUTUROS van DESPUÉS de los pasados/en curso (ya ordenados desc): el feed muestra primero
    # lo trabajado y al final el backlog en gris. Los filtros se aplican a AMBOS por igual
    # (preservan el orden, así que los futuros siguen al final).
    todas = todas + futuros
    if etapa:
        todas = [r for r in todas if r["clase"] == "run" and r["etapa_actual"] == etapa]
    if estado:
        todas = [r for r in todas if r["estado_global"] == estado]
    if tipo:
        todas = [r for r in todas if r["clase"] == "actividad" and r.get("tipo") == tipo]
    if clase:
        todas = [r for r in todas if r["clase"] == clase]
    total = len(todas)
    # SUMATORIO del universo filtrado (no solo la página): el coste agregado de lo listado. El
    # POOL (Fusionar/Priorizar) corre por LOTE de marca, así que es contexto por-TARJETA, no
    # coste por run: el agregado suma las métricas REALES de cada run (sin pool) y añade el coste
    # del pool UNA sola vez por marca con runs de pipeline en el filtro (si no, se inflaría ×runs).
    totales = dict(_METRICAS_CERO)
    marcas_con_runs: set[str] = set()
    for r in todas:
        es_run_pool = r["clase"] == "run" and (r.get("origen") or "") == ORIGEN_PIPELINE
        m = (met_por_run.get(r["id"]) if es_run_pool else r.get("metricas")) or {}
        totales["items"] += int(m.get("items") or 0)
        totales["tokens"] += int(m.get("tokens") or 0)
        totales["coste_usd"] = round(totales["coste_usd"] + (m.get("coste_usd") or 0.0), 6)
        totales["duration_ms"] += int(m.get("duration_ms") or 0)
        if es_run_pool:
            marcas_con_runs.add(r.get("marca", "") or "")
    for marca_run in marcas_con_runs:
        pool = _con_pool(None, pool_marca.get(marca_run, []))
        totales["items"] += int(pool.get("items") or 0)
        totales["tokens"] += int(pool.get("tokens") or 0)
        totales["coste_usd"] = round(totales["coste_usd"] + (pool.get("coste_usd") or 0.0), 6)
        totales["duration_ms"] += int(pool.get("duration_ms") or 0)
    pagina = todas[desplazamiento : desplazamiento + limite]
    return {
        "pipelines": pagina,
        "paginacion": envoltura_paginacion(total, limite, desplazamiento),
        # Suma de las métricas de TODOS los items que casan el filtro (tokens/coste/
        # duración; `items` = generaciones sumadas). La UI lo pinta junto al conteo.
        "totales": totales,
        # Backlog FUTURO (temas del tablero sin trabajar, `futuro=True` en `pipelines`):
        # `futuros_total` = todo el backlog de la marca; `futuros_mostrados` = los materializados
        # tras el cap. `futuros_total - futuros_mostrados` = el "+N más" que el front anuncia.
        "futuros_total": futuros_total,
        "futuros_mostrados": futuros_mostrados,
    }
