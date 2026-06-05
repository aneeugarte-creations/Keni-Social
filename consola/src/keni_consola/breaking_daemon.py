"""Daemon del Carril Rápido de Breaking (Claro Sports).

PROBLEMA QUE RESUELVE
=====================
El Carril Rápido expone los temas breaking de Claro Sports para que el equipo prepare
un borrador con un tap en la UI. Sin el daemon, el equipo activa cada borrador a mano.
Con el daemon encendido (`KENI_BREAKING=1`), el sistema lo hace solo: barre el snapshot
del Investigador cada N minutos, detecta temas breaking de Claro Sports sin borrador y
pre-genera copy en segundo plano. El equipo llega y sólo tiene que revisar y publicar.

SEGURO POR DISEÑO (CONSERVADOR)
================================
  - GATEADO: el daemon sólo materializa con `KENI_BREAKING=1` (def OFF).
    Sin el flag, el hilo arranca pero NO hace nada; el equipo sigue con el tap manual.
  - SÓLO BORRADORES: el copy generado entra al flujo de revisión humana normal.
    La publicación real sigue gateada por `KENI_PUBLICAR_REAL` (OFF).
  - CAP por barrido (`KENI_BREAKING_MAX`, def 3): cada item lanza un `claude -p`.
  - DEDUP: no se re-genera si ya hay un borrador con `origen='breaking'` para ese título.
  - MARCA FIJA: Claro Sports (el carril breaking es específico de este piloto).
  - BEST-EFFORT: ningún fallo por item mata el hilo; se loguea y se sigue.

Reutiliza `autogen_copy.lanzar_para_topic` (mismo camino que el botón manual) y
`dominio.breaking.items_breaking` (helper puro de selección).
"""

from __future__ import annotations

import logging
import threading
from datetime import date
from typing import Any

from . import autogen_copy, config, daemon_util, marcas, repos
from .dominio import breaking as dom_breaking

_log = logging.getLogger("keni_consola.breaking_daemon")

# Marca para la que opera el daemon (el carril breaking es de Claro Sports).
_MARCA_BREAKING = "claro-sports"


def _titulos_ya_preparados(marca: str) -> set[str]:
    """Claves de título de los borradores breaking existentes para la marca (dedup).

    Lee los contenidos con `origen='breaking'` del tablero y devuelve sus claves de dedup
    para que el daemon no re-genere lo que ya existe. Best-effort → set vacío.
    """
    try:
        todos = repos.listar_contenido(marca=marca, clase="contenido")
        return {
            dom_breaking.clave_de_titulo((it.get("titulo") or "").strip())
            for it in todos
            if (it.get("origen") or "") == "breaking"
        }
    except Exception:  # noqa: BLE001
        _log.exception("breaking_daemon: no se pudo leer los borradores existentes (marca=%s)", marca)
        return set()


def items_a_preparar(
    items: list[dict[str, Any]],
    *,
    maximo: int,
    ya_preparados: set[str],
) -> list[dict[str, Any]]:
    """Subconjunto de `items` breaking que aún no tienen borrador (PURA, testeable).

    Reglas:
      - No están en `ya_preparados` (dedup por clave de título).
      - Se respeta el `maximo` (cap por barrido).
    """
    elegidos: list[dict[str, Any]] = []
    for item in items:
        if len(elegidos) >= maximo:
            break
        titulo = (item.get("titulo") or "").strip()
        clave = dom_breaking.clave_de_titulo(titulo)
        if not clave:
            continue
        if clave in ya_preparados:
            continue
        elegidos.append(item)
    return elegidos


def ejecutar_barrido() -> list[dict[str, Any]]:
    """Un barrido: selecciona temas breaking sin borrador y prepara drafts + copy.

    Best-effort por item: un fallo se loguea y no mata el barrido.
    """
    if not marcas.es_marca(_MARCA_BREAKING):
        return []

    geo = config.radar_auto_geo()
    items = dom_breaking.items_breaking(_MARCA_BREAKING, geo)
    if not items:
        return []

    ya_preparados = _titulos_ya_preparados(_MARCA_BREAKING)
    a_preparar = items_a_preparar(
        items,
        maximo=config.breaking_max(),
        ya_preparados=ya_preparados,
    )

    preparados: list[dict[str, Any]] = []
    for item in a_preparar:
        try:
            contenido_item = repos.crear_contenido(
                clase="contenido",
                flujo="importante",
                titulo=(item.get("titulo") or "").strip(),
                descripcion=(item.get("por_que") or "").strip(),
                marca=_MARCA_BREAKING,
                prioridad="alta",
                fecha_objetivo=date.today().isoformat(),
                autor=None,
                origen="breaking",
                tipo_contenido="fuente",
            )
        except Exception:  # noqa: BLE001
            _log.exception(
                "breaking_daemon: fallo al crear el borrador (titulo=%s)", item.get("titulo")
            )
            continue

        # Encolar copy (best-effort: si falla no tumba la creación del borrador).
        try:
            autogen_copy.lanzar_para_topic(contenido_item)
        except Exception:  # noqa: BLE001
            _log.exception(
                "breaking_daemon: fallo al encolar copy (contenido_id=%s)", contenido_item.get("id")
            )

        preparados.append(contenido_item)

    if preparados:
        _log.info(
            "Breaking daemon: %d borrador(es) preparados para %s.",
            len(preparados), _MARCA_BREAKING,
        )
    return preparados


def _intervalo_segundos() -> float:
    return config.breaking_intervalo_min() * 60.0


def iniciar_breaking(intervalo_segundos: float | None = None) -> threading.Thread:
    """Arranca el hilo demonio del Carril Rápido de Breaking (GATEADO EN VIVO).

    Espejo de `iniciar_autogen`: el hilo arranca SIEMPRE y comprueba `KENI_BREAKING` en
    cada ciclo, así que encender/apagar en runtime aplica sin reiniciar. El hilo es daemon;
    un fallo de barrido se loguea y NO lo mata. Pensado para el servidor real (`daemons.py`),
    NO para `crear_app` (los tests no lo arrancan).
    """
    intervalo = intervalo_segundos if intervalo_segundos is not None else _intervalo_segundos()

    def bucle() -> None:
        daemon_util.bucle_gateado(
            activo_fn=config.gate_maquina(config.breaking_auto_activo),
            intervalo_seg_fn=lambda: intervalo,
            sweep_fn=ejecutar_barrido,
            log=_log,
        )

    hilo = threading.Thread(target=bucle, name="breaking-daemon", daemon=True)
    hilo.start()
    estado = "ACTIVO" if config.breaking_auto_activo() else "EN ESPERA (KENI_BREAKING off)"
    _log.info(
        "Breaking daemon %s, cada %.0f min (max/barrido=%d).",
        estado, intervalo / 60.0, config.breaking_max(),
    )
    return hilo
