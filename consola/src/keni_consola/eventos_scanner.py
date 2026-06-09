"""Barrido de VENCIMIENTOS del tablero: emite `contenido.vencido` cuando toca.

Hermano de `programador.py` (mismo patron de hilo demonio), pero para los EVENTOS
INTERNOS del tablero (no para publicar en Metricool). Un contenido vence cuando su
`fecha_entrega` ya paso y NO esta cerrado (`publicado`/`hecha`). Cada barrido detecta
los vencidos y llama a `dominio.eventos.emitir` con una `clave_idempotencia`
(`contenido.vencido:<id>:<fecha_entrega>`) de modo que un contenido vencido NO se
re-notifique en cada barrido: la bitacora de eventos desduplica por esa clave.

El calculo de "que esta vencido" es una funcion PURA y DETERMINISTA
(`contenidos_vencidos`) que recibe `hoy` inyectado, testeable sin reloj ni hilo. El
arranque del hilo (`iniciar_scanner_vencimientos`) vive en el servidor real
(`__main__`), NO en `crear_app` (igual que el programador): los tests crean la app sin
arrancarlo. SAFE BY DEFAULT: sin webhooks activos, `emitir` no toca la red.
"""

from __future__ import annotations

import logging
import threading
from datetime import date

from . import config, daemon_util, marcas, repos
from .dominio import eventos
from .tiempo import hoy_utc

_log = logging.getLogger("keni_consola.eventos_scanner")

# Estados en los que un deadline vencido ya no importa (coincide con `api/contenido`).
_ESTADOS_CERRADOS = ("publicado", "hecha")


def contenidos_vencidos(items: list[dict], hoy: str) -> list[dict]:
    """Subconjunto de `items` cuyo `fecha_entrega` ya paso y no estan cerrados (PURA).

    `hoy` es una fecha ISO ('YYYY-MM-DD'). Un item esta vencido si tiene `fecha_entrega`
    no vacia, estrictamente anterior a `hoy`, y su `estado` no es terminal.
    """
    vencidos: list[dict] = []
    for it in items:
        entrega = (it.get("fecha_entrega") or "").strip()
        if not entrega or entrega >= hoy:
            continue
        if it.get("estado") in _ESTADOS_CERRADOS:
            continue
        vencidos.append(it)
    return vencidos


def emitir_vencimientos(hoy: date | None = None) -> int:
    """Emite `contenido.vencido` por cada contenido recien vencido. Devuelve cuantos NUEVOS emitio.

    Es lo que corre cada barrido del hilo y tambien se puede llamar a mano (test/CLI). La
    idempotencia (clave `contenido.vencido:<id>:<fecha_entrega>`) hace que solo cuente los
    que aun no se habian notificado: re-ejecutar es seguro y no duplica avisos.
    """
    hoy_iso = (hoy or hoy_utc()).isoformat()
    try:
        # Filtro EN SQL (`fecha_entrega < hoy AND estado NOT IN (cerrados)`): antes se traia
        # el tablero ENTERO en cada barrido y se filtraba en Python (full scan por minuto).
        items = repos.listar_contenido_vencido(hoy_iso)
    except Exception:  # noqa: BLE001 -- un fallo de lectura no debe matar el barrido
        _log.exception("No se pudo leer el tablero para el barrido de vencimientos.")
        return 0
    emitidos = 0
    # `contenidos_vencidos` (pura) se mantiene como defensa barata y para tests; sobre el
    # resultado ya filtrado en SQL es un no-op.
    for it in contenidos_vencidos(items, hoy_iso):
        entrega = (it.get("fecha_entrega") or "").strip()
        clave = f"contenido.vencido:{it['id']}:{entrega}"
        nuevo = eventos.emitir(
            "contenido.vencido",
            {
                "contenido_id": it["id"],
                "titulo": it.get("titulo", ""),
                "marca": it.get("marca", ""),
                "marca_nombre": marcas.etiqueta_de(it["marca"]) if it.get("marca") else "",
                "fecha_entrega": entrega,
                "responsable_nombre": it.get("responsable_nombre", ""),
                "estado": it.get("estado", ""),
            },
            contenido_id=it["id"],
            clave_idempotencia=clave,
        )
        if nuevo:
            emitidos += 1
    return emitidos


def iniciar_scanner_vencimientos(
    intervalo_segundos: float | None = None,
) -> threading.Thread:
    """Arranca un hilo demonio que emite los vencimientos del tablero (GATEADO EN VIVO).

    El hilo arranca SIEMPRE y comprueba `KENI_EVENTOS_VENCIMIENTOS` en cada ciclo: apagar/
    encender en runtime aplica sin reiniciar (apagar en <= ~1 min o el intervalo si es menor;
    encender tras estar apagado dispara un barrido de inmediato). Pensado para el servidor
    real (`__main__`), NO para `crear_app`. El hilo es daemon: muere al cerrar el proceso. Un
    fallo de un barrido se loguea y NO mata el hilo (el siguiente reintenta).
    """
    intervalo = (
        intervalo_segundos
        if intervalo_segundos is not None
        else config.eventos_intervalo_segundos()
    )

    def barrido() -> None:
        n = emitir_vencimientos()
        if n:
            _log.info("Vencimientos: %d contenido(s) notificado(s).", n)

    def bucle() -> None:
        daemon_util.bucle_gateado(
            activo_fn=config.eventos_vencimientos_activos,
            intervalo_seg_fn=lambda: intervalo,
            sweep_fn=barrido,
            log=_log,
        )

    hilo = threading.Thread(target=bucle, name="eventos-vencimientos", daemon=True)
    hilo.start()
    estado = "activo" if config.eventos_vencimientos_activos() else "en espera (KENI_EVENTOS_VENCIMIENTOS=0)"
    _log.info("Barrido de vencimientos del tablero %s, cada %.0f s.", estado, intervalo)
    return hilo
