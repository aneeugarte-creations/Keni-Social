"""Paso de RE-SCORE: repuntúa periódicamente la ventana para que la frescura DECAIGA."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from .... import config, repos
from ....dominio import agrupar
from .. import _comun
from .._comun import (
    _log,
    _palabras_relevancia,
    _rendimiento_bonus,
    _rendimiento_top_lineas,
)


def paso_rescore(
    clusters_ventana: list[dict[str, Any]] | None = None, *, forzar: bool = False
) -> dict[str, Any]:
    """Re-puntúa periódicamente las historias `nuevo` de la ventana (score que ENVEJECE).

    DECISIÓN (score congelado): la FRESCURA (peso 0.25) solo se evaluaba al re-puntuar — es
    decir, cuando un item nuevo tocaba el cluster — y el score quedaba PERSISTIDO; el listado,
    la promoción CI y el GC ordenan/filtran por ese score obsoleto, así que una historia de
    hace 3 días podía outrankear a las nuevas para siempre. De las dos opciones (A: re-score
    periódico de la ventana en el barrido; B: persistir `score_base` sin frescura y computar
    `score_base + w·frescura(ultimo_visto, now())` en cada ORDER BY) elegimos la A: `puntuar`
    es pura, los clusters de la ventana ya se cargan por barrido, y el score persistido sigue
    siendo LA verdad única que leen UI/promoción/GC sin tocar esquema ni consultas.

    Throttle: como mucho una pasada por `_RESCORE_INTERVALO_SEG` (la frescura decae despacio).
    Solo escribe los scores que CAMBIAN (≥ 0.001), en una sola conexión. Best-effort.
    """
    ahora_mono = time.monotonic()
    if (
        not forzar
        and _comun._ultimo_rescore
        and (ahora_mono - _comun._ultimo_rescore) < _comun._RESCORE_INTERVALO_SEG
    ):
        return {"revisados": 0, "actualizados": 0}
    try:
        clusters = (
            clusters_ventana
            if clusters_ventana is not None
            else repos.clusters_recientes(config.cluster_ventana_h())
        )
    except Exception:  # noqa: BLE001 -- sin pool legible no se re-puntúa nada (no actualiza el throttle)
        _log.warning("recolectar_daemon: no se pudo leer la ventana para el re-score.", exc_info=True)
        return {"revisados": 0, "actualizados": 0}

    breaking_peso = config.cluster_breaking_peso()
    breaking_ventana_h = config.cluster_breaking_ventana_h()
    perfil_activo = config.alguna_marca_con_etapa(config.ENV_PRIORIZAR_PERFIL_IA)
    rendimiento_activo = config.rendimiento_ranking_activo()
    ahora = datetime.now(UTC)
    palabras_cache: dict[str, frozenset[str]] = {}
    pesos_cache: dict[str, Any] = {}  # perfil de pesos POR MARCA (modelo v2)
    eventos_cache: dict[str, list[dict[str, Any]]] = {}  # agenda POR MARCA (señal de evento)
    rend_cache: dict[str, tuple[set[str], dict[str, str], list[dict[str, Any]]]] = {}
    cambios: dict[str, dict[str, Any]] = {}
    revisados = 0
    for c in clusters:
        if (c.get("estado") or "nuevo") != "nuevo":
            continue  # usados/descartados ya no compiten en la priorización
        revisados += 1
        try:
            marca_c = str(c.get("marca") or "")
            if marca_c not in palabras_cache:
                palabras_cache[marca_c] = _palabras_relevancia(marca_c, perfil_activo)
                pesos_cache[marca_c] = config.score_pesos(marca_c)
                eventos_cache[marca_c] = _comun.eventos_proximos(marca_c)
            cl = dict(c)
            # `bonus_rendimiento` no se persiste: se recomputa si la señal está activa.
            if rendimiento_activo and marca_c:
                if marca_c not in rend_cache:
                    rend_cache[marca_c] = _rendimiento_top_lineas(marca_c)
                top_lineas, vert_id_a_nombre, vert_etiquetas = rend_cache[marca_c]
                if top_lineas:
                    cl["bonus_rendimiento"] = _rendimiento_bonus(
                        cl, top_lineas, vert_id_a_nombre, vert_etiquetas
                    )
            score, razon, desglose = agrupar.puntuar_detalle(
                cl, palabras_marca=palabras_cache[marca_c], eventos=eventos_cache[marca_c],
                ahora=ahora, pesos=pesos_cache[marca_c],
                breaking_peso=breaking_peso, breaking_ventana_h=breaking_ventana_h,
            )
            # Breaking/velocidad DECAEN con el reloj (la ventana se ancla en ahora): el
            # re-score persiste el flag vivo para que el umbral/los cupos no traten como
            # última hora una historia de ayer.
            breaking_vivo = int(desglose.get("breaking") or 0)
            vel_viva = float(desglose.get("velocidad") or 0.0)
            cambia_score = abs(score - float(c.get("score") or 0.0)) >= 0.001
            cambia_breaking = breaking_vivo != int(c.get("breaking") or 0)
            cambia_vel = abs(vel_viva - float(c.get("velocidad") or 0.0)) >= 0.001
            if cambia_score or cambia_breaking or cambia_vel:
                # El re-score refresca TAMBIÉN la explicación (si no, la razón persistida
                # explicaría un score viejo: p. ej. seguiría diciendo "reciente" días después).
                cambios[str(c["id"])] = {
                    "score": score, "score_razon": razon, "score_desglose": desglose,
                    "breaking": breaking_vivo, "velocidad": vel_viva,
                }
        except Exception:  # noqa: BLE001 -- una historia problemática no aborta la pasada
            _log.exception("recolectar_daemon: fallo al re-puntuar el cluster %s.", c.get("id"))

    actualizados = 0
    if cambios:
        try:
            actualizados = repos.actualizar_scores_clusters(cambios)
        except Exception:  # noqa: BLE001 -- persistir el re-score es best-effort
            _log.exception("recolectar_daemon: fallo al persistir el re-score de la ventana.")
            return {"revisados": revisados, "actualizados": 0}
    _comun._ultimo_rescore = ahora_mono
    if actualizados:
        _log.info("recolectar_daemon: re-score de la ventana: %d historia(s) repuntuadas.", actualizados)
    return {"revisados": revisados, "actualizados": actualizados}
