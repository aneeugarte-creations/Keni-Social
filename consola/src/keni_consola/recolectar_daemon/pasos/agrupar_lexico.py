"""Paso de MERGE LÉXICO tardío: fusiona historias de la ventana que el léxico descubre iguales."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import keni_consola.recolectar_daemon as _pkg

from ... import config, repos
from ...dominio import agrupar
from .. import _comun
from .._comun import _log


def paso_agrupar_lexico(
    clusters_ventana: list[dict[str, Any]] | None = None, *, forzar: bool = False
) -> dict[str, Any]:
    """Funde historias de la ventana que el LÉXICO descubre iguales TARDE. Best-effort.

    La asignación incremental compara cada item solo contra los clusters que existían en su
    momento: dos historias del mismo evento pueden nacer por separado (orden de llegada,
    traducción tardía) y quedarse duplicadas en el pool. Esto agrupa los clusters `nuevo`
    sin promover cuyo título (o traducción) casa con ratio >= `KENI_CLUSTER_UMBRAL_MERGE`
    (0.86, más estricto que el de asignación; 0 apaga) y los fusiona con `_fusionar_grupo`
    (anti-TOCTOU incluido). SIN IA: complementa el fusionar semántico de Haiku (gateado), no
    la sustituye. Throttled a una pasada por `_AGRUPAR_LEXICO_INTERVALO_SEG`.
    """
    umbral = config.cluster_umbral_merge()
    if umbral <= 0:
        return {"grupos": 0, "fusionadas": 0}
    ahora_mono = time.monotonic()
    if (
        not forzar
        and _comun._ultimo_agrupar_lexico
        and (ahora_mono - _comun._ultimo_agrupar_lexico) < _comun._AGRUPAR_LEXICO_INTERVALO_SEG
    ):
        return {"grupos": 0, "fusionadas": 0}
    try:
        clusters = (
            clusters_ventana
            if clusters_ventana is not None
            else repos.clusters_recientes(config.cluster_ventana_h())
        )
    except Exception:  # noqa: BLE001 -- sin pool legible no se fusiona nada (no toca el throttle)
        _log.warning("recolectar_daemon: no se pudo leer la ventana para el merge léxico.", exc_info=True)
        return {"grupos": 0, "fusionadas": 0}

    # Solo historias del pool sin promover: lo usado/descartado no se toca (y _fusionar_grupo
    # re-verifica anti-TOCTOU por si el pipeline promueve entre la lectura y fusionar).
    candidatos = [
        c for c in clusters
        if (c.get("estado") or "nuevo") == "nuevo" and not (c.get("publicacion_id") or "")
    ]
    grupos = agrupar.grupos_lexicos(candidatos, umbral=umbral)
    if not grupos:
        _comun._ultimo_agrupar_lexico = ahora_mono
        return {"grupos": 0, "fusionadas": 0}

    pesos = config.score_pesos()
    breaking_peso = config.cluster_breaking_peso()
    breaking_ventana_h = config.cluster_breaking_ventana_h()
    fuentes_baja = config.fuentes_baja_confianza()
    perfil_activo = config.priorizar_perfil_activo()
    ahora = datetime.now(UTC)
    por_id = {str(c["id"]): c for c in candidatos}
    grupos_total = 0
    fusionadas_total = 0
    for grupo in grupos:
        try:
            if _pkg._fusionar_grupo(
                grupo, por_id, pesos=pesos, breaking_peso=breaking_peso,
                breaking_ventana_h=breaking_ventana_h, fuentes_baja=fuentes_baja,
                perfil_activo=perfil_activo, ahora=ahora,
            ):
                grupos_total += 1
                fusionadas_total += len(grupo) - 1
        except Exception:  # noqa: BLE001 -- un fusionado problemático no aborta la pasada
            _log.exception("recolectar_daemon: fallo al fusionar un grupo léxico de historias.")
    _comun._ultimo_agrupar_lexico = ahora_mono
    if grupos_total:
        _log.info(
            "recolectar_daemon: merge léxico: %d grupo(s), %d historia(s) absorbida(s).",
            grupos_total, fusionadas_total,
        )
    return {"grupos": grupos_total, "fusionadas": fusionadas_total}
