"""Barrido del pipeline en DOS procesos independientes (ADR 0011 F3) + daemons.

  • INVESTIGACIÓN — caducidad + CI (admisión) → QA de la fuente. Recolecta del pool rankeado,
    admite por marca y verifica. Loop propio (gate Selección/Validación, lock
    `pipeline_investigacion`).
  • PRODUCCIÓN — CD (copy) → arte → avance a revisión. Convierte la historia verificada en
    pieza. Loop propio (gate siempre-activo bajo la máquina por el AVANCE, lock
    `pipeline_produccion`).

`iniciar_pipeline` arranca un hilo demonio gateado en vivo por proceso. `ejecutar_barrido`
(combinado) corre los dos en orden para el disparo a demanda y los tests.
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
    VERDICTO_NO_VERIFICADO,
    _log,
    anotar_intento,
    en_backoff,
    intentos_de,
    marcar_fallo_etapa,
)
from ._avance import ejecutar_avance
from ._copy import lanzar_copy_de_tema, temas_autogen_sin_copy, temas_para_copy
from ._ingesta import clusters_pendientes_qa, promover_clusters_marca
from ._qa import lanzar_qa_cluster, lanzar_qa_fuente, temas_sin_qa

__all__ = [
    "ejecutar_barrido",
    "_ejecutar_barrido",
    "ejecutar_investigacion",
    "_ejecutar_investigacion",
    "ejecutar_produccion",
    "_ejecutar_produccion",
    "ejecutar_qa",
    "ejecutar_qa_clusters",
    "ejecutar_cd",
    "ejecutar_arte",
    "ejecutar_avance",
    "_intervalo_segundos",
    "_intervalo_investigacion_segundos",
    "_intervalo_produccion_segundos",
    "iniciar_pipeline",
]

# DOS PROCESOS (ADR 0011 F3): el espinazo noticia→pieza son DOS loops independientes, no uno.
#   • INVESTIGACIÓN — caducidad + CI (admisión) + QA (criba de la fuente). Recolecta, admite y
#     VERIFICA. Su gate es `alguna_etapa_investigacion_activa` (Selección/Validación) bajo la
#     máquina; su lock es `pipeline_investigacion`.
#   • PRODUCCIÓN — CD (copy) + arte + avance a revisión. Convierte la historia verificada en
#     pieza. Su gate es `alguna_etapa_produccion_activa` (siempre True bajo la máquina: el
#     AVANCE corre incondicional); su lock es `pipeline_produccion`.
# Cada loop tiene su propio hilo demonio, cadencia y single-flight, así que se pueden
# encender/parar y escalar por separado (investigar sin producir, p. ej.). `ejecutar_barrido`
# (combinado) sigue existiendo para el disparo a demanda y los tests: corre los dos en orden.
_LOCK_INVESTIGACION = "pipeline_investigacion"
_LOCK_PRODUCCION = "pipeline_produccion"


def ejecutar_investigacion() -> dict[str, Any]:
    """Un TICK del proceso de INVESTIGACIÓN: caducidad + CI (admisión) → QA de la fuente.

    Recolecta del pool ya fusionado/rankeado, ADMITE por marca solo hasta llenar el cupo en
    vuelo (gate serial WIP) y lanza la CRIBA de la fuente (`claude -p`) de lo admitido sin
    veredicto. Best-effort. Devuelve `{temas, cribados}`.

    SINGLE-FLIGHT cross-proceso (advisory lock): el daemon de investigación y el disparo a
    demanda comparten este barrido; el dedup (`_claves_dedup_marca`) es leer-luego-escribir en
    Python, así que dos barridos solapados podrían admitir/cribar el MISMO tema dos veces. El
    lock hace que un segundo barrido concurrente salga de inmediato con un resumen vacío.
    """
    from .. import db

    with db.lock_barrido(_LOCK_INVESTIGACION) as ok:
        if not ok:
            _log.debug("investigación: otro barrido en curso; se omite este.")
            return {"temas": [], "cribados": []}
        return _ejecutar_investigacion()


def ejecutar_produccion() -> dict[str, Any]:
    """Un TICK del proceso de PRODUCCIÓN: CD (copy) → arte → avance a revisión.

    Genera copy SOLO de los temas verificados (`temas_para_copy`), los ilustra (etapa arte) y
    avanza los borradores completos a la cola de revisión. Best-effort. Devuelve
    `{lanzados, artes, avances}`. Single-flight con su propio lock (`pipeline_produccion`):
    independiente del de investigación, así los dos loops nunca se serializan entre sí.
    """
    from .. import db

    with db.lock_barrido(_LOCK_PRODUCCION) as ok:
        if not ok:
            _log.debug("producción: otro barrido en curso; se omite este.")
            return {"lanzados": [], "artes": [], "avances": []}
        return _ejecutar_produccion()


def ejecutar_barrido() -> dict[str, Any]:
    """Un TICK COMBINADO (investigación + producción) EN ORDEN: para el disparo a demanda y los
    tests, que esperan el resumen completo `{temas, cribados, lanzados, artes, avances}`.

    En producción real cada proceso corre en su PROPIO hilo (`iniciar_pipeline` arranca los
    dos); este combinado existe para conservar la entrada única a demanda. Cada mitad toma su
    propio lock, así que el single-flight sigue siendo por proceso.
    """
    inv = ejecutar_investigacion()
    prod = ejecutar_produccion()
    return {**inv, **prod}


# Estados del EMBUDO de verificación: clusters `nuevo` que ya entraron al circuito de QA y aún
# no se admitieron (en vuelo, verificados-pendientes o saltados). Acotan cuánta QA se lanza por
# tick (presupuesto = tope en vuelo − embudo) para que la criba no recorra todo el pool.
_FUNNEL_QA = (QA_EN_CURSO, VERDICTO_NO_VERIFICADO, QA_SALTADA)
# Veredictos que SÍ admiten a producción: la historia pasó la criba (o la QA estaba saltada).
_VERIFICADAS = (VERDICTO_NO_VERIFICADO, QA_SALTADA)


def _ejecutar_investigacion() -> dict[str, Any]:
    """Cuerpo de INVESTIGACIÓN (ya bajo el single-flight de `ejecutar_investigacion`).

    Rediseño F3 (la frontera "QA = investigación" en los datos): la QA corre sobre la HISTORIA
    (cluster) ANTES de materializar contenido, y la admisión solo promueve las VERIFICADAS:
      0) FRESCURA: caduca los temas en vuelo (TTL) y resetea las QA de cluster `en_curso` zombi.
      1) QA: criba las candidatas sin veredicto (top del ranking que pasan el listón), acotada
         por el embudo. Asíncrona; persiste el veredicto en el cluster.
      2) ADMISIÓN: promueve a tema (con copy pendiente) las historias ya verificadas, heredando
         su veredicto al contenido. Las `problema` no se materializan.
    """
    autor = _ref._autor_pipeline()
    maximo = config.pipeline_max()
    # --- Fase 0 · FRESCURA. ------------------------------------------------------------------
    # VENTANA DESLIZANTE sobre el ranking: lo que no se completó a tiempo caduca y libera su hueco
    # (temas en vuelo); y una QA de cluster que murió (en_curso zombi) se resetea para re-cribar.
    try:
        _ingesta.caducar_temas_viejos()
    except Exception:  # noqa: BLE001 -- la caducidad es saneo; nunca rompe el barrido
        _log.exception("pipeline: fallo la caducidad de temas en vuelo.")
    try:
        _ingesta.caducar_qa_clusters_en_curso()
    except Exception:  # noqa: BLE001 -- el reaper de QA es saneo; nunca rompe el barrido
        _log.exception("pipeline: fallo el reaper de QA de clusters en curso.")
    # --- Fase QA (criba de la FUENTE sobre la historia, pre-admisión). -----------------------
    cribados = ejecutar_qa_clusters(autor=autor)
    # --- Fase ADMISIÓN · "Crear noticias": materializa las historias YA VERIFICADAS por marca. -
    # Etapa CI = toggle "Crear noticias" (`KENI_PIPELINE_SELECCION`): si está OFF no entra nada. La
    # admisión consume el pool RANKEADO restringido a las verificadas (`no_verificado`/`saltada`),
    # llena el cupo en vuelo (gate serial WIP) y los cupos del plan/diario, y HEREDA el veredicto
    # del cluster al contenido (la pieza nace verificada y lista para copy).
    temas_nuevos: list[dict[str, Any]] = []
    for marca in marcas.ids():
        # FUENTE ÚNICA de verdad (config.etapa_activa): maestro global ON y marca no excluida.
        if not config.etapa_activa(config.ENV_PIPELINE_SELECCION, marca):
            continue
        # SERIAL POR MARCA: no metas más historias si esta marca ya tiene cola EN VUELO (sin copy).
        cupo = config.pipeline_en_vuelo_max() - _ingesta.temas_en_vuelo(marca)
        if cupo <= 0:
            continue
        # VOLUMEN: con PLAN EDITORIAL DIARIO, llena los cupos POR CATEGORÍA que queden hoy; sin
        # plan, cae al cupo diario simple. La admisión es SELECCIÓN, no goteo.
        cupos_cat = _ingesta.cupos_categoria_restantes(marca)
        if cupos_cat is not None:
            if not cupos_cat:
                _log.debug("pipeline: plan diario de %s completo; hoy no entra más.", marca)
                continue
            cupo = min(cupo, sum(cupos_cat.values()))
        else:
            cupo_volumen = _ingesta.cupo_produccion_restante(marca)
            if cupo_volumen is not None:
                if cupo_volumen <= 0:
                    _log.debug("pipeline: cupo diario agotado para %s.", marca)
                    continue
                cupo = min(cupo, cupo_volumen)
        try:
            temas_nuevos.extend(promover_clusters_marca(
                marca, maximo=min(maximo, cupo), cupos_categoria=cupos_cat,
                qa_estados=_VERIFICADAS,
            ))
        except Exception:  # noqa: BLE001 -- un fallo de una marca no rompe el barrido
            _log.exception("pipeline: fallo la admisión de historias (CI) de la marca %s", marca)
            continue
    if temas_nuevos or cribados:
        _log.info(
            "investigación: %d cribado(s) (QA), %d tema(s) admitido(s) (CI).",
            len(cribados), len(temas_nuevos),
        )
    return {"temas": temas_nuevos, "cribados": cribados}


def ejecutar_qa_clusters(*, autor: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Fase QA del proceso de INVESTIGACIÓN (ADR 0011 F3): criba la FUENTE de las HISTORIAS
    candidatas ANTES de materializar contenido.

    Por marca con admisión activa (`KENI_PIPELINE_SELECCION`): toma las candidatas sin veredicto
    que pasan el listón (`clusters_pendientes_qa`), acotadas por el presupuesto del EMBUDO
    (`tope en vuelo − embudo`) para no cribar todo el pool. Si la Validación está activa, lanza
    la criba `claude -p` y marca el cluster `en_curso` (asíncrona: el veredicto lo persiste el
    `procesar` sobre el cluster). Si la Validación está OFF para la marca, marca el cluster
    `saltada` (sin `claude -p`) para que la admisión lo promueva igual. Best-effort por historia;
    `ColaLlenaError` corta la criba de esa marca (el siguiente tick reintenta). Devuelve los
    cribados (`{id, gen_id, verdicto}`).
    """
    if autor is None:
        autor = _ref._autor_pipeline()
    cribados: list[dict[str, Any]] = []
    en_vuelo_max = config.pipeline_en_vuelo_max()
    for marca in marcas.ids():
        # La QA solo tiene sentido si la admisión de la marca está activa (solo verificamos lo que
        # admitiríamos). El override por marca de Selección excluye la marca aquí también.
        if not config.etapa_activa(config.ENV_PIPELINE_SELECCION, marca):
            continue
        # PRESUPUESTO DEL EMBUDO: no cribes más de lo que cabe en vuelo (verificación acotada,
        # como la admisión). A medida que la admisión drena verificadas (pasan a `usado`), el
        # embudo encoge y se libera presupuesto para cribar la siguiente tanda.
        try:
            embudo = repos.contar_clusters_funnel_qa(marca, _FUNNEL_QA)
        except Exception:  # noqa: BLE001 -- sin contador fiable, no cribamos esta marca este tick
            _log.warning("pipeline: no se pudo contar el embudo de QA (%s)", marca, exc_info=True)
            continue
        presupuesto = en_vuelo_max - embudo
        if presupuesto <= 0:
            continue
        pendientes = clusters_pendientes_qa(marca, maximo=presupuesto)
        if not pendientes:
            continue
        # Validación OFF para la marca: se SALTA la criba; el cluster se marca `saltada` para que
        # la admisión lo promueva igual (sin verificar). Misma FUENTE ÚNICA (config.etapa_activa).
        validacion_on = config.etapa_activa(config.ENV_PIPELINE_VALIDACION, marca)
        for cluster in pendientes:
            cid = (cluster.get("id") or "").strip()
            if not cid:
                continue
            if not validacion_on:
                try:
                    repos.marcar_cluster_qa(cid, QA_SALTADA)
                except Exception:  # noqa: BLE001 -- un fallo al marcar saltada no mata la fase
                    _log.exception("pipeline: fallo al marcar QA de cluster saltada (%s).", cid)
                else:
                    cribados.append({"id": cid, "gen_id": "", "verdicto": QA_SALTADA})
                continue
            try:
                gen = lanzar_qa_cluster(cluster, autor=autor)
            except generaciones.ColaLlenaError as e:
                _log.info("pipeline: QA en pausa por admisión (%s); el resto entra en el próximo tick.", e)
                break
            except Exception:  # noqa: BLE001 -- un fallo por historia no debe matar la fase QA
                _log.exception("pipeline: fallo la criba de la fuente (QA) de la historia %s (marca %s).", cid, marca)
                continue
            if gen is not None:
                cribados.append({"id": cid, "gen_id": gen.get("id", "") if isinstance(gen, dict) else "", "verdicto": QA_EN_CURSO})
    return cribados


def _ejecutar_produccion() -> dict[str, Any]:
    """Cuerpo de PRODUCCIÓN (ya bajo el single-flight de `ejecutar_produccion`)."""
    autor = _ref._autor_pipeline()
    # --- Fase CD (copy) + Etapa ARTE + Etapa AVANCE. -----------------------------------------
    lanzados = ejecutar_cd(autor=autor)
    # Etapa de arte (tras copy): ilustra los temas con copy y sin imagen. Gateada por su propio
    # toggle "Generar arte" (KENI_PIPELINE_ARTE) + máquina; si está OFF, devuelve [].
    artes = ejecutar_arte()
    # Etapa de AVANCE (tras arte): los borradores COMPLETOS (copy + foto) entran solos a la
    # cola de revisión. Incondicional bajo el maestro KENI_MAQUINA (sin toggle propio).
    avances = ejecutar_avance()
    if lanzados or artes or avances:
        _log.info(
            "producción: %d copy encolado(s) (CD), %d arte(s) (etapa arte), %d avance(s) (a revisión).",
            len(lanzados), len(artes), len(avances),
        )
    return {"lanzados": lanzados, "artes": artes, "avances": avances}


def _ejecutar_barrido() -> dict[str, Any]:
    """Cuerpo COMBINADO (investigación + producción) SIN locks: para los tests que parchean
    `_ejecutar_barrido` y esperan el resumen completo en una sola pasada determinista."""
    inv = _ejecutar_investigacion()
    prod = _ejecutar_produccion()
    return {**inv, **prod}


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


# TICK del flujo continuo (constante, NO un ajuste): los loops ya no barren "por tandas" cada
# N minutos; reaccionan al ESTADO cada pocos segundos. En cuanto la QA de una pieza termina, el
# siguiente tick de producción lanza su Copy (latencia entre etapas: segundos, no minutos). El
# volumen NO lo pone el tick sino la ADMISIÓN (gate serial en vuelo por marca) + el backpressure
# de la cola; un tick sin trabajo son unas pocas lecturas indexadas a BD. Cada proceso tiene su
# propia constante para poder divergir (p. ej. investigar más rápido que producir) sin tocar el
# otro; hoy ambos son 15 s.
_TICK_INVESTIGACION_SEGUNDOS = 15.0
_TICK_PRODUCCION_SEGUNDOS = 15.0
_TICK_SEGUNDOS = _TICK_INVESTIGACION_SEGUNDOS  # alias retro: cadencia "del pipeline" = investigación.


def _intervalo_investigacion_segundos() -> float:
    """Cadencia del tick de INVESTIGACIÓN (constante; el volumen lo regula la admisión)."""
    return _TICK_INVESTIGACION_SEGUNDOS


def _intervalo_produccion_segundos() -> float:
    """Cadencia del tick de PRODUCCIÓN (constante; el volumen lo regula la admisión/cola)."""
    return _TICK_PRODUCCION_SEGUNDOS


def _intervalo_segundos() -> float:
    """Alias retro de la cadencia del flujo continuo (= investigación)."""
    return _TICK_SEGUNDOS


def iniciar_pipeline(
    intervalo_segundos: float | None = None,
) -> tuple[threading.Thread, threading.Thread]:
    """Arranca los DOS hilos demonio del pipeline de contenido (ADR 0011 F3, GATEADOS EN VIVO).

    Pensado para el servidor real (`daemons`/`__main__`), NO para `crear_app` (los tests no lo
    arrancan, igual que el resto de daemons). Arranca un hilo por proceso:
      • INVESTIGACIÓN — gate `alguna_etapa_investigacion_activa` (Selección/Validación) bajo la
        máquina: con ambas etapas OFF el loop duerme (nada que admitir/cribar).
      • PRODUCCIÓN — gate `alguna_etapa_produccion_activa` (siempre True bajo la máquina: el
        AVANCE de borradores completos a revisión corre incondicional, así nunca se duerme con
        la máquina ON). Copy/Arte se auto-gatean dentro del barrido por su propio toggle.
    Apagar/encender en runtime aplica sin reiniciar. Los hilos son daemon; un fallo de barrido se
    loguea y NO los mata. Devuelve `(hilo_investigacion, hilo_produccion)`.
    """
    intervalo_inv = (
        intervalo_segundos if intervalo_segundos is not None else _intervalo_investigacion_segundos()
    )
    intervalo_prod = (
        intervalo_segundos if intervalo_segundos is not None else _intervalo_produccion_segundos()
    )

    def bucle_investigacion() -> None:
        daemon_util.bucle_gateado(
            activo_fn=config.gate_maquina(config.alguna_etapa_investigacion_activa),
            intervalo_seg_fn=lambda: intervalo_inv,
            sweep_fn=ejecutar_investigacion,
            log=_log,
            nombre="investigacion",
        )

    def bucle_produccion() -> None:
        daemon_util.bucle_gateado(
            activo_fn=config.gate_maquina(config.alguna_etapa_produccion_activa),
            intervalo_seg_fn=lambda: intervalo_prod,
            sweep_fn=ejecutar_produccion,
            log=_log,
            nombre="produccion",
        )

    hilo_inv = threading.Thread(
        target=bucle_investigacion, name="pipeline-investigacion-daemon", daemon=True
    )
    hilo_prod = threading.Thread(
        target=bucle_produccion, name="pipeline-produccion-daemon", daemon=True
    )
    hilo_inv.start()
    hilo_prod.start()
    estado = "ACTIVA" if config.maquina_activa() else "EN ESPERA (máquina apagada)"
    _log.info(
        "Pipeline de contenido %s — investigación cada %.0fs, producción cada %.0fs (max/barrido=%d).",
        estado, intervalo_inv, intervalo_prod, config.pipeline_max(),
    )
    return hilo_inv, hilo_prod
