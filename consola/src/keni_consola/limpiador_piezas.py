"""Purga de borradores MUERTOS del tablero: politica de retencion a N dias (def 90).

POLITICA (aprobada por el dueño): un tema auto-generado (pipeline/portal/historia) que NINGUN
humano toco jamas se borra pasados `KENI_PIEZAS_PURGA_DIAS` dias (0 = apagada). Todo lo
publicado o con cualquier huella humana (responsable, comentario, edicion de copy, aprobacion,
etiqueta humana, avance de estado…) se conserva PARA SIEMPRE. El criterio exacto de "muerto" y
el borrado (cascada canonica de `borrar_publicacion` + FKs) viven en `db_purga_piezas`; los
objetos de media que queden sin dueño los recoge el GC de media (`KENI_MEDIA_GC`).

CADENCIA: no tiene hilo propio; corre como paso del limpiador de generaciones (el daemon de
mantenimiento SIEMPRE activo, cada `KENI_LIMPIADOR_INTERVALO_MIN`). El gate es el propio valor
de la retencion (`dias <= 0` = no-op), leido EN VIVO en cada barrido (aplica sin reiniciar).
Cada ejecucion ACTIVA registra su propio latido/historial (`daemon_barridos`, daemon
`limpiador_piezas`), como el resto de barridos de mantenimiento.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from . import config, db_purga_piezas, latidos

_log = logging.getLogger("keni_consola.limpiador_piezas")

# Nombre del daemon en latidos/historial (panel de Sistema).
DAEMON = "limpiador_piezas"

# Tope de borrados por barrido: drena un backlog grande en varias pasadas (cadencia del
# limpiador) en vez de una rafaga de DELETEs sobre la BD viva.
LOTE_POR_BARRIDO = 200


def resumen_purga(res: dict[str, Any]) -> str:
    """Resumen corto de una purga para el historial: total y desglose por marca."""
    purgadas = int((res or {}).get("purgadas", 0) or 0)
    if not purgadas:
        return "sin novedad"
    por_marca = (res or {}).get("por_marca") or {}
    detalle = ", ".join(f"{marca}: {n}" for marca, n in sorted(por_marca.items()))
    return f"{purgadas} borrador(es) muerto(s) purgado(s) ({detalle})"


def ejecutar_purga() -> dict[str, Any]:
    """Una pasada de purga con la retencion VIVA. Devuelve `{activo, purgadas, por_marca, corte}`.

    Con la purga apagada (`piezas_purga_dias() <= 0`) es un no-op silencioso (ni borra ni
    registra latido, igual que un daemon gateado OFF). Activa, borra el lote y deja una fila en
    el historial (`daemon_barridos`) con el desglose por marca; un fallo registra el barrido en
    error y RE-LANZA (el llamador del limpiador lo captura como best-effort).
    """
    dias = config.piezas_purga_dias()
    if dias <= 0:
        return {"activo": False, "purgadas": 0, "por_marca": {}, "corte": ""}
    intervalo = float(config.limpiador_intervalo_seg())
    t0 = time.monotonic()
    try:
        res = db_purga_piezas.purgar_borradores_muertos(dias, limite=LOTE_POR_BARRIDO)
    except Exception as e:
        latidos.barrido(
            DAEMON, ok=False, intervalo_seg=intervalo, tick_seg=60.0,
            duracion_ms=int((time.monotonic() - t0) * 1000), error=repr(e),
        )
        raise
    if res.get("purgadas"):
        _log.info(
            "Purga de borradores muertos: %s (retencion %d dias).", resumen_purga(res), dias
        )
    latidos.barrido(
        DAEMON, ok=True, intervalo_seg=intervalo, tick_seg=60.0,
        duracion_ms=int((time.monotonic() - t0) * 1000), resumen=resumen_purga(res),
    )
    return {"activo": True, **res}
