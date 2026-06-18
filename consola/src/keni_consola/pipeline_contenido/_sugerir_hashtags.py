"""Etapa de SUGERIR HASHTAGS del pipeline (tras Redactar, antes de Ilustrar).

El pipeline redacta el copy SIN hashtags (el copy unificado nunca los lleva). Esta etapa trabaja
por CONTENIDO, no por pieza: los hashtags son GEMELOS en todas las redes de un contenido, así que
agrupa las piezas borrador por `publicacion_id` y, para cada contenido al que le faltan hashtags,
ENCOLA UNA sola sugerencia `claude -p` READ-ONLY (`dominio.sugerir_hashtags`). El post-procesado
arma la lista (fijos de la marca + temáticos de la IA + relleno) y la escribe IDÉNTICA en todas las
piezas del contenido. NO toca el copy: el feed la muestra en gris para aceptar/rechazar de un clic.

REGLAS DE SELECCIÓN (`contenidos_para_sugerir_hashtags`, pura):
  - Agrupa las piezas `borrador` con copy ya redactado (`contenido` no vacío) por `publicacion_id`.
  - El contenido entra si a alguna de sus piezas le FALTAN hashtags (`falta_hashtags`) y ninguna
    tiene ya una sugerencia calculada (idempotencia barata por tick).
  - La marca usa hashtags en alguna de las redes del contenido (`cantidad_contenido > 0`).

Gateada por `KENI_PIPELINE_SUGERIR_HASHTAGS` (def ON) bajo el maestro `KENI_MAQUINA`.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .. import config, repos
from ..dominio import sugerir_hashtags as dom_sugerir

__all__ = ["ejecutar_sugerir_hashtags", "contenidos_para_sugerir_hashtags"]

_log = logging.getLogger("keni_consola.pipeline_contenido")

# Cap de contenidos encolados por barrido: acota el trabajo de un tick (el daemon barre cada pocos
# segundos, así que un backlog se drena en minutos igualmente).
_MAX_POR_BARRIDO = 50

# Estados de pieza donde la sugerencia aplica (borrador + en revisión). Fuente única en el dominio:
# las piezas completas de nacimiento (video/carrusel) avanzan solas a revisión antes de que el job
# async termine, así que el barrido también debe mirarlas ahí.
_ESTADOS_SUGERIBLES = dom_sugerir.ESTADOS_SUGERIBLES


def _ya_tiene_sugerencia(pub: dict[str, Any]) -> bool:
    """True si la pieza ya tiene una sugerencia persistida en `hashtags_sugeridos`."""
    crudo = pub.get("hashtags_sugeridos")
    if isinstance(crudo, (list, tuple)):
        return bool(crudo)
    if isinstance(crudo, str) and crudo.strip():
        try:
            datos = json.loads(crudo)
        except (ValueError, TypeError):
            return False
        return isinstance(datos, list) and bool(datos)
    return False


def contenidos_para_sugerir_hashtags(
    pubs: list[dict[str, Any]], *, maximo: int = _MAX_POR_BARRIDO
) -> list[tuple[str, list[dict[str, Any]]]]:
    """Agrupa por contenido las piezas SUGERIBLES (borrador o en revisión) y devuelve
    `(publicacion_id, twins)` de las que necesitan sugerencia de hashtags (PURA; reglas en el
    módulo). Preserva el orden de aparición del primero."""
    por_contenido: dict[str, list[dict[str, Any]]] = {}
    orden: list[str] = []
    for pub in pubs:
        if pub.get("estado") not in _ESTADOS_SUGERIBLES or not str(pub.get("contenido") or "").strip():
            continue
        pid = str(pub.get("publicacion_id") or "")
        if not pid:
            continue
        if pid not in por_contenido:
            por_contenido[pid] = []
            orden.append(pid)
        por_contenido[pid].append(pub)

    elegidos: list[tuple[str, list[dict[str, Any]]]] = []
    for pid in orden:
        twins = por_contenido[pid]
        if not any(dom_sugerir.falta_hashtags(t) for t in twins):
            continue
        if any(_ya_tiene_sugerencia(t) for t in twins):
            continue
        marca = str(twins[0].get("marca") or "")
        redes = [str(t.get("red") or "") for t in twins if t.get("red")]
        if dom_sugerir.cantidad_contenido(marca, redes) <= 0:
            continue
        elegidos.append((pid, twins))
        if len(elegidos) >= maximo:
            break
    return elegidos


def ejecutar_sugerir_hashtags() -> list[dict[str, Any]]:
    """Etapa de Sugerir hashtags del barrido (tras Redactar): encola UNA sugerencia por contenido
    al que le faltan hashtags. Gateada por `KENI_PIPELINE_SUGERIR_HASHTAGS` + máquina.

    Cubre las piezas en `_ESTADOS_SUGERIBLES` (borrador + en revisión), no solo borradores: las
    piezas que avanzan solas a revisión (video/carrusel completos de nacimiento) seguirían sin
    sugerencia si solo barriéramos borradores.

    Best-effort: un fallo por contenido se loguea y se sigue. Devuelve las generaciones encoladas.
    """
    if not config.gate_maquina(config.sugerir_hashtags_activo)():
        return []
    try:
        pubs: list[dict[str, Any]] = []
        for estado in _ESTADOS_SUGERIBLES:
            pubs.extend(repos.listar_piezas(estado=estado))
    except Exception:  # noqa: BLE001 -- sin tablero, la etapa no actúa
        _log.exception("pipeline: no se pudieron leer las piezas para sugerir hashtags.")
        return []
    encoladas: list[dict[str, Any]] = []
    for pid, twins in contenidos_para_sugerir_hashtags(pubs):
        try:
            gen = dom_sugerir.lanzar_para_contenido(pid, twins)
        except Exception:  # noqa: BLE001 -- un contenido que falla no aborta la etapa
            _log.exception(
                "pipeline: falló la sugerencia de hashtags del contenido %s (marca %s).",
                pid, (twins[0].get("marca", "") if twins else ""),
            )
            continue
        if gen:
            encoladas.append(gen)
    return encoladas
