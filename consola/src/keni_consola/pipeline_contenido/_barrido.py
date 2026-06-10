"""Barrido del pipeline (CI → QA de la fuente → CD → arte) + daemon.

Orquesta las tres fases en orden por marca (rediseño QPC: la criba de la fuente va ANTES del
copy), bajo un single-flight cross-proceso, y expone el hilo demonio gateado en vivo
(`iniciar_pipeline`).
"""

from __future__ import annotations

import threading
from typing import Any

from .. import config, daemon_util, generaciones, marcas, repos
from ..tiempo import hoy_utc
from . import _ingesta, _ref
from ._comun import (
    _MAX_INTENTOS_ETAPA,
    QA_EN_CURSO,
    QA_SALTADA,
    _log,
    anotar_intento,
    en_backoff,
    intentos_de,
    marcar_fallo_etapa,
)
from ._copy import lanzar_copy_de_tema, temas_autogen_sin_copy, temas_para_copy
from ._ingesta import promover_clusters_marca
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
    """Un TICK del flujo continuo: CI (admisión) → QA de la fuente → CD (copy de los OK).

    Tres fases EN ORDEN (rediseño QPC), SIN topes por etapa (el volumen lo regula la ADMISIÓN):
      1) CI: por marca, ADMITE historias solo hasta llenar su cupo en vuelo (gate serial WIP).
      2) QA: lanza la criba de la FUENTE (`claude -p`) de los temas admitidos sin veredicto.
         ASÍNCRONA: marca el tema `en_curso` y el `procesar` persiste el veredicto
         (`no_verificado`/`problema`) al completar; el SIGUIENTE tick (segundos) encadena.
      3) CD: genera copy SOLO de los temas cuya QA salió `no_verificado` y que aún no tienen copy
         (`temas_para_copy`). Los `problema` NO generan copy.

    Best-effort: un fallo por marca/tema se loguea y se sigue; si la cola de generación está
    llena, se corta la fase en curso (el siguiente tick reintenta: backpressure). Devuelve un
    resumen `{temas, cribados, lanzados}` (para el endpoint/los tests).

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
    # --- Fase 0 · FRESCURA: caduca los temas en vuelo que superaron el TTL. ------------------
    # El pipeline es VENTANA DESLIZANTE sobre el ranking (sin colas intermedias): lo que no se
    # completó a tiempo caduca y libera su hueco del gate serial; hoy entra lo de hoy. Sin esto,
    # un backlog (p. ej. una etapa apagada unos días) bloquea la admisión para siempre.
    try:
        _ingesta.caducar_temas_viejos()
    except Exception:  # noqa: BLE001 -- la caducidad es saneo; nunca rompe el barrido
        _log.exception("pipeline: fallo la caducidad de temas en vuelo.")
    # --- Fase CI · "Crear noticias": crea los temas (sin copy) por marca. --------------------
    # Etapa CI = toggle "Crear noticias" (`KENI_PIPELINE_SELECCION`), 1 toggle = 1 etapa: si el maestro está
    # OFF no entran temas nuevos (aunque el daemon barra por otra etapa, p. ej. Copy de temas ya
    # ingeridos). Por marca, el override `KENI_PIPELINE_SELECCION::marca=0` excluye esa marca de la ingesta.
    # CI consume el pool ya FUSIONADO y RANKEADO (Ola B): promueve las top-N historias por marca
    # (no un tema por item RSS), ordenadas por el score del algoritmo de ponderación. Esto frena el
    # volumen y respeta la jerarquización. El clustering del pool lo alimenta el daemon de ingesta.
    temas_nuevos: list[dict[str, Any]] = []
    for marca in marcas.ids():
        # FUENTE ÚNICA de verdad (config.etapa_activa): maestro global ON y marca no excluida.
        # La misma lectura que pinta la etapa en /api/pipelines y el toggle en el catálogo.
        if not config.etapa_activa(config.ENV_PIPELINE_SELECCION, marca):
            continue
        # NOTA (frescura): con la etapa Copy apagada para la marca, lo admitido queda "apto sin
        # copy" (curación manual en el tablero) y, si nadie lo trabaja, CADUCA al TTL — el gate
        # serial se libera solo y al día siguiente entra lo fresco del ranking, nunca el backlog.
        # SERIAL POR MARCA: no metas más historias si esta marca ya tiene cola EN VUELO (sin
        # cribar/sin copy). Promueve solo hasta llenar su cupo; si está lleno, salta. Así cada item
        # que entró se COMPLETA (QA→copy) antes de meter nuevos, en vez de atascar QA con backlog.
        cupo = config.pipeline_en_vuelo_max() - _ingesta.temas_en_vuelo(marca)
        if cupo <= 0:
            continue
        # CUPOS DE VOLUMEN (día móvil + franja horaria): anclan la producción a la cadencia
        # real de publicación de la marca y convierten la admisión en SELECCIÓN (pocas plazas
        # por franja, para las mejores historias del ranking en ese momento). None = sin cupos.
        cupo_volumen = _ingesta.cupo_produccion_restante(marca)
        if cupo_volumen is not None:
            if cupo_volumen <= 0:
                _log.debug("pipeline: cupo de volumen agotado para %s; franja/día llenos.", marca)
                continue
            cupo = min(cupo, cupo_volumen)
        try:
            temas_nuevos.extend(promover_clusters_marca(marca, maximo=min(maximo, cupo)))
        except Exception:  # noqa: BLE001 -- un fallo de una marca no rompe el barrido
            _log.exception("pipeline: fallo la promoción de historias (CI) de la marca %s", marca)
            continue
    # --- Fase QA (criba de la fuente) + Fase CD (copy) + Etapa ARTE. -------------------------
    cribados = ejecutar_qa(autor=autor)
    lanzados = ejecutar_cd(autor=autor)
    # Etapa de arte (tras copy): ilustra los temas con copy y sin imagen. Gateada por su propio
    # toggle "Generar arte" (KENI_PIPELINE_ARTE) + máquina; si está OFF, devuelve [].
    artes = ejecutar_arte()
    if temas_nuevos or cribados or lanzados or artes:
        _log.info(
            "pipeline: %d tema(s) ingerido(s) (CI), %d cribado(s) (QA), %d copy encolado(s) (CD), "
            "%d arte(s) (etapa arte).",
            len(temas_nuevos), len(cribados), len(lanzados), len(artes),
        )
    return {"temas": temas_nuevos, "cribados": cribados, "lanzados": lanzados, "artes": artes}


def ejecutar_qa(*, autor: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Fase QA del tick: lanza la CRIBA de la fuente (`claude -p`) de los temas sin veredicto.

    SIN tope propio (flujo continuo): aquí solo puede haber lo que la ADMISIÓN dejó entrar (gate
    serial en vuelo por marca); el backpressure real lo pone la cola (`ColaLlenaError` corta la
    fase y el siguiente tick reintenta). REINTENTOS ACOTADOS: cada lanzamiento anota su intento
    en el tema; al agotar `_MAX_INTENTOS_ETAPA`, el tema se marca `problema` (sale del cupo en
    vuelo y el fallo queda visible). Best-effort por tema. Devuelve los temas cuya QA se lanzó.
    """
    if autor is None:
        autor = _ref._autor_pipeline()
    cribados: list[dict[str, Any]] = []
    for tema in temas_sin_qa():
        marca_t = tema.get("marca") or ""
        # Etapa QA desactivada (`KENI_PIPELINE_VALIDACION` off, global o `::marca`): se SALTA la criba.
        # No se lanza `claude -p`; se marca el tema `saltada` para que CD lo recoja igual (sin
        # verificar) y la vista Pipelines pinte QA como "saltada". No cuenta para el cap ni rompe.
        # Misma FUENTE ÚNICA (config.etapa_activa) que la vista y el catálogo de ajustes.
        if not config.etapa_activa(config.ENV_PIPELINE_VALIDACION, marca_t):
            try:
                repos.actualizar_contenido(tema.get("id", "") or "", {"qa_veredicto": QA_SALTADA})
            except Exception:  # noqa: BLE001 -- un fallo al marcar saltada no debe matar la fase
                _log.exception("pipeline: fallo al marcar QA saltada de un tema.")
            else:
                cribados.append({"id": tema.get("id", ""), "gen_id": "", "verdicto": QA_SALTADA})
            continue
        # Reintentos acotados: una QA que falla vuelve a "sin veredicto" (saneo del worker) y se
        # relanzaría cada tick para siempre; al agotar los intentos, salida TERMINAL (problema).
        if intentos_de(tema, "qa_intentos") >= _MAX_INTENTOS_ETAPA:
            marcar_fallo_etapa(
                tema.get("id", "") or "", "Validación",
                f"La criba de la fuente falló {_MAX_INTENTOS_ETAPA} veces.",
            )
            continue
        # Backoff creciente entre intentos (1/4/16 min): un fallo transitorio no quema los 3
        # intentos en <1 min con el tick corto; se SALTA el tema (el barrido no duerme).
        if en_backoff(tema, "qa_intentos"):
            continue
        try:
            gen = lanzar_qa_fuente(tema, autor=autor)
        except generaciones.ColaLlenaError as e:
            # El mensaje distingue cola llena de pausa/presupuesto (subclases): que el log diga
            # la verdad ("presupuesto agotado" no es "demasiadas generaciones").
            _log.info("pipeline: QA en pausa por admisión (%s); el resto entra en el próximo tick.", e)
            break
        except Exception:  # noqa: BLE001 -- un fallo por tema no debe matar la fase QA
            _log.exception(
                "pipeline: fallo la criba de la fuente (QA) del tema %s (marca %s).",
                tema.get("id", ""), marca_t,
            )
            continue
        if gen is not None:
            # El intento se anota TRAS el lanzamiento efectivo: una cola llena o un fallo
            # previo al lanzamiento no queman intentos (solo los `claude -p` reales cuentan).
            anotar_intento(tema, "qa_intentos")
            cribados.append({"id": tema.get("id", ""), "gen_id": gen.get("id", ""), "verdicto": QA_EN_CURSO})
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
    SIN topes propios (flujo continuo): el carril 1 lo acota la ADMISIÓN (gate serial en vuelo);
    el carril 2, el dedup por etiqueta + el backpressure de la cola. Si la cola se llena, corta la
    fase (el siguiente tick reintenta). REINTENTOS ACOTADOS en el carril 1: al agotar
    `_MAX_INTENTOS_ETAPA`, el tema se marca `problema` (sale del cupo en vuelo, fallo visible).
    Best-effort por tema. Devuelve las generaciones de copy lanzadas.
    """
    if autor is None:
        autor = _ref._autor_pipeline()
    # Etapa CD = toggle "Generar copy" (`KENI_PIPELINE_COPY`), 1 toggle = 1 etapa: si el maestro está
    # OFF no se genera copy (aunque el daemon barra por otra etapa). Por marca se filtra abajo.
    if not config.pipeline_activo():
        return []
    lanzados: list[dict[str, Any]] = []
    for tema in temas_para_copy():
        # Exclusión por marca: no generamos copy de temas de una marca apagada a mano (aunque
        # ya estuvieran ingeridos antes de apagarla). Misma FUENTE ÚNICA que la vista/catálogo.
        if not config.etapa_activa(config.ENV_PIPELINE_COPY, tema.get("marca") or ""):
            continue
        # Reintentos acotados: un copy fallido conserva `copy_pendiente` (dedup al éxito) y se
        # relanzaría cada tick para siempre; al agotar los intentos, salida TERMINAL (problema).
        if intentos_de(tema, "cd_intentos") >= _MAX_INTENTOS_ETAPA:
            marcar_fallo_etapa(
                tema.get("id", "") or "", "Copy",
                f"La generación de copy falló {_MAX_INTENTOS_ETAPA} veces.",
            )
            continue
        # Backoff creciente entre intentos (1/4/16 min): mismo rationale que en la fase QA.
        if en_backoff(tema, "cd_intentos"):
            continue
        try:
            gen = lanzar_copy_de_tema(tema, autor=autor)
        except generaciones.ColaLlenaError as e:
            _log.info("pipeline: CD en pausa por admisión (%s); el resto entra en el próximo tick.", e)
            return lanzados
        except Exception:  # noqa: BLE001 -- un fallo por tema no debe matar la fase CD
            _log.exception(
                "pipeline: fallo la generación de copy (CD) del tema %s (marca %s).",
                tema.get("id", ""), tema.get("marca", ""),
            )
            continue
        if gen:
            # Tras el lanzamiento efectivo (cola llena o fallo previo no queman intentos). Si el
            # copy completó EN LÍNEA (tests síncronos), `copy_pendiente` ya se limpió y no anota.
            anotar_intento(tema, "cd_intentos")
            lanzados.append(gen)
    # Fundido de la selección de autogen_copy: la etapa de copy también redacta los temas del
    # news-pool/tablero (orígenes de noticias) que aún no tienen copy, vía el lanzador NEUTRO.
    from .. import autogen_copy

    for item in temas_autogen_sin_copy():
        try:
            gen = autogen_copy.lanzar_para_topic(item)
        except generaciones.ColaLlenaError as e:
            _log.info("pipeline: CD (pool) en pausa por admisión (%s); el resto entra en el próximo barrido.", e)
            break
        except Exception:  # noqa: BLE001 -- un fallo por tema no debe matar la fase CD
            _log.exception(
                "pipeline: fallo la generación de copy (CD) del tema %s del pool (marca %s).",
                item.get("id", ""), item.get("marca", ""),
            )
            continue
        if gen:
            lanzados.append(gen)
    return lanzados


# Fracción de lanzamientos de arte fallidos en un ciclo a partir de la cual se emite UN ERROR
# agregado (señal de proveedor de imagen caído, no de temas sueltos).
_UMBRAL_FALLO_ARTE = 0.5


def ejecutar_arte() -> list[dict[str, Any]]:
    """Etapa de ARTE del pipeline (tras copy): ilustra los temas con copy y sin imagen.

    Toggle "Generar arte" (`KENI_PIPELINE_ARTE`, gateado además por el maestro `KENI_MAQUINA`).
    FUNDE el antiguo daemon suelto `autogen_arte`: reutiliza su selección
    (`autogen_arte.topics_sin_arte`) y su lanzador (`autogen_arte.lanzar_para_topic` →
    `media.generar_imagen`), con cap por barrido (`KENI_AUTOGEN_ARTE_MAX`). Per-marca: salta las
    marcas apagadas a mano (lo hace la propia selección, gateada por `ENV_PIPELINE_ARTE`). Sin
    proveedor de imagen configurado, no hace nada. Best-effort: un fallo por tema se loguea y se
    sigue. Devuelve los artes adjuntados.

    GATEADO EN VIVO: solo actúa con `KENI_PIPELINE_ARTE=1` Y `KENI_MAQUINA=1`. Sin el toggle, la
    etapa no ilustra (el equipo hace el arte a mano).
    """

    from .. import autogen_arte

    if not config.gate_maquina(config.autogen_arte_activo)():
        return []
    from .. import media

    if not media.proveedor_configurado():
        _log.info("pipeline: etapa de arte sin proveedor de imagen configurado; se omite.")
        return []
    try:
        # Solo la clase 'contenido' (el filtro va en SQL; las tareas nunca se ilustran).
        # `topics_sin_arte` aplica el resto de reglas (estado, copy sin imagen, dedup...).
        items = repos.listar_contenido(clase="contenido")
    except Exception:  # noqa: BLE001 -- sin tablero, la etapa de arte no actúa
        _log.exception("pipeline: no se pudo leer el tablero para la etapa de arte.")
        return []
    elegidos = autogen_arte.topics_sin_arte(
        items,
        plataformas_por_item=autogen_arte._plataformas_por_item(items),
        ya_procesados=autogen_arte.ids_ya_procesados(),
        maximo=config.autogen_arte_max(),
        etiquetas_por_item=autogen_arte._etiquetas_por_item(),
        hoy=hoy_utc(),
    )

    # EN PARALELO (antes en serie): cada arte es una llamada HTTP sincrona al proveedor de
    # imagen (segundos por tema); con el cap por barrido (def 3), ilustrarlos a la vez deja
    # la etapa en ~el tiempo del mas lento. Cada tema es independiente y best-effort.
    fallidos: list[str] = []  # ids de los temas cuyo arte reventó en ESTE ciclo (append es atómico)

    def _ilustrar(item: dict[str, Any]) -> dict[str, Any] | None:
        try:
            return autogen_arte.lanzar_para_topic(item)
        except Exception:  # noqa: BLE001 -- un fallo por tema no debe matar la etapa de arte
            fallidos.append(str(item.get("id", "") or ""))
            _log.exception(
                "pipeline: fallo la generación de arte del tema %s (marca %s).",
                item.get("id", ""), item.get("marca", ""),
            )
            return None

    adjuntados: list[dict[str, Any]] = []
    if elegidos:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(
            max_workers=min(4, len(elegidos)), thread_name_prefix="pipeline-arte"
        ) as pool:
            adjuntados = [res for res in pool.map(_ilustrar, elegidos) if res]
    # Fallo MASIVO (> _UMBRAL_FALLO_ARTE de los lanzamientos del ciclo): casi seguro el proveedor
    # de imagen caído, no temas sueltos. Un ÚNICO ERROR agregado (alertable), además de los
    # `exception` por tema de arriba.
    if elegidos and len(fallidos) > _UMBRAL_FALLO_ARTE * len(elegidos):
        _log.error(
            "pipeline: arte: %d/%d lanzamiento(s) fallido(s) en este barrido "
            "(¿proveedor de imagen caído?). Temas: %s",
            len(fallidos), len(elegidos), ", ".join(fallidos),
        )
    if adjuntados:
        _log.info("pipeline: %d tema(s) ilustrado(s) (etapa arte).", len(adjuntados))
    return adjuntados


# TICK del flujo continuo (constante, NO un ajuste): el pipeline ya no barre "por tandas" cada
# N minutos; reacciona al ESTADO cada pocos segundos. En cuanto la QA de una pieza termina, el
# siguiente tick lanza su Copy (latencia entre etapas: segundos, no minutos). El volumen NO lo
# pone el tick sino la ADMISIÓN (gate serial en vuelo por marca) + el backpressure de la cola;
# un tick sin trabajo son unas pocas lecturas indexadas a BD.
_TICK_SEGUNDOS = 15.0


def _intervalo_segundos() -> float:
    """Cadencia del tick del flujo continuo (constante; el volumen lo regula la admisión)."""
    return _TICK_SEGUNDOS


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
