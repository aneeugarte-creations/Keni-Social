"""Puente metricas -> priorizacion (Fase 5, loop de aprendizaje).

PROBLEMA QUE RESUELVE
=====================
La "lista viva" del dia (`priorizacion`/`api.panel`) ordena por señales que el contenido YA
tiene (prioridad, fecha, compromiso, frescura, viralidad). La Fase 5 quiere que, ADEMAS, lo
que HISTORICAMENTE rinde por marca pese un poco mas: si las piezas de una marca consiguen mas
engagement que las del resto, sus piezas del dia suben un escalon.

Este modulo traduce el rendimiento historico (engagement medio por marca, de la fachada de
metricas) en un mapa `marca -> bonus` que `priorizacion.ordenar_por_score` suma al score. El
bonus esta ACOTADO (0..`priorizacion.BONUS_METRICAS_MAX`) para empujar sin pisar al compromiso
humano ni a la fecha.

CONSERVADOR / DEGRADABLE (no rompe nada)
========================================
  - GATEADO por `KENI_PRIORIZA_METRICAS` (def OFF): sin el flag, `bonus_por_marca` devuelve un
    mapa vacio y la lista del dia ordena EXACTAMENTE como antes de la Fase 5.
  - BEST-EFFORT: lee la fachada de metricas `keni_metricas.servicio` (SOLO LECTURA, ADR 0005
    §Seams #6 — infra compartida, no un cruce de app). Si la fachada no esta disponible, una
    marca falla o no hay engagement, esa marca simplemente no recibe bonus (mapa parcial o vacio).
  - PURO el calculo: `bonus_desde_engagement` solo depende de sus argumentos (testeable sin red).

La FRONTERA con metricas se respeta: NO se importan internals del router `metricas`; se usa la
fachada `servicio` (lo mismo que hace `api.panel`) y la traduccion de id de marca de `marcas`.
"""

from __future__ import annotations

import logging

from . import config, marcas, priorizacion

_log = logging.getLogger("keni_consola.metricas_priorizacion")


def bonus_desde_engagement(engagement_por_marca: dict[str, float]) -> dict[str, float]:
    """Mapa `marca -> bonus` (0..`BONUS_METRICAS_MAX`) desde el engagement medio por marca.

    PURA y determinista. Escala RELATIVA: la marca con MAYOR engagement recibe el bonus maximo;
    el resto, proporcional a su engagement frente a ese maximo. Asi el bonus no depende de la
    magnitud absoluta del engagement (1% vs 10%), solo de quien rinde mas DENTRO del piloto.

    Reglas defensivas:
      - se ignoran marcas con engagement <=0, None o no numerico (no aportan señal),
      - si no queda ninguna marca con engagement >0, devuelve {} (sin bonus para nadie),
      - el maximo posible es exactamente `priorizacion.BONUS_METRICAS_MAX`.
    """
    validos: dict[str, float] = {}
    for marca, valor in engagement_por_marca.items():
        try:
            v = float(valor)
        except (TypeError, ValueError):
            continue
        if v > 0:
            validos[marca] = v
    if not validos:
        return {}
    tope = max(validos.values())
    if tope <= 0:
        return {}
    return {
        marca: round(priorizacion.BONUS_METRICAS_MAX * (v / tope), 2)
        for marca, v in validos.items()
    }


def _engagement_marca(marca_id: str, rango: str) -> float | None:
    """Engagement medio (%) historico de una marca via la fachada de metricas. None si no hay.

    BEST-EFFORT: cualquier fallo (fachada no disponible, marca fuera de alcance, sin piezas)
    devuelve None y se omite la marca. La fachada espera el id en forma `id_metricas`.
    """
    try:
        from keni_metricas import servicio  # perezoso: la fachada puede no estar instalada
    except Exception:  # noqa: BLE001 -- sin fachada de metricas: degrada a sin bonus
        return None
    try:
        analitica = servicio.construir_analitica_piezas(
            rango, marca=marcas.id_metricas_de(marca_id)
        )
    except Exception:  # noqa: BLE001 -- marca sin datos / fuera de alcance / fuente invalida
        return None
    engagement = (analitica or {}).get("engagement") or {}
    media = engagement.get("media")
    if media is None:
        return None
    try:
        return float(media)
    except (TypeError, ValueError):
        return None


def bonus_por_marca() -> dict[str, float]:
    """Mapa `id de marca -> bonus de priorizacion`, leyendo las metricas historicas.

    GATEADO por `KENI_PRIORIZA_METRICAS` (def OFF): si el flag esta apagado, devuelve {} y la
    priorizacion ordena como hoy. Con el flag ON, consulta el engagement medio por marca (la
    fachada de metricas) y lo convierte en un bonus RELATIVO acotado (`bonus_desde_engagement`).
    BEST-EFFORT de extremo a extremo: nunca lanza; un fallo global devuelve {}.
    """
    if not config.prioriza_metricas_activo():
        return {}
    try:
        rango = config.prioriza_metricas_rango()
        engagement: dict[str, float] = {}
        for marca_id in marcas.ids():
            media = _engagement_marca(marca_id, rango)
            if media is not None:
                engagement[marca_id] = media
        return bonus_desde_engagement(engagement)
    except Exception:  # noqa: BLE001 -- el bonus es opcional; nunca tumba la lista del dia
        _log.exception("No se pudo calcular el bonus de metricas para priorizacion.")
        return {}
