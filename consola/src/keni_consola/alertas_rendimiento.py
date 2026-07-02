"""Barrido de ALERTAS de rendimiento (Fase 3 auto-operativa).

Emite `pieza.bajo_rendimiento` cuando una pieza publicada cae bajo el umbral de engagement
(`KENI_ALERTAS_UMBRAL_ENGAGEMENT`): el equipo se entera (webhook/Slack) sin vigilar metricas.
Tambien vigila la COLA DE REVISION: si una marca acumula piezas en `en_revision` sin decision
durante mas de `KENI_ALERTAS_REVISION_HORAS` (def 24), emite `revision.estancada` (AGREGADO
por marca) y avisa in-app a sus coordinadores. Idempotente por bucket diario (re-ejecutar el
mismo dia no duplica avisos). El antiguo carril de "candidatas a reciclaje" se retiro.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, date, datetime, timedelta

from . import config, daemon_util, marcas, metricas_pieza, redes, repos
from .dominio import eventos, notificaciones
from .estados import ESTADO_EN_REVISION
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
        items = repos.listar_publicacion()
        por_contenido: dict[str, list[dict]] = {}
        for plat in repos.listar_piezas_fila():
            por_contenido.setdefault(plat["publicacion_id"], []).append(plat)
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
                    "publicacion_id": it["id"],
                    "pieza_id": plat["id"],
                    "titulo": it.get("titulo", ""),
                    "marca": marca,
                    "marca_nombre": marcas.etiqueta_de(marca) if marca else "",
                    "red": red,
                    "red_nombre": redes.nombre_por_id(red) if red else "",
                    "id_post_metricool": id_post,
                    "engagement_pct": eng,
                    "umbral": umbral,
                },
                publicacion_id=it["id"],
                pieza_id=plat["id"],
                clave_idempotencia=clave,
            )
            if nuevo:
                emitidos += 1
    return emitidos


def _a_naive_utc(dt: datetime) -> datetime:
    """Normaliza un datetime a naive-UTC (un aware se convierte a UTC antes de soltar el offset)."""
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def estancadas_por_marca(
    pubs: list[dict], *, ahora: datetime, horas: int
) -> dict[str, int]:
    """Conteo por marca de las piezas en revisión SIN decisión desde hace más de `horas` (PURA).

    La espera se mide desde `enviado_a_revision_en` (el sello de entrada a la cola); si una
    pieza legada no lo trae, cae a `fecha_actualizacion`. Un timestamp ilegible NO cuenta
    (no se alerta sobre datos que no se pueden juzgar). Piezas sin marca se ignoran.
    """
    ahora_naive = _a_naive_utc(ahora)
    corte = timedelta(hours=max(1, horas))
    conteo: dict[str, int] = {}
    for pub in pubs:
        marca = str(pub.get("marca") or "")
        if not marca:
            continue
        ts = str(
            pub.get("enviado_a_revision_en") or pub.get("fecha_actualizacion") or ""
        ).strip()
        if not ts:
            continue
        try:
            espera = ahora_naive - _a_naive_utc(datetime.fromisoformat(ts))
        except (TypeError, ValueError):
            continue
        if espera > corte:
            conteo[marca] = conteo.get(marca, 0) + 1
    return conteo


def _emitir_revision_estancada(hoy_iso: str, horas: int) -> int:
    """Emite `revision.estancada` (AGREGADO por marca) por las piezas atascadas en revisión.

    Lee SOLO las piezas en `en_revision`, cuenta por marca las que esperan una decisión desde
    hace más de `horas` y emite UN evento por marca con el conteo, idempotente por día (la
    clave es marca+día: si la cola sigue atascada mañana, vuelve a avisar). Cuando el evento
    es NUEVO, además avisa in-app a los coordinadores de la marca (mismo agregado). Devuelve
    cuántos eventos NUEVOS emitió.
    """
    try:
        pubs = repos.listar_piezas(estado=ESTADO_EN_REVISION)
    except Exception:  # noqa: BLE001 -- un fallo de lectura no debe matar el barrido
        _log.exception("alertas: fallo al leer la cola de revisión para estancadas.")
        return 0
    conteo = estancadas_por_marca(pubs, ahora=datetime.now(UTC), horas=horas)
    emitidos = 0
    for marca, n in sorted(conteo.items()):
        nuevo = eventos.emitir(
            "revision.estancada",
            {
                "marca": marca,
                "marca_nombre": marcas.etiqueta_de(marca),
                "n": n,
                "horas": horas,
            },
            clave_idempotencia=f"revision.estancada:{marca}:{hoy_iso}",
        )
        if nuevo:
            emitidos += 1
            _log.warning(
                "Alertas: %d pieza(s) de %s llevan más de %d h esperando revisión.",
                n, marca, horas,
            )
            notificaciones.tras_revision_estancada(marca, n, horas)
    return emitidos


def emitir_alertas(hoy: date | None = None) -> int:
    """Corre UN barrido de alertas. Devuelve cuantos avisos NUEVOS emitio.

    Dos carriles: `pieza.bajo_rendimiento` (por pieza publicada bajo el umbral de engagement)
    y `revision.estancada` (agregado por marca: piezas atascadas en la cola de revision).
    Es lo que ejecuta cada vuelta del hilo y tambien se puede llamar a mano (test/CLI).
    La idempotencia por bucket diario hace que re-ejecutar el mismo dia no duplique avisos.
    """
    hoy_iso = (hoy or hoy_utc()).isoformat()
    umbral = config.alertas_umbral_engagement()
    bajo = _emitir_bajo_rendimiento(hoy_iso, umbral)
    estancadas = _emitir_revision_estancada(hoy_iso, config.alertas_revision_horas())
    return bajo + estancadas


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

    def barrido() -> int:
        emitidas = emitir_alertas()
        if emitidas:
            _log.info("Alertas: %d aviso(s) nuevo(s) (bajo rendimiento / revisión estancada).", emitidas)
        return emitidas

    def _resumen(n: int) -> str:
        return f"{n} alerta(s) emitida(s)" if n else "sin novedad"

    def bucle() -> None:
        daemon_util.bucle_gateado(
            activo_fn=config.alertas_rendimiento_activas,
            intervalo_seg_fn=lambda: intervalo,
            sweep_fn=barrido,
            log=_log,
            resumen_fn=_resumen,
        )

    hilo = threading.Thread(target=bucle, name="alertas-rendimiento-daemon", daemon=True)
    hilo.start()
    estado = "activo" if config.alertas_rendimiento_activas() else "en espera (KENI_ALERTAS_RENDIMIENTO=0)"
    _log.info("Barrido de alertas de rendimiento %s, cada %.0f h.", estado, intervalo / 3600.0)
    return hilo
