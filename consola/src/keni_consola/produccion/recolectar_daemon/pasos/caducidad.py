"""Paso de CADUCIDAD (TTL): caduca el pool por edad y purga lo caducado tras la retención."""

from __future__ import annotations

import time
from typing import Any

from .... import config, latidos, repos
from .. import _comun
from .._comun import _log

# Nombre con el que el paso deja su latido/historial (`daemon_latidos`/`daemon_barridos`):
# aparece como una fila más del panel Sistema, sin hilo propio (corre dentro del barrido de
# ingesta). Registrado en la clasificación de `latidos` (etiqueta/descripción/clase).
DAEMON_CADUCIDAD = "caducidad"


def _sin_novedad() -> dict[str, Any]:
    """Resumen a ceros del paso (throttle o pool ya limpio)."""
    return {
        "caducadas": 0, "purgadas": 0, "items_purgados": 0,
        "usados_purgados": 0, "items_usados": 0,
    }


def _resumen_caducidad(res: dict[str, Any]) -> str:
    """Resumen corto del barrido de caducidad para el historial (`daemon_barridos`)."""
    partes = []
    if res.get("caducadas"):
        partes.append(f"{res['caducadas']} historia(s) caducada(s)")
    if res.get("items_purgados"):
        partes.append(f"{res['items_purgados']} item(s) purgado(s)")
    if res.get("usados_purgados") or res.get("items_usados"):
        partes.append(
            f"{res.get('usados_purgados', 0)} usada(s) huérfana(s) "
            f"({res.get('items_usados', 0)} item(s))"
        )
    return " · ".join(partes) if partes else "sin novedad"


def paso_caducidad(*, forzar: bool = False) -> dict[str, Any]:
    """Caduca el pool por edad (TTL) y purga lo caducado tras la retención. THROTTLED, OBSERVADO.

    El feed es perecedero POR DISEÑO: una historia `nuevo` sin actividad en `KENI_NOTICIAS_TTL_H`
    (def 72h, la vida de la frescura del score) caduca sola y se BORRA (sale del panel, del
    priorización y de la promoción; sus items quedan como lápida `descartado` anti-reaparición; lo
    usado con publicación viva nunca caduca), y las lápidas/sueltos viejos se purgan del todo tras
    `KENI_NOTICIAS_RETENCION_H` (def 14 días). Además purga lo USADO HUÉRFANO (historias `usado`
    cuya publicación ya no existe, tras `KENI_NOTICIAS_USADOS_RETENCION_DIAS`; best-effort, ver
    `repos.purgar_usados_huerfanos`). Corre DENTRO del barrido de recolección: donde se construye
    el feed, se limpia el feed (no depende de que el GC por relevancia esté encendido).

    OBSERVABILIDAD: es el único freno siempre-activo del pool y su fallo era una línea de log
    tragada. Cada pasada REAL (no throttled) deja su latido + fila de historial como el
    pseudo-daemon `caducidad` (`latidos.barrido`: ok/error + conteos + timestamp), visible en el
    panel Sistema junto al resto de daemons. La lógica del borrado vive en
    `db_noticias.caducar_pool`/`purgar_usados_huerfanos`; aquí throttle, latido y log.
    """
    ahora_mono = time.monotonic()
    if (
        not forzar
        and _comun._ultima_caducidad
        and (ahora_mono - _comun._ultima_caducidad) < _comun._CADUCIDAD_INTERVALO_SEG
    ):
        return _sin_novedad()
    inicio = time.monotonic()
    try:
        resumen: dict[str, Any] = dict(repos.caducar_pool(
            ttl_horas=config.noticias_ttl_horas(),
            retencion_horas=config.noticias_retencion_horas(),
        ))
    except Exception as e:  # noqa: BLE001 -- latir el error y re-lanzar (el bucle ya lo loguea)
        latidos.barrido(
            DAEMON_CADUCIDAD, ok=False,
            intervalo_seg=_comun._CADUCIDAD_INTERVALO_SEG,
            tick_seg=2 * _comun._CADUCIDAD_INTERVALO_SEG,
            duracion_ms=int((time.monotonic() - inicio) * 1000),
            error=str(e),
        )
        raise
    _comun._ultima_caducidad = ahora_mono
    # Lo USADO cuyo tema ya no existe (publicación borrada): best-effort APARTE del TTL —un
    # fallo aquí no invalida la caducidad ya hecha— pero dentro del mismo latido/resumen.
    resumen.setdefault("usados_purgados", 0)
    resumen.setdefault("items_usados", 0)
    try:
        huerfanos = repos.purgar_usados_huerfanos(config.noticias_usados_retencion_dias())
        resumen["usados_purgados"] = huerfanos.get("historias", 0)
        resumen["items_usados"] = huerfanos.get("items", 0)
    except Exception:  # noqa: BLE001 -- aditivo: nunca invalida la caducidad del pool
        _log.warning(
            "recolectar_daemon: fallo la purga de historias usadas huérfanas.", exc_info=True
        )
    latidos.barrido(
        DAEMON_CADUCIDAD, ok=True,
        intervalo_seg=_comun._CADUCIDAD_INTERVALO_SEG,
        # tick 2x el throttle: el umbral de "atrasado" del panel (~2 ticks + margen) tolera que
        # la pasada real llegue con el barrido de ingesta siguiente, no exactamente cada 15 min.
        tick_seg=2 * _comun._CADUCIDAD_INTERVALO_SEG,
        duracion_ms=int((time.monotonic() - inicio) * 1000),
        resumen=_resumen_caducidad(resumen),
    )
    if any(resumen.values()):
        _log.info(
            "recolectar_daemon: caducidad del pool: %d historia(s) caducada(s), %d purgada(s), "
            "%d item(s) purgado(s); usados huérfanos: %d historia(s), %d item(s).",
            resumen["caducadas"], resumen["purgadas"], resumen["items_purgados"],
            resumen["usados_purgados"], resumen["items_usados"],
        )
    return resumen
