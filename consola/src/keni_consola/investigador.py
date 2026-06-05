"""Investigador (Fase 1): MATERIALIZA el snapshot del Radar por marca en Postgres.

PROBLEMA QUE RESUELVE
=====================
El Radar (`api/radar.py`) y la Parrilla (`api/parrilla.py`) descargan Trends + TODOS los
feeds del equipo + agencias EN EL PATH DE CARGA de cada request (la cache con TTL de Fase 0
amortigua, pero el primer hit tras el TTL sigue golpeando la red). El Investigador invierte el
flujo: un daemon barre cada N horas, consolida el Radar POR MARCA, lo PUNTUA y lo PERSISTE como
snapshot (`repos.upsert_radar_items`). Los endpoints leen del snapshot (rapido, sin red) cuando
esta fresco, y caen al camino en vivo si no hay snapshot.

SEGURO POR DISEÑO (CERO REGRESION CON FLAG OFF)
===============================================
  - GATEADO EN VIVO: el daemon arranca SIEMPRE pero solo materializa con `KENI_INVESTIGADOR=1`
    (def OFF, `config.investigador_activo()`). Sin el flag, NO escribe nada y los endpoints
    NUNCA leen del snapshot (ver `api.radar._temas_desde_snapshot`): comportamiento de Fase 0.
  - NO MUTA LA CACHE: consolida SIEMPRE sobre COPIAS (`api_radar._grupos_para_consolidar`),
    nunca sobre los grupos crudos cacheados (consolidar funde mutando el representante).
  - BEST-EFFORT: ningun fallo (lectura del Radar, scoring, escritura) lanza; se loguea y se
    sigue. `materializar_snapshot` devuelve el nº de items escritos (0 ante fallo).
"""

from __future__ import annotations

import logging
import threading
from datetime import date, timedelta
from typing import Any

from . import config, daemon_util, marcas, parrilla, radar, relevancia_marca, repos
from .dominio import dedup

_log = logging.getLogger("keni_consola.investigador")

# Ventana (dias) para mapear el estado editorial reciente de la marca (publicado/en_parrilla).
_VENTANA_ESTADO_DIAS = 60

# BREAKING (Fase 3): un tema es "breaking" cuando su señal ACELERA fuerte entre el snapshot
# anterior y el actual (no solo "es viral", sino "esta calentando AHORA"). Dos umbrales:
#   - `_ACEL_BREAKING`: incremento RELATIVO minimo respecto a la señal previa para considerarlo
#     una aceleracion (0.5 = +50% snapshot-a-snapshot).
#   - `_MIN_SENAL_BREAKING`: piso ABSOLUTO de señal nueva, para no marcar como breaking saltos
#     porcentualmente grandes sobre numeros minusculos (p.ej. 100 -> 200 es +100% pero
#     irrelevante). Solo temas que ademas superan este volumen cuentan.
# Sin señal PREVIA (primer snapshot del tema) -> NO breaking: sin historial no se inventa.
_ACEL_BREAKING = 0.5  # +50% de aceleracion relativa minima
_MIN_SENAL_BREAKING = 10_000  # piso absoluto de señal nueva para que la aceleracion cuente


def _es_breaking(senal_nueva: Any, senal_previa: Any | None) -> bool:
    """True si `senal_nueva` ACELERA respecto a `senal_previa` (aceleracion de señal = breaking).

    Requiere las TRES condiciones: (1) hay señal previa (snapshot anterior con el tema),
    (2) la nueva supera la previa por al menos `_ACEL_BREAKING` (relativo), y (3) la nueva
    supera el piso absoluto `_MIN_SENAL_BREAKING`. Best-effort ante tipos raros -> False.
    """
    if senal_previa is None:
        return False
    try:
        nueva = float(senal_nueva)
        previa = float(senal_previa)
    except (TypeError, ValueError):
        return False
    if previa <= 0:
        return False
    return nueva >= previa * (1 + _ACEL_BREAKING) and nueva >= _MIN_SENAL_BREAKING


def _estado_por_clave(marca: str) -> dict[str, str]:
    """Mapea `dedup.clave(titulo) -> 'publicado'|'en_parrilla'` del contenido reciente de la marca.

    Lee el contenido `clase='contenido'` de la marca en una ventana de `_VENTANA_ESTADO_DIAS`
    dias y clasifica cada titulo por su estado editorial: `publicado` si la pieza ya salio,
    `en_parrilla` si esta en el tablero (cualquier otro estado). 'publicado' GANA (si una clave
    aparece publicada y tambien en parrilla, queda 'publicado'). Best-effort: `{}` si falla.
    """
    try:
        desde = (date.today() - timedelta(days=_VENTANA_ESTADO_DIAS)).isoformat()
        items = repos.listar_contenido(marca=marca, clase="contenido", desde=desde)
    except Exception:  # noqa: BLE001 -- un fallo de lectura no debe abortar la materializacion
        _log.exception("investigador: no se pudo leer el estado editorial de la marca %s", marca)
        return {}

    estados: dict[str, str] = {}
    for it in items:
        titulo = (it.get("titulo") or "").strip()
        if not titulo:
            continue
        clave = dedup.clave(titulo)
        if not clave:
            continue
        publicado = (it.get("estado") or "") == "publicado"
        nuevo = "publicado" if publicado else "en_parrilla"
        # 'publicado' gana: no degradar una clave ya marcada como publicada.
        if estados.get(clave) == "publicado":
            continue
        estados[clave] = nuevo
    return estados


def _senal_previa_por_clave(marca: str, geo: str) -> dict[str, int]:
    """Mapea `clave -> senal` del snapshot PERSISTIDO de `(marca, geo)` (para detectar breaking).

    Lee el snapshot anterior via `repos.listar_radar_items`. Vacio (primer snapshot, daemon
    OFF, o fallo de lectura) -> `{}` (best-effort: nadie sera breaking sin historial).
    """
    try:
        previos = repos.listar_radar_items(marca=marca, geo=geo)
    except Exception:  # noqa: BLE001 -- un fallo de lectura no debe abortar la materializacion
        _log.exception("investigador: no se pudo leer el snapshot previo (marca=%s, geo=%s)", marca, geo)
        return {}
    mapa: dict[str, int] = {}
    for it in previos:
        clave = (it.get("clave") or "").strip()
        if not clave:
            continue
        try:
            mapa[clave] = int(it.get("senal") or 0)
        except (TypeError, ValueError):
            mapa[clave] = 0
    return mapa


def _breaking_por_clave(marca: str | None, geo: str | None = None) -> dict[str, bool]:
    """Mapea `clave -> breaking(bool)` desde el snapshot persistido de la marca.

    Lee el flag `breaking` que el daemon materializo en `radar_items`. Sin marca, sin snapshot
    (daemon OFF) o ante fallo -> `{}` (cero efecto: todo tema cae a `breaking=False`). El `geo`
    es opcional: si no se pasa, no se filtra por geo (toma el del barrido configurado).
    """
    if not marca:
        return {}
    try:
        # Default de geo: el del barrido del daemon (mismo que usa `ejecutar_barrido`), para
        # apuntar al snapshot que el Investigador escribe. Sin filtrar si no se puede derivar.
        geo_eff = geo if geo is not None else config.radar_auto_geo()
        items = repos.listar_radar_items(marca=marca, geo=geo_eff or "")
    except Exception:  # noqa: BLE001 -- best-effort: el badge breaking nunca tumba el endpoint
        _log.exception("investigador: no se pudo leer breaking del snapshot (marca=%s)", marca)
        return {}
    mapa: dict[str, bool] = {}
    for it in items:
        clave = (it.get("clave") or "").strip()
        if clave:
            mapa[clave] = bool(it.get("breaking"))
    return mapa


def umbral_prioritario() -> int:
    """Umbral de señal a partir del cual un tema es PRIORITARIO (muy viral / atender primero).

    REUSA `config.radar_auto_umbral()` (def 50000): el MISMO umbral con el que el daemon de
    auto-promocion del Radar decide que un tema es "lo suficientemente viral" para empujarlo
    solo al tablero. Asi el badge de prioridad y la auto-promocion comparten una unica nocion
    de "tema fuerte" (un solo numero que tunear, en BACKEND, via `KENI_RADAR_AUTO_UMBRAL`).
    """
    return config.radar_auto_umbral()


def prioritario_de_senal(senal: Any) -> bool:
    """True si la `senal` del tema alcanza el umbral de prioridad (best-effort ante tipos raros)."""
    try:
        return int(senal) >= umbral_prioritario()
    except (TypeError, ValueError):
        return False


def anotar_estado_prioritario(temas: list[dict[str, Any]], marca: str | None) -> None:
    """Anota IN-PLACE cada tema serializado con `estado`, `prioritario` y `breaking` (ADITIVOS).

    - `estado`: `'publicado' | 'en_parrilla' | 'nuevo'`, cruzando el titulo del tema contra el
      estado editorial reciente de la marca (`_estado_por_clave`). Se calcula AL LEER, asi el
      badge funciona AUNQUE el daemon del Investigador este OFF. UNA sola query al tablero por
      request (no N+1): el mapa clave->estado se computa una vez y se consulta en memoria.
    - `prioritario`: `senal >= umbral_prioritario()` (tema muy viral, atenderlo primero).
    - `breaking`: flag de ACELERACION de señal, leido del snapshot persistido (`radar_items`,
      lo materializa el daemon del Investigador). UNA sola query extra al snapshot (no N+1).
      Sin marca / sin snapshot (daemon OFF) -> `breaking=False` para todos (cero efecto).

    BEST-EFFORT / CERO REGRESION: si el cruce al tablero falla (o no hay marca), todo cae a
    `estado='nuevo'` y `breaking=False`; nunca lanza, nunca rompe el endpoint. No toca los
    campos existentes. La firma publica `(temas, marca)` NO cambia (los endpoints la llaman asi).
    """
    estados = _estado_por_clave(marca) if marca else {}
    breaking = _breaking_por_clave(marca)
    for tema in temas:
        clave = dedup.clave(str(tema.get("titulo", "")))
        tema["estado"] = estados.get(clave, "nuevo") if clave else "nuevo"
        tema["prioritario"] = prioritario_de_senal(tema.get("senal", 0))
        tema["breaking"] = breaking.get(clave, False) if clave else False


def materializar_snapshot(marca: str, geo: str) -> int:
    """Consolida el Radar de una marca, lo puntua y lo PERSISTE como snapshot. Devuelve nº escritos.

    Pasos:
      (a) lee los grupos crudos cacheados del Radar y consolida sobre COPIAS (nunca muta la
          cache: `_grupos_para_consolidar`).
      (b) filtra al FOCO de la marca (palabras de marca + `tema_en_foco`) si hay vocabulario.
      (c) por tema: clave de dedup (salta si vacia), score+razon (`parrilla.puntuar_tema`),
          estado editorial (`_estado_por_clave`), url canonica del primer enlace; arma el item.
      (d) escribe via `repos.upsert_radar_items`.

    Best-effort: NUNCA lanza; devuelve 0 ante cualquier fallo.
    """
    try:
        from .api import radar as api_radar

        grupos, _fuentes = api_radar._radar_consolidado(geo, incluir_feeds=True, marca=marca)
        temas = radar.consolidar(*api_radar._grupos_para_consolidar(grupos))

        # Vocabulario de marca SOLO para inclinar el score (`puntuar_tema`), NO para FILTRAR:
        # el snapshot materializa TODO el radar consolidado y el FOCO se aplica al LEER (el
        # endpoint ya descarta/cuenta fuera_foco, igual que en el camino en vivo). Filtrar aqui
        # duplicaria el foco y perderia el conteo `total_fuera_foco` que el endpoint reporta.
        palabras = relevancia_marca.palabras_de_marca(marca)

        estados = _estado_por_clave(marca)

        # BREAKING: señal PREVIA por clave (snapshot ANTERIOR de esta misma marca/geo). Una
        # sola lectura ANTES del upsert (el upsert refresca las filas: hay que leer antes).
        # Primera materializacion (sin filas previas) -> mapa vacio -> nadie es breaking.
        senal_previa = _senal_previa_por_clave(marca, geo)

        items: list[dict[str, Any]] = []
        for tema in temas:
            clave = dedup.clave(tema.titulo)
            if not clave:
                continue
            score, razon = parrilla.puntuar_tema(tema, geo, palabras)
            url_canonica = ""
            if tema.enlaces and tema.enlaces[0].url:
                url_canonica = dedup.url_canonica(tema.enlaces[0].url)
            d = tema.a_dict()
            d.update(
                clave=clave,
                score=float(score),
                razon=razon,
                estado=estados.get(clave, "nuevo"),
                url_canonica=url_canonica,
                breaking=_es_breaking(d.get("senal", 0), senal_previa.get(clave)),
            )
            items.append(d)

        return repos.upsert_radar_items(marca, geo, items)
    except Exception:  # noqa: BLE001 -- la materializacion no debe romper el daemon ni el endpoint
        _log.exception("investigador: fallo materializando el snapshot (marca=%s, geo=%s)", marca, geo)
        return 0


def ejecutar_barrido() -> dict[str, int]:
    """Un barrido: materializa el snapshot de CADA marca del catalogo en el geo configurado.

    Geo: `config.radar_auto_geo()` (compartido con la auto-promocion del Radar; def MX). Tolerante
    a fallos por marca (un fallo se loguea y se sigue con la siguiente). Devuelve `{marca: nº}`.
    """
    geo = config.radar_auto_geo()
    resumen: dict[str, int] = {}
    for marca in marcas.ids():
        try:
            resumen[marca] = materializar_snapshot(marca, geo)
        except Exception:  # noqa: BLE001 -- un fallo por marca no aborta el barrido completo
            _log.exception("investigador: fallo en el barrido de la marca %s", marca)
            resumen[marca] = 0
    total = sum(resumen.values())
    if total:
        _log.info("Investigador: snapshot materializado, %d item(s) en %d marca(s) (geo=%s).",
                  total, len(resumen), geo)
    return resumen


def _intervalo_segundos() -> float:
    """Intervalo del barrido en segundos (a partir de `KENI_INVESTIGADOR_INTERVALO_HORAS`)."""
    return config.investigador_intervalo_horas() * 3600.0


def iniciar_investigador(intervalo_segundos: float | None = None) -> threading.Thread:
    """Arranca el hilo demonio del Investigador (GATEADO EN VIVO).

    Espejo de `radar_auto.iniciar_radar_auto`: el hilo arranca SIEMPRE y comprueba
    `KENI_INVESTIGADOR` en cada ciclo, asi que encender/apagar en runtime aplica sin reiniciar
    (apagar en <= ~1 min; encender tras estar apagado dispara un barrido de inmediato). El hilo
    es daemon; un fallo de barrido se loguea y NO lo mata. Pensado para el servidor real
    (`daemons.py`), NO para `crear_app` (los tests no lo arrancan, igual que los demas daemons).
    """
    intervalo = intervalo_segundos if intervalo_segundos is not None else _intervalo_segundos()

    def bucle() -> None:
        daemon_util.bucle_gateado(
            activo_fn=config.gate_maquina(config.investigador_activo),
            intervalo_seg_fn=lambda: intervalo,
            sweep_fn=ejecutar_barrido,
            log=_log,
        )

    hilo = threading.Thread(target=bucle, name="investigador-daemon", daemon=True)
    hilo.start()
    estado = "ACTIVO" if config.investigador_activo() else "EN ESPERA (KENI_INVESTIGADOR off)"
    _log.info("Investigador %s, cada %.0f h.", estado, intervalo / 3600.0)
    return hilo
