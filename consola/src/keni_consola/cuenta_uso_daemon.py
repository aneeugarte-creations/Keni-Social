"""Muestreo de fondo del ESTADO de las cuentas de Claude: uso (snapshot) + caducidad (aviso).

PROBLEMA QUE RESUELVE
=====================
El medidor de la suscripción (`cuenta_claude.uso()` -> `claude -p /usage`) solo se refrescaba
cuando un admin abría el panel Sistema→Cuenta. El indicador siempre-visible de la barra lateral
y el gate diario por porcentaje necesitan el dato SIN intervención: este daemon lo muestrea en
background y lo deja en la tabla `cuenta_uso` (último snapshot + base del consumo de hoy).

En la misma pasada vigila la CADUCIDAD de la credencial de cada cuenta y avisa ANTES de que se
pare la generación (`cuenta.credencial_expira` -> webhook/Slack + aviso in-app a los admin). El
cupo y la credencial son los dos estados que deciden si una cuenta puede generar; el medidor solo
cubría el primero, y una credencial muerta no la delata (`claude auth status` sigue diciendo
`loggedIn`, y el medidor cacheado congela el último porcentaje bueno).

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

from . import config, cuenta_claude, daemon_util, repos, ruteo_cuentas
from .dominio import eventos, jobspec, notificaciones
from .tiempo import hoy_utc

_log = logging.getLogger("keni_consola.cuenta_uso_daemon")


def _avisar_credencial(cuenta: str, hoy_iso: str) -> bool:
    """Avisa si la credencial de `cuenta` ya caducó o le queda menos de la antelación configurada.

    Sin credencial viva NO se genera nada con esa cuenta, y una sin `refreshToken` no se renueva
    sola: el arreglo es un `claude auth login` a mano. Por eso el aviso es PROACTIVO
    (`config.cuenta_aviso_caducidad_h`), para llegar antes de que la generación se pare.

    Un aviso por ESTADO y día (`clave_idempotencia`): el paso de «por caducar» a «caducada» vuelve
    a avisar, pero el barrido no repite el mismo aviso en cada muestreo. Devuelve True si emitió uno
    NUEVO. Best-effort: sin lectura de la credencial (`conocida=False`) no afirma nada.
    """
    estado = cuenta_claude.caducidad(cuenta)
    if not estado.get("conocida"):
        return False
    caducada = bool(estado.get("caducada"))
    horas = float(estado.get("segundos_restantes") or 0.0) / 3600.0
    antelacion = config.cuenta_aviso_caducidad_h()
    if not caducada and (antelacion <= 0 or horas > antelacion):
        return False
    etiqueta = ruteo_cuentas.etiqueta_de_cuenta(cuenta)
    nuevo = eventos.emitir(
        "cuenta.credencial_expira",
        {
            "cuenta": cuenta,
            "etiqueta": etiqueta,
            "caducada": caducada,
            "horas_restantes": round(horas, 1),
            "expira_en_iso": estado.get("expira_en_iso") or "",
            # Una credencial sin refresh NO se renueva sola: el aviso es la única vía de arreglo.
            "tiene_refresh": bool(estado.get("tiene_refresh")),
        },
        clave_idempotencia=(
            f"cuenta.credencial_expira:{cuenta}:{'caducada' if caducada else 'aviso'}:{hoy_iso}"
        ),
    )
    if nuevo:
        _log.warning(
            "cuenta %s: credencial %s (expira %s); hace falta `claude auth login`.",
            cuenta, "CADUCADA" if caducada else f"caduca en {horas:.1f} h",
            estado.get("expira_en_iso") or "?",
        )
        notificaciones.tras_credencial_por_caducar(
            cuenta, etiqueta, caducada=caducada, horas=horas,
        )
    return nuevo


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

    En la misma pasada vigila la CADUCIDAD de la credencial de cada cuenta (`_avisar_credencial`):
    es el otro estado que decide si esa cuenta puede generar, y se lee del mismo sitio.
    """
    filas: dict[str, dict] = {}
    hoy_iso = hoy_utc()
    for cuenta in jobspec.CUENTAS:
        datos = cuenta_claude.uso(cuenta)
        campos = _extraer_medidores(datos)
        filas[cuenta] = repos.guardar_uso_cuenta(cuenta=cuenta, **campos)
        try:
            _avisar_credencial(cuenta, hoy_iso)
        except Exception:  # noqa: BLE001 -- la vigilancia nunca frena el muestreo de uso
            _log.warning("cuenta %s: fallo el aviso de caducidad.", cuenta, exc_info=True)
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
