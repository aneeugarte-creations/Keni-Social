"""Barrido de ALERTAS de rendimiento (Fase 3 auto-operativa).

Emite `pieza.bajo_rendimiento` cuando una pieza publicada cae bajo el umbral de engagement
(`KENI_ALERTAS_UMBRAL_ENGAGEMENT`): el equipo se entera (webhook/Slack) sin vigilar metricas.
Idempotente por bucket diario (re-ejecutar el mismo dia no duplica avisos). El antiguo carril
de "candidatas a reciclaje" se retiro: lo sustituye el EVERGREEN DIARIO automatico
(`evergreen_diario`), que reemite solo una pieza green aprobada al dia.
"""

from __future__ import annotations

import logging
import threading
from datetime import date

from . import config, daemon_util, marcas, metricas_pieza, redes, repos
from .dominio import eventos
from .tiempo import hoy_utc

_log = logging.getLogger("keni_consola.alertas_rendimiento")


def _emitir_bajo_rendimiento(hoy_iso: str, umbral: float) -> int:
    """Emite `pieza.bajo_rendimiento` por cada pieza publicada que cae bajo el umbral.

    Recorre las filas por plataforma del tablero con `id_post_metricool`, lee su
    rendimiento (cacheado, degradacion honesta) y, si esta ENCONTRADO y su engagement es
    < `umbral`, emite la alerta. Una pieza "sin datos" (no encontrada en Metricool, p.ej.
    recien publicada) NO dispara alerta: no hay rendimiento que juzgar. Devuelve NUEVAS.
    """
    try:
        items = repos.listar_contenido()
        por_contenido: dict[str, list[dict]] = {}
        for plat in repos.listar_contenido_plataforma():
            por_contenido.setdefault(plat["contenido_id"], []).append(plat)
    except Exception:  # noqa: BLE001 -- un fallo de lectura no debe matar el barrido
        _log.exception("alertas: fallo al leer el tablero para bajo rendimiento.")
        return 0

    emitidos = 0
    for it in items:
        marca = it.get("marca") or ""
        if not marca:
            continue
        for plat in por_contenido.get(it["id"], []):
            id_post = plat.get("id_post_metricool") or ""
            red = plat.get("red") or ""
            if not id_post:
                continue
            rend = metricas_pieza.rendimiento(marca, red, id_post)
            if not rend.get("encontrado"):
                continue
            try:
                eng = float(rend.get("engagement_pct") or 0.0)
            except (TypeError, ValueError):
                continue
            if eng >= umbral:
                continue
            clave = f"pieza.bajo_rendimiento:{plat['id']}:{hoy_iso}"
            nuevo = eventos.emitir(
                "pieza.bajo_rendimiento",
                {
                    "contenido_id": it["id"],
                    "plataforma_id": plat["id"],
                    "titulo": it.get("titulo", ""),
                    "marca": marca,
                    "marca_nombre": marcas.etiqueta_de(marca) if marca else "",
                    "red": red,
                    "red_nombre": redes.nombre_por_id(red) if red else "",
                    "id_post_metricool": id_post,
                    "engagement_pct": eng,
                    "umbral": umbral,
                },
                contenido_id=it["id"],
                plataforma_id=plat["id"],
                clave_idempotencia=clave,
            )
            if nuevo:
                emitidos += 1
    return emitidos


def emitir_alertas(hoy: date | None = None) -> int:
    """Corre UN barrido de alertas. Devuelve cuantas `pieza.bajo_rendimiento` NUEVAS emitio.

    (El carril de reciclaje se retiro con la feature: el evergreen diario automatico
    sustituye a las sugerencias de "retomar" piezas.) Es lo que ejecuta cada vuelta del
    hilo y tambien se puede llamar a mano (test/CLI). La idempotencia por bucket diario
    hace que re-ejecutar el mismo dia no duplique avisos.
    """
    hoy_iso = (hoy or hoy_utc()).isoformat()
    umbral = config.alertas_umbral_engagement()
    return _emitir_bajo_rendimiento(hoy_iso, umbral)


def iniciar_alertas_rendimiento(
    intervalo_segundos: float | None = None,
) -> threading.Thread:
    """Arranca un hilo demonio que emite las alertas de rendimiento (GATEADO EN VIVO).

    El hilo arranca SIEMPRE y comprueba `KENI_ALERTAS_RENDIMIENTO` en cada ciclo: apagar/
    encender en runtime aplica sin reiniciar (apagar en <= ~1 min; encender tras estar
    apagado dispara un barrido de inmediato). Pensado para el servidor real (`__main__`), NO
    para `crear_app`. El hilo es daemon: muere al cerrar el proceso. Un fallo de un barrido se
    loguea y NO mata el hilo (el siguiente reintenta).
    """
    intervalo = (
        intervalo_segundos
        if intervalo_segundos is not None
        else config.alertas_rendimiento_horas() * 3600.0
    )

    def barrido() -> None:
        bajo = emitir_alertas()
        if bajo:
            _log.info("Alertas: %d pieza(s) de bajo rendimiento.", bajo)

    def bucle() -> None:
        daemon_util.bucle_gateado(
            activo_fn=config.alertas_rendimiento_activas,
            intervalo_seg_fn=lambda: intervalo,
            sweep_fn=barrido,
            log=_log,
        )

    hilo = threading.Thread(target=bucle, name="alertas-rendimiento-daemon", daemon=True)
    hilo.start()
    estado = "activo" if config.alertas_rendimiento_activas() else "en espera (KENI_ALERTAS_RENDIMIENTO=0)"
    _log.info("Barrido de alertas de rendimiento %s, cada %.0f h.", estado, intervalo / 3600.0)
    return hilo
