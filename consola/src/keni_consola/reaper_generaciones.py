"""Reaper de generaciones zombi: cierra las `ejecutando` huerfanas (proceso muerto).

PROBLEMA QUE RESUELVE
=====================
Una generacion nace `estado='ejecutando'` y solo pasa a terminal cuando corre su finalizador
(`generaciones.lanzar_job_*`). Si el PROCESO que la ejecuta muere a mitad (reinicio/deploy,
OOM, worker matado, o `generar()` de imagen colgado), el finalizador nunca corre y el registro
queda ZOMBI en `ejecutando` PARA SIEMPRE: el Monitor de Actividad lo muestra "Ejecutando…"
indefinidamente (no esta roto: refleja el estado real). El wall-timeout de `claude -p` solo
protege si el proceso sigue vivo, no ante una muerte del proceso.

SOLUCION
========
Un hilo demonio que barre periodicamente (y al arrancar) las generaciones `ejecutando` cuyo
`fecha_inicio` es mas viejo que `KENI_GENERACIONES_TTL_HORAS` (def 1 h) y las cierra como
`error`/`interrumpido` (`generaciones.reclamar_zombis`). El TTL es MUY superior al wall-timeout
(~10 min), asi una generacion realmente viva nunca se marca por error. El barrido al arrancar
limpia de inmediato los huerfanos que dejo el crash/deploy anterior.

SIEMPRE ACTIVO (no es una feature gateada): es un mecanismo de saneamiento. Vive en `__main__`
(servidor real), NO en `crear_app`, para no arrancarlo en los tests (igual que el resto de
daemons). El barrido es best-effort: un fallo se loguea y NO mata el hilo.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import UTC, datetime, timedelta

from . import config, daemon_util, generaciones
from .tiempo import iso_utc

_log = logging.getLogger("keni_consola.reaper_generaciones")

# TTL del saneo de QA 'en_curso' ≈ 2× el wall-timeout real de la criba: un zombi se detecta en
# minutos, y una criba VIVA nunca se toca (el doble del timeout deja margen de sobra al worker).
_FACTOR_TTL_QA_EN_CURSO = 2


def _ttl_qa_en_curso_seg() -> int:
    """TTL (s) del saneo de temas `verificar_veredicto='en_curso'` huérfanos.

    El override explícito (`KENI_QA_EN_CURSO_TTL_MIN`) manda; sin él, se DERIVA del timeout
    real de la criba (`config.qa_fuente_timeout()`; si está a 0 —sin endurecer—, rige el
    global `config.claude_timeout()`), x`_FACTOR_TTL_QA_EN_CURSO`. No duplica la constante.
    """
    if (os.environ.get(config.ENV_QA_EN_CURSO_TTL_MIN) or "").strip():
        return config.qa_en_curso_ttl_seg()
    return _FACTOR_TTL_QA_EN_CURSO * (config.qa_fuente_timeout() or config.claude_timeout())


def _sanear_qa_en_curso() -> int:
    """Saneo de temas del pipeline ZOMBI en `verificar_veredicto='en_curso'`. Devuelve cuántos tocó.

    La fase QA marca el tema `en_curso` ANTES de lanzar la criba; si el lanzamiento o la
    generación mueren sin finalizador, el tema quedaba excluido PARA SIEMPRE de `temas_sin_verificar`
    y contando en `temas_en_vuelo` (bloquea el cupo serial de su marca). Por cada zombi más
    viejo que el TTL (`_ttl_qa_en_curso_seg`, vs `actualizado`):
      - etapa Verificar ACTIVA para la marca -> se resetea a "" (re-criba en el barrido);
      - APAGADA (`KENI_PIPELINE_VERIFICAR` off, global o `::marca`) -> se marca `saltada`
        (CD lo recoge sin re-cribar; re-cribar con la etapa apagada lo dejaría zombi otra vez).
    WARN por tema (tema_id + marca + destino). El worker además sanea en caliente al cerrar un
    job de QA en error; esto es la red para las muertes no graciosas.
    """
    from . import repos
    from .pipeline_contenido import ORIGEN_PIPELINE, QA_EN_CURSO, QA_SALTADA

    umbral = iso_utc(datetime.now(UTC) - timedelta(seconds=_ttl_qa_en_curso_seg()))
    tocados = 0
    for tema in repos.listar_contenido():
        if (tema.get("origen") or "") != ORIGEN_PIPELINE:
            continue
        if (tema.get("verificar_veredicto") or "") != QA_EN_CURSO:
            continue
        # `actualizado` lo refresca cada escritura, incluida la que puso `en_curso`: un
        # `en_curso` legítimo y reciente NUNCA se toca. Sin fecha no hay evidencia: se respeta.
        actualizado = (tema.get("actualizado") or "").strip()
        if not actualizado or actualizado >= umbral:
            continue
        tema_id = (tema.get("id") or "").strip()
        marca = tema.get("marca") or ""
        verificar_activa = config.etapa_activa(config.ENV_PIPELINE_VERIFICAR, marca)
        nuevo = "" if verificar_activa else QA_SALTADA
        try:
            repos.actualizar_contenido(tema_id, {"verificar_veredicto": nuevo})
        except Exception:  # noqa: BLE001 -- best-effort por tema; el resto del saneo sigue
            _log.warning(
                "Reaper de generaciones: no se pudo sanear la QA zombi del tema %s.",
                tema_id, exc_info=True,
            )
            continue
        tocados += 1
        _log.warning(
            "Reaper de generaciones: QA 'en_curso' zombi del tema %s (marca %s) -> %s.",
            tema_id, marca, "re-criba" if verificar_activa else "saltada",
        )
    return tocados


def ejecutar_barrido() -> int:
    """Un barrido: reclama zombis y PODA registros viejos. Devuelve cuantas zombis cerro.

    Dos saneamientos en el mismo tick (reusa el scheduling del reaper, no abre un proceso
    nuevo): (1) cierra las `ejecutando` huerfanas (`reclamar_zombis`); (2) PODA los registros
    YAML fuera de la politica de retencion (`podar_generaciones`, #128), que acota disco +
    el escaneo de `_todas_ordenadas`. La poda es best-effort y NO afecta al valor devuelto
    (que sigue siendo el numero de zombis cerradas, contrato del reaper); un fallo se loguea
    y no aborta el barrido (asi un problema de poda nunca impide reclamar zombis).
    """
    n = generaciones.reclamar_zombis(config.generaciones_ttl_seg())
    if n:
        _log.info("Reaper de generaciones: %d generacion(es) zombi cerrada(s) como error.", n)
    try:
        generaciones.podar_generaciones()
    except Exception:  # noqa: BLE001 -- la poda es best-effort; no debe tumbar el barrido
        _log.warning("Reaper de generaciones: fallo la poda de registros viejos.", exc_info=True)
    # Tercer saneamiento: lotes de cajones ZOMBI atascados en `parseando`. Si el worker muere
    # entre el INSERT de los ítems y el UPDATE del lote, el lote queda `parseando` para siempre
    # (spinner "Procesando con Haiku…" eterno en el SPA + lote no borrable). Mismo TTL que las
    # generaciones zombi (muy superior al wall-timeout, así nunca toca un parseo vivo). El
    # `creado` del lote es ISO naive local, así que el umbral también lo es. Best-effort.
    try:
        from . import repos

        umbral = iso_utc(
            datetime.now(UTC) - timedelta(seconds=config.generaciones_ttl_seg())
        )
        m = repos.sanear_lotes_parseando_huerfanos(umbral)
        if m:
            _log.info("Reaper de generaciones: %d lote(s) de cajón zombi reconciliado(s).", m)
    except Exception:  # noqa: BLE001 -- saneamiento aditivo; un fallo no debe tumbar el barrido
        _log.warning("Reaper de generaciones: fallo el saneo de lotes de cajón.", exc_info=True)
    # Cuarto saneamiento: temas del pipeline ZOMBI en `verificar_veredicto='en_curso'` (detalle en
    # `_sanear_qa_en_curso`): TTL derivado del timeout real de la criba (~2×) y, con la etapa
    # de Validación apagada, el zombi pasa a `saltada` (CD lo recoge) en vez de re-cribarse.
    try:
        z = _sanear_qa_en_curso()
        if z:
            _log.info(
                "Reaper de generaciones: %d tema(s) con QA 'en_curso' zombi saneado(s).", z
            )
    except Exception:  # noqa: BLE001 -- saneamiento aditivo; un fallo no debe tumbar el barrido
        _log.warning("Reaper de generaciones: fallo el saneo de QA en_curso.", exc_info=True)
    return n


def _resumen_barrido(n: int) -> str:
    """Resumen corto del barrido del reaper para el historial (zombis cerradas)."""
    return f"{n} generación(es) zombi cerrada(s)" if n else "sin novedad"


def iniciar_reaper(intervalo_segundos: float | None = None) -> threading.Thread:
    """Arranca el hilo demonio del reaper (SIEMPRE activo). Barre al arrancar y cada N min.

    Pensado para el servidor real (`__main__`), NO para `crear_app` (los tests no lo arrancan).
    El hilo es daemon; un fallo de barrido se loguea y NO lo mata.
    """
    intervalo = (
        intervalo_segundos if intervalo_segundos is not None else float(config.reaper_intervalo_seg())
    )

    def bucle() -> None:
        daemon_util.bucle_gateado(
            activo_fn=lambda: True,  # saneamiento: siempre activo
            intervalo_seg_fn=lambda: intervalo,
            sweep_fn=ejecutar_barrido,
            log=_log,
            resumen_fn=_resumen_barrido,
        )

    hilo = threading.Thread(target=bucle, name="reaper-generaciones-daemon", daemon=True)
    hilo.start()
    _log.info(
        "Reaper de generaciones ACTIVO cada %.0f min (TTL %.0f h).",
        intervalo / 60.0, config.generaciones_ttl_seg() / 3600.0,
    )
    return hilo
