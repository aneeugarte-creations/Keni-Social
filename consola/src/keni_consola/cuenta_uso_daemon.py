"""Muestreo de fondo del USO de la cuenta de Claude: persiste un snapshot cada N minutos.

PROBLEMA QUE RESUELVE
=====================
El medidor de la suscripción (`cuenta_claude.uso()` -> `claude -p /usage`) solo se refrescaba
cuando un admin abría el panel Sistema→Cuenta. El indicador siempre-visible de la barra lateral
y el gate diario por porcentaje necesitan el dato SIN intervención: este daemon lo muestrea en
background y lo deja en la tabla `cuenta_uso` (último snapshot + base del consumo de hoy).

DÓNDE CORRE: en el proceso `daemons` (la imagen con Node + `claude`); el `back` NO ejecuta
`claude`. El endpoint admin (`api/sistema/uso`) solo LEE la tabla.

SIEMPRE ACTIVO (no es una feature gateada): es mantenimiento/observabilidad de la cuenta, igual
que el limpiador de generaciones. Vive en `daemons.main()` (servidor real), NO en `crear_app`,
para no arrancarlo en los tests. El muestreo es best-effort: un fallo se loguea y NO mata el hilo.
"""

from __future__ import annotations

import logging
import threading
import time

from . import config, cuenta_claude, daemon_util, repos
from .dominio import jobspec

_log = logging.getLogger("keni_consola.cuenta_uso_daemon")


def _extraer_medidores(uso: dict) -> dict:
    """Mapea el dict de `cuenta_claude.uso()` a los campos del snapshot (PURA).

    Reconoce los dos medidores por su etiqueta (la que da el CLI): "Current session" ->
    `sesion_5h_pct` (+ su reset, para el burn rate); "Current week (all models)" -> `semana_pct`
    (+ su reset). Cada `*_pct` es None si su medidor no aparece. `conectada` refleja si la lectura
    trae medidor (incluido el cacheado); `actualizado_ts` es el epoch que `uso()` adjunta (o el
    instante actual si no lo trae).
    """
    conectada = bool(uso.get("disponible"))
    semana_pct: int | None = None
    sesion_5h_pct: int | None = None
    reset_semana_iso = ""
    reset_semana_txt = ""
    reset_sesion_iso = ""
    for medidor in uso.get("medidores") or []:
        etiqueta = (medidor.get("etiqueta") or "").lower()
        pct = medidor.get("pct")
        if "session" in etiqueta:
            sesion_5h_pct = pct
            reset_sesion_iso = medidor.get("reset_iso") or ""
        elif "week" in etiqueta:
            semana_pct = pct
            reset_semana_iso = medidor.get("reset_iso") or ""
            reset_semana_txt = medidor.get("reset") or ""
    return {
        "conectada": conectada,
        "semana_pct": semana_pct,
        "sesion_5h_pct": sesion_5h_pct,
        "reset_semana_iso": reset_semana_iso,
        "reset_semana_txt": reset_semana_txt,
        "reset_sesion_iso": reset_sesion_iso,
        "actualizado_ts": uso.get("actualizado") if uso.get("actualizado") is not None else time.time(),
    }


def ejecutar_barrido() -> dict:
    """Un muestreo: lee el uso (`claude -p /usage`) de CADA cuenta (A/B) y persiste su snapshot.

    Best-effort POR CUENTA: si una cuenta no está logueada, su lectura no trae medidor y su fila
    queda `conectada=false` (no rompe ni frena la otra). Devuelve `{cuenta: fila}` para todas las
    cuentas, que alimenta el resumen del barrido (`_resumen_barrido`).
    """
    filas: dict[str, dict] = {}
    for cuenta in jobspec.CUENTAS:
        datos = cuenta_claude.uso(cuenta)
        campos = _extraer_medidores(datos)
        filas[cuenta] = repos.guardar_uso_cuenta(cuenta=cuenta, **campos)
    return filas


def _resumen_cuenta(fila: dict | None) -> str:
    """Resumen de UNA cuenta: `semana N%` si hay medidor, si no `sin medidor`."""
    if not fila or not fila.get("conectada"):
        return "sin medidor"
    semana = fila.get("semana_pct")
    return f"semana {semana}%" if semana is not None else "muestreado"


def _resumen_barrido(filas: dict) -> str:
    """Resumen corto del muestreo de AMBAS cuentas para el historial del daemon.

    P. ej. "a: semana 67% · b: sin medidor". Acepta el `{cuenta: fila}` de `ejecutar_barrido`.
    """
    if not filas:
        return "sin cuentas"
    return " · ".join(f"{cuenta}: {_resumen_cuenta(filas.get(cuenta))}" for cuenta in jobspec.CUENTAS)


def iniciar_muestreo_uso(intervalo_segundos: float | None = None) -> threading.Thread:
    """Arranca el hilo demonio del muestreo de uso (SIEMPRE activo). Muestrea al arrancar y cada N min.

    Pensado para el servidor real (`daemons.main()`), NO para `crear_app` (los tests no lo
    arrancan). El hilo es daemon; un fallo de muestreo se loguea y NO lo mata.
    """
    intervalo = (
        intervalo_segundos
        if intervalo_segundos is not None
        else float(config.uso_muestreo_intervalo_seg())
    )

    def bucle() -> None:
        daemon_util.bucle_gateado(
            activo_fn=lambda: True,  # mantenimiento: siempre activo
            intervalo_seg_fn=lambda: intervalo,
            sweep_fn=ejecutar_barrido,
            log=_log,
            resumen_fn=_resumen_barrido,
        )

    hilo = threading.Thread(target=bucle, name="cuenta-uso-daemon", daemon=True)
    hilo.start()
    _log.info("Muestreo de uso de la cuenta ACTIVO cada %.0f min.", intervalo / 60.0)
    return hilo
