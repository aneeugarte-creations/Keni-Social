"""Etapa de SUGERIR HASHTAGS del pipeline (tras Redactar, antes de Ilustrar).

El pipeline redacta el copy SIN hashtags (el copy unificado nunca los lleva). Esta etapa, para
cada borrador recién redactado que aún no tiene hashtags (`falta_hashtags`), ENCOLA una sugerencia
`claude -p` READ-ONLY (`dominio.sugerir_hashtags`) que elige los más relevantes de la biblioteca de
la marca y los guarda en `pieza.hashtags_sugeridos`. NO toca el copy: el feed mostrará la
sugerencia en gris para que un humano la acepte/rechace de un clic.

REGLAS DE SELECCIÓN (`piezas_para_sugerir_hashtags`, pura):
  - Estado `borrador` y con copy ya redactado (`contenido` no vacío).
  - SIN hashtags en el copy (`falta_hashtags`): si ya los lleva, no se sugiere nada.
  - La red de la marca usa hashtags (`cantidad_sugerida > 0`; p. ej. YouTube no).
  - Aún sin sugerencia calculada (`hashtags_sugeridos` vacío): idempotencia barata por tick.

Gateada por `KENI_PIPELINE_SUGERIR_HASHTAGS` (def ON) bajo el maestro `KENI_MAQUINA`.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .. import config, hashtags_biblioteca, repos
from ..dominio import sugerir_hashtags as dom_sugerir

__all__ = ["ejecutar_sugerir_hashtags", "piezas_para_sugerir_hashtags"]

_log = logging.getLogger("keni_consola.pipeline_contenido")

# Cap de sugerencias encoladas por barrido: acota el trabajo de un tick (el daemon barre cada
# pocos segundos, así que un backlog se drena en minutos igualmente).
_MAX_POR_BARRIDO = 50


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


def piezas_para_sugerir_hashtags(
    pubs: list[dict[str, Any]], *, maximo: int = _MAX_POR_BARRIDO
) -> list[dict[str, Any]]:
    """Filtra los borradores que necesitan sugerencia de hashtags (PURA; reglas en el módulo)."""
    elegidas: list[dict[str, Any]] = []
    for pub in pubs:
        if pub.get("estado") != "borrador":
            continue
        if not str(pub.get("contenido") or "").strip():
            continue
        if not dom_sugerir.falta_hashtags(pub):
            continue
        if _ya_tiene_sugerencia(pub):
            continue
        if hashtags_biblioteca.cantidad_sugerida(
            str(pub.get("marca") or ""), str(pub.get("red") or "")
        ) <= 0:
            continue
        elegidas.append(pub)
        if len(elegidas) >= maximo:
            break
    return elegidas


def ejecutar_sugerir_hashtags() -> list[dict[str, Any]]:
    """Etapa de Sugerir hashtags del barrido (tras Redactar): encola sugerencias para los
    borradores sin hashtags. Gateada por `KENI_PIPELINE_SUGERIR_HASHTAGS` + máquina.

    Best-effort: un fallo por pieza se loguea y se sigue. Devuelve las generaciones encoladas.
    """
    if not config.gate_maquina(config.sugerir_hashtags_activo)():
        return []
    try:
        pubs = repos.listar_piezas(estado="borrador")
    except Exception:  # noqa: BLE001 -- sin tablero, la etapa no actúa
        _log.exception("pipeline: no se pudieron leer los borradores para sugerir hashtags.")
        return []
    encoladas: list[dict[str, Any]] = []
    for pub in piezas_para_sugerir_hashtags(pubs):
        try:
            gen = dom_sugerir.lanzar_para_publicacion(pub["id"])
        except Exception:  # noqa: BLE001 -- una pieza que falla no aborta la etapa
            _log.exception(
                "pipeline: falló la sugerencia de hashtags de la pieza %s (marca %s).",
                pub.get("id", ""), pub.get("marca", ""),
            )
            continue
        if gen:
            encoladas.append(gen)
    return encoladas
