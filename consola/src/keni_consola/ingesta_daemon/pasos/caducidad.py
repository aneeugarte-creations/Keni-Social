"""Paso de CADUCIDAD (TTL): caduca el pool por edad y purga lo caducado tras la retención."""

from __future__ import annotations

import time
from typing import Any

from ... import config, repos
from .. import _comun
from .._comun import _log


def paso_caducidad(*, forzar: bool = False) -> dict[str, Any]:
    """Caduca el pool por edad (TTL) y purga lo caducado tras la retención. Best-effort, THROTTLED.

    El feed es perecedero POR DISEÑO: una historia `nuevo` sin actividad en `KENI_NOTICIAS_TTL_H`
    (def 72h, la vida de la frescura del score) caduca sola a `descartado` (sale del panel, del
    priorización y de la promoción; lo usado nunca caduca), y lo caducado sin usar se borra tras
    `KENI_NOTICIAS_RETENCION_H` (def 14 días). Corre DENTRO del barrido de recolección: donde se
    construye el feed, se limpia el feed (no depende de que el GC por relevancia esté encendido).
    La lógica vive en `db_noticias.caducar_pool`; aquí solo el throttle y el log.
    """
    ahora_mono = time.monotonic()
    if (
        not forzar
        and _comun._ultima_caducidad
        and (ahora_mono - _comun._ultima_caducidad) < _comun._CADUCIDAD_INTERVALO_SEG
    ):
        return {"caducadas": 0, "purgadas": 0, "items_purgados": 0}
    resumen = repos.caducar_pool(
        ttl_horas=config.noticias_ttl_horas(),
        retencion_horas=config.noticias_retencion_horas(),
    )
    _comun._ultima_caducidad = ahora_mono
    if resumen["caducadas"] or resumen["purgadas"] or resumen["items_purgados"]:
        _log.info(
            "ingesta_daemon: caducidad del pool: %d historia(s) caducada(s), %d purgada(s), "
            "%d item(s) purgado(s).",
            resumen["caducadas"], resumen["purgadas"], resumen["items_purgados"],
        )
    return resumen
