"""Programador de publicaciones (#9, Fase 3): prepara las piezas vencidas EN DRY-RUN.

Que hace y, sobre todo, que NO hace
===================================
Una pieza APROBADA puede PROGRAMARSE para una fecha-hora (via `api/aprobacion.py`):
pasa a estado `programado` con su `fecha_programada`. Este modulo es el reloj del
servidor: un hilo demonio que, cuando una pieza programada VENCE (su
`fecha_programada <= ahora`), la MARCA como "lista para publicar" estampando
`preparado_en`. Corre 24-7 en el servidor compartido (ADR 0001), sin la maquina de
nadie encendida.

GATING (frontera del producto, CRITICO): el posteo REAL a Meta/TikTok depende de #5
(Meta App Review) y #8, que estan BLOQUEADOS/externos. Por eso el programador **NO
publica en ninguna plataforma**: solo PREPARA (dry-run) y deja la pieza en `programado`
con `preparado_en` puesto. La pieza NUNCA pasa sola a `publicado`: "el humano aprueba;
el sistema no publica solo". Cuando #5/#8 aterricen, el posteo real se engancha aqui
(en `_preparar`), sin cambiar el resto del flujo.

El calculo de "que esta vencido" es una funcion PURA y DETERMINISTA (`piezas_vencidas`)
que recibe `ahora` inyectado, para poder testearla sin reloj real ni hilo. El hilo
(`iniciar_programador`) vive en el servidor real (`__main__`), NO en `crear_app`: los
tests no lo arrancan (igual que la captura comercial). Cada operacion abre/cierra su
propia conexion, asi que correr en un hilo aparte es seguro.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime
from typing import Any

from . import repos
from .estados import ESTADO_PROGRAMADO

_log = logging.getLogger("keni_consola.programador")

# Cadencia por defecto del barrido del programador (segundos). Un minuto basta: la
# granularidad de las fechas programadas es el minuto.
INTERVALO_SEGUNDOS_DEF = 60.0


def _parsear_fecha(valor: str) -> datetime | None:
    """Parsea una `fecha_programada` ISO ('YYYY-MM-DDTHH:MM' o con segundos); None si no es valida."""
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor)
    except ValueError:
        return None


def piezas_vencidas(
    programadas: list[dict[str, Any]], ahora: datetime
) -> list[dict[str, Any]]:
    """Subconjunto de `programadas` que ya vencio y aun NO se preparo (PURA, testeable).

    Una pieza esta vencida si: su estado es `programado`, tiene `fecha_programada`
    valida <= `ahora`, y NO tiene `preparado_en` (no se preparo ya). Determinista:
    depende solo de sus argumentos (no del reloj real ni de la BD).
    """
    vencidas: list[dict[str, Any]] = []
    for pub in programadas:
        if pub.get("estado") != ESTADO_PROGRAMADO:
            continue
        if pub.get("preparado_en"):  # ya preparada en un barrido anterior
            continue
        fecha = _parsear_fecha(pub.get("fecha_programada") or "")
        if fecha is None or fecha > ahora:
            continue
        vencidas.append(pub)
    return vencidas


def _preparar(pub: dict[str, Any], ahora: datetime) -> dict[str, Any] | None:
    """Prepara UNA pieza vencida en DRY-RUN: estampa `preparado_en`. NO publica.

    Deja la pieza en `programado` (no en `publicado`): la frontera del producto es que
    el sistema no publica solo. Aqui es donde se engancharia el posteo real cuando #5/#8
    aterricen (Meta App Review + cuentas reales), sin tocar el resto del flujo.
    """
    return repos.actualizar_publicacion(
        pub["id"], {"preparado_en": ahora.isoformat(timespec="seconds")}
    )


def preparar_vencidas(ahora: datetime | None = None) -> int:
    """Prepara (dry-run) todas las piezas programadas ya vencidas. Devuelve cuantas preparo.

    Es lo que corre cada barrido del hilo y tambien se puede llamar a mano (test/CLI).
    Lee SOLO las piezas en estado `programado` (filtro en el indice), no todo el catalogo.
    """
    ahora = ahora or datetime.now()
    programadas = repos.listar_publicaciones(estado=ESTADO_PROGRAMADO)
    preparadas = 0
    for pub in piezas_vencidas(programadas, ahora):
        if _preparar(pub, ahora) is not None:
            preparadas += 1
    return preparadas


def _intervalo_segundos() -> float:
    """Intervalo del barrido en segundos (configurable por entorno; util en demo/tests)."""
    crudo = os.environ.get("KENI_PROGRAMADOR_INTERVALO_SEGUNDOS")
    if crudo:
        try:
            return max(1.0, float(crudo))
        except ValueError:
            pass
    return INTERVALO_SEGUNDOS_DEF


def iniciar_programador(intervalo_segundos: float | None = None) -> threading.Thread:
    """Arranca un hilo demonio que prepara (dry-run) las piezas vencidas en bucle.

    Pensado para el servidor real (`__main__`), NO para `crear_app`: los tests crean la
    app sin arrancar esto. El hilo es daemon: muere al cerrar el proceso. Prepara una vez
    al arrancar y luego cada `intervalo`. Un fallo de un barrido se loguea y NO mata el
    hilo (el siguiente barrido reintenta).
    """
    intervalo = intervalo_segundos if intervalo_segundos is not None else _intervalo_segundos()

    def bucle() -> None:
        while True:
            try:
                n = preparar_vencidas()
                if n:
                    _log.info(
                        "Programador: %d pieza(s) preparada(s) en DRY-RUN (sin publicar; "
                        "posteo real gated por #5/#8).",
                        n,
                    )
            except Exception:  # noqa: BLE001 -- un fallo de barrido no debe matar el hilo
                _log.exception("Fallo en el barrido del programador.")
            time.sleep(intervalo)

    hilo = threading.Thread(target=bucle, name="programador-publicaciones", daemon=True)
    hilo.start()
    _log.info(
        "Programador de publicaciones activo cada %.0f s (DRY-RUN: prepara, no publica).",
        intervalo,
    )
    return hilo
