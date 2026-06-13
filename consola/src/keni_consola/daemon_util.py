"""Bucle de demonio GATEADO y RESPONSIVO en caliente (toggle on/off sin reiniciar).

PROBLEMA QUE RESUELVE
=====================
Los daemons gateados (radar-auto, autogen-copy, autogen-arte, alertas, vencimientos)
comprobaban su flag UNA sola vez al arrancar: si estaba OFF, el hilo no se creaba, asi que
encender el flag en runtime (lo persiste otra rama, leido por `config`) NO tenia efecto
hasta reiniciar el proceso. Aqui invertimos el diseno: el hilo arranca SIEMPRE y comprueba
el flag EN VIVO en cada ciclo. Apagar aplica en <= `tick_seg`; encender tras estar apagado
dispara un barrido de inmediato.

DISENO
======
  - `toca_ejecutar` es una funcion PURA (sin reloj, sin estado global) que decide, dado el
    flag y los tiempos, si toca correr el barrido AHORA y cual es el proximo instante. Es la
    unica logica con ramas, asi que se testea sin hilos ni sleeps.
  - `bucle_gateado` es el bucle `while True` que duerme en pasos cortos (`min(tick_seg,
    intervalo)`) para ser responsivo al apagado, y usa `toca_ejecutar` para decidir cuando
    invocar `sweep_fn`. Captura las excepciones de `sweep_fn` (loguea, no mata el hilo).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any


def toca_ejecutar(activo: bool, ahora: float, proximo: float, intervalo: float) -> tuple[bool, float]:
    """Decide si toca correr el barrido AHORA y devuelve el proximo instante (PURA).

    Reglas:
      - Si NO esta `activo`: devuelve `(False, 0.0)`. El 0.0 RESETEA `proximo`, de modo que
        al re-activar (proximo=0.0 <= ahora) el primer barrido corre YA, sin esperar al
        intervalo.
      - Si esta `activo` y `ahora >= proximo`: toca correr; el nuevo proximo es
        `ahora + intervalo`.
      - Si esta `activo` pero aun no toca (`ahora < proximo`): no corre y conserva `proximo`.

    Determinista: depende solo de sus argumentos.
    """
    if not activo:
        return (False, 0.0)
    if ahora >= proximo:
        return (True, ahora + intervalo)
    return (False, proximo)


def bucle_gateado(
    *,
    activo_fn: Callable[[], bool],
    intervalo_seg_fn: Callable[[], float],
    sweep_fn: Callable[[], Any],
    tick_seg: float = 60.0,
    log: logging.Logger,
    nombre: str | None = None,
    _max_vueltas: int | None = None,
) -> None:
    """Bucle GATEADO y responsivo: corre `sweep_fn` solo mientras `activo_fn()` sea True.

    Duerme en pasos cortos (`min(tick_seg, intervalo)`) para que apagar aplique en <=
    `tick_seg`. Usa `toca_ejecutar` para decidir cada vuelta. Al ENCENDER tras estar
    apagado, ejecuta el primer barrido de inmediato (el reset de `proximo` a 0.0 lo
    garantiza). Un fallo de `sweep_fn` se loguea y NO mata el hilo (la siguiente vuelta
    reintenta).

    LATIDOS (observabilidad): cada vuelta registra un latido de ciclo y cada sweep uno de
    barrido (ok/error + duracion) via `latidos` (best-effort: un fallo del latido no toca
    el bucle). `nombre` identifica al daemon en la tabla; si no se pasa, se deriva del
    modulo de `sweep_fn` (asi los 10 call sites existentes quedan instrumentados sin
    cambios).

    BARRIDO FORZADO (operacion sin SSH): cada vuelta consulta el flag cross-proceso
    `barrido_solicitado` (lo escribe `POST /api/sistema/daemons/{daemon}/barrer` desde el
    contenedor back) y, si esta pedido Y el gate esta ON, ejecuta el sweep YA (consumiendo
    el flag: un solo barrido por solicitud) y reprograma el siguiente barrido normal a
    `ahora + intervalo`. Con el gate OFF el flag NO se consume ni se barre (la API ya
    responde 409 en ese caso; si el gate se apago entre medias, la solicitud espera a la
    reactivacion, cuyo primer barrido corre de inmediato de todos modos).

    `_max_vueltas` (solo para tests) acota el numero de iteraciones del bucle; en
    produccion se deja en None (bucle infinito).
    """
    from . import latidos  # import tardio: mantiene este modulo importable sin la app entera

    daemon = nombre or latidos.nombre_de_sweep(sweep_fn)
    proximo = 0.0  # 0.0 => si arranca ACTIVO, el primer barrido corre de inmediato.
    vueltas = 0
    while True:
        activo = activo_fn()
        intervalo = intervalo_seg_fn()
        correr, proximo = toca_ejecutar(activo, time.monotonic(), proximo, intervalo)
        # Barrido FORZADO: se consume SIEMPRE que el gate este ON (aunque tocara barrer ya:
        # ese barrido satisface la solicitud y no debe quedar otro colgado para el tick
        # siguiente). Best-effort: sin BD, `consumir_solicitud` devuelve False y no pasa nada.
        if activo and latidos.consumir_solicitud(daemon):
            correr = True
            proximo = time.monotonic() + intervalo
        if correr:
            t0 = time.monotonic()
            try:
                sweep_fn()
                latidos.barrido(
                    daemon, ok=True, intervalo_seg=intervalo, tick_seg=tick_seg,
                    duracion_ms=int((time.monotonic() - t0) * 1000),
                )
            except Exception as e:  # noqa: BLE001 -- un fallo de barrido no debe matar el hilo
                log.exception("Fallo en el barrido del daemon gateado.")
                latidos.barrido(
                    daemon, ok=False, intervalo_seg=intervalo, tick_seg=tick_seg,
                    duracion_ms=int((time.monotonic() - t0) * 1000), error=repr(e),
                )
        else:
            latidos.ciclo(daemon, activo=activo, intervalo_seg=intervalo, tick_seg=tick_seg)
        vueltas += 1
        if _max_vueltas is not None and vueltas >= _max_vueltas:
            return
        # Duerme en un paso corto para ser responsivo al apagado, nunca mas que el intervalo.
        time.sleep(min(tick_seg, max(intervalo, 0.0)) if intervalo > 0 else tick_seg)
