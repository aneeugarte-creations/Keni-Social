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
)

# Tope de items a AGRUPAR por barrido: el agrupar es best-effort y ACOTADO. Si un
# barrido inserta más, el resto queda sin cluster y se recoge en el siguiente tick (siguen
# en la ventana). Evita un barrido caro tras un arranque en frío con miles de items pendientes.
_CLUSTER_BATCH = 500


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
    pesos = config.score_pesos()  # pesos editables del algoritmo de ponderación
    perfil_activo = config.priorizar_perfil_activo()  # relevancia desde la línea editorial (Haiku)
    perfil_ttl = config.perfil_editorial_ttl_horas()
    perfil_refrescadas: set[str] = set()  # 1 refresco por marca por barrido (Haiku acotado)
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
                        candidato = repos.cluster_por_url_canonica(url_rec, desde)
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
            marca_por_ia = False  # ¿la marca la asignó el clasificador IA en este tick?
            if not marca_c:
                # Encaje por VOCABULARIO: una historia formada SOLO por items sin marca
                # (Trends/agencias) quedaba con marca='' e INVISIBLE para la promoción por
                # marca. Se le asigna la marca cuyo vocabulario mejor casa (sobre umbral);
                # si ninguna pasa, queda sin marca como antes (honesto).
                if vocabularios is None:
                    vocabularios = {
                        m: _palabras_relevancia(m, perfil_activo) for m in marcas.ids()
                    }
                marca_c = agrupar.marca_por_vocabulario(recalc, vocabularios)
                if not marca_c:
                    # Ya clasificada en un tick anterior (vocabulario o IA): preserva la
                    # asignación en vez de re-derivarla (evita reclasificar y perder marca).
                    marca_c = str(base.get("marca") or "")
                corroborada = int(recalc.get("n_fuentes") or 0) >= 2
                if (
                    not marca_c
                    and (bool(int(recalc.get("breaking") or 0)) or corroborada)
                    and config.clasificar_marca_ia()
                ):
                    # SIN marca pero con peso real (última hora, o corroborada por 2+ fuentes):
                    # encaje por IA (Haiku) en una de las marcas activas; cae a la de noticias si
                    # la IA duda. Sin esto, una historia que el vocabulario no casa (jerga/entidad
                    # nueva) pero que varios medios cubren quedaba sin clasificar e invisible en los
                    # paneles por marca. Se limita a corroboradas (2+ fuentes) para no clasificar
                    # contenido irrelevante de fuente única.
                    marca_c = _pkg._clasificar_marca_ia(recalc)
                    if marca_c:
                        marca_por_ia = True
                if marca_c:
                    recalc["marca"] = marca_c
            # Relevancia desde la LÍNEA EDITORIAL (perfil Haiku) si está activa (maestro + por-marca:
            # el toggle "Priorizar"); si no, la base inicial.
            if (
                perfil_activo and marca_c and marca_c not in perfil_refrescadas
                and not config.marca_apagada(config.ENV_PRIORIZAR_PERFIL_IA, marca_c)
            ):
                perfil_refrescadas.add(marca_c)
                perfil_editorial.refrescar_si_corresponde(
                    marca_c, ttl_horas=perfil_ttl, ahora=ahora,
                    al_refrescar=lambda m, kws, prompt, salida: _pkg._registrar_actividad_ia(
                        m,
                        f"Priorizar historias — {marcas.etiqueta_de(m)}: {len(kws)} temas clave",
                        salida,  # la respuesta REAL de Haiku (keywords del perfil)
                        prompt=prompt,
                    ),
                )
            palabras = _palabras_relevancia(marca_c, perfil_activo)
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
                recalc, palabras_marca=palabras, ahora=ahora, pesos=pesos,
                breaking_peso=breaking_peso, breaking_ventana_h=breaking_ventana_h,
            )
            recalc["score"] = score
            # Explicación PERSISTIDA: la razón humana y el desglose por señal viajan con el
            # score (el panel y el umbral de promoción los muestran; sin esto la priorización es
            # una caja negra y el equipo no puede auditar por qué algo sube o baja).
            recalc["score_razon"] = razon
            recalc["score_desglose"] = desglose
            indice[cid] = repos.upsert_noticia_cluster(recalc)
            # Sella el encaje de marca por IA aparte del upsert (la columna está en `_NO_PISAR`):
            # así un recalc posterior sin el flag no lo borra (mismo patrón que Traducir).
            if marca_por_ia:
                try:
                    repos.marcar_cluster_marca_ia(cid)
                except Exception:  # noqa: BLE001 -- observabilidad; nunca rompe el barrido
                    _log.warning("recolectar_daemon: no se pudo sellar marca_clasificada_por_ia (%s)", cid)
        except Exception:  # noqa: BLE001 -- recalcular un cluster no aborta el paso
            _log.exception("recolectar_daemon: fallo al recalcular el cluster %s.", cid)

    return {
        "items": len(pendientes),
        "clusters_nuevos": nuevos,
        "clusters_tocados": len(tocados),
        "clusters_ventana": list(indice.values()),
    }
