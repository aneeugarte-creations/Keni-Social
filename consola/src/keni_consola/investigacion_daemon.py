"""Daemon de Agentes de investigacion (Ola 6).

PROBLEMA QUE RESUELVE
=====================
Los briefs de investigacion pueden correrse a demanda (boton en la UI), pero el daemon
permite que el sistema los corra periodicamente: barre los briefs activos, lanza cada
uno con `dominio.investigacion_agente.correr_brief` y deposita candidatos fechados para
revision humana. El equipo llega y encuentra candidatos del dia listos para aceptar o
descartar; NUNCA se auto-crea contenido en el tablero.

SEGURO POR DISEÑO (CONSERVADOR)
================================
  - GATEADO: el daemon solo barre con `KENI_INVESTIGACION_AUTO=1` (def OFF). Sin el flag
    el hilo arranca pero NO hace nada; el equipo corre los briefs a demanda.
  - SOLO CANDIDATOS: no crea tablero, no genera copy, no publica.
  - DEDUP por (enlace, titulo+dia): no se repite un candidato ya existente para la misma
    fecha (evita inundar al equipo barrido tras barrido con los mismos temas).
  - CAP por barrido (`KENI_INVESTIGACION_MAX`, def 5): total de candidatos a insertar
    en un ciclo; no el total por brief (cada brief puede traer varios).
  - BEST-EFFORT: un fallo de un brief se loguea y NO mata el hilo; los otros siguen.
"""

from __future__ import annotations

import logging
import threading
import unicodedata
from datetime import date
from typing import Any

from . import config, daemon_util, repos
from .dominio import investigacion_agente

_log = logging.getLogger("keni_consola.investigacion_daemon")


# --------------------------------------------------------------------------- #
# Dedup                                                                        #
# --------------------------------------------------------------------------- #


def _normaliza(texto: str) -> str:
    """Minusculas, sin acentos, espacios colapsados (para dedup)."""
    s = unicodedata.normalize("NFKD", texto or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.strip().lower().split())


def _claves_existentes(fecha: str) -> set[str]:
    """Claves (enlace canonico y titulo+dia) de candidatos ya existentes para la fecha.

    Cada candidato con enlace no vacio aporta su enlace normalizado; todos aportan
    `titulo_norm|fecha` como segunda clave. Best-effort: un fallo devuelve set vacio.
    """
    try:
        existentes = repos.listar_inv_candidatos(fecha=fecha)
    except Exception:  # noqa: BLE001
        _log.exception("investigacion_daemon: no se pudo leer candidatos existentes.")
        return set()
    claves: set[str] = set()
    for c in existentes:
        enlace = (c.get("enlace") or "").strip()
        if enlace:
            claves.add(_normaliza(enlace))
        titulo = _normaliza(c.get("titulo") or "")
        if titulo:
            claves.add(f"{titulo}|{fecha}")
    return claves


def _filtrar_nuevos(
    candidatos: list[dict[str, Any]],
    *,
    fecha: str,
    ya_existentes: set[str],
    cap_restante: int,
) -> list[dict[str, Any]]:
    """De la lista de candidatos del agente, devuelve solo los que no estan en `ya_existentes`.

    PURA y testeable. Respeta `cap_restante` y actualiza `ya_existentes` en memoria
    para que multiples briefs en el mismo barrido no se dupliquen entre si.
    """
    nuevos: list[dict[str, Any]] = []
    for cand in candidatos:
        if len(nuevos) >= cap_restante:
            break
        enlace = _normaliza(cand.get("enlace") or "")
        titulo = _normaliza(cand.get("titulo") or "")
        if enlace and enlace in ya_existentes:
            continue
        clave_t = f"{titulo}|{fecha}"
        if titulo and clave_t in ya_existentes:
            continue
        nuevos.append(cand)
        if enlace:
            ya_existentes.add(enlace)
        if titulo:
            ya_existentes.add(clave_t)
    return nuevos


# --------------------------------------------------------------------------- #
# Barrido principal                                                            #
# --------------------------------------------------------------------------- #


def ejecutar_barrido() -> int:
    """Corre todos los briefs activos y deposita candidatos (best-effort).

    Devuelve el total de candidatos insertados en este barrido.
    """
    hoy = date.today().isoformat()
    cap_total = config.investigacion_max()
    briefs = repos.listar_inv_briefs(solo_activos=True)
    if not briefs:
        return 0

    ya_existentes = _claves_existentes(hoy)
    total_insertados = 0

    for brief in briefs:
        cap_restante = cap_total - total_insertados
        if cap_restante <= 0:
            break
        try:
            candidatos, errores = investigacion_agente.correr_brief(brief, fecha=hoy)
        except Exception:  # noqa: BLE001 -- un brief que falla no mata el daemon
            _log.exception(
                "investigacion_daemon: fallo al correr brief '%s' (%s).",
                brief.get("nombre", "?"), brief.get("id", "?"),
            )
            continue
        if errores:
            _log.debug(
                "investigacion_daemon: brief '%s' reporto %d error(es).",
                brief.get("nombre", "?"), len(errores),
            )
        nuevos = _filtrar_nuevos(candidatos, fecha=hoy, ya_existentes=ya_existentes, cap_restante=cap_restante)
        if not nuevos:
            continue
        insertados = repos.crear_inv_candidatos(nuevos)
        total_insertados += len(insertados)
        _log.info(
            "investigacion_daemon: brief '%s' -> %d candidato(s) nuevos (hoy=%s).",
            brief.get("nombre", "?"), len(insertados), hoy,
        )

    if total_insertados:
        _log.info("investigacion_daemon: barrido completo, %d candidato(s) insertados.", total_insertados)
    return total_insertados


# --------------------------------------------------------------------------- #
# Arranque del hilo                                                            #
# --------------------------------------------------------------------------- #


def _intervalo_segundos() -> float:
    return config.investigacion_intervalo_horas() * 3600.0


def iniciar_investigacion(intervalo_segundos: float | None = None) -> threading.Thread:
    """Arranca el hilo daemon de investigacion (GATEADO EN VIVO).

    El hilo arranca SIEMPRE y comprueba `KENI_INVESTIGACION_AUTO` en cada ciclo: apagar/
    encender en runtime aplica sin reiniciar el proceso. Sin el flag (def OFF) el hilo
    corre pero no barre nada. Los candidatos que produce son PROPUESTAS; NUNCA auto-tablero.
    """
    intervalo = intervalo_segundos if intervalo_segundos is not None else _intervalo_segundos()

    def bucle() -> None:
        daemon_util.bucle_gateado(
            activo_fn=config.gate_maquina(config.investigacion_auto_activa),
            intervalo_seg_fn=lambda: intervalo,
            sweep_fn=ejecutar_barrido,
            log=_log,
        )

    hilo = threading.Thread(target=bucle, name="investigacion-daemon", daemon=True)
    hilo.start()
    estado = "ACTIVO" if config.investigacion_auto_activa() else "EN ESPERA (KENI_INVESTIGACION_AUTO off)"
    _log.info(
        "Investigacion daemon %s, cada %.0f h (max=%d).",
        estado, intervalo / 3600.0, config.investigacion_max(),
    )
    return hilo
