"""Barrido de ALERTAS de rendimiento / reciclaje proactivo (Fase 3 auto-operativa).

Hermano de `eventos_scanner.py` (mismo patron de hilo demonio + idempotencia por clave),
pero en vez de vencimientos del tablero emite alertas PROACTIVAS sobre el rendimiento de
las piezas publicadas:

  1. RECICLAJE — reusa la heuristica YA existente (`dominio.reciclaje.sugerencias_de_reciclaje`,
     la MISMA que alimenta el `PanelReciclaje` del tablero): por cada candidata emite
     `pieza.reciclaje_sugerida`. Asi el equipo se entera (webhook/Slack) sin tener que
     abrir la consola, y el banner del tablero ("N candidatas") ya muestra la lista.
  2. BAJO RENDIMIENTO — por cada pieza publicada del tablero con `id_post_metricool` cuyo
     engagement REAL (Metricool, via `metricas_pieza.rendimiento`, cacheado) cae por debajo
     del umbral configurable (`KENI_ALERTAS_UMBRAL_ENGAGEMENT`, def 1.0%), emite
     `pieza.bajo_rendimiento`.

IDEMPOTENCIA: cada alerta lleva una `clave_idempotencia` con un BUCKET DIARIO
(`<tipo>:<id>:<YYYY-MM-DD>`), de modo que la MISMA pieza no re-emite la alerta en cada
barrido del dia (la bitacora de eventos desduplica por esa clave). Al dia siguiente, si
sigue siendo candidata / sigue rindiendo bajo, se vuelve a avisar UNA vez.

SAFE BY DEFAULT: `eventos.emitir` no toca la red si no hay webhooks activos (solo bitacora
el evento interno). El arranque del hilo (`iniciar_alertas_rendimiento`) vive en el
servidor real (`__main__`), NO en `crear_app`: los tests crean la app sin arrancarlo. Un
fallo de barrido se loguea y NO mata el hilo.
"""

from __future__ import annotations

import logging
import threading
from datetime import date

from . import config, daemon_util, marcas, metricas_pieza, redes, repos
from .dominio import eventos, reciclaje

_log = logging.getLogger("keni_consola.alertas_rendimiento")


def _emitir_reciclaje(hoy_iso: str) -> int:
    """Emite `pieza.reciclaje_sugerida` por cada candidata de la heuristica. Devuelve NUEVAS."""
    try:
        candidatas = reciclaje.sugerencias_de_reciclaje()
    except Exception:  # noqa: BLE001 -- un fallo de la heuristica no debe matar el barrido
        _log.exception("alertas: fallo al calcular candidatas de reciclaje.")
        return 0
    emitidos = 0
    for c in candidatas:
        clave = f"pieza.reciclaje_sugerida:{c['id']}:{hoy_iso}"
        nuevo = eventos.emitir(
            "pieza.reciclaje_sugerida",
            {
                "pieza_id": c["id"],
                "titulo": c.get("titulo", ""),
                "marca": c.get("marca", ""),
                "marca_nombre": c.get("marca_nombre", ""),
                "red": c.get("red", ""),
                "red_nombre": c.get("red_nombre", ""),
                "motivo": c.get("motivo", ""),
                "motivo_detalle": c.get("motivo_detalle", ""),
            },
            clave_idempotencia=clave,
        )
        if nuevo:
            emitidos += 1
    return emitidos


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


def emitir_alertas(hoy: date | None = None) -> tuple[int, int]:
    """Corre UN barrido de alertas. Devuelve `(reciclaje_nuevas, bajo_rendimiento_nuevas)`.

    Es lo que ejecuta cada vuelta del hilo y tambien se puede llamar a mano (test/CLI).
    La idempotencia por bucket diario hace que re-ejecutar el mismo dia no duplique avisos.
    """
    hoy_iso = (hoy or date.today()).isoformat()
    umbral = config.alertas_umbral_engagement()
    return _emitir_reciclaje(hoy_iso), _emitir_bajo_rendimiento(hoy_iso, umbral)


def iniciar_alertas_rendimiento(
    intervalo_segundos: float | None = None,
) -> threading.Thread:
    """Arranca un hilo demonio que emite las alertas de rendimiento/reciclaje (GATEADO EN VIVO).

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
        recic, bajo = emitir_alertas()
        if recic or bajo:
            _log.info(
                "Alertas: %d candidata(s) de reciclaje, %d pieza(s) de bajo rendimiento.",
                recic, bajo,
            )

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
