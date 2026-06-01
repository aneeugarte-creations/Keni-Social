"""Tests de la logica PURA y del bucle gateado de `daemon_util`.

Se testea la funcion PURA `toca_ejecutar` (apagado resetea, encendido corre ya, respeta el
intervalo) y una traza ACOTADA de `bucle_gateado` con `activo_fn`/`sweep_fn` inyectados y
`_max_vueltas` para no entrar en el bucle infinito (sin sleeps largos: `tick_seg` minusculo).
"""

from __future__ import annotations

import logging

from keni_consola import daemon_util

_LOG = logging.getLogger("test_daemon_util")


def test_apagado_no_corre_y_resetea_proximo():
    # Aunque `proximo` ya estuviera fijado, apagar NO corre y resetea a 0.0.
    correr, proximo = daemon_util.toca_ejecutar(activo=False, ahora=100.0, proximo=200.0, intervalo=60.0)
    assert correr is False
    assert proximo == 0.0


def test_encender_tras_apagado_corre_ya():
    # Tras un reset (proximo=0.0), al re-activar el primer barrido corre de inmediato.
    correr, proximo = daemon_util.toca_ejecutar(activo=True, ahora=100.0, proximo=0.0, intervalo=60.0)
    assert correr is True
    assert proximo == 160.0


def test_activo_respeta_intervalo():
    # Activo pero aun no toca: no corre y conserva el `proximo` pendiente.
    correr, proximo = daemon_util.toca_ejecutar(activo=True, ahora=100.0, proximo=160.0, intervalo=60.0)
    assert correr is False
    assert proximo == 160.0


def test_activo_justo_en_proximo_corre():
    # `ahora == proximo` cuenta como "toca" (>=).
    correr, proximo = daemon_util.toca_ejecutar(activo=True, ahora=160.0, proximo=160.0, intervalo=60.0)
    assert correr is True
    assert proximo == 220.0


def test_bucle_gateado_no_corre_si_apagado():
    llamadas = []
    daemon_util.bucle_gateado(
        activo_fn=lambda: False,
        intervalo_seg_fn=lambda: 3600.0,
        sweep_fn=lambda: llamadas.append(1),
        tick_seg=0.0,  # sin sleep real (intervalo>0 cap a min(tick, intervalo)=0)
        log=_LOG,
        _max_vueltas=3,
    )
    assert llamadas == []


def test_bucle_gateado_corre_de_inmediato_si_activo():
    llamadas = []
    daemon_util.bucle_gateado(
        activo_fn=lambda: True,
        intervalo_seg_fn=lambda: 3600.0,  # intervalo enorme: solo debe correr 1 vez
        sweep_fn=lambda: llamadas.append(1),
        tick_seg=0.0,
        log=_LOG,
        _max_vueltas=3,
    )
    # Corre en la 1a vuelta; las siguientes no, porque proximo = ahora + 3600.
    assert llamadas == [1]


def test_bucle_gateado_captura_excepcion_y_sigue():
    llamadas = []

    def sweep_que_falla():
        llamadas.append(1)
        raise RuntimeError("boom")

    # No debe propagar; loguea y sigue (aqui solo corre 1 vez por el intervalo grande).
    daemon_util.bucle_gateado(
        activo_fn=lambda: True,
        intervalo_seg_fn=lambda: 3600.0,
        sweep_fn=sweep_que_falla,
        tick_seg=0.0,
        log=_LOG,
        _max_vueltas=2,
    )
    assert llamadas == [1]
