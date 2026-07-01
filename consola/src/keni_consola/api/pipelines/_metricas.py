"""PIPELINES · métricas por run + evidencia del POOL (Fusionar/Encaje) y del arte IA.

Agrega las generaciones REALES correlacionadas a cada run (items/tokens/coste/duración) y
deriva, de las mismas generaciones, qué marcas corrieron el pool y qué runs tienen arte IA —
señales que el motor de etapas usa para no pintar "Saltada" una fase con output. Compartido
por `feed` y `detalle`.
"""

from __future__ import annotations

from ... import actividad
from ...pipeline_contenido import TIPO_ACTIVIDAD
from ..actividad import _es_marcador_pipeline
from ._comun import (
    _METRICAS_CERO,
    _PREFIJO_POOL_EDITORIAL,
    _PREFIJO_POOL_FUSION,
    _TIPOS_ACCION_SUELTA,
)


def _sumar_gen(acc: dict, g: dict) -> None:
    """Acumula en `acc` las métricas de UNA generación (normalización del dominio `actividad`)."""
    m = actividad.normalizar_generacion(g)["metricas"]
    acc["items"] += 1
    acc["tokens"] += m["tokens"] or 0
    acc["coste_usd"] = round(acc["coste_usd"] + (m["coste_usd"] or 0.0), 6)
    acc["duration_ms"] += m["duration_ms"] or 0


def _metricas_por_run(gens: list[dict], ids_runs: set[str]) -> dict[str, dict]:
    """Suma las métricas de las generaciones REALES (no marcadores) por run.

    Devuelve `publicacion_id -> {items, tokens, coste_usd, duration_ms}` solo para los ids de
    `ids_runs`. La correlación generación→run usa DOS vías (la unión, dedup por generación):
      - el `publicacion_id` del propio registro (lo sella `dominio.generar.lanzar`), y
      - los MARCADORES de etapa (`gen_id` → `publicacion_id`): los registros previos a sellar
        `publicacion_id` en el lanzamiento solo están atados por su marcador; sin esta vía,
        sus runs salían a CERO en el feed.
    La normalización de métricas es la del dominio `actividad` (la misma del feed):
    tokens_in+tokens_out -> tokens, total_cost_usd -> coste_usd. Los marcadores de etapa
    (sin coste) no suman.
    """
    # gen_id -> publicacion_id según los marcadores de etapa (CD/verificación/ARTE).
    cid_por_gen: dict[str, str] = {}
    for g in gens:
        if not _es_marcador_pipeline(g):
            continue
        cid = g.get("publicacion_id") or ""
        gid = g.get("gen_id") or ""
        if cid in ids_runs and gid:
            cid_por_gen.setdefault(gid, cid)
    out: dict[str, dict] = {}
    for g in gens:
        if _es_marcador_pipeline(g):
            continue
        # Las acciones manuales sobre el post (convertir en carrusel) NO suman a la run: salen
        # como su propia fila suelta en el feed; sumarlas aquí las contaría dos veces.
        if (g.get("tipo") or "") in _TIPOS_ACCION_SUELTA:
            continue
        cid = (g.get("publicacion_id") or "") or cid_por_gen.get(g.get("id") or "", "")
        if cid not in ids_runs:
            continue
        _sumar_gen(out.setdefault(cid, dict(_METRICAS_CERO)), g)
    return out


def _pool_por_marca(gens: list[dict]) -> dict[str, list[dict]]:
    """Por marca, las generaciones de POOL que el detalle ENLAZA en Fusionar/Priorizar: la
    "Fusionar historias" más reciente y el "Priorizar historias" más reciente.

    Es la MISMA selección que `_generacion_pool_de_marca` (recientes por fecha_fin/inicio),
    pero en lote para la lista. Las métricas de la run suman ESTAS generaciones (las etapas
    que su detalle muestra), de modo que la tarjeta cuadra con el agregado de sus etapas.
    OJO: el pool corre por LOTE de marca, así que su coste aparece en cada run del lote
    (es contexto por-tarjeta); el coste GLOBAL sin duplicar son los KPIs de agregados.
    """
    mejores: dict[tuple[str, str], dict] = {}
    for g in gens:
        if (g.get("tipo") or "") != "pipeline":
            continue
        etiqueta = g.get("etiqueta", "") or ""
        for prefijo in (_PREFIJO_POOL_FUSION, _PREFIJO_POOL_EDITORIAL):
            if not etiqueta.startswith(prefijo):
                continue
            clave = (g.get("marca", "") or "", prefijo)
            fecha = g.get("fecha_fin") or g.get("fecha_inicio") or ""
            previa = mejores.get(clave)
            fecha_previa = (previa or {}).get("fecha_fin") or (previa or {}).get("fecha_inicio") or ""
            if previa is None or fecha >= fecha_previa:
                mejores[clave] = g
    out: dict[str, list[dict]] = {}
    for (marca, _), g in mejores.items():
        out.setdefault(marca, []).append(g)
    return out


def _con_pool(metricas: dict | None, pool: list[dict]) -> dict:
    """Métricas de la run + las de sus etapas de POOL (Fusionar/Encaje enlazadas). Copia nueva."""
    acc = dict(metricas or _METRICAS_CERO)
    for g in pool:
        _sumar_gen(acc, g)
    return acc


def _runs_con_arte_ia(gens: list[dict]) -> set[str]:
    """Ids de contenido con EVIDENCIA de arte GENERADO por IA (auto-arte).

    El auto-arte deja dos trazas correlacionadas al tema: el MARCADOR de etapa
    (`tipo='pipeline_etapa'`, etiqueta "ILUSTRAR · …") y la generación con el prompt real
    (`tipo='pipeline'`, etiqueta "Arte — …"). Cualquiera de las dos vale. La etapa Ilustrar se
    deriva de ESTA evidencia, no de si la pieza tiene imagen (la foto de la nota de una
    fuente propia no es arte IA).
    """
    out: set[str] = set()
    for g in gens:
        cid = g.get("publicacion_id") or ""
        if not cid:
            continue
        etiqueta = (g.get("etiqueta", "") or "")
        tipo = g.get("tipo") or ""
        if (tipo == TIPO_ACTIVIDAD and etiqueta.startswith("ILUSTRAR")) or (
            tipo == "pipeline" and etiqueta.startswith("Arte")
        ):
            out.add(cid)
    return out


def _runs_con_hashtags(gens: list[dict]) -> set[str]:
    """Ids de contenido con EVIDENCIA de que la etapa Sugerir hashtags corrió.

    La sugerencia se lanza por CONTENIDO (`tipo='sugerir-hashtags'`, una sola por tema) y sella el
    `publicacion_id` del tema (= id de la run). Su presencia es la evidencia de que la etapa corrió,
    igual que el arte IA lo es para Ilustrar; la etapa Sugerir hashtags se deriva de ESTA evidencia
    (no la corre cuando el copy ya traía hashtags, así que sin evidencia se pinta "saltada").
    """
    return {
        cid
        for g in gens
        if (g.get("tipo") or "") == "sugerir-hashtags" and (cid := g.get("publicacion_id") or "")
    }


def _runs_con_critica_ia(gens: list[dict]) -> set[str]:
    """Ids de contenido con EVIDENCIA de que la Crítica IA corrió (job `tipo='critica-ia'`).

    El crítico con visión se lanza POR PIEZA en la cadena de aprobación; su generación sella el
    `publicacion_id` del tema padre (= id de la run). Su presencia es la evidencia de que la etapa
    Crítica corrió, igual que el arte IA lo es para Ilustrar.
    """
    return {
        cid
        for g in gens
        if (g.get("tipo") or "") == "critica-ia" and (cid := g.get("publicacion_id") or "")
    }


def _runs_con_decisor(gens: list[dict]) -> set[str]:
    """Ids de contenido con EVIDENCIA de que el Decisor de formato corrió (job `tipo='decisor'`).

    El Decisor se lanza POR TEMA, justo antes de Redactar, y sella el `publicacion_id` del tema
    (= id de la run). Su presencia es la evidencia de que la etapa corrió, igual que el arte IA
    lo es para Ilustrar.
    """
    return {
        cid
        for g in gens
        if (g.get("tipo") or "") == "decisor" and (cid := g.get("publicacion_id") or "")
    }


def _marcas_con_pool(gens: list[dict], prefijo: str) -> set[str]:
    """Marcas con alguna generación de POOL (tipo `pipeline`, etiqueta con `prefijo`).

    Es la evidencia de que la IA del pool (Fusionar / Priorizar, por lote de marca)
    CORRIÓ: la usa la derivación de etapas para no pintar "Saltada" una fase con output.
    """
    return {
        (g.get("marca", "") or "")
        for g in gens
        if (g.get("tipo") or "") == "pipeline"
        and (g.get("etiqueta", "") or "").startswith(prefijo)
    }
