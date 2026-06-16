"""Limpiador de generaciones colgadas: cierra las `ejecutando` sueltas (proceso muerto).

PROBLEMA QUE RESUELVE
=====================
Una generacion nace `estado='ejecutando'` y solo pasa a terminal cuando corre su finalizador
(`generaciones.lanzar_job_*`). Si el PROCESO que la ejecuta muere a mitad (reinicio/deploy,
OOM, worker matado, o `generar()` de imagen colgado), el finalizador nunca corre y el registro
queda COLGADA en `ejecutando` PARA SIEMPRE: el Monitor de Actividad lo muestra "Ejecutando…"
indefinidamente (no esta roto: refleja el estado real). El wall-timeout de `claude -p` solo
protege si el proceso sigue vivo, no ante una muerte del proceso.

SOLUCION
========
Un hilo demonio que barre periodicamente (y al arrancar) las generaciones `ejecutando` cuyo
`fecha_inicio` es mas viejo que `KENI_GENERACIONES_TTL_HORAS` (def 1 h) y las cierra como
`error`/`interrumpido` (`generaciones.reclamar_atascadas`). El TTL es MUY superior al wall-timeout
(~10 min), asi una generacion realmente viva nunca se marca por error. El barrido al arrancar
limpia de inmediato los sueltos que dejo el crash/deploy anterior.

SIEMPRE ACTIVO (no es una feature gateada): es un mecanismo de reparación. Vive en `__main__`
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

_log = logging.getLogger("keni_consola.limpiador_generaciones")

# TTL de la reparación de QA 'en_curso' ≈ 2× el wall-timeout real de la verificación: una colgada se detecta en
# minutos, y una verificación VIVA nunca se toca (el doble del timeout deja margen de sobra al worker).
_FACTOR_TTL_VERIFICACION_EN_CURSO = 2


def _ttl_verificacion_en_curso_seg() -> int:
    """TTL (s) de la reparación de temas `verificacion_fuente='en_curso'` sueltos.

    El override explícito (`KENI_VERIFICACION_EN_CURSO_TTL_MIN`) manda; sin él, se DERIVA del timeout
    real de la verificación (`config.verificacion_fuente_timeout()`; si está a 0 —sin endurecer—, rige el
    global `config.claude_timeout()`), x`_FACTOR_TTL_VERIFICACION_EN_CURSO`. No duplica la constante.
    """
    if (os.environ.get(config.ENV_VERIFICACION_EN_CURSO_TTL_MIN) or "").strip():
        return config.verificacion_en_curso_ttl_seg()
    return _FACTOR_TTL_VERIFICACION_EN_CURSO * (config.verificacion_fuente_timeout() or config.claude_timeout())


def _reparar_verificacion_en_curso() -> int:
    """Reparación de temas del pipeline COLGADOS en `verificacion_fuente='en_curso'`. Devuelve cuántos tocó.

    La fase QA marca el tema `en_curso` ANTES de lanzar la verificación; si el lanzamiento o la
    generación mueren sin finalizador, el tema quedaba sin re-verificar PARA SIEMPRE
    y contando en `temas_en_proceso` (bloquea el cupo serial de su marca). Por cada colgado más
    viejo que el TTL (`_ttl_verificacion_en_curso_seg`, vs `actualizado`):
      - etapa Verificar ACTIVA para la marca -> se resetea a "" (re-verificación en el barrido);
      - APAGADA (`KENI_PIPELINE_VERIFICAR` off, global o `::marca`) -> se marca `saltada`
        (CD lo recoge sin re-verificar; re-verificar con la etapa apagada lo dejaría colgado otra vez).
    WARN por tema (tema_id + marca + destino). El worker además repara en caliente al cerrar un
    job de QA en error; esto es la red para las muertes no limpias.
    """
    from . import repos
    from .pipeline_contenido import ORIGEN_PIPELINE, VERIFICACION_EN_CURSO, VERIFICACION_SALTADA

    umbral = iso_utc(datetime.now(UTC) - timedelta(seconds=_ttl_verificacion_en_curso_seg()))
    tocados = 0
    for tema in repos.listar_contenido():
        if (tema.get("origen") or "") != ORIGEN_PIPELINE:
            continue
        if (tema.get("verificacion_fuente") or "") != VERIFICACION_EN_CURSO:
            continue
        # `actualizado` lo refresca cada escritura, incluida la que puso `en_curso`: un
        # `en_curso` legítimo y reciente NUNCA se toca. Sin fecha no hay evidencia: se respeta.
        actualizado = (tema.get("actualizado") or "").strip()
        if not actualizado or actualizado >= umbral:
            continue
        tema_id = (tema.get("id") or "").strip()
        marca = tema.get("marca") or ""
        verificar_activa = config.etapa_activa(config.ENV_PIPELINE_VERIFICAR, marca)
        nuevo = "" if verificar_activa else VERIFICACION_SALTADA
        try:
            repos.actualizar_contenido(tema_id, {"verificacion_fuente": nuevo})
        except Exception:  # noqa: BLE001 -- best-effort por tema; el resto de la reparación sigue
            _log.warning(
                "Limpiador de generaciones: no se pudo reparar la QA colgada del tema %s.",
                tema_id, exc_info=True,
            )
            continue
        tocados += 1
        _log.warning(
            "Limpiador de generaciones: QA 'en_curso' colgada del tema %s (marca %s) -> %s.",
            tema_id, marca, "re-verificación" if verificar_activa else "saltada",
        )
    return tocados


def ejecutar_barrido() -> int:
    """Un barrido: reclama las colgadas y BORRA registros viejos. Devuelve cuantas colgadas cerro.

    Dos reparaciones en el mismo tick (reusa el scheduling del limpiador, no abre un proceso
    nuevo): (1) cierra las `ejecutando` sueltas (`reclamar_atascadas`); (2) BORRA los registros
    YAML fuera de la politica de retencion (`purgar_generaciones`, #128), que acota disco +
    el escaneo de `_todas_ordenadas`. El borrado es best-effort y NO afecta al valor devuelto
    (que sigue siendo el numero de colgadas cerradas, contrato del limpiador); un fallo se loguea
    y no aborta el barrido (asi un problema de borrado nunca impide reclamar atascadas).
    """
    n = generaciones.reclamar_atascadas(config.generaciones_ttl_seg())
    if n:
        _log.info("Limpiador de generaciones: %d generacion(es) colgada(s) cerrada(s) como error.", n)
    try:
        generaciones.purgar_generaciones()
    except Exception:  # noqa: BLE001 -- el borrado es best-effort; no debe tumbar el barrido
        _log.warning("Limpiador de generaciones: fallo el borrado de registros viejos.", exc_info=True)
    # Tercera reparación: lotes de cajones COLGADOS atascados en `parseando`. Si el worker muere
    # entre el INSERT de los ítems y el UPDATE del lote, el lote queda `parseando` para siempre
    # (spinner "Procesando con Haiku…" eterno en el SPA + lote no borrable). Mismo TTL que las
    # generaciones colgadas (muy superior al wall-timeout, así nunca toca un parseo vivo). El
    # `creado` del lote es ISO naive local, así que el umbral también lo es. Best-effort.
    try:
        from . import repos

        umbral = iso_utc(
            datetime.now(UTC) - timedelta(seconds=config.generaciones_ttl_seg())
        )
        m = repos.reparar_lotes_parseando_sueltos(umbral)
        if m:
            _log.info("Limpiador de generaciones: %d lote(s) de cajón colgado reconciliado(s).", m)
    except Exception:  # noqa: BLE001 -- reparación aditiva; un fallo no debe tumbar el barrido
        _log.warning("Limpiador de generaciones: fallo la reparación de lotes de cajón.", exc_info=True)
    # Cuarta reparación: temas del pipeline COLGADOS en `verificacion_fuente='en_curso'` (detalle en
    # `_reparar_verificacion_en_curso`): TTL derivado del timeout real de la verificación (~2×) y, con la etapa
    # de Validación apagada, el colgado pasa a `saltada` (CD lo recoge) en vez de re-verificarse.
    try:
        z = _reparar_verificacion_en_curso()
        if z:
            _log.info(
                "Limpiador de generaciones: %d tema(s) con QA 'en_curso' colgada reparado(s).", z
            )
    except Exception:  # noqa: BLE001 -- reparación aditiva; un fallo no debe tumbar el barrido
        _log.warning("Limpiador de generaciones: fallo la reparación de QA en_curso.", exc_info=True)
    return n


def _resumen_barrido(n: int) -> str:
    """Resumen corto del barrido del limpiador para el historial (colgadas cerradas)."""
    return f"{n} generación(es) colgada(s) cerrada(s)" if n else "sin novedad"


def iniciar_limpiador(intervalo_segundos: float | None = None) -> threading.Thread:
    """Arranca el hilo demonio del limpiador (SIEMPRE activo). Barre al arrancar y cada N min.

    Pensado para el servidor real (`__main__`), NO para `crear_app` (los tests no lo arrancan).
    El hilo es daemon; un fallo de barrido se loguea y NO lo mata.
    """
    intervalo = (
        intervalo_segundos if intervalo_segundos is not None else float(config.limpiador_intervalo_seg())
    )

    def bucle() -> None:
        daemon_util.bucle_gateado(
            activo_fn=lambda: True,  # reparación: siempre activo
            intervalo_seg_fn=lambda: intervalo,
            sweep_fn=ejecutar_barrido,
            log=_log,
            resumen_fn=_resumen_barrido,
        )

    hilo = threading.Thread(target=bucle, name="limpiador-generaciones-daemon", daemon=True)
    hilo.start()
    _log.info(
        "Limpiador de generaciones ACTIVO cada %.0f min (TTL %.0f h).",
        intervalo / 60.0, config.generaciones_ttl_seg() / 3600.0,
    )
    return hilo
