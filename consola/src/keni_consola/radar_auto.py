"""Auto-promocion del Radar de tendencias a "lo importante del dia" (fase3).

PROBLEMA QUE RESUELVE
=====================
El Radar (`radar.py`/`api/radar.py`) descubre lo MAS VIRAL del momento, pero "lo importante
del dia" solo entra al tablero si ALGUIEN pulsa el boton "promover" (`POST /api/contenido/
desde-radar`). Objetivo de producto: que la operativa sea automatica. Aqui un daemon (espejo
de `metricas_refresco.py`) barre el Radar cada N horas y promueve SOLO los temas que superan
un UMBRAL ALTO de señal a contenido `flujo='importante'` (origen 'radar-auto'), de forma que
"lo importante del dia" no dependa de un clic manual.

SEGURO POR DISEÑO (CONSERVADOR)
===============================
  - GATEADO: el daemon solo arranca con `KENI_RADAR_AUTO=1` (def OFF). Sin el flag, el Radar
    sigue siendo SOLO-propone, como hasta ahora.
  - UMBRAL ALTO: solo entra lo MUY viral (`senal >= KENI_RADAR_AUTO_UMBRAL`, def 50K). La
    `senal` es el trafico aproximado REAL de Google Trends (`radar.traduce_trafico`), no un
    invento. Los temas de feeds RSS (señal cualitativa baja) NUNCA superan el umbral.
  - CAP por barrido (`KENI_RADAR_AUTO_MAX`, def 3): aunque muchos superen el umbral, no se
    inunda el tablero; entran los de MAYOR señal.
  - REVISABLE: lo promovido es contenido normal del tablero, que el equipo edita o borra. El
    endpoint `/api/radar/auto/*` permite VER la bandeja (que se promoveria) y ejecutar el
    batch a demanda, sin esperar al daemon.
  - DEDUP: no se re-promueve un tema cuyo titulo ya existe como contenido `origen='radar-auto'`
    (evita duplicados barrido tras barrido del mismo trending).

La logica de SELECCION (umbral + orden + cap + dedup) es PURA y testeable (`temas_promovibles`).
La PROMOCION (`promover_temas`) reutiliza el MISMO camino que `desde-radar`
(`repos.crear_contenido(flujo='importante')`). Cada operacion abre/cierra su conexion (via
`repos`), asi que correr en un hilo aparte es seguro (igual que el resto de daemons).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from . import config, marcas, repos

_log = logging.getLogger("keni_consola.radar_auto")

# Origen reservado de las piezas auto-promovidas (distinto del 'radar' del boton manual),
# para que la dedup y la UI distingan lo automatico de lo manual.
ORIGEN_AUTO = "radar-auto"


def _clave_titulo(titulo: str) -> str:
    """Clave de dedup de un titulo: minusculas, sin espacios extremos/colapsados."""
    return " ".join((titulo or "").strip().lower().split())


def titulos_ya_promovidos() -> set[str]:
    """Claves de titulo de los contenidos ya auto-promovidos (para no duplicar).

    Lee los items del tablero con `origen='radar-auto'` (los crea ESTE modulo) y devuelve sus
    titulos normalizados. Best-effort: si la lectura falla, devuelve set vacio (peor caso: un
    posible duplicado, nunca una excepcion que rompa el barrido).
    """
    try:
        items = repos.listar_contenido(flujo="importante")
    except Exception:  # noqa: BLE001 -- un fallo de lectura no debe abortar el barrido
        return set()
    return {
        _clave_titulo(it.get("titulo", ""))
        for it in items
        if (it.get("origen") or "") == ORIGEN_AUTO
    }


def temas_promovibles(
    temas: list[dict[str, Any]],
    *,
    umbral: int,
    maximo: int,
    ya_promovidos: set[str],
) -> list[dict[str, Any]]:
    """Subconjunto de `temas` del Radar que se debe auto-promover (PURA, testeable).

    `temas` son los dicts del Radar (`radar.Tema.a_dict()`: `{titulo, senal, por_que, ...}`).
    Reglas, en orden:
      - se descartan los de señal por DEBAJO del `umbral` (solo lo MUY viral entra solo),
      - se descartan los ya promovidos (dedup por titulo normalizado) y los duplicados
        dentro del propio barrido,
      - se ORDENAN por señal desc (el Radar ya los trae asi, pero no dependemos de ello),
      - se RECORTA a `maximo` (cap de seguridad por barrido).

    Determinista: depende solo de sus argumentos.
    """
    vistos = set(ya_promovidos)
    candidatos: list[dict[str, Any]] = []
    for tema in temas:
        titulo = (tema.get("titulo") or "").strip()
        if not titulo:
            continue
        try:
            senal = int(tema.get("senal", 0))
        except (TypeError, ValueError):
            senal = 0
        if senal < umbral:
            continue
        clave = _clave_titulo(titulo)
        if clave in vistos:
            continue
        vistos.add(clave)
        candidatos.append(tema)
    candidatos.sort(key=lambda t: -int(t.get("senal", 0) or 0))
    return candidatos[:maximo]


def _marca_valida(marca_id: str) -> str:
    """Devuelve `marca_id` si es una marca del catalogo, o "" (no se confia del entorno)."""
    return marca_id if marca_id and marcas.es_marca(marca_id) else ""


def _descripcion_de(tema: dict[str, Any]) -> str:
    """Descripcion para la pieza promovida: el "por que sube" del tema (sin inventar)."""
    return (tema.get("por_que") or "").strip()


def promover_temas(temas: list[dict[str, Any]], *, marca: str = "") -> list[dict[str, Any]]:
    """Promueve una lista de temas YA filtrados a contenido `flujo='importante'`.

    Mismo camino que `POST /api/contenido/desde-radar`, pero con `origen='radar-auto'` y sin
    filas por plataforma (el equipo elige redes al editarlo). Devuelve los contenidos creados.
    `marca` (id canonico) se valida; invalida o vacia => sin marca.
    """
    from datetime import date

    marca_ok = _marca_valida(marca)
    creados: list[dict[str, Any]] = []
    for tema in temas:
        titulo = (tema.get("titulo") or "").strip()
        if not titulo:
            continue
        item = repos.crear_contenido(
            clase="contenido",
            flujo="importante",
            titulo=titulo[:300],
            descripcion=_descripcion_de(tema)[:8000],
            marca=marca_ok,
            prioridad="alta",  # supero un umbral alto de viralidad: merece prioridad
            fecha_objetivo=date.today().isoformat(),
            origen=ORIGEN_AUTO,
        )
        creados.append(item)
    return creados


def _leer_radar(geo: str) -> list[dict[str, Any]]:
    """Trae los temas del Radar (Trends + feeds) como dicts. Best-effort (nunca lanza).

    Reutiliza los helpers de `api.radar` (mismas fuentes, mismo guard SSRF, mismo descargador).
    Consolida con `radar.consolidar` para deduplicar y ordenar por señal, igual que el endpoint.
    """
    try:
        from . import radar
        from .api import radar as api_radar

        temas_trends, _estado = api_radar._radar_trends(geo)
        temas_feeds, _estados = api_radar._radar_feeds()
        consolidados = radar.consolidar(temas_trends, temas_feeds)
        return [t.a_dict() for t in consolidados]
    except Exception:  # noqa: BLE001 -- el Radar no disponible no debe romper el barrido
        _log.exception("No se pudo leer el Radar para la auto-promocion.")
        return []


def ejecutar_barrido() -> list[dict[str, Any]]:
    """Un barrido de auto-promocion: lee el Radar, filtra y promueve. Devuelve lo creado.

    Lo llaman el daemon y el endpoint de ejecucion a demanda. Usa la config viva (umbral, geo,
    cap, marca). Best-effort: un fallo se loguea y devuelve lista vacia (no rompe el hilo).
    """
    geo = config.radar_auto_geo()
    temas = _leer_radar(geo)
    if not temas:
        return []
    elegidos = temas_promovibles(
        temas,
        umbral=config.radar_auto_umbral(),
        maximo=config.radar_auto_max(),
        ya_promovidos=titulos_ya_promovidos(),
    )
    if not elegidos:
        return []
    creados = promover_temas(elegidos, marca=config.radar_auto_marca())
    if creados:
        _log.info(
            "Radar auto-promocion: %d tema(s) promovido(s) a 'importante' (geo=%s, umbral=%d).",
            len(creados), geo, config.radar_auto_umbral(),
        )
    return creados


def previsualizar_bandeja() -> list[dict[str, Any]]:
    """Temas que se promoverian AHORA (sin escribir nada): la bandeja revisable.

    Mismo filtro que `ejecutar_barrido` pero SIN promover: la UI muestra que entraria para que
    el equipo lo apruebe/ejecute a demanda. Cada item lleva su `senal`/`por_que`/`enlaces`.
    """
    geo = config.radar_auto_geo()
    temas = _leer_radar(geo)
    if not temas:
        return []
    return temas_promovibles(
        temas,
        umbral=config.radar_auto_umbral(),
        maximo=config.radar_auto_max(),
        ya_promovidos=titulos_ya_promovidos(),
    )


def _intervalo_segundos() -> float:
    """Intervalo del barrido en segundos (a partir de `KENI_RADAR_AUTO_INTERVALO_HORAS`)."""
    return config.radar_auto_intervalo_horas() * 3600.0


def iniciar_radar_auto(intervalo_segundos: float | None = None) -> threading.Thread | None:
    """Arranca el hilo demonio de auto-promocion del Radar, SI el flag esta activo.

    Pensado para el servidor real (`__main__`), NO para `crear_app` (los tests no lo arrancan,
    igual que el resto de daemons). Devuelve None (y no arranca nada) si `KENI_RADAR_AUTO` esta
    OFF: CONSERVADOR por defecto. El hilo es daemon; un fallo de barrido se loguea y NO lo mata.
    """
    if not config.radar_auto_activo():
        _log.info("Radar auto-promocion DESACTIVADO (KENI_RADAR_AUTO no esta activo).")
        return None

    intervalo = intervalo_segundos if intervalo_segundos is not None else _intervalo_segundos()

    def bucle() -> None:
        while True:
            try:
                ejecutar_barrido()
            except Exception:  # noqa: BLE001 -- un fallo de barrido no debe matar el hilo
                _log.exception("Fallo en el barrido de auto-promocion del Radar.")
            time.sleep(intervalo)

    hilo = threading.Thread(target=bucle, name="radar-auto-daemon", daemon=True)
    hilo.start()
    _log.info(
        "Radar auto-promocion ACTIVO cada %.0f h (umbral=%d, max/barrido=%d).",
        intervalo / 3600.0, config.radar_auto_umbral(), config.radar_auto_max(),
    )
    return hilo
