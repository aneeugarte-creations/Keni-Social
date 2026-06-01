"""Auto-refresco de Algoritmos: ingiere los feeds de inteligencia de plataforma cada N horas.

Espejo de `radar_auto.py` / `metricas_refresco.py`: un hilo demonio GATEADO que llama a
`algoritmos.refrescar()` periodicamente para que la pagina Algoritmos y el panel se
mantengan al dia sin un clic manual.

SEGURO POR DISEÑO
=================
  - GATEADO: solo ingiere con `KENI_ALGORITMOS_AUTO=1` (def OFF). Sin el flag, el hilo vive
    pero no hace nada (toggle en caliente via `daemon_util.bucle_gateado`).
  - SOLO LECTURA EXTERNA: `refrescar` solo descarga feeds RSS publicos (guard SSRF reusado del
    RSS) y persiste noticias clasificadas. No publica, no genera, no llama a `claude -p`.
  - DEGRADACION HONESTA: una fuente que falla se anota con su error y no rompe el barrido.

La primera vez (tabla vacia) SIEMBRA las fuentes recomendadas, para que el barrido tenga de
donde leer aunque nadie haya configurado fuentes todavia.
"""

from __future__ import annotations

import logging
import threading

from . import algoritmos, config, daemon_util, repos

_log = logging.getLogger("keni_consola.algoritmos_refresco")


def ejecutar_barrido() -> None:
    """Un barrido de ingesta: siembra si hace falta y refresca todas las fuentes activas.

    Best-effort: cualquier fallo se loguea dentro de `refrescar` (degradacion honesta por
    fuente); aqui solo registramos el resultado agregado.
    """
    if repos.contar_fuentes_algoritmo() == 0:
        creadas = algoritmos.sembrar()
        if creadas:
            _log.info("Algoritmos: sembradas %d fuente(s) recomendada(s).", len(creadas))
    resumen = algoritmos.refrescar()
    _log.info(
        "Algoritmos: ingesta de %d fuente(s) -> %d nueva(s), %d actualizada(s), %d error(es).",
        resumen.get("fuentes", 0),
        resumen.get("insertadas", 0),
        resumen.get("actualizadas", 0),
        len(resumen.get("errores", [])),
    )


def _intervalo_segundos() -> float:
    """Intervalo del barrido en segundos (a partir de `KENI_ALGORITMOS_INTERVALO_HORAS`)."""
    return config.algoritmos_intervalo_horas() * 3600.0


def iniciar_refresco_algoritmos(intervalo_segundos: float | None = None) -> threading.Thread:
    """Arranca el hilo demonio de auto-refresco de Algoritmos (GATEADO EN VIVO).

    El hilo arranca SIEMPRE y comprueba `KENI_ALGORITMOS_AUTO` en cada ciclo: encender/apagar
    en runtime aplica sin reiniciar. El hilo es daemon; un fallo de barrido se loguea y NO lo
    mata. No lo arranca `crear_app` (los tests no levantan daemons), solo `__main__`/`daemons`.
    """
    intervalo = intervalo_segundos if intervalo_segundos is not None else _intervalo_segundos()

    def bucle() -> None:
        daemon_util.bucle_gateado(
            activo_fn=config.algoritmos_auto_activo,
            intervalo_seg_fn=lambda: intervalo,
            sweep_fn=ejecutar_barrido,
            log=_log,
        )

    hilo = threading.Thread(target=bucle, name="algoritmos-refresco-daemon", daemon=True)
    hilo.start()
    estado = "ACTIVO" if config.algoritmos_auto_activo() else "EN ESPERA (KENI_ALGORITMOS_AUTO off)"
    _log.info("Algoritmos auto-refresco %s, cada %.0f h.", estado, intervalo / 3600.0)
    return hilo
