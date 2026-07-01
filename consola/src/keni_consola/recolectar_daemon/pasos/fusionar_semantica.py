"""Paso de FUSIONAR SEMÁNTICAMENTE (Fase 2b): ENCOLA un job de fusión Haiku POR MARCA.

A diferencia de la fusión INLINE de antes (el barrido corría Haiku y fundía en el mismo hilo), el
barrido agrupa las historias `nuevo` recientes POR MARCA y ENCOLA un job `claude` por marca, ruteado
al carril de la CUENTA de esa marca (`ruteo_cuentas.carril_de_marca`). El worker corre la pasada
principal de agrupación y su post-procesado (`fusionar_semantica.construir_procesar_fusionar`) ancla
por agenda, VERIFICA y FUNDE los grupos del mismo hecho, ETIQUETA las familias de macro-evento y las
facetea en subtemas. Así el gasto entra en el carril por cuenta y la fusión no bloquea el barrido.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any

from ... import config, generaciones, marcas, repos, ruteo_cuentas
from ...dominio import fusionar_semantica, jobspec
from .. import _comun
from .._comun import _log

# TTL del marcador "fusión en curso" por marca: si el job no completa en este margen (deploy/OOM/error
# de claude), la marca se RE-ABRE para re-encolarse en un barrido posterior. Generoso: el Haiku es
# rápido, así que esto cubre un cuelgue real, no un job sano esperando en cola.
_FUSION_ENCOLADA_TTL_MIN = 30

# Campos de cada historia que VIAJAN en el spec del job (el resto los re-lee el worker de repos al
# fundir). Bastan para el ancla de agenda (textos), el lote/por_id (id/titulo/tema_macro) y elegir la
# canónica (n_fuentes/score). El texto se manda SIN truncar aquí: `procesar_fusiones` lo acota.
_CAMPOS_SPEC = (
    "id", "titulo", "titulo_es", "resumen", "resumen_es", "tema_macro", "n_fuentes", "score", "marca",
)


def _fresco_para_fusion(cluster: dict[str, Any], corte: datetime) -> bool:
    """True si el cluster tuvo actividad (`ultimo_visto`) en/tras `corte` (ventana de fusión).

    Lee `ultimo_visto` con `fromisoformat` (tolera el canon sin offset de `iso_utc` y el ISO con
    offset; naive se ASUME UTC, convención del sistema). Si la marca no es legible, NO excluye el
    cluster (conservador: ante la duda, se procesa).
    """
    crudo = str(cluster.get("ultimo_visto") or "").strip()
    if not crudo:
        return True
    try:
        visto = datetime.fromisoformat(crudo)
    except ValueError:
        return True
    if visto.tzinfo is None:
        visto = visto.replace(tzinfo=UTC)
    return visto >= corte


def _spec_recientes(clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Proyección SERIALIZABLE de las historias de la marca para el spec del job (solo `_CAMPOS_SPEC`)."""
    return [{k: c.get(k) for k in _CAMPOS_SPEC} for c in clusters]


def paso_fusionar_semantica(
    *,
    recientes: list[dict[str, Any]] | None = None,
    forzar: bool = False,
) -> dict[str, Any]:
    """ENCOLA un job de fusión semántica POR MARCA por las historias `nuevo` recientes (def ON).

    Agrupa por marca las historias `nuevo` vivas (frescas) de la ventana y, por cada marca con ≥2,
    ENCOLA un job `claude` ruteado al carril de la cuenta de la marca; el worker corre la pasada
    principal de agrupación y su post-procesado funde/etiqueta (`construir_procesar_fusionar`).
    Best-effort: un fallo de encolado de una marca limpia su marcador (para reintentar) y no aborta
    las demás. El gate de parada/presupuesto lo aplica `cola.encolar` (además del `ia_fondo_bloqueada`
    que el barrido comprueba antes de llamar aquí). Devuelve `{encolados, marcas, candidatos}`.

    Throttle: como mucho una pasada por `config.fusion_intervalo_seg()` (no re-evaluar la ventana en
    cada tick de 30s); `forzar=True` lo salta (tests). Skip-if-unchanged: si el conjunto candidato no
    cambió desde la última pasada, no hay nada nuevo que encolar. `recientes` (opcional): los clusters
    de la ventana YA cargados por el paso de agrupar del MISMO barrido (evita re-leer la BD).

    IDEMPOTENCIA: el marcador PERSISTIDO `fusion_en_curso` (sello por marca con TTL en un JSON bajo el
    dir de datos) impide re-encolar una marca cuyo job sigue en vuelo y sobrevive a reinicios; el
    throttle/huella en memoria solo evita TRABAJO redundante (no coordina barrido↔worker).
    """
    if not config.alguna_marca_con_etapa(config.ENV_PIPELINE_FUSIONAR):
        return {"encolados": 0, "marcas": 0, "candidatos": 0}
    from ...pipeline_contenido import _intentos  # perezoso: evita ciclo daemon<->pipeline en carga

    ahora_mono = time.monotonic()
    if (
        not forzar
        and _comun._ultimo_fusionar
        and (ahora_mono - _comun._ultimo_fusionar) < config.fusion_intervalo_seg()
    ):
        return {"encolados": 0, "marcas": 0, "candidatos": 0}
    ventana_h = config.cluster_ventana_h()
    ahora = datetime.now(UTC)

    if recientes is not None:
        recientes_todas = recientes
    else:
        try:
            recientes_todas = repos.clusters_recientes(ventana_h)
        except Exception:  # noqa: BLE001 -- sin pool legible, no se encola nada
            _log.exception("recolectar_daemon: no se pudieron leer historias para fusionar.")
            return {"encolados": 0, "marcas": 0, "candidatos": 0}

    nuevos = [c for c in recientes_todas if (c.get("estado") or "nuevo") == "nuevo"]

    # Frescura del lote: solo lo VIVO entra al LLM. Un cluster `nuevo` sin actividad en la ventana
    # de fusión (más corta que la de agrupación) ya se digirió; reenviarlo en cada barrido
    # reprocesaría historias de hace días sin nada que cambiar. También estabiliza la huella.
    corte_fusion = ahora - timedelta(hours=config.fusion_ventana_h())
    nuevos = [c for c in nuevos if _fresco_para_fusion(c, corte_fusion)]

    # FILTRO DE RELEVANCIA: no gastar fusión (ni sus sub-llamadas Cotejar/Subtema) en historias que
    # no se publicarían. Fuera del lote los clusters con `score` por debajo del umbral (mismo campo
    # que el umbral de promoción). `0` desactiva el filtro. SALVAGUARDA: si una marca queda con <2
    # clusters tras el filtro, el bloque por marca de abajo la salta (no fusiona ese ciclo).
    umbral_score = config.fusion_min_score()
    if umbral_score > 0:
        nuevos = [c for c in nuevos if float(c.get("score") or 0.0) >= umbral_score]

    # Skip-if-unchanged: si el conjunto candidato no cambió desde la última pasada evaluada, no hay
    # nada nuevo que encolar -> no se evalúa por marca. `forzar` lo salta.
    huella = _comun._huella_lote(nuevos)
    if not forzar and _comun._ultima_huella_fusionar == huella:
        _comun._ultimo_fusionar = ahora_mono
        return {"encolados": 0, "marcas": 0, "candidatos": 0}

    por_marca: dict[str, list[dict[str, Any]]] = {}
    for c in nuevos:
        por_marca.setdefault(c.get("marca") or "", []).append(c)

    encolados = 0
    marcas_encoladas = 0
    candidatos = 0
    for marca_f, clusters in por_marca.items():
        if len(clusters) < 2:
            continue
        # Toggle "Fusionar" POR MARCA: si la etapa no está encendida para esta marca, no se fusiona.
        # El feed compartido (marca vacía) sigue el default de fábrica vía `etapa_activa`.
        if marca_f and not config.etapa_activa(config.ENV_PIPELINE_FUSIONAR, marca_f):
            continue
        candidatos += len(clusters)
        # IDEMPOTENCIA: no re-encolar una marca cuya fusión sigue EN VUELO (marcador persistido).
        if fusionar_semantica.fusion_en_curso(
            marca_f, ahora=ahora, ttl_min=_FUSION_ENCOLADA_TTL_MIN
        ):
            continue
        # Reintentos acotados: una fusión que nunca completa (claude cae) se re-abre por TTL y se
        # re-encolaría sin fin. Al agotar el tope se deja de re-encolar esa marca; el backoff espacia.
        if _intentos.tope_alcanzado(marca_f, _intentos.ETAPA_FUSIONAR):
            continue
        if _intentos.en_backoff(marca_f, _intentos.ETAPA_FUSIONAR):
            continue
        if _encolar_fusion(marca_f, clusters, ahora=ahora):
            encolados += len(clusters)
            marcas_encoladas += 1

    _comun._ultimo_fusionar = ahora_mono
    _comun._ultima_huella_fusionar = huella
    if marcas_encoladas:
        _log.info(
            "recolectar_daemon: fusionar semántico: %d marca(s) encolada(s) (%d historia(s)).",
            marcas_encoladas, encolados,
        )
    return {"encolados": encolados, "marcas": marcas_encoladas, "candidatos": candidatos}


def _encolar_fusion(marca: str, clusters: list[dict[str, Any]], *, ahora: datetime) -> bool:
    """Crea el registro de generación y ENCOLA el job de fusión de UNA marca. True si encoló.

    Compone la pasada PRINCIPAL (`construir_prompt_fusion` sobre el lote acotado) y arma el spec con
    el carril de la CUENTA de la marca y el modelo de la fusión (`config.fusion_modelo()`). Marca la
    fusión EN CURSO ANTES de encolar (idempotencia entre barridos) y la RE-ABRE si la admisión rechaza
    el encolado (presupuesto/pausa). El worker corre `claude -p` y su post-procesado funde/etiqueta.
    Devuelve False (sin lanzar) ante un lote sin prompt (<2 válidos) o si la admisión lo rechaza;
    cualquier otro fallo se loguea y devuelve False (best-effort: nunca aborta el paso).
    """
    from ... import cola  # noqa: PLC0415 -- import perezoso: cola vive en el paquete raíz

    maximo = config.fusion_semantica_max()
    lote = clusters[:maximo]
    prompt = fusionar_semantica.construir_prompt_fusion(lote)
    if not prompt:
        return False  # <2 historias válidas: nada que fundir

    # IDEMPOTENCIA: marca la fusión en curso ANTES de encolar; si la admisión la rechaza más abajo,
    # se re-abre. Mismo orden que Traducir/Perfil (marcar -> encolar -> limpiar si se rechaza).
    fusionar_semantica.marcar_fusion_encolada(marca, ahora=ahora)
    etiqueta_marca = marcas.etiqueta_de(marca) if marca else "sin marca"
    gen_id = ""
    try:
        gen = generaciones.crear({
            "tipo": "pipeline",
            # Fusionar es INVESTIGACION (motor de noticias): gasta tokens y cuenta para el presupuesto
            # de investigación, ruteado al carril de la cuenta de la marca.
            "proceso": generaciones.PROCESO_INVESTIGACION,
            "etapa": "Fusionar",
            "marca": marca,
            "etiqueta": f"Fusionar historias — {len(lote)} del mismo evento · {etiqueta_marca}",
            "prompt": prompt,
        })
        gen_id = gen["id"]
        spec = jobspec.construir(
            prompt=prompt,
            procesar=jobspec.construir_fusionar(marca=marca, recientes=_spec_recientes(clusters)),
            # Carril de la CUENTA de la marca: el worker que monta esa cuenta reclama el job.
            carril=ruteo_cuentas.carril_de_marca(marca),
            # La fusión usa SU PROPIO modelo (`config.fusion_modelo()`, def sonnet): agrupar por evento
            # es más sutil que traducir, mismo modelo que usaba la fusión inline. Es JSON-in/JSON-out
            # (agrupa ids de titulares en una sola respuesta), igual que el camino síncrono
            # (`_ejecutar_haiku`): `sin_tools` evita exponer esquemas de tools (~17k tokens) y
            # `max_turns=1` la corre en un turno sin bucle agéntico (~500 tokens de JSON en vez de ~4000
            # de razonamiento/turnos), como sus etapas hermanas Traducir/Decisor/Sugerir-hashtags.
            endurecer={"modelo": config.fusion_modelo(), "sin_tools": True, "max_turns": 1},
            # Lo lanza la maquina: AUTOMATICO, cede el paso a los lanzamientos manuales del equipo.
            prioridad=jobspec.PRIORIDAD_AUTOMATICO,
        )
        cola.encolar(gen_id, spec, proceso=generaciones.PROCESO_INVESTIGACION, marca=marca)
        from ...pipeline_contenido import _intentos

        _intentos.anotar(marca, _intentos.ETAPA_FUSIONAR)
        return True
    except generaciones.ColaLlenaError:
        # Admisión rechazada (presupuesto/pausa): borra el registro recién creado y RE-ABRE la marca
        # (no es un fallo real) para que un barrido posterior la reintente sin esperar al TTL.
        if gen_id:
            generaciones.borrar_registro(gen_id)
        fusionar_semantica.limpiar_fusion_encolada(marca)
        return False
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo aborta el barrido
        _log.exception("recolectar_daemon: fallo al encolar la fusión de %r.", marca)
        if gen_id:
            generaciones.borrar_registro(gen_id)
        fusionar_semantica.limpiar_fusion_encolada(marca)
        return False
