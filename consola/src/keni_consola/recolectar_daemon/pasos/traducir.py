"""Paso de TRADUCIR (Ola D): ENCOLA un job de traducción a ES POR MARCA por cada lote de clusters
EXTRANJEROS recientes sin traducir.

A diferencia del traducir pool-wide INLINE de antes (una llamada Haiku para todas las marcas), el
barrido agrupa los candidatos POR MARCA y ENCOLA un job `claude` por marca, ruteado al carril de la
CUENTA de esa marca (`ruteo_cuentas.carril_de_marca`). Así la tropicalización/voz es por marca y el
gasto entra en el carril por cuenta. La traducción la corre el worker (no el barrido) y su
post-procesado persiste `titulo_es`/`resumen_es`/`traducido=1`.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from keni_shared import marcas

from ... import config, generaciones, repos, ruteo_cuentas
from ...dominio import jobspec, traducir
from ...tiempo import iso_utc
from .._comun import _log

# TTL del marcador `traduccion_encolada`: si un job no completa en este margen (deploy/OOM/error de
# claude), el cluster se RE-ABRE para re-encolarse en un barrido posterior. Generoso: los Haiku son
# rápidos, así que esto cubre un cuelgue real, no un job sano esperando en cola.
_ENCOLADA_TTL_MIN = 30


def paso_traducir() -> dict[str, Any]:
    """Encola un job de traducción a ES POR MARCA para los clusters EXTRANJEROS recientes sin traducir.

    1. RE-ABRE los clusters cuyo job anterior quedó atascado (marca `traduccion_encolada` más vieja
       que el TTL): así un job interrumpido no deja el cluster sin traducir para siempre.
    2. Selecciona hasta `KENI_TRAD_LOTE` clusters con `idioma != es`, `score >= KENI_TRAD_MIN_SCORE`,
       `traducido=0` y SIN job en curso, dentro de la ventana reciente.
    3. Los AGRUPA por `marca` y, por cada marca, MARCA sus clusters `traduccion_encolada` (idempotencia:
       no se re-encolan mientras su job sigue en curso) y ENCOLA un job `claude` ruteado al carril de
       la cuenta de la marca (`proceso=investigacion`). El worker corre la traducción y persiste los
       `*_es`/`traducido=1`.

    Idempotente y best-effort: un fallo de encolado de una marca limpia su marca de encolado (para
    reintentar) y no aborta las demás. El gate de parada/presupuesto lo aplica `cola.encolar`
    (además del gate de `ia_fondo_bloqueada` que el barrido comprueba antes de llamar aquí).
    Antes de encolar, REUTILIZA la traducción de una marca hermana (mismo `clave`, ya `traducido=1`)
    copiándola sin llamar al modelo; solo el residual se agrupa y encola. Devuelve
    `{encolados, marcas, candidatos, reutilizados}`.
    """
    umbral = iso_utc(datetime.now(UTC) - timedelta(minutes=_ENCOLADA_TTL_MIN))
    try:
        reabiertos = repos.reparar_traduccion_encolada_atascada(umbral)
        if reabiertos:
            _log.info("recolectar_daemon: %d cluster(s) de traducción atascados re-abiertos.", reabiertos)
    except Exception:  # noqa: BLE001 -- re-abrir atascados es best-effort; nunca aborta el paso
        _log.exception("recolectar_daemon: fallo al re-abrir traducciones atascadas.")

    ventana_h = config.cluster_ventana_h()
    min_score = config.trad_min_score()
    lote = config.trad_lote()
    candidatos = repos.clusters_extranjeros_sin_traducir(
        ventana_h, min_score=min_score, limite=lote
    )
    if not candidatos:
        return {"encolados": 0, "marcas": 0, "candidatos": 0}

    from ...pipeline_contenido import _intentos  # perezoso: evita ciclo daemon<->pipeline en carga

    # CACHÉ POR CLAVE: si una marca HERMANA ya tradujo este artículo (misma clave), copia su ES sin
    # volver a llamar al modelo. Una fuente multimarca crea un cluster por marca con la misma clave;
    # en cuanto una lo traduce, las demás lo reutilizan. Solo el residual (claves aún sin traducir en
    # ninguna marca) se agrupa y encola.
    residual: list[dict[str, Any]] = []
    reutilizados = 0
    for c in candidatos:
        clave = str(c.get("clave") or "")
        trad = repos.traduccion_por_clave(clave) if clave else None
        if trad and trad.get("titulo_es"):
            try:
                repos.marcar_cluster_traducido(
                    str(c["id"]),
                    titulo_es=trad["titulo_es"],
                    resumen_es=trad.get("resumen_es") or "",
                    titulo_original=trad.get("titulo_original") or "",
                )
                reutilizados += 1
                continue
            except Exception:  # noqa: BLE001 -- si la copia falla, cae al encolado normal
                _log.exception(
                    "recolectar_daemon: fallo al copiar la traducción hermana de %s.", c.get("id")
                )
        residual.append(c)
    if reutilizados:
        _log.info(
            "recolectar_daemon: %d traducción(es) reutilizada(s) de una marca hermana (sin modelo).",
            reutilizados,
        )
    if not residual:
        return {"encolados": 0, "marcas": 0, "candidatos": len(candidatos), "reutilizados": reutilizados}

    por_marca: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in residual:
        por_marca[str(c.get("marca") or "")].append(c)

    encolados = 0
    marcas_encoladas = 0
    for marca, clusters in por_marca.items():
        # Respeta el toggle por marca: una marca con Traducir apagado no encola traducción.
        if not config.etapa_activa(config.ENV_PIPELINE_TRADUCIR, marca):
            continue
        # Reintentos acotados POR CLUSTER: una traducción que nunca completa se re-abre por TTL y se
        # re-encolaría sin fin. Excluye los clusters que agotaron el tope o están en backoff.
        clusters = [
            c for c in clusters
            if not _intentos.tope_alcanzado(str(c["id"]), _intentos.ETAPA_TRADUCIR)
            and not _intentos.en_backoff(str(c["id"]), _intentos.ETAPA_TRADUCIR)
        ]
        if not clusters:
            continue
        ids = [str(c["id"]) for c in clusters]
        # IDEMPOTENCIA: marca el lote ANTES de encolar; solo entran al job los que esta llamada
        # marcó (los que seguían `traducido=0` sin job en curso). Si otro barrido ya marcó alguno,
        # `marcar_clusters_traduccion_encolada` lo deja fuera (no lo re-encola).
        try:
            marcados = repos.marcar_clusters_traduccion_encolada(ids)
        except Exception:  # noqa: BLE001 -- un fallo al marcar no debe encolar sin idempotencia
            _log.exception("recolectar_daemon: fallo al marcar el lote de traducción de %r.", marca)
            continue
        if not marcados:
            continue
        if _encolar_traduccion(marca, clusters):
            for c in clusters:
                _intentos.anotar(str(c["id"]), _intentos.ETAPA_TRADUCIR)
            encolados += len(clusters)
            marcas_encoladas += 1
        else:
            # El encolado no ocurrió (admisión rechazada por presupuesto/pausa): re-abre el lote
            # para que un barrido posterior lo reintente sin esperar al TTL del limpiador.
            try:
                repos.limpiar_traduccion_encolada(ids)
            except Exception:  # noqa: BLE001 -- el limpiador de atascados lo cubre si esto falla
                _log.exception("recolectar_daemon: fallo al re-abrir el lote de traducción de %r.", marca)

    return {
        "encolados": encolados,
        "marcas": marcas_encoladas,
        "candidatos": len(candidatos),
        "reutilizados": reutilizados,
    }


def _encolar_traduccion(marca: str, clusters: list[dict[str, Any]]) -> bool:
    """Crea el registro de generación y ENCOLA el job de traducción de UNA marca. True si encoló.

    Compone el prompt por lotes (`traducir.construir_prompt_traduccion`) con el título/resumen
    ORIGINAL de cada cluster y arma el spec con el carril de la CUENTA de la marca. El worker corre
    `claude -p` y su post-procesado (`construir_procesar_traducir`) persiste las traducciones.
    Devuelve False (sin lanzar) si la admisión rechaza el encolado (presupuesto/pausa); cualquier
    otro fallo se loguea y devuelve False (best-effort: nunca aborta el paso).
    """
    from ... import cola  # noqa: PLC0415 -- import perezoso: cola vive en el paquete raíz

    items = [
        {"id": str(c["id"]), "titulo": c.get("titulo") or "", "resumen": c.get("resumen") or ""}
        for c in clusters
    ]
    originales = [{"id": it["id"], "titulo": it["titulo"]} for it in items]
    prompt = traducir.construir_prompt_traduccion(items)
    etiqueta_marca = marcas.etiqueta_de(marca) if marca else "sin marca"
    gen_id = ""
    try:
        gen = generaciones.crear({
            "tipo": "pipeline",
            # Traducir es INVESTIGACION (motor de noticias): gasta tokens y cuenta para el presupuesto
            # de investigación, ruteado al carril de la cuenta de la marca.
            "proceso": generaciones.PROCESO_INVESTIGACION,
            "etapa": "Traducir",
            "marca": marca,
            "etiqueta": f"Traducir historias — {len(items)} a ES (MX) · {etiqueta_marca}",
            "prompt": prompt,
        })
        gen_id = gen["id"]
        spec = jobspec.construir(
            prompt=prompt,
            procesar=jobspec.construir_traducir(marca=marca, originales=originales),
            # Carril de la CUENTA de la marca: el worker que monta esa cuenta reclama el job.
            carril=ruteo_cuentas.carril_de_marca(marca),
            # Haiku (config.insumos_modelo()): traducir+tropicalizar es mecánico, no necesita un modelo
            # grande (mismo modelo que usaba el traducir inline y que usa el parseo de insumos).
            # `sin_tools`: es JSON-in/JSON-out, no usa herramienta alguna → `--tools ""` (ahorro
            # ~17k tokens/llamada; el traducir corre por marca a ráfagas con la caché fría).
            endurecer={"modelo": config.insumos_modelo(), "sin_tools": True},
            # Lo lanza la maquina: AUTOMATICO, cede el paso a los lanzamientos manuales del equipo.
            prioridad=jobspec.PRIORIDAD_AUTOMATICO,
        )
        cola.encolar(gen_id, spec, proceso=generaciones.PROCESO_INVESTIGACION, marca=marca)
        return True
    except generaciones.ColaLlenaError:
        # Admisión rechazada (presupuesto/pausa): borra el registro recién creado (no es un fallo
        # real) para no ensuciar Actividad con cadáveres que el barrido reintenta cada pocos segundos.
        if gen_id:
            generaciones.borrar_registro(gen_id)
        return False
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo aborta el barrido
        _log.exception("recolectar_daemon: fallo al encolar la traducción de %r.", marca)
        if gen_id:
            generaciones.borrar_registro(gen_id)
        return False
