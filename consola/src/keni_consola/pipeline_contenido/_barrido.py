"""Barrido del pipeline (CI → QA de la fuente → CD → arte) + daemon.

Orquesta las tres fases en orden por marca (rediseño QPC: la criba de la fuente va ANTES del
copy), bajo un single-flight cross-proceso, y expone el hilo demonio gateado en vivo
(`iniciar_pipeline`).
"""

from __future__ import annotations

import threading
from typing import Any

from .. import config, daemon_util, generaciones, marcas, repos
from . import _ref
from ._comun import QA_EN_CURSO, QA_SALTADA, _log
from ._copy import lanzar_copy_de_tema, temas_autogen_sin_copy, temas_para_copy
from ._ingesta import _claves_dedup_marca, crear_tema_de, ingerir_marca
from ._qa import lanzar_qa_fuente, temas_sin_qa

__all__ = [
    "ejecutar_barrido",
    "_ejecutar_barrido",
    "ejecutar_qa",
    "ejecutar_cd",
    "ejecutar_arte",
    "_intervalo_segundos",
    "iniciar_pipeline",
]


def ejecutar_barrido() -> dict[str, Any]:
    """Un barrido del pipeline: CI (crea temas) → QA de la fuente → CD (copy de los OK).

    Tres fases EN ORDEN (rediseño QPC):
      1) CI: por cada marca con feeds activos, crea temas SIN copy (`crear_tema_de`) y marca los
         items usados (dedup).
      2) QA: lanza la criba de la FUENTE (`claude -p`) de los temas nuevos sin veredicto, con tope
         `_QA_LANZAR_MAX`. ASÍNCRONA: marca el tema `en_curso` y el `procesar` persiste el veredicto
         (`no_verificado`/`problema`) al completar (normalmente en un barrido posterior).
      3) CD: genera copy SOLO de los temas cuya QA salió `no_verificado` y que aún no tienen copy
         (`temas_para_copy`), con tope `_CD_LANZAR_MAX`. Los `problema` NO generan copy (ahorro).

    Best-effort: un fallo por marca/tema se loguea y se sigue; si la cola de generación está
    llena, se corta la fase en curso (reintenta el siguiente barrido). Devuelve un resumen
    `{temas, cribados, lanzados}` (para el endpoint/los tests).

    SINGLE-FLIGHT cross-proceso (advisory lock de Postgres): el daemon y el endpoint a demanda
    comparten este barrido; su dedup (`_claves_dedup_marca`) es leer-luego-escribir en Python,
    así que dos barridos solapados podrían ingerir/cribar/generar el MISMO tema dos veces. El
    lock hace que un segundo barrido concurrente salga de inmediato con un resumen vacío.
    """
    from .. import db

    with db.lock_barrido("pipeline_contenido") as ok:
        if not ok:
            _log.debug("pipeline: otro barrido en curso; se omite este.")
            return {"temas": [], "cribados": [], "lanzados": [], "artes": []}
        return _ejecutar_barrido()


def _ejecutar_barrido() -> dict[str, Any]:
    """Cuerpo del barrido del pipeline (ya bajo el single-flight de `ejecutar_barrido`)."""
    autor = _ref._autor_pipeline()
    maximo = config.pipeline_max()
    # --- Fase CI · "Crear noticias": crea los temas (sin copy) por marca. --------------------
    # Etapa CI = toggle "Crear noticias" (`KENI_INGESTA`), 1 toggle = 1 etapa: si el maestro está
    # OFF no entran temas nuevos (aunque el daemon barra por otra etapa, p. ej. Copy de temas ya
    # ingeridos). Por marca, el override `KENI_INGESTA::marca=0` excluye esa marca de la ingesta.
    temas_nuevos: list[dict[str, Any]] = []
    for marca in marcas.ids() if config.ingesta_activa() else []:
        # Exclusión por marca: si "Crear noticias" de ESTA marca se apagó a mano, no se ingiere
        # nada suyo (no entran temas nuevos). Sin override, sigue al maestro (global).
        if config.marca_apagada(config.ENV_INGESTA, marca):
            continue
        try:
            trabajos = ingerir_marca(marca, maximo=maximo)
        except Exception:  # noqa: BLE001 -- un fallo de ingesta de una marca no rompe el barrido
            _log.exception("pipeline: fallo la ingesta (CI) de la marca %s", marca)
            continue
        # Dedup: claves de los títulos del contenido reciente de la marca (ventana `_DIAS_DEDUP`).
        # `crear_tema_de` salta los trabajos cuyo título ya esté aquí (duplicado en cola o
        # republicado) y va añadiendo los nuevos, para dedup también DENTRO de este barrido.
        claves_vistas = _claves_dedup_marca(marca)
        for trabajo in trabajos:
            try:
                tema = crear_tema_de(trabajo, claves_vistas=claves_vistas)
            except Exception:  # noqa: BLE001 -- un fallo por item no debe matar el barrido
                _log.exception("pipeline: fallo la creación del tema (CI) de un item.")
                continue
            if tema:
                temas_nuevos.append(tema)
    # --- Fase QA (criba de la fuente) + Fase CD (copy) + Etapa ARTE. -------------------------
    cribados = ejecutar_qa(autor=autor)
    lanzados = ejecutar_cd(autor=autor)
    # Etapa de arte (tras copy): ilustra los temas con copy y sin imagen. Gateada por su propio
    # toggle "Generar arte" (KENI_AUTOGEN_ARTE) + máquina; si está OFF, devuelve [].
    artes = ejecutar_arte()
    if temas_nuevos or cribados or lanzados or artes:
        _log.info(
            "pipeline: %d tema(s) ingerido(s) (CI), %d cribado(s) (QA), %d copy encolado(s) (CD), "
            "%d arte(s) (etapa arte).",
            len(temas_nuevos), len(cribados), len(lanzados), len(artes),
        )
    return {"temas": temas_nuevos, "cribados": cribados, "lanzados": lanzados, "artes": artes}


def ejecutar_qa(*, autor: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Fase QA del barrido: lanza la CRIBA de la fuente (`claude -p`) de los temas sin veredicto.

    Con TOPE de lanzamientos por barrido (`_QA_LANZAR_MAX`): evita la ráfaga de `claude -p` que
    satura el worker e inunda Actividad de QA "en curso". Los temas restantes se criban en el
    siguiente barrido (drenaje gradual). Si la cola se llena, corta la fase (reintenta luego).
    Best-effort por tema. Devuelve los temas cuya QA se lanzó.
    """
    if autor is None:
        autor = _ref._autor_pipeline()
    cribados: list[dict[str, Any]] = []
    lanzados = 0
    qa_global = config.qa_activo()
    for tema in temas_sin_qa():
        marca_t = tema.get("marca") or ""
        # Etapa QA desactivada (maestro `KENI_QA` off o `KENI_QA::marca=0`): se SALTA la criba.
        # No se lanza `claude -p`; se marca el tema `saltada` para que CD lo recoja igual (sin
        # verificar) y la vista Pipelines pinte QA como "saltada". No cuenta para el cap ni rompe.
        if not qa_global or config.marca_apagada(config.ENV_QA, marca_t):
            try:
                repos.actualizar_contenido(tema.get("id", "") or "", {"qa_veredicto": QA_SALTADA})
            except Exception:  # noqa: BLE001 -- un fallo al marcar saltada no debe matar la fase
                _log.exception("pipeline: fallo al marcar QA saltada de un tema.")
            else:
                cribados.append({"id": tema.get("id", ""), "gen_id": "", "verdicto": QA_SALTADA})
            continue
        if lanzados >= _ref._QA_LANZAR_MAX:
            break
        try:
            gen = lanzar_qa_fuente(tema, autor=autor)
        except generaciones.ColaLlenaError:
            _log.info("pipeline: cola llena en QA; el resto entra en el próximo barrido.")
            break
        except Exception:  # noqa: BLE001 -- un fallo por tema no debe matar la fase QA
            _log.exception("pipeline: fallo la criba de la fuente (QA) de un tema.")
            continue
        if gen is not None:
            cribados.append({"id": tema.get("id", ""), "gen_id": gen.get("id", ""), "verdicto": QA_EN_CURSO})
            lanzados += 1
    return cribados


def ejecutar_cd(*, autor: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Fase CD (etapa de copy): genera copy de los temas con QA `no_verificado` y sin copy aún,
    Y de los temas del news-pool (orígenes de noticias) que aún no tienen copy.

    DOS fuentes de temas, una sola ruta de copy (la etapa de copy es el ÚNICO motor):
      1) temas del propio pipeline (origen `pipeline`) cuya QA salió `no_verificado`
         (`temas_para_copy` → `lanzar_copy_de_tema`),
      2) temas que las FUENTES de noticias metieron al tablero sin copy
         (`temas_autogen_sin_copy` → `autogen_copy.lanzar_para_topic`), FUNDIENDO aquí la
         selección del antiguo daemon suelto `autogen_copy`.
    Con TOPE por barrido (`_CD_LANZAR_MAX` para 1, `_AUTOGEN_LANZAR_MAX` dentro de la selección
    para 2). Si la cola se llena, corta la fase (reintenta luego). Best-effort por tema.
    Devuelve las generaciones de copy lanzadas.
    """
    if autor is None:
        autor = _ref._autor_pipeline()
    # Etapa CD = toggle "Generar copy" (`KENI_PIPELINE`), 1 toggle = 1 etapa: si el maestro está
    # OFF no se genera copy (aunque el daemon barra por otra etapa). Por marca se filtra abajo.
    if not config.pipeline_activo():
        return []
    lanzados: list[dict[str, Any]] = []
    contador = 0
    for tema in temas_para_copy():
        if contador >= _ref._CD_LANZAR_MAX:
            break
        # Exclusión por marca: no generamos copy de temas de una marca apagada a mano (aunque
        # ya estuvieran ingeridos antes de apagarla).
        if config.marca_apagada(config.ENV_PIPELINE, tema.get("marca") or ""):
            continue
        try:
            gen = lanzar_copy_de_tema(tema, autor=autor)
        except generaciones.ColaLlenaError:
            _log.info("pipeline: cola llena en CD; el resto entra en el próximo barrido.")
            return lanzados
        except Exception:  # noqa: BLE001 -- un fallo por tema no debe matar la fase CD
            _log.exception("pipeline: fallo la generación de copy (CD) de un tema.")
            continue
        if gen:
            lanzados.append(gen)
            contador += 1
    # Fundido de la selección de autogen_copy: la etapa de copy también redacta los temas del
    # news-pool/tablero (orígenes de noticias) que aún no tienen copy, vía el lanzador NEUTRO.
    from .. import autogen_copy

    for item in temas_autogen_sin_copy():
        try:
            gen = autogen_copy.lanzar_para_topic(item)
        except generaciones.ColaLlenaError:
            _log.info("pipeline: cola llena en CD (pool); el resto entra en el próximo barrido.")
            break
        except Exception:  # noqa: BLE001 -- un fallo por tema no debe matar la fase CD
            _log.exception("pipeline: fallo la generación de copy (CD) de un tema del pool.")
            continue
        if gen:
            lanzados.append(gen)
    return lanzados


def ejecutar_arte() -> list[dict[str, Any]]:
    """Etapa de ARTE del pipeline (tras copy): ilustra los temas con copy y sin imagen.

    Toggle "Generar arte" (`KENI_AUTOGEN_ARTE`, gateado además por el maestro `KENI_MAQUINA`).
    FUNDE el antiguo daemon suelto `autogen_arte`: reutiliza su selección
    (`autogen_arte.topics_sin_arte`) y su lanzador (`autogen_arte.lanzar_para_topic` →
    `media.generar_imagen`), con cap por barrido (`KENI_AUTOGEN_ARTE_MAX`). Per-marca: salta las
    marcas apagadas a mano (lo hace la propia selección, gateada por `ENV_AUTOGEN_ARTE`). Sin
    proveedor de imagen configurado, no hace nada. Best-effort: un fallo por tema se loguea y se
    sigue. Devuelve los artes adjuntados.

    GATEADO EN VIVO: solo actúa con `KENI_AUTOGEN_ARTE=1` Y `KENI_MAQUINA=1`. Sin el toggle, la
    etapa no ilustra (el equipo hace el arte a mano).
    """
    from datetime import date

    from .. import autogen_arte

    if not config.gate_maquina(config.autogen_arte_activo)():
        return []
    from .. import media

    if not media.proveedor_configurado():
        _log.info("pipeline: etapa de arte sin proveedor de imagen configurado; se omite.")
        return []
    try:
        items = repos.listar_contenido()
    except Exception:  # noqa: BLE001 -- sin tablero, la etapa de arte no actúa
        _log.exception("pipeline: no se pudo leer el tablero para la etapa de arte.")
        return []
    elegidos = autogen_arte.topics_sin_arte(
        items,
        plataformas_por_item=autogen_arte._plataformas_por_item(items),
        ya_procesados=autogen_arte.ids_ya_procesados(),
        maximo=config.autogen_arte_max(),
        etiquetas_por_item=autogen_arte._etiquetas_por_item(),
        hoy=date.today(),
    )
    adjuntados: list[dict[str, Any]] = []
    for item in elegidos:
        try:
            res = autogen_arte.lanzar_para_topic(item)
        except Exception:  # noqa: BLE001 -- un fallo por tema no debe matar la etapa de arte
            _log.exception("pipeline: fallo la generación de arte de un tema.")
            continue
        if res:
            adjuntados.append(res)
    if adjuntados:
        _log.info("pipeline: %d tema(s) ilustrado(s) (etapa arte).", len(adjuntados))
    return adjuntados


def _intervalo_segundos() -> float:
    """Intervalo del barrido en segundos (a partir de `KENI_PIPELINE_INTERVALO_HORAS`)."""
    return config.pipeline_intervalo_horas() * 3600.0


def iniciar_pipeline(intervalo_segundos: float | None = None) -> threading.Thread:
    """Arranca el hilo demonio del pipeline de contenido (GATEADO EN VIVO).

    Pensado para el servidor real (`daemons`/`__main__`), NO para `crear_app` (los tests no lo
    arrancan, igual que el resto de daemons). El hilo arranca SIEMPRE y comprueba en cada ciclo si
    ALGUNA etapa está activa (`alguna_etapa_pipeline_activa`): con solo "Crear noticias" encendida
    barre para ingerir (CI) aunque Copy esté OFF; cada fase del barrido se auto-gatea por su propio
    toggle. Apagar/encender en runtime aplica sin reiniciar. El hilo es daemon; un fallo de barrido
    se loguea y NO lo mata.
    """
    intervalo = intervalo_segundos if intervalo_segundos is not None else _intervalo_segundos()

    def bucle() -> None:
        daemon_util.bucle_gateado(
            activo_fn=config.gate_maquina(config.alguna_etapa_pipeline_activa),
            intervalo_seg_fn=lambda: intervalo,
            sweep_fn=ejecutar_barrido,
            log=_log,
        )

    hilo = threading.Thread(target=bucle, name="pipeline-contenido-daemon", daemon=True)
    hilo.start()
    estado = "ACTIVO" if config.alguna_etapa_pipeline_activa() else "EN ESPERA (todas las etapas off)"
    _log.info(
        "Pipeline de contenido %s, cada %.0f h (max/barrido=%d).",
        estado, intervalo / 3600.0, config.pipeline_max(),
    )
    return hilo
