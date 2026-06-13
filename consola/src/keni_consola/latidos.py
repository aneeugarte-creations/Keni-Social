"""Latidos de los daemons de fondo: fachada BEST-EFFORT sobre `db_latidos`.

QUÉ RESUELVE (auditoría 2026-06, observabilidad): hasta ahora el único signo de vida de
los daemons era el log. Si un hilo moría o un barrido llevaba horas fallando, nadie lo
veía sin entrar por ssh. Con esto cada daemon deja un LATIDO persistido (tabla
`daemon_latidos`) en cada vuelta del bucle y en cada barrido, y el panel Sistema lo
muestra (endpoint `/api/sistema/daemons`), juzgando "atrasado" sin conocer la config.

CONTRATO DE SEGURIDAD: registrar un latido NUNCA rompe un barrido ni mata un hilo.
Todas las funciones capturan cualquier excepción (BD caída, esquema a medias, sin
DATABASE_URL en unit tests) y la degradan a un log debug. Además el latido de CICLO se
THROTTLEA (mínimo `_MIN_ENTRE_CICLOS_SEG` entre escrituras por daemon) para que un tick
corto no meta escrituras innecesarias.

Aparte de la tabla, este módulo mantiene el FICHERO de latido del PROCESO `daemons`
(`tocar_fichero`, lo escribe el bucle principal de `keni_consola.daemons`): es lo que
sondea el healthcheck del contenedor en deploy (sin depender de la BD para liveness).
"""
from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from typing import Any

_log = logging.getLogger("keni_consola.latidos")

# Nombre estable por módulo del sweep: los daemons gateados NO pasan nombre (bucle_gateado
# lo deriva del módulo de su `sweep_fn`); estos alias pulen los casos poco legibles para
# que el panel muestre nombres cortos y estables aunque el módulo se renombre.
_ALIAS = {
    "ingesta_daemon": "ingesta",
    "media_gc_daemon": "media_gc",
    "noticias_gc_daemon": "noticias_gc",
    "trends_daemon": "trends",
    "algoritmos_refresco": "algoritmos",
    "patrones_refresco": "patrones",
    "reaper_generaciones": "reaper",
    "eventos_scanner": "vencimientos",
    "sugerencias_editoriales": "sugerencias",
}

# Daemons RETIRADOS/renombrados: sus filas viejas pueden seguir en `daemon_latidos`
# (el upsert nunca borra) pero ya no hay hilo que las actualice; la sonda del panel
# (`api.sistema.sonda_daemons`) las IGNORA para no pintar falsos "atrasado".
#   - "pipeline": el hilo único del pipeline se partió en "investigacion" + "produccion"
#     (cada loop late con su propio nombre); la fila vieja quedó huérfana.
RETIRADOS = frozenset({"pipeline"})

# Mínimo entre DOS latidos de ciclo del mismo daemon (las de barrido no se throttlean:
# son una por sweep y traen el resultado). 30s mantiene el panel fresco con coste nulo.
_MIN_ENTRE_CICLOS_SEG = 30.0
_ultimo_ciclo: dict[str, float] = {}

# Fichero de latido del PROCESO daemons (healthcheck del contenedor). Override por env
# para tests/local; el default vive en /tmp (efímero, fuera del volumen de datos).
ENV_FICHERO_LATIDO = "KENI_DAEMONS_LATIDO_FICHERO"
_FICHERO_LATIDO_DEF = "/tmp/keni-daemons.latido"  # noqa: S108 -- señal de liveness, sin datos


def nombre_de_sweep(sweep_fn: Callable[[], Any]) -> str:
    """Nombre estable del daemon a partir del módulo donde vive su `sweep_fn`."""
    modulo = getattr(sweep_fn, "__module__", "") or ""
    corto = modulo.rsplit(".", 1)[-1] or "desconocido"
    return _ALIAS.get(corto, corto)


def ciclo(daemon: str, *, activo: bool, intervalo_seg: float, tick_seg: float) -> None:
    """Latido de CICLO (el bucle dio una vuelta), throttleado y best-effort."""
    ahora = time.monotonic()
    if ahora - _ultimo_ciclo.get(daemon, 0.0) < _MIN_ENTRE_CICLOS_SEG:
        return
    try:
        from . import db_latidos

        db_latidos.latido_ciclo(
            daemon, activo=activo, intervalo_seg=intervalo_seg, tick_seg=tick_seg
        )
        _ultimo_ciclo[daemon] = ahora
    except Exception as e:  # noqa: BLE001 -- un latido jamás rompe un barrido
        _log.debug("Latido de ciclo de %s no registrado: %s", daemon, e)


def barrido(
    daemon: str,
    *,
    ok: bool,
    intervalo_seg: float,
    tick_seg: float,
    duracion_ms: int = 0,
    error: str = "",
) -> None:
    """Latido de BARRIDO (el sweep corrió, bien o mal), best-effort."""
    try:
        from . import db_latidos

        db_latidos.latido_barrido(
            daemon,
            ok=ok,
            intervalo_seg=intervalo_seg,
            tick_seg=tick_seg,
            duracion_ms=duracion_ms,
            error_txt=error,
        )
        _ultimo_ciclo[daemon] = time.monotonic()
    except Exception as e:  # noqa: BLE001 -- un latido jamás rompe un barrido
        _log.debug("Latido de barrido de %s no registrado: %s", daemon, e)


def fichero_latido() -> str:
    """Ruta del fichero de latido del proceso daemons (healthcheck del contenedor)."""
    return os.environ.get(ENV_FICHERO_LATIDO) or _FICHERO_LATIDO_DEF


def tocar_fichero() -> None:
    """Escribe el instante actual en el fichero de latido (best-effort, atómico).

    El healthcheck del contenedor `daemons` compara el MTIME del fichero con el reloj:
    si lleva demasiado sin tocarse, el proceso principal está colgado/muerto y autoheal
    reinicia el contenedor. Escritura a tmp + rename para no dejar un fichero a medias.
    """
    ruta = fichero_latido()
    try:
        tmp = f"{ruta}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(f"{time.time():.0f}\n")
        os.replace(tmp, ruta)
    except Exception as e:  # noqa: BLE001 -- liveness best-effort
        _log.debug("No se pudo tocar el fichero de latido %s: %s", ruta, e)
