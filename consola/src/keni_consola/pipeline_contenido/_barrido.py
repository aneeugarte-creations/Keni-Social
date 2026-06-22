"""Barrido del pipeline en DOS procesos independientes (ADR 0011) + daemons.

  • INVESTIGACIÓN — caducidad + CI (admisión) → verificación de la fuente. Recolecta del pool rankeado,
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
from . import _admitir, _ref
from ._comun import (
    _MAX_INTENTOS_ETAPA,
    VERIFICACION_EN_CURSO,
    VERIFICACION_SALTADA,
    VERIFICACION_VERIFICADO,
    VERIFICADAS_OK,
    _copy_pendiente_leido,
    _log,
    anotar_intento,
    en_backoff,
    intentos_de,
    marcar_fallo_etapa,
)
from ._avance import ejecutar_avance
from ._redactar import lanzar_redactar_de_tema, temas_autogen_sin_copy, temas_para_redactar
from ._admitir import clusters_pendientes_verificar, promover_clusters_marca
from ._verificar import lanzar_verificar_cluster

__all__ = [
    "ejecutar_barrido",
    "_ejecutar_barrido",
    "ejecutar_investigacion",
    "_ejecutar_investigacion",
    "ejecutar_produccion",
    "_ejecutar_produccion",
    "ejecutar_portal",
    "_ejecutar_portal",
    "ejecutar_verificar_clusters",
    "ejecutar_redactar",
    "ejecutar_ilustrar",
    "ejecutar_avance",
    "_intervalo_segundos",
    "_intervalo_investigacion_segundos",
    "_intervalo_produccion_segundos",
    "_intervalo_portal_segundos",
    "iniciar_pipeline",
]

# DOS PROCESOS (ADR 0011): el espinazo noticia→pieza son DOS loops independientes, no uno.
#   • INVESTIGACIÓN — caducidad + CI (admisión) + verificación (verificación de la fuente). Recolecta, admite y
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
_LOCK_PORTAL = "pipeline_portal"

# Nombres de los DOS loops en `daemon_latidos` (= los que `iniciar_pipeline` arranca y que
# `latidos.BARRIBLES` declara): el destino del barrido FORZADO cross-proceso.
_DAEMON_INVESTIGACION = "investigacion"
_DAEMON_PRODUCCION = "produccion"
_DAEMON_PORTAL = "portal"

# Categoría del plan con la que nace una última hora (ver `_admitir.categoria_efectiva`).
_CATEGORIA_BREAKING = "breaking"


def _despertar_daemon(daemon: str) -> None:
    """Pide un barrido INMEDIATO del loop `daemon` vía el flag cross-proceso `barrido_solicitado`.

    Reutiliza el mecanismo que ya existe (`POST /api/sistema/daemons/{d}/barrer`): el
    `daemon_util.bucle_gateado` del loop consulta el flag en cada tick y, si está pedido Y su gate
    está ON, ejecuta el sweep YA (consumiéndolo: un solo barrido por solicitud). El tick de 15s
    sigue siendo el FALLBACK. Best-effort: si el daemon nunca latió (sin fila), si la BD no está o
    si el loop está apagado, no pasa nada. NUNCA lanza (despertar es un extra, no parte del flujo)."""
    try:
        from .. import db_latidos

        db_latidos.solicitar_barrido(daemon)
    except Exception:  # noqa: BLE001 -- despertar es best-effort; el tick de 15s ya recoge igual
        _log.debug("pipeline: no se pudo solicitar barrido de %s", daemon, exc_info=True)


def ejecutar_investigacion() -> dict[str, Any]:
    """Un TICK del proceso de INVESTIGACIÓN: caducidad + CI (admisión) → verificación de la fuente.

    Recolecta del pool ya fusionado/rankeado, ADMITE por marca solo hasta llenar el cupo en
    curso (gate serial WIP) y lanza la VERIFICACIÓN de la fuente (`claude -p`) de lo admitido sin
    verificacion. Best-effort. Devuelve `{temas, verificados}`.

    SINGLE-FLIGHT cross-proceso (advisory lock): el daemon de investigación y el disparo a
    demanda comparten este barrido; el dedup (`_claves_dedup_marca`) es leer-luego-escribir en
    Python, así que dos barridos solapados podrían admitir/verificar el MISMO tema dos veces. El
    lock hace que un segundo barrido concurrente salga de inmediato con un resumen vacío.
    """
    from .. import db

    with db.lock_barrido(_LOCK_INVESTIGACION) as ok:
        if not ok:
            _log.debug("investigación: otro barrido en curso; se omite este.")
            return {"temas": [], "verificados": []}
        return _ejecutar_investigacion()


def ejecutar_produccion() -> dict[str, Any]:
    """Un TICK del proceso de PRODUCCIÓN: CD (copy) → arte → avance a revisión.

    Genera copy SOLO de los temas verificados (`temas_para_redactar`), los ilustra (etapa Ilustrar) y
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


def ejecutar_portal() -> dict[str, Any]:
    """Un TICK del canal PORTAL: admite DIRECTO las historias de fuente PROPIA como temas
    `origen='portal'` (sin umbral ni verificación). La producción normal las redacta luego
    (`temas_pipeline` las incluye). Single-flight con su propio lock (`pipeline_portal`),
    independiente de investigación/producción. Devuelve `{temas}`."""
    from .. import db

    with db.lock_barrido(_LOCK_PORTAL) as ok:
        if not ok:
            _log.debug("portal: otro barrido en curso; se omite este.")
            return {"temas": []}
        return _ejecutar_portal()


def _ejecutar_portal() -> dict[str, Any]:
    """Cuerpo del canal PORTAL (bajo el single-flight de `ejecutar_portal`).

    Por marca con Recolectar activo, admite las historias de fuente PROPIA del pool como temas
    `origen='portal'`/`saltada` (cross-marca: TODO el contenido propio va al Portal, sin pasar por
    verificación). Best-effort por marca. Despierta producción si admitió algo. Devuelve `{temas}`.
    """
    temas: list[dict[str, Any]] = []
    maximo = config.pipeline_max()
    for marca in marcas.noticias():
        if not config.etapa_activa(config.ENV_PIPELINE_RECOLECTAR, marca):
            continue
        try:
            temas.extend(_admitir.promover_portal(marca, maximo=maximo))
        except Exception:  # noqa: BLE001 -- una marca problemática no aborta el barrido del Portal
            _log.exception("portal: fallo admitiendo la marca %s", marca)
    if temas:
        _despertar_daemon(_DAEMON_PRODUCCION)  # hay copy nuevo que redactar
    return {"temas": temas}


def ejecutar_barrido() -> dict[str, Any]:
    """Un TICK COMBINADO (investigación + producción) EN ORDEN: para el disparo a demanda y los
    tests, que esperan el resumen completo `{temas, verificados, lanzados, artes, avances}`.

    En producción real cada proceso corre en su PROPIO hilo (`iniciar_pipeline` arranca los
    dos); este combinado existe para conservar la entrada única a demanda. Cada mitad toma su
    propio lock, así que el single-flight sigue siendo por proceso.
    """
    inv = ejecutar_investigacion()
    prod = ejecutar_produccion()
    return {**inv, **prod}


# Estados del ADMISION de verificación: clusters `nuevo` que ya entraron al circuito de verificación y aún
# no se admitieron (en proceso, verificados-pendientes o saltados). Acotan cuánta verificación se lanza por
# tick (presupuesto = tope en proceso − admision) para que la verificación no recorra todo el pool.
_ADMISION_VERIFICACION = (VERIFICACION_EN_CURSO, VERIFICACION_VERIFICADO, VERIFICACION_SALTADA)


def _ejecutar_investigacion() -> dict[str, Any]:
    """Cuerpo de INVESTIGACIÓN (ya bajo el single-flight de `ejecutar_investigacion`).

    Rediseño F3 (la frontera "verificación = investigación" en los datos): la verificación corre sobre la HISTORIA
    (cluster) ANTES de materializar contenido, y la admisión solo promueve las VERIFICADAS:
      0) FRESCURA: caduca los temas en curso (TTL) y resetea las verificación de cluster `en_curso` atascadas.
      1) verificación: verifica las candidatas sin verificacion (top del ranking que pasan el umbral), acotada
         por el admision. Asíncrona; persiste el verificacion en el cluster.
      2) ADMISIÓN: promueve a tema (con copy pendiente) las historias ya verificadas, heredando
         su verificacion al contenido. Las `problema` no se materializan.
    """
    autor = _ref._autor_pipeline()
    maximo = config.pipeline_max()
    # --- Fase 0 · FRESCURA. ------------------------------------------------------------------
    # VENTANA DESLIZANTE sobre el ranking: lo que no se completó a tiempo caduca y libera su hueco
    # (temas en curso); y una verificación de cluster que murió (en_curso atascada) se resetea para re-verificar.
    try:
        _admitir.caducar_temas_viejos()
    except Exception:  # noqa: BLE001 -- la caducidad es limpieza; nunca rompe el barrido
        _log.exception("pipeline: fallo la caducidad de temas en curso.")
    try:
        _admitir.caducar_verificacion_clusters_en_curso()
    except Exception:  # noqa: BLE001 -- el limpiador de verificación es limpieza; nunca rompe el barrido
        _log.exception("pipeline: fallo el limpiador de verificación de clusters en curso.")
    # --- Fase verificación (verificación de la FUENTE sobre la historia, pre-admisión). -----------------------
    verificados = ejecutar_verificar_clusters(autor=autor)
    # --- Fase ADMISIÓN · "Crear noticias": materializa las historias YA VERIFICADAS por marca. -
    # Etapa CI = toggle "Crear noticias" (`KENI_PIPELINE_RECOLECTAR`): si está OFF no entra nada. La
    # admisión consume el pool RANKEADO restringido a las verificadas (`no_verificado`/`saltada`),
    # llena el cupo en curso (gate serial WIP) y los cupos del plan/diario, y HEREDA el verificacion
    # del cluster al contenido (la pieza nace verificada y lista para copy).
    temas_nuevos: list[dict[str, Any]] = []
    for marca in marcas.noticias():
        # FUENTE ÚNICA de verdad (config.etapa_activa): maestro global ON y marca no excluida.
        if not config.etapa_activa(config.ENV_PIPELINE_RECOLECTAR, marca):
            continue
        # SERIAL POR MARCA: no metas más historias si esta marca ya tiene cola en curso (sin copy).
        cupo = config.pipeline_en_proceso_max() - _admitir.temas_en_proceso(marca)
        if cupo <= 0:
            continue
        # VOLUMEN: con PLAN EDITORIAL DIARIO, llena los cupos POR CATEGORÍA que queden hoy; sin
        # plan, cae al cupo diario simple. La admisión es SELECCIÓN, no goteo.
        cupos_cat = _admitir.cupos_categoria_restantes(marca)
        if cupos_cat is not None:
            if not cupos_cat:
                _log.debug("pipeline: plan diario de %s completo; hoy no entra más.", marca)
                continue
            cupo = min(cupo, sum(cupos_cat.values()))
        else:
            cupo_volumen = _admitir.cupo_produccion_restante(marca)
            if cupo_volumen is not None:
                if cupo_volumen <= 0:
                    _log.debug("pipeline: cupo diario agotado para %s.", marca)
                    continue
                cupo = min(cupo, cupo_volumen)
        try:
            temas_nuevos.extend(promover_clusters_marca(
                marca, maximo=min(maximo, cupo), cupos_categoria=cupos_cat,
                verificacion_estados=VERIFICADAS_OK,
            ))
        except Exception:  # noqa: BLE001 -- un fallo de una marca no rompe el barrido
            _log.exception("pipeline: fallo la admisión de historias (CI) de la marca %s", marca)
            continue
    if temas_nuevos or verificados:
        _log.info(
            "investigación: %d verificado(s) (verificación), %d tema(s) admitido(s) (CI).",
            len(verificados), len(temas_nuevos),
        )
    # PRIORIDAD (no sólo polling): una ÚLTIMA HORA recién admitida no debe esperar al siguiente
    # tick de producción (hasta 15s) para que se le redacte el copy. Despertamos el loop de
    # PRODUCCIÓN vía el flag cross-proceso `barrido_solicitado` (el tick de 15s sigue de fallback).
    # El loop de INVESTIGACIÓN es ESTE mismo, así que no hay que despertarlo. Best-effort.
    if any((t.get("categoria") or "") == _CATEGORIA_BREAKING for t in temas_nuevos):
        _despertar_daemon(_DAEMON_PRODUCCION)
    return {"temas": temas_nuevos, "verificados": verificados}


def ejecutar_verificar_clusters(*, autor: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Fase verificación del proceso de INVESTIGACIÓN (ADR 0011): verifica la FUENTE de las HISTORIAS
    candidatas ANTES de materializar contenido.

    Por marca con admisión activa (`KENI_PIPELINE_RECOLECTAR`): toma las candidatas sin verificacion
    que pasan el umbral (`clusters_pendientes_verificar`), acotadas por el presupuesto del ADMISION
    (`tope en proceso − admision`) para no verificar todo el pool. Si la Validación está activa, lanza
    la verificación `claude -p` y marca el cluster `en_curso` (asíncrona: el verificacion lo persiste el
    `procesar` sobre el cluster). Si la Validación está OFF para la marca, la historia AJENA NO se
    verifica NI se admite: queda sin verificar en el pool para que el humano la decida (nada ajeno se
    auto-produce sin verificar). Best-effort por historia; `ColaLlenaError` corta la verificación de
    esa marca (el siguiente tick reintenta). Devuelve los verificados (`{id, gen_id, verificacion_fuente}`).

    MARCA PROPIA: las historias de fuente propia (`fuentes_rss.propia=1`) NO pasan por aquí —
    `clusters_pendientes_verificar` ya las omite—: las admite DIRECTO el canal Portal (sin
    verificación), aparte. Esta fase solo verifica las historias de fuentes AJENAS.
    """
    if autor is None:
        autor = _ref._autor_pipeline()
    verificados: list[dict[str, Any]] = []
    en_proceso_max = config.pipeline_en_proceso_max()
    for marca in marcas.noticias():
        # La verificación solo tiene sentido si la admisión de la marca está activa (solo verificamos lo que
        # admitiríamos). El override por marca de Selección excluye la marca aquí también.
        if not config.etapa_activa(config.ENV_PIPELINE_RECOLECTAR, marca):
            continue
        # PRESUPUESTO DEL ADMISION: no verifiques más de lo que cabe en proceso (verificación acotada,
        # como la admisión). A medida que la admisión vacía verificadas (pasan a `usado`), el
        # admision encoge y se libera presupuesto para verificar la siguiente tanda.
        try:
            admision = repos.contar_clusters_admision_verificacion(marca, _ADMISION_VERIFICACION)
        except Exception:  # noqa: BLE001 -- sin contador fiable, no verificamos esta marca este tick
            _log.warning("pipeline: no se pudo contar el admision de verificación (%s)", marca, exc_info=True)
            continue
        presupuesto = en_proceso_max - admision
        if presupuesto <= 0:
            continue
        pendientes = clusters_pendientes_verificar(marca, maximo=presupuesto)
        if not pendientes:
            continue
        validacion_on = config.etapa_activa(config.ENV_PIPELINE_VERIFICAR, marca)
        for cluster in pendientes:
            cid = (cluster.get("id") or "").strip()
            if not cid:
                continue
            # Validación OFF para la marca: la historia AJENA NO se verifica ni se admite; queda sin
            # verificar en el pool para que el humano la decida (nada ajeno se auto-produce sin verificar).
            if not validacion_on:
                continue
            try:
                gen = lanzar_verificar_cluster(cluster, autor=autor)
            except generaciones.ColaLlenaError as e:
                _log.info("pipeline: verificación en pausa por admisión (%s); el resto entra en el próximo tick.", e)
                break
            except Exception:  # noqa: BLE001 -- un fallo por historia no debe matar la fase verificación
                _log.exception("pipeline: fallo la verificación de la fuente (verificación) de la historia %s (marca %s).", cid, marca)
                continue
            if gen is not None:
                verificados.append({"id": cid, "gen_id": gen.get("id", "") if isinstance(gen, dict) else "", "verificacion_fuente": VERIFICACION_EN_CURSO})
    return verificados


def _ejecutar_produccion() -> dict[str, Any]:
    """Cuerpo de PRODUCCIÓN (ya bajo el single-flight de `ejecutar_produccion`)."""
    autor = _ref._autor_pipeline()
    # --- Fase CD (copy) + Etapa ARTE + Etapa AVANCE. -----------------------------------------
    # La sugerencia de hashtags NO es un paso del tick: la encadena el propio post-proceso del copy
    # (`dominio.copy`), en cuanto el borrador existe, vía cola — no un barrido async aparte.
    lanzados = ejecutar_redactar(autor=autor)
    # Etapa de Ilustrar (tras copy): ilustra los temas con copy y sin imagen. Gateada por su propio
    # toggle "Generar arte" (KENI_PIPELINE_ILUSTRAR) + máquina; si está OFF, devuelve [].
    artes = ejecutar_ilustrar()
    # Etapa de arte de STOCK (paralela a Ilustrar): a los temas con copy y sin imagen les adjunta
    # una foto de ayuda (original del RSS o API gratuita) atenuada + "SIN LICENCIA", nunca
    # publicable sin autorizar. Gateada por KENI_PIPELINE_STOCK (def OFF); si está OFF devuelve [].
    from .. import autogen_stock

    stock = autogen_stock.ejecutar_stock()
    # Etapa de AVANCE (tras arte): los borradores COMPLETOS (copy + foto) entran solos a la
    # cola de revisión. Incondicional bajo el maestro KENI_MAQUINA (sin toggle propio).
    avances = ejecutar_avance()
    if lanzados or artes or stock or avances:
        _log.info(
            "producción: %d copy (CD), %d arte(s) (Ilustrar), %d stock, %d avance(s).",
            len(lanzados), len(artes), len(stock), len(avances),
        )
    return {"lanzados": lanzados, "artes": artes, "stock": stock, "avances": avances}


def _ejecutar_barrido() -> dict[str, Any]:
    """Cuerpo COMBINADO (investigación + producción) SIN locks: para los tests que parchean
    `_ejecutar_barrido` y esperan el resumen completo en una sola pasada determinista."""
    inv = _ejecutar_investigacion()
    prod = _ejecutar_produccion()
    return {**inv, **prod}


# UN SOLO CAMINO DE verificación (ADR 0011): la verificación corre SOBRE EL CLUSTER, PRE-admisión
# (`ejecutar_verificar_clusters`), nunca sobre el TEMA post-admisión. La FRONTERA queda nítida en código:
# Investigación verifica la fuente ANTES de cruzar (cluster → verificacion) y la admisión solo
# promueve las VERIFICADAS.


def ejecutar_redactar(*, autor: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Fase CD (etapa de Redactar): genera copy de los temas con verificación `no_verificado` y sin copy aún,
    Y de los temas del news-pool (orígenes de noticias) que aún no tienen copy.

    DOS fuentes de temas, una sola ruta de copy (la etapa de Redactar es el ÚNICO motor):
      1) temas del propio pipeline (origen `pipeline`) cuya verificación salió `no_verificado`
         (`temas_para_redactar` → `lanzar_redactar_de_tema`),
      2) temas que las FUENTES de noticias metieron al tablero sin copy
         (`temas_autogen_sin_copy` → `autogen_redactar.lanzar_para_topic`).
    SIN topes propios (flujo continuo): el carril 1 lo acota la ADMISIÓN (gate serial en curso);
    el carril 2, el dedup por etiqueta + el backpressure de la cola. Si la cola se llena, corta la
    fase (el siguiente tick reintenta). REINTENTOS ACOTADOS en el carril 1: al agotar
    `_MAX_INTENTOS_ETAPA`, el tema se marca `problema` (sale del cupo en curso, fallo visible).
    Best-effort por tema. Devuelve las generaciones de copy lanzadas.
    """
    if autor is None:
        autor = _ref._autor_pipeline()
    # Etapa CD = toggle "Generar copy" (`KENI_PIPELINE_REDACTAR`), 1 toggle = 1 etapa: si el maestro está
    # OFF no se genera copy (aunque el daemon barra por otra etapa). Por marca se filtra abajo.
    if not config.pipeline_activo():
        return []
    # Import perezoso (evita ciclos en la carga del paquete): el Decisor toca `dominio.generar`.
    from ..dominio import decisor as decisor_dom

    lanzados: list[dict[str, Any]] = []
    for tema in temas_para_redactar():
        # Exclusión por marca: no generamos copy de temas de una marca apagada a mano (aunque
        # ya estuvieran ingeridos antes de apagarla). Misma FUENTE ÚNICA que la vista/catálogo.
        if not config.etapa_activa(config.ENV_PIPELINE_REDACTAR, tema.get("marca") or ""):
            continue
        # DECISOR (etapa PREVIA): si está activo para la marca y el tema aún no tiene camino, decide
        # primero (foto|carrusel) y redacta en el siguiente tick (el camino se guarda en
        # `copy_pendiente`, que lee `lanzar_redactar_de_tema`). Acotado por intentos: si el Decisor
        # falla repetidamente, se redacta directo (camino="" → el modelo decide) para no bloquear el
        # tema. Sin el flag (`KENI_PIPELINE_DECISOR` OFF), se redacta directo como hoy.
        if (
            config.etapa_activa(config.ENV_PIPELINE_DECISOR, tema.get("marca") or "")
            and not str(_copy_pendiente_leido(tema).get("camino") or "").strip()
            and intentos_de(tema, "decisor_intentos") < _MAX_INTENTOS_ETAPA
        ):
            try:
                gen = decisor_dom.lanzar_para_tema(tema)
            except generaciones.ColaLlenaError as e:
                _log.info("pipeline: Decisor en pausa por admisión (%s); el resto entra en el próximo tick.", e)
                return lanzados
            except Exception:  # noqa: BLE001 -- un fallo del Decisor no debe matar la fase
                _log.exception(
                    "pipeline: fallo el Decisor del tema %s (marca %s).",
                    tema.get("id", ""), tema.get("marca", ""),
                )
            else:
                if gen:
                    anotar_intento(tema, "decisor_intentos")
                    lanzados.append(gen)
                    continue  # decide ahora; redacta en el siguiente tick
        # Reintentos acotados: un copy fallido conserva `copy_pendiente` (dedup al éxito) y se
        # relanzaría cada tick para siempre; al agotar los intentos, salida TERMINAL (problema).
        if intentos_de(tema, "redactar_intentos") >= _MAX_INTENTOS_ETAPA:
            marcar_fallo_etapa(
                tema.get("id", "") or "", "Copy",
                f"La generación de copy falló {_MAX_INTENTOS_ETAPA} veces.",
            )
            continue
        # Backoff creciente entre intentos (1/4/16 min): mismo rationale que en la fase verificación.
        if en_backoff(tema, "redactar_intentos"):
            continue
        try:
            gen = lanzar_redactar_de_tema(tema, autor=autor)
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
            # Tras el lanzamiento efectivo (cola llena o fallo previo no gastan intentos). Si el
            # copy completó EN LÍNEA (tests síncronos), `copy_pendiente` ya se limpió y no anota.
            anotar_intento(tema, "redactar_intentos")
            lanzados.append(gen)
    # Fundido de la selección de autogen_redactar: la etapa de Redactar también redacta los temas del
    # news-pool/tablero (orígenes de noticias) que aún no tienen copy, vía el lanzador NEUTRO.
    from .. import autogen_redactar

    for item in temas_autogen_sin_copy():
        try:
            gen = autogen_redactar.lanzar_para_topic(item)
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


def ejecutar_ilustrar() -> list[dict[str, Any]]:
    """Etapa de Ilustrar del pipeline (tras copy): ilustra los temas con copy y sin imagen.

    Toggle "Generar arte" (`KENI_PIPELINE_ILUSTRAR`, gateado además por el maestro `KENI_MAQUINA`).
    FUNDE el antiguo daemon suelto `autogen_ilustrar`: reutiliza su selección
    (`autogen_ilustrar.topics_sin_arte`) y su lanzador (`autogen_ilustrar.lanzar_para_topic` →
    `media.generar_imagen`), con cap por barrido (`KENI_AUTOGEN_ARTE_MAX`). Per-marca: salta las
    marcas apagadas a mano (lo hace la propia selección, gateada por `ENV_PIPELINE_ILUSTRAR`). Sin
    proveedor de imagen configurado, no hace nada. Best-effort: un fallo por tema se loguea y se
    sigue. Devuelve los artes adjuntados.

    GATEADO EN VIVO: solo actúa con `KENI_PIPELINE_ILUSTRAR=1` Y `KENI_MAQUINA=1`. Sin el toggle, la
    etapa no ilustra (el equipo hace el arte a mano).
    """

    from .. import autogen_ilustrar

    if not config.gate_maquina(config.ilustrar_activo)():
        return []
    from .. import media

    if not media.proveedor_configurado():
        _log.info("pipeline: etapa de Ilustrar sin proveedor de imagen configurado; se omite.")
        return []
    try:
        # Solo la clase 'contenido' (el filtro va en SQL; las tareas nunca se ilustran).
        # `topics_sin_arte` aplica el resto de reglas (estado, copy sin imagen, dedup...).
        items = repos.listar_publicacion(clase="contenido")
    except Exception:  # noqa: BLE001 -- sin tablero, la etapa de Ilustrar no actúa
        _log.exception("pipeline: no se pudo leer el tablero para la etapa de Ilustrar.")
        return []
    elegidos = autogen_ilustrar.topics_sin_arte(
        items,
        plataformas_por_item=autogen_ilustrar._plataformas_por_item(items),
        ya_procesados=autogen_ilustrar.ids_ya_procesados(),
        maximo=config.autogen_arte_max(),
        etiquetas_por_item=autogen_ilustrar._etiquetas_por_item(),
        hoy=hoy_utc(),
    )

    # EN PARALELO: `lanzar_para_topic` no genera la imagen en línea; solo SELECCIONA y ENCOLA un
    # job de proceso (el WORKER genera la imagen en su carril, fuera del barrido). El encolado es
    # barato, pero el pool no estorba y mantiene el cap por barrido. Cada tema es independiente y
    # best-effort.
    fallidos: list[str] = []  # ids de los temas cuyo ENCOLADO reventó en ESTE ciclo (append es atómico)

    def _ilustrar(item: dict[str, Any]) -> dict[str, Any] | None:
        try:
            return autogen_ilustrar.lanzar_para_topic(item)
        except generaciones.ColaLlenaError:
            # BACKPRESSURE (cola llena / presupuesto / pausa), NO un fallo del proveedor: el
            # siguiente tick reintenta. NO lo contamos como `fallido` (no debe disparar la alerta
            # "¿proveedor de imagen caído?", que es para fallos reales de generación).
            return None
        except Exception:  # noqa: BLE001 -- un fallo por tema no debe matar la etapa de Ilustrar
            fallidos.append(str(item.get("id", "") or ""))
            _log.exception(
                "pipeline: fallo el encolado de arte del tema %s (marca %s).",
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
        _log.info("pipeline: %d tema(s) ilustrado(s) (etapa Ilustrar).", len(adjuntados))
    return adjuntados


# TICK del flujo continuo (constante, NO un ajuste): reaccionan al ESTADO cada pocos segundos.
# En cuanto la verificación de una pieza termina, el siguiente tick de producción lanza su Copy. El volumen
# NO lo pone el tick sino la ADMISIÓN (gate serial en curso por marca) + el backpressure de la
# cola. Cada proceso tiene su propia constante para poder divergir sin tocar el otro.
#
# CADENCIA BASE + BACKOFF: la base es 30 s. Cuando el pool está seco, `bucle_gateado` espacia
# el barrido vacío ×2 hasta `_BACKOFF_MAX_SEGUNDOS`, y vuelve a la base en cuanto un barrido HACE
# algo (verifica/admite/redacta/avanza) o se fuerza desde el panel. Así el coste ocioso cae sin
# perder reactividad: el primer barrido con trabajo recupera el ritmo.
_TICK_INVESTIGACION_SEGUNDOS = 30.0
_TICK_PRODUCCION_SEGUNDOS = 30.0
_TICK_SEGUNDOS = _TICK_INVESTIGACION_SEGUNDOS  # alias retro: cadencia "del pipeline" = investigación.
# Tope del backoff cuando se barre en vacío (5 ticks base): a partir de aquí el loop ocioso no
# espacia más. 120 s mantiene la latencia de arranque acotada cuando vuelve a entrar trabajo.
_BACKOFF_MAX_SEGUNDOS = 120.0


def _intervalo_investigacion_segundos() -> float:
    """Cadencia del tick de INVESTIGACIÓN (constante; el volumen lo regula la admisión)."""
    return _TICK_INVESTIGACION_SEGUNDOS


def _intervalo_produccion_segundos() -> float:
    """Cadencia del tick de PRODUCCIÓN (constante; el volumen lo regula la admisión/cola)."""
    return _TICK_PRODUCCION_SEGUNDOS


def _intervalo_portal_segundos() -> float:
    """Cadencia del tick del canal PORTAL (constante; el volumen lo regula el cap por barrido)."""
    return _TICK_PRODUCCION_SEGUNDOS


def _intervalo_segundos() -> float:
    """Alias retro de la cadencia del flujo continuo (= investigación)."""
    return _TICK_SEGUNDOS


def _resumen_investigacion(res: dict[str, Any]) -> str:
    """Resumen corto del barrido de INVESTIGACIÓN para el historial (qué verificó/admitió)."""
    verificados = len(res.get("verificados") or [])
    temas = len(res.get("temas") or [])
    if not verificados and not temas:
        return "sin novedad"
    return f"{verificados} cluster(s) verificado(s) · {temas} tema(s) admitido(s)"


def _resumen_produccion(res: dict[str, Any]) -> str:
    """Resumen corto del barrido de PRODUCCIÓN para el historial (copy/arte/avances)."""
    copys = len(res.get("lanzados") or [])
    artes = len(res.get("artes") or [])
    avances = len(res.get("avances") or [])
    if not (copys or artes or avances):
        return "sin novedad"
    return f"{copys} copy · {artes} arte(s) · {avances} avance(s) a revisión"


def _trabajo_investigacion(res: dict[str, Any]) -> bool:
    """¿El barrido de INVESTIGACIÓN hizo algo? (señal de backoff: verificó o admitió)."""
    return bool(res) and bool((res.get("verificados") or []) or (res.get("temas") or []))


def _trabajo_produccion(res: dict[str, Any]) -> bool:
    """¿El barrido de PRODUCCIÓN hizo algo? (señal de backoff: copy, arte o avance)."""
    return bool(res) and bool(
        (res.get("lanzados") or []) or (res.get("artes") or []) or (res.get("avances") or [])
    )


def _resumen_portal(res: dict[str, Any]) -> str:
    """Resumen corto del barrido del canal PORTAL para el historial (temas de fuente propia)."""
    n = len(res.get("temas") or [])
    return f"{n} tema(s) de Portal" if n else "sin novedad"


def _trabajo_portal(res: dict[str, Any]) -> bool:
    """¿El barrido del PORTAL hizo algo? (señal de backoff: admitió temas de fuente propia)."""
    return bool(res) and bool(res.get("temas") or [])


def iniciar_pipeline(
    intervalo_segundos: float | None = None,
) -> tuple[threading.Thread, threading.Thread, threading.Thread]:
    """Arranca los TRES hilos demonio del pipeline de contenido (ADR 0011, GATEADOS EN VIVO).

    Pensado para el servidor real (`daemons`/`__main__`), NO para `crear_app` (los tests no lo
    arrancan, igual que el resto de daemons). Arranca un hilo por proceso:
      • INVESTIGACIÓN — gate `alguna_etapa_investigacion_activa` (Selección/Validación) bajo la
        máquina: con ambas etapas OFF el loop duerme (nada que admitir/verificar).
      • PRODUCCIÓN — gate `alguna_etapa_produccion_activa` (siempre True bajo la máquina: el
        AVANCE de borradores completos a revisión corre incondicional, así nunca se duerme con
        la máquina ON). Copy/Arte se auto-gatean dentro del barrido por su propio toggle.
      • PORTAL — gate Recolectar bajo la máquina: admite DIRECTO las historias de fuente propia
        como temas `origen='portal'` (sin umbral ni verificación); la producción las redacta.
    Apagar/encender en runtime aplica sin reiniciar. Los hilos son daemon; un fallo de barrido se
    loguea y NO los mata. Devuelve `(hilo_investigacion, hilo_produccion, hilo_portal)`.
    """
    intervalo_inv = (
        intervalo_segundos if intervalo_segundos is not None else _intervalo_investigacion_segundos()
    )
    intervalo_prod = (
        intervalo_segundos if intervalo_segundos is not None else _intervalo_produccion_segundos()
    )
    intervalo_portal = (
        intervalo_segundos if intervalo_segundos is not None else _intervalo_portal_segundos()
    )

    def bucle_investigacion() -> None:
        daemon_util.bucle_gateado(
            activo_fn=config.gate_maquina(config.alguna_etapa_investigacion_activa),
            intervalo_seg_fn=lambda: intervalo_inv,
            sweep_fn=ejecutar_investigacion,
            log=_log,
            nombre="investigacion",
            resumen_fn=_resumen_investigacion,
            trabajo_fn=_trabajo_investigacion,
            backoff_max_seg=_BACKOFF_MAX_SEGUNDOS,
        )

    def bucle_produccion() -> None:
        daemon_util.bucle_gateado(
            activo_fn=config.gate_maquina(config.alguna_etapa_produccion_activa),
            intervalo_seg_fn=lambda: intervalo_prod,
            sweep_fn=ejecutar_produccion,
            log=_log,
            nombre="produccion",
            resumen_fn=_resumen_produccion,
            trabajo_fn=_trabajo_produccion,
            backoff_max_seg=_BACKOFF_MAX_SEGUNDOS,
        )

    def bucle_portal() -> None:
        daemon_util.bucle_gateado(
            activo_fn=config.gate_maquina(config.recolectar_activo),
            intervalo_seg_fn=lambda: intervalo_portal,
            sweep_fn=ejecutar_portal,
            log=_log,
            nombre="portal",
            resumen_fn=_resumen_portal,
            trabajo_fn=_trabajo_portal,
            backoff_max_seg=_BACKOFF_MAX_SEGUNDOS,
        )

    hilo_inv = threading.Thread(
        target=bucle_investigacion, name="pipeline-investigacion-daemon", daemon=True
    )
    hilo_prod = threading.Thread(
        target=bucle_produccion, name="pipeline-produccion-daemon", daemon=True
    )
    hilo_portal = threading.Thread(
        target=bucle_portal, name="pipeline-portal-daemon", daemon=True
    )
    hilo_inv.start()
    hilo_prod.start()
    hilo_portal.start()
    estado = "ACTIVA" if config.maquina_activa() else "EN ESPERA (máquina apagada)"
    _log.info(
        "Pipeline de contenido %s — investigación cada %.0fs, producción cada %.0fs, "
        "portal cada %.0fs (backoff hasta %.0fs en vacío; max/barrido=%d).",
        estado, intervalo_inv, intervalo_prod, intervalo_portal, _BACKOFF_MAX_SEGUNDOS,
        config.pipeline_max(),
    )
    return hilo_inv, hilo_prod, hilo_portal
