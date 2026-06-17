"""Paso de FUSIONAR SEMÁNTICAMENTE (Fase 2b): fusiona con Haiku las historias del mismo evento."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import keni_consola.recolectar_daemon as _pkg

from ... import config, marcas, repos
from ...dominio import fusionar_semantica, traducir
from .. import _comun
from .._comun import _log


def paso_fusionar_semantica(
    *,
    ejecutor: fusionar_semantica.Ejecutor | None = None,
    recientes: list[dict[str, Any]] | None = None,
    forzar: bool = False,
) -> dict[str, Any]:
    """Fusiona con IA (Haiku) las historias del MISMO evento, por marca. Gateado `KENI_PIPELINE_FUSIONAR` (def ON).

    Por marca, manda hasta `KENI_FUSION_SEMANTICA_MAX` historias `nuevo` recientes a Haiku para que
    agrupe las del mismo acontecimiento, y fusiona cada grupo (`_fusionar_grupo`). Es la VÍA REAL de
    agrupación de historias del mismo evento con titulares distintos (la formación de clusters solo
    dedup-ea EXACTO: url canónica o hash de título). Best-effort: un fallo por marca/grupo se loguea
    y no aborta el paso. Devuelve `{grupos, fusionadas}`.

    Throttle: como mucho una pasada por `_FUSIONAR_INTERVALO_SEG` (no re-llamar a Haiku en cada tick
    de 30s); `forzar=True` lo salta (tests). `recientes` (opcional): los clusters de la ventana YA
    cargados por el paso de agrupar del MISMO barrido (evita re-leer la BD). None = leer de
    `repos.clusters_recientes`.
    """
    if not config.fusionar_semantica_activo():
        return {"grupos": 0, "fusionadas": 0}
    ahora_mono = time.monotonic()
    if (
        not forzar
        and _comun._ultimo_fusionar
        and (ahora_mono - _comun._ultimo_fusionar) < _comun._FUSIONAR_INTERVALO_SEG
    ):
        return {"grupos": 0, "fusionadas": 0}
    ventana_h = config.cluster_ventana_h()
    maximo = config.fusion_semantica_max()
    pesos = config.score_pesos()
    breaking_peso = config.cluster_breaking_peso()
    breaking_ventana_h = config.cluster_breaking_ventana_h()
    fuentes_baja = config.fuentes_baja_confianza()
    perfil_activo = config.priorizar_perfil_activo()
    ahora = datetime.now(UTC)

    if recientes is not None:
        recientes_todas = recientes
    else:
        try:
            recientes_todas = repos.clusters_recientes(ventana_h)
        except Exception:  # noqa: BLE001 -- sin pool legible, no se fusiona nada
            _log.exception("recolectar_daemon: no se pudieron leer historias para fusionar.")
            return {"grupos": 0, "fusionadas": 0}

    por_marca: dict[str, list[dict[str, Any]]] = {}
    for c in recientes_todas:
        if (c.get("estado") or "nuevo") == "nuevo":
            por_marca.setdefault(c.get("marca") or "", []).append(c)

    grupos_total = 0
    fusionadas_total = 0
    for marca_f, recientes in por_marca.items():
        if len(recientes) < 2:
            continue
        # Excepción por marca (toggle "Fusionar"): si está apagada para esta marca, no se fusiona.
        if config.marca_apagada(config.ENV_PIPELINE_FUSIONAR, marca_f):
            continue
        lote = recientes[:maximo]
        por_id = {str(c["id"]): c for c in lote}
        # Descarta métricas residuales de pasos previos del hilo: lo acumulado a partir de
        # aquí es el coste de Fusionar de ESTA marca (lo sella el registro de actividad).
        traducir.tomar_metricas_acumuladas()
        # Capturamos el PROMPT y la SALIDA reales de Haiku (para la transparencia de la actividad).
        haiku: dict[str, str] = {"prompt": "", "salida": ""}
        try:
            grupos = fusionar_semantica.proponer_fusiones(
                lote, ejecutor=ejecutor,
                al_ejecutar=lambda p, s, _h=haiku: _h.update(prompt=p, salida=s),
            )
        except Exception:  # noqa: BLE001 -- un fallo de Haiku por marca no aborta el paso
            _log.exception("recolectar_daemon: fallo proponiendo fusiones de una marca.")
            continue
        grupos_marca = 0
        fusionadas_marca = 0
        descripciones: list[str] = []
        for grupo in grupos:
            try:
                if _pkg._fusionar_grupo(
                    grupo, por_id, pesos=pesos, breaking_peso=breaking_peso,
                    breaking_ventana_h=breaking_ventana_h, fuentes_baja=fuentes_baja,
                    perfil_activo=perfil_activo, ahora=ahora,
                ):
                    grupos_total += 1
                    fusionadas_total += len(grupo) - 1
                    grupos_marca += 1
                    fusionadas_marca += len(grupo) - 1
                    titulos = [str((por_id.get(i) or {}).get("titulo") or i).strip() for i in grupo]
                    descripciones.append(" + ".join(t for t in titulos if t))
            except Exception:  # noqa: BLE001 -- un fusionado problemático no aborta el paso
                _log.exception("recolectar_daemon: fallo al fusionar un grupo de historias.")
        # Actividad IA: deja constancia VISIBLE de la dedup semántica por marca, con el Haiku REAL
        # (prompt + salida) y un resumen humano de qué historias se unieron.
        if grupos_marca:
            resumen = (
                "Historias del mismo acontecimiento unidas por IA (dedup semántico):\n"
                + "\n".join(f"• {d}" for d in descripciones)
            )
            salida_real = haiku["salida"].strip()
            salida = (f"{salida_real}\n\n— — —\n{resumen}" if salida_real else resumen)
            _pkg._registrar_actividad_ia(
                marca_f,
                f"Fusionar historias — {marcas.etiqueta_de(marca_f)}: "
                f"{fusionadas_marca} absorbida(s) en {grupos_marca} grupo(s)",
                salida,
                prompt=haiku["prompt"],
            )
    _comun._ultimo_fusionar = ahora_mono
    if grupos_total:
        _log.info(
            "recolectar_daemon: fusionar semántico: %d grupo(s), %d historia(s) absorbida(s).",
            grupos_total, fusionadas_total,
        )
    return {"grupos": grupos_total, "fusionadas": fusionadas_total}
