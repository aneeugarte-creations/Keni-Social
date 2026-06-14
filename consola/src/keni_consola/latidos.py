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

# Daemons cuyo bucle corre sobre `daemon_util.bucle_gateado` y por tanto CONSUMEN el flag
# `barrido_solicitado` (POST /api/sistema/daemons/{daemon}/barrer): para ellos «Barrer ahora»
# funciona de verdad. Los bucles LEGADOS (programador, metricas, metricas_piezas, comercial)
# NO miran el flag: ofrecerles el botón sería mentir, así que la sonda del panel expone
# `barrible` y el front solo lo ofrece a estos. Mantener en sintonía con los call sites de
# `bucle_gateado` (el nombre sale de `nombre_de_sweep`/`_ALIAS` o del `nombre=` explícito).
BARRIBLES = frozenset({
    "ingesta",
    "media_gc",
    "noticias_gc",
    "trends",
    "algoritmos",
    "patrones",
    "reaper",
    "vencimientos",
    "sugerencias",
    "alertas_rendimiento",
    "investigacion",
    "produccion",
})

# GRUPO ("motor"/papel) de cada daemon: clasifica los daemons para el dashboard de
# "Workers" del panel Sistema (el front agrupa por aquí en vez de hardcodear nombres).
# Fuente única, igual que BARRIBLES. Cuatro grupos:
#   - "investigacion": alimentan el motor de REUTILIZAR (descubrir/ingerir/validar fuentes).
#   - "produccion":    el motor de CREAR borradores (copy+arte) y sugerencias editoriales.
#   - "flujo":         actúan EN el flujo de publicación/comercial; NO gastan tokens claude.
#   - "infra":         pura infraestructura (métricas, GC, alertas, reaper, patrones).
# Un daemon registrado que NO esté en ningún conjunto cae a "infra" por defecto (ver
# `grupo_de`): al añadir un daemon nuevo, clasifícalo aquí o asume que se pinta como infra.
GRUPO_INVESTIGACION = frozenset({"ingesta", "trends", "algoritmos", "investigacion"})
GRUPO_PRODUCCION = frozenset({"produccion", "sugerencias"})
GRUPO_FLUJO = frozenset({"comercial", "programador", "vencimientos"})
GRUPO_INFRA = frozenset({
    "metricas",
    "metricas_piezas",
    "alertas_rendimiento",
    "media_gc",
    "patrones",
    "noticias_gc",
    "reaper",
})

# Daemons que ENCOLAN/EJECUTAN `claude -p` y por tanto GASTAN tokens. El resto opera sin
# modelo (lee feeds/métricas, mueve piezas, GC). `patrones` deriva de Metricool SIN claude
# (verificado en patrones_refresco.py) => fuera. Fuente única para `gasta_tokens` en la sonda.
GASTA_TOKENS = frozenset({"investigacion", "produccion", "sugerencias"})


# CLASE + MOTOR de cada daemon (dashboard de Workers, contrato ADITIVO con el de `grupo_de`).
# Mapeo EXPLÍCITO (fuente única, igual que GRUPO_*/GASTA_TOKENS), pensado para clasificar a mano
# cada daemon nuevo al añadirlo. Es una vista mas afilada que `grupo`:
#   - `clase`:  "ia"      -> gasta tokens Y tiene prompt (corre `claude -p`).
#               "maquina" -> parte de la MAQUINA de contenido pero NO-IA (alimenta/opera los
#                            motores sin modelo: feeds, scheduler, GC del pool de noticias).
#               "sistema" -> pura infraestructura (métricas, GC de media, alertas, reaper,
#                            patrones, comercial).
#   - `motor`:  "investigacion" | "produccion" | None. El loop de la máquina (ADR 0011) al que
#               sirve el daemon; None para los de `sistema` (no pertenecen a ningún motor).
# Verificado contra cada módulo (punto de partida editable; reclasifica aquí al añadir un daemon):
#   - ia:  investigacion (loop de criba/QA -> motor investigacion), produccion (loop de copy/arte
#          -> motor produccion), sugerencias (digest editorial con `claude -p` -> motor produccion).
#   - maquina/investigacion:  ingesta (admisión RSS), trends (Google Trends), algoritmos (feeds
#          de algoritmo), noticias_gc (poda el POOL de noticias que alimenta reutilizar).
#   - maquina/produccion:     programador (publica la parrilla), vencimientos (escáner de eventos
#          que dispara producción por caducidad).
#   - sistema/None:  reaper, media_gc, metricas, metricas_piezas, alertas_rendimiento, patrones
#          (deriva de Metricool SIN claude), comercial.
# Cualquier daemon NO mapeado cae a ("sistema", None) (ver `clase_de`/`motor_de`): nunca rompe el
# panel y, como mucho, sale como infraestructura hasta que se clasifique aquí.
_CLASE_MOTOR: dict[str, tuple[str, str | None]] = {
    "investigacion": ("ia", "investigacion"),
    "produccion": ("ia", "produccion"),
    "sugerencias": ("ia", "produccion"),
    "ingesta": ("maquina", "investigacion"),
    "trends": ("maquina", "investigacion"),
    "algoritmos": ("maquina", "investigacion"),
    "noticias_gc": ("maquina", "investigacion"),
    "programador": ("maquina", "produccion"),
    "vencimientos": ("maquina", "produccion"),
    "reaper": ("sistema", None),
    "media_gc": ("sistema", None),
    "metricas": ("sistema", None),
    "metricas_piezas": ("sistema", None),
    "alertas_rendimiento": ("sistema", None),
    "patrones": ("sistema", None),
    "comercial": ("sistema", None),
}
_CLASE_MOTOR_DEFAULT: tuple[str, str | None] = ("sistema", None)


def clase_de(daemon: str) -> str:
    """Clase del daemon ("ia"|"maquina"|"sistema"); default "sistema" si no está mapeado."""
    return _CLASE_MOTOR.get(daemon, _CLASE_MOTOR_DEFAULT)[0]


def motor_de(daemon: str) -> str | None:
    """Motor del daemon ("investigacion"|"produccion") o None (sistema / no mapeado)."""
    return _CLASE_MOTOR.get(daemon, _CLASE_MOTOR_DEFAULT)[1]


# CLAVE de AJUSTE (KENI_*) que GOBIERNA el on/off de cada daemon: la que el front pasa a
# POST /api/ajustes para encender/apagar el daemon DESDE SU FILA (toggle in-place del panel
# Sistema). Fuente única, igual que BARRIBLES/GRUPO_*. Cada valor es una clave REAL del
# catálogo de ajustes (`ajustes_catalogo`) — un test lo verifica. Verificado contra el
# `activo_fn` de cada `bucle_gateado` (ver daemons.py + cada módulo):
#   - ingesta            -> KENI_PIPELINE_SELECCION   (ingesta_daemon/_bucle: ingesta_activa)
#   - trends             -> KENI_TRENDS               (trends_daemon: trends_activo)
#   - algoritmos         -> KENI_ALGORITMOS_AUTO      (algoritmos_refresco: algoritmos_auto_activo)
#   - sugerencias        -> KENI_SUGERENCIAS_EDITORIALES (sugerencias_editoriales_activo)
#   - media_gc           -> KENI_MEDIA_GC             (media_gc_daemon: media_gc_activo)
#   - noticias_gc        -> KENI_NOTICIAS_GC          (noticias_gc_daemon: noticias_gc_activo)
#   - patrones           -> KENI_PATRONES_AUTO        (patrones_refresco: patrones_auto_activo)
#   - alertas_rendimiento-> KENI_ALERTAS_RENDIMIENTO  (alertas_rendimiento_activas)
#   - vencimientos       -> KENI_EVENTOS_VENCIMIENTOS (eventos_scanner: eventos_vencimientos_activos)
#   - investigacion      -> KENI_MAQUINA   (loop pipeline: gate_maquina(alguna_etapa_investigacion_activa);
#                                           su on/off real son varias claves de etapa —Selección/Validación—
#                                           sin una clave propia, así que el toggle de fila usa el MAESTRO)
#   - produccion         -> KENI_MAQUINA   (loop pipeline: gate_maquina(alguna_etapa_produccion_activa),
#                                           que siempre es True bajo la máquina => su único interruptor es el MAESTRO)
# Los gateados de máquina (ingesta/trends/algoritmos/sugerencias) corren además bajo
# KENI_MAQUINA (AND), pero el toggle de SU fila gobierna su flag PROPIO; el maestro es otra fila.
CLAVE_GATE = {
    "ingesta": "KENI_PIPELINE_SELECCION",
    "trends": "KENI_TRENDS",
    "algoritmos": "KENI_ALGORITMOS_AUTO",
    "sugerencias": "KENI_SUGERENCIAS_EDITORIALES",
    "media_gc": "KENI_MEDIA_GC",
    "noticias_gc": "KENI_NOTICIAS_GC",
    "patrones": "KENI_PATRONES_AUTO",
    "alertas_rendimiento": "KENI_ALERTAS_RENDIMIENTO",
    "vencimientos": "KENI_EVENTOS_VENCIMIENTOS",
    "investigacion": "KENI_MAQUINA",
    "produccion": "KENI_MAQUINA",
}

# Daemons SIEMPRE-ON sin toggle de ajuste: su bucle corre incondicionalmente (legados con
# `while True`, o `reaper` con `activo_fn=lambda: True`). No tienen fila-toggle => clave_gate
# null. Nota: `programador` SIEMPRE corre (su gate KENI_PUBLICAR_REAL solo decide publicar de
# verdad vs dry-run, no apaga el daemon), por eso queda sin gate de encendido.
SIN_GATE = frozenset({"reaper", "programador", "comercial", "metricas", "metricas_piezas"})


def clave_gate_de(daemon: str) -> str | None:
    """Clave de ajuste (KENI_*) que enciende/apaga el daemon desde su fila, o None.

    None = el daemon es SIEMPRE-ON (sin toggle: legados/reaper) o aún no está clasificado.
    El front usa esto para pintar (o no) el switch on/off in-place y, si lo hay, qué clave
    pasar a POST /api/ajustes. Fuente única, igual que `grupo_de`/`gasta_tokens`.
    """
    return CLAVE_GATE.get(daemon)


def grupo_de(daemon: str) -> str:
    """Grupo ("motor"/papel) de un daemon para el dashboard de Workers; default "infra".

    Un daemon no clasificado en ningún conjunto se trata como infraestructura: nunca
    rompe el panel y, como mucho, sale en el grupo equivocado hasta que se clasifique.
    """
    if daemon in GRUPO_INVESTIGACION:
        return "investigacion"
    if daemon in GRUPO_PRODUCCION:
        return "produccion"
    if daemon in GRUPO_FLUJO:
        return "flujo"
    return "infra"  # GRUPO_INFRA + cualquier daemon nuevo sin clasificar


def gasta_tokens(daemon: str) -> bool:
    """True si el daemon encola/ejecuta `claude -p` (gasta tokens); False el resto."""
    return daemon in GASTA_TOKENS


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


def consumir_solicitud(daemon: str) -> bool:
    """Consume la solicitud de BARRIDO FORZADO pendiente del daemon, si la hay (best-effort).

    La escribe el back (POST /api/sistema/daemons/{daemon}/barrer) y la consulta
    `bucle_gateado` en cada tick: True => el bucle ejecuta el sweep YA (la solicitud queda
    limpiada de forma atomica en BD, asi dispara UN solo barrido). Mismo contrato de
    seguridad que el resto del modulo: un fallo de BD degrada a False (sin barrido extra,
    sin romper el bucle).
    """
    try:
        from . import db_latidos

        return db_latidos.consumir_solicitud_barrido(daemon)
    except Exception as e:  # noqa: BLE001 -- la consulta del flag jamás rompe el bucle
        _log.debug("Solicitud de barrido de %s no consultada: %s", daemon, e)
        return False


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
