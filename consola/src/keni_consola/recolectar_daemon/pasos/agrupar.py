"""Paso de AGRUPAR (Ola B): agrupa en historias los items recientes sin cluster."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import keni_consola.recolectar_daemon as _pkg

from ... import config, marcas, repos
from ...dominio import agrupar, perfil_editorial
from ...tiempo import iso_utc
from .._comun import (
    _log,
    _palabras_relevancia,
    _rendimiento_bonus,
    _rendimiento_top_lineas,
    eventos_proximos,
)

# Tope de items a AGRUPAR por barrido: el agrupar es best-effort y ACOTADO. Si un
# barrido inserta más, el resto queda sin cluster y se recoge en el siguiente tick (siguen
# en la ventana). Evita un barrido caro tras un arranque en frío con miles de items pendientes.
_CLUSTER_BATCH = 500

# TTL del marcador "refresco en curso" del perfil editorial: si el job no completa en este margen
# (deploy/OOM/error de claude), la marca se RE-ABRE para re-encolarse en un barrido posterior.
# Generoso: el Haiku es rápido, así que esto cubre un cuelgue real, no un job sano esperando en cola.
_PERFIL_ENCOLADO_TTL_MIN = 30


def _encolar_perfil(marca: str, *, ttl_horas: int, ahora: datetime) -> None:
    """ENCOLA el refresco del perfil editorial de `marca` como job Haiku (carril de su cuenta).

    Solo encola si el perfil NECESITA refresco (cache ausente/caducado/editorial cambiada) y NO hay
    ya un refresco EN VUELO para la marca (marcador `refresco_encolado_en` dentro del TTL). Marca el
    refresco en curso ANTES de encolar (idempotencia entre barridos: un barrido posterior no lo
    re-encola mientras el job sigue en vuelo) y lo RE-ABRE si la admisión rechaza el encolado
    (presupuesto/pausa). El worker corre `claude -p` y su post-procesado escribe el cache. La
    actividad IA («Priorizar») queda registrada por el registro de generación que crea aquí (el
    worker la completa al terminar). Best-effort: cualquier fallo se loguea y no aborta el barrido.
    """
    from ... import cola, generaciones, ruteo_cuentas  # noqa: PLC0415 -- import perezoso (paquete raíz)
    from ...dominio import jobspec  # noqa: PLC0415 -- import perezoso (evita ciclo dominio<->daemon)
    from ...pipeline_contenido import _intentos  # noqa: PLC0415 -- perezoso (evita ciclo daemon<->pipeline)

    if not perfil_editorial.necesita_refresco(marca, ttl_horas=ttl_horas, ahora=ahora):
        return
    if perfil_editorial.refresco_en_curso(marca, ahora=ahora, ttl_min=_PERFIL_ENCOLADO_TTL_MIN):
        return
    # Reintentos acotados: un refresco que nunca completa (claude cae) se re-abre por TTL y se
    # re-encolaría sin fin. Al agotar el tope se deja de re-encolar esa marca; el backoff espacia.
    if _intentos.tope_alcanzado(marca, _intentos.ETAPA_PERFIL):
        return
    if _intentos.en_backoff(marca, _intentos.ETAPA_PERFIL):
        return
    prompt = perfil_editorial.construir_prompt_perfil(marca)
    if not prompt:
        return  # sin editorial: nada que refrescar

    # IDEMPOTENCIA: marca el refresco en curso ANTES de encolar; si la admisión lo rechaza más abajo,
    # se re-abre. Mismo orden que el paso de Traducir (marcar -> encolar -> limpiar si se rechaza).
    perfil_editorial.marcar_refresco_encolado(marca, ahora=ahora)
    etiqueta_marca = marcas.etiqueta_de(marca) if marca else "sin marca"
    gen_id = ""
    try:
        gen = generaciones.crear({
            "tipo": "pipeline",
            # Priorizar (perfil editorial) es INVESTIGACION (motor de noticias): gasta tokens y cuenta
            # para el presupuesto de investigación, ruteado al carril de la cuenta de la marca.
            "proceso": generaciones.PROCESO_INVESTIGACION,
            "etapa": "Priorizar",
            "marca": marca,
            "etiqueta": f"Priorizar historias — {etiqueta_marca}: perfil editorial",
            "prompt": prompt,
        })
        gen_id = gen["id"]
        spec = jobspec.construir(
            prompt=prompt,
            procesar=jobspec.construir_perfil(marca=marca),
            # Carril de la CUENTA de la marca: el worker que monta esa cuenta reclama el job.
            carril=ruteo_cuentas.carril_de_marca(marca),
            # Haiku (config.insumos_modelo()): extraer temas/keywords es mecánico, mismo modelo que
            # usaba el refresco inline y que usan Traducir/insumos.
            endurecer={"modelo": config.insumos_modelo()},
            # Lo lanza la maquina: AUTOMATICO, cede el paso a los lanzamientos manuales del equipo.
            prioridad=jobspec.PRIORIDAD_AUTOMATICO,
        )
        cola.encolar(gen_id, spec, proceso=generaciones.PROCESO_INVESTIGACION, marca=marca)
        _intentos.anotar(marca, _intentos.ETAPA_PERFIL)
    except generaciones.ColaLlenaError:
        # Admisión rechazada (presupuesto/pausa): borra el registro recién creado y RE-ABRE la marca
        # (no es un fallo real) para que un barrido posterior la reintente sin esperar al TTL.
        if gen_id:
            generaciones.borrar_registro(gen_id)
        perfil_editorial.limpiar_refresco_encolado(marca)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo aborta el barrido
        _log.exception("recolectar_daemon: fallo al encolar el perfil de %r.", marca)
        if gen_id:
            generaciones.borrar_registro(gen_id)
        perfil_editorial.limpiar_refresco_encolado(marca)


def paso_agrupar() -> dict[str, Any]:
    """Agrupa en HISTORIAS los items recientes SIN cluster. Best-effort, ACOTADO a la ventana.

    Incremental: NO re-agrupa el archivo entero. Carga (1) los clusters cuya `ultimo_visto`
    está en la ventana (`KENI_CLUSTER_VENTANA_H`) y (2) hasta `_CLUSTER_BATCH` items recientes
    sin `cluster_id`, en orden cronológico. Para cada item: lo une al cluster reciente que casa
    por clave EXACTA (misma url canónica host+path, o hash de título idéntico) o crea uno nuevo.
    La decisión usa `agrupar.Asignador` (índice `clave → id`: O(items), no O(items × clusters)).
    Las historias del mismo evento con titulares DISTINTOS las agrupa después la fusión semántica
    con Haiku (`paso_fusionar_semantica`). Las asignaciones se escriben en LOTE (un UPDATE por
    cluster tocado, no uno por item). Al final, recalcula y `upsert`ea SOLO los clusters tocados
    (puntuándolos con su vocabulario de marca; si la marca dominante queda VACÍA —historias
    solo-Trends/agencias— se intenta el encaje por vocabulario de cada marca).

    Durabilidad: un cluster NUEVO se persiste (stub) ANTES de asignarle items, así un proceso
    que muera a mitad no deja items apuntando a un cluster que solo existía en memoria; además,
    al inicio se REPARAN los items con `cluster_id` colgante de barridos anteriores.

    Devuelve `{items, clusters_nuevos, clusters_tocados, clusters_ventana}` (`clusters_ventana`
    = los clusters de la ventana ya actualizados, para que el barrido los REUTILICE en la
    fusionar/re-score sin re-leer la BD). Un fallo de un item se loguea y no aborta el paso.
    """
    ventana_h = config.cluster_ventana_h()
    breaking_peso = config.cluster_breaking_peso()
    breaking_ventana_h = config.cluster_breaking_ventana_h()
    fuentes_baja = config.fuentes_baja_confianza()
    # Relevancia desde la línea editorial (Haiku) si ALGUNA marca tiene «Priorizar» encendida; el
    # refinamiento por marca lo hace `_palabras_relevancia`/`etapa_activa` más abajo.
    perfil_activo = config.alguna_marca_con_etapa(config.ENV_PRIORIZAR_PERFIL_IA)
    perfil_ttl = config.perfil_editorial_ttl_horas()
    perfil_refrescadas: set[str] = set()  # 1 intento de encolado de perfil por marca por barrido
    # Pesos del score y agenda POR MARCA (modelo v2): perfil distinto por marca y señal de evento
    # contra SU `rota_eventos`. Perezosos (1 lectura por marca y barrido), como el rendimiento.
    pesos_cache: dict[str, Any] = {}
    eventos_cache: dict[str, list[dict[str, Any]]] = {}
    # Señal de RENDIMIENTO (Fase 2c, gateada): líneas top por engagement, POR MARCA y perezoso.
    rendimiento_activo = config.rendimiento_ranking_activo()
    rend_cache: dict[str, tuple[set[str], dict[str, str], list[dict[str, Any]]]] = {}

    # REPARACIÓN: items con `cluster_id` colgante (cluster que ya no existe, p. ej. proceso
    # muerto a mitad de un barrido antiguo) vuelven a '' y se re-agrupan. Best-effort.
    try:
        reparados = repos.limpiar_items_cluster_colgante()
        if reparados:
            _log.info("recolectar_daemon: %d item(s) con cluster colgante reparados.", reparados)
    except Exception:  # noqa: BLE001 -- la reparación es best-effort; nunca aborta el paso
        _log.warning("recolectar_daemon: no se pudieron reparar items colgantes.", exc_info=True)

    ahora = datetime.now(UTC)
    desde = iso_utc(ahora - timedelta(hours=ventana_h))
    pendientes = repos.items_sin_cluster(desde, _CLUSTER_BATCH)
    if not pendientes:
        return {"items": 0, "clusters_nuevos": 0, "clusters_tocados": 0}

    # Índice de trabajo de los clusters de la ventana (vivo durante el paso, para que items del
    # MISMO barrido se unan entre sí sin re-consultar la BD). id -> dict-resumen del cluster.
    recientes = repos.clusters_recientes(ventana_h)
    indice: dict[str, dict[str, Any]] = {c["id"]: c for c in recientes}
    asignador = agrupar.Asignador(recientes)
    tocados: set[str] = set()
    asignaciones: dict[str, list[str]] = {}  # cluster_id -> item_ids (escritura en lote)
    nuevos = 0

    for item in pendientes:
        try:
            destino = asignador.asignar(item)
            if destino is None:
                # Cruce exacto por URL a NIVEL DE ITEM: la clave del cluster solo guarda la
                # url del representativo; si otra fuente ya archivó este MISMO recurso, su
                # cluster está en BD aunque el asignador no lo viera. Best-effort.
                url_rec = agrupar.url_canonica_clustering(
                    str(item.get("url") or item.get("url_canonica") or "")
                )
                if url_rec:
                    try:
                        # Scoped a la marca del item: el cruce por url solo une historias del
                        # MISMO mercado (el clustering es por marca).
                        candidato = repos.cluster_por_url_canonica(
                            url_rec, desde, marca=str(item.get("marca") or "")
                        )
                    except Exception:  # noqa: BLE001 -- el cruce por url es aditivo
                        candidato = ""
                    if candidato and (candidato in indice or repos.obtener_noticia_cluster(candidato)):
                        destino = candidato
            if destino is None:
                # Cluster nuevo: lo funda este item (un cluster en blanco con su identidad).
                # Se PERSISTE el stub ANTES de asignarle items (durabilidad ante caída).
                destino = uuid.uuid4().hex[:12]
                stub = {
                    "id": destino,
                    "titulo": item.get("titulo") or "",
                    "clave": agrupar.clave_cluster(item),
                    # La marca del item FUNDA el cluster: el clustering es por marca (el fan-out
                    # multimarca crea una historia por mercado). `recalcular` la reconfirma/afina.
                    "marca": item.get("marca") or "",
                    "estado": "nuevo",
                    "publicacion_id": "",
                    "creado": "",
                }
                repos.upsert_noticia_cluster(stub)
                indice[destino] = stub
                asignador.agregar(stub)
                nuevos += 1
            asignaciones.setdefault(destino, []).append(item["id"])
            tocados.add(destino)
        except Exception:  # noqa: BLE001 -- un item problemático no aborta el paso
            _log.exception("recolectar_daemon: fallo al agrupar el item %s.", item.get("id"))

    # Asignación en LOTE: un UPDATE por cluster tocado (antes, uno por item: ~500 round-trips).
    try:
        repos.asignar_cluster_items(asignaciones)
    except Exception:  # noqa: BLE001 -- si el lote falla, los items siguen sin cluster (reintento próximo tick)
        _log.exception("recolectar_daemon: fallo al asignar items a clusters (lote).")
        return {
            "items": len(pendientes), "clusters_nuevos": nuevos, "clusters_tocados": 0,
            "clusters_ventana": list(indice.values()),
        }

    vocabularios: dict[str, frozenset[str]] | None = None  # perezoso (encaje sin marca)

    # Recalcula + puntúa SOLO los clusters tocados, leyendo sus items ya persistidos.
    for cid in tocados:
        try:
            base = indice.get(cid) or repos.obtener_noticia_cluster(cid) or {"id": cid}
            items_cluster = repos.items_de_cluster(cid, limite=500)
            if not items_cluster:
                continue
            recalc = agrupar.recalcular(
                base,
                items_cluster,
                breaking_peso=breaking_peso,
                breaking_ventana_h=breaking_ventana_h,
                fuentes_baja_confianza=fuentes_baja,
                ahora=ahora,
            )
            marca_c = recalc.get("marca") or ""
            if not marca_c:
                # Encaje por VOCABULARIO (determinista): una historia formada SOLO por items sin
                # marca (Trends/agencias) queda con marca='' e INVISIBLE para la promoción por
                # marca. Se le asigna la marca cuyo vocabulario mejor casa (sobre umbral); si
                # ninguna pasa, queda SIN marca (honesto: no se infiere a ciegas).
                if vocabularios is None:
                    # Solo marcas de NOTICIAS: el contenido propio (p. ej. piso-15) se salta la
                    # investigación, así que su vocabulario no compite por estas historias.
                    vocabularios = {
                        m: _palabras_relevancia(m, perfil_activo) for m in marcas.noticias()
                    }
                marca_c = agrupar.marca_por_vocabulario(recalc, vocabularios)
                if not marca_c:
                    # Ya clasificada en un tick anterior (vocabulario): preserva la asignación en
                    # vez de re-derivarla (evita reclasificar y perder marca).
                    marca_c = str(base.get("marca") or "")
                if marca_c:
                    recalc["marca"] = marca_c
            # Relevancia desde la LÍNEA EDITORIAL (perfil Haiku) si la etapa "Priorizar" está
            # encendida PARA ESTA marca (`etapa_activa`); si no, la base inicial. El refresco se
            # ENCOLA como job `claude` por marca (ruteado al carril de su cuenta); el worker corre el
            # Haiku y escribe el cache. Los gates se conservan: lo corta la parada de emergencia /
            # presupuesto (`ia_fondo_bloqueada`), como al resto del fondo. Las lecturas de
            # `palabras(marca)` (abajo) usan el cache vigente (posiblemente algo viejo: aceptable).
            if (
                perfil_activo and marca_c and marca_c not in perfil_refrescadas
                and config.etapa_activa(config.ENV_PRIORIZAR_PERFIL_IA, marca_c)
                and not _pkg.ia_fondo_bloqueada()
            ):
                perfil_refrescadas.add(marca_c)
                _encolar_perfil(marca_c, ttl_horas=perfil_ttl, ahora=ahora)
            palabras = _palabras_relevancia(marca_c, perfil_activo)
            if marca_c not in pesos_cache:
                pesos_cache[marca_c] = config.score_pesos(marca_c)
                eventos_cache[marca_c] = eventos_proximos(marca_c)
            # Señal de rendimiento (Fase 2c): 1 si la historia cae en una línea top POR MARCA.
            if rendimiento_activo and marca_c:
                if marca_c not in rend_cache:
                    rend_cache[marca_c] = _rendimiento_top_lineas(marca_c)
                top_lineas, vert_id_a_nombre, vert_etiquetas = rend_cache[marca_c]
                if top_lineas:
                    recalc["bonus_rendimiento"] = _rendimiento_bonus(
                        recalc, top_lineas, vert_id_a_nombre, vert_etiquetas
                    )
            score, razon, desglose = agrupar.puntuar_detalle(
                recalc, palabras_marca=palabras, eventos=eventos_cache[marca_c],
                ahora=ahora, pesos=pesos_cache[marca_c],
                breaking_peso=breaking_peso, breaking_ventana_h=breaking_ventana_h,
            )
            recalc["score"] = score
            # Explicación PERSISTIDA: la razón humana y el desglose por señal viajan con el
            # score (el panel y el umbral de promoción los muestran; sin esto la priorización es
            # una caja negra y el equipo no puede auditar por qué algo sube o baja).
            recalc["score_razon"] = razon
            recalc["score_desglose"] = desglose
            indice[cid] = repos.upsert_noticia_cluster(recalc)
        except Exception:  # noqa: BLE001 -- recalcular un cluster no aborta el paso
            _log.exception("recolectar_daemon: fallo al recalcular el cluster %s.", cid)

    return {
        "items": len(pendientes),
        "clusters_nuevos": nuevos,
        "clusters_tocados": len(tocados),
        "clusters_ventana": list(indice.values()),
    }
