"""PIPELINES · motor de derivación de RUNS y sus 7 etapas.

El núcleo compartido por la lista (`feed`) y el detalle (`detalle`): convierte un `contenido`
del pipeline + sus piezas por plataforma (+ su historia/cluster) en el objeto `run` que pinta
la UI, con un estado por etapa derivado del ESTADO REAL (no de los logs: robusto y
auto-curativo). No depende de los módulos de endpoint.
"""

from __future__ import annotations

from ... import config
from ...pipeline_contenido import (
    ORIGEN_PIPELINE,
    QA_CADUCADA,
    QA_SALTADA,
    VERDICTO_NO_VERIFICADO,
    VERDICTO_PROBLEMA,
    qa_lexico,
)
from ._comun import (
    _ESTADO_SALTADA,
    _ESTADOS_APROBADOS,
    _ESTADOS_EN_CURSO,
    _ETAPAS_IA,
    _METRICAS_CERO,
    _marca_nombre,
    _qa_fuente_de,
    _red_nombre,
)


def _cluster_publico(cluster: dict | None) -> dict | None:
    """Forma reducida de la HISTORIA (cluster) de la que nació el tema, para la UI. None si no hay.

    Es la PRUEBA de que hubo dedup + jerarquización por IA aguas arriba (pool de noticias): cuántas
    fuentes corroboran, cuántas notas se agruparon (fusión), el score del ranking, la verificación
    por corroboración y si fue breaking. La vista lo pinta junto a la etapa Jerarquización.
    """
    if not cluster:
        return None
    return {
        "id": cluster.get("id", "") or "",
        "n_fuentes": int(cluster.get("n_fuentes", 0) or 0),
        "n_items": int(cluster.get("n_items", 0) or 0),
        "score": round(float(cluster.get("score", 0.0) or 0.0), 3),
        "breaking": bool(cluster.get("breaking", 0)),
        "verificacion": cluster.get("verificacion", "") or "",
        "senal": int(cluster.get("senal", 0) or 0),
    }


def _etapa_off(env_flag: str, marca: str) -> bool:
    """Etapa desactivada para `marca`: la negación del resolver ÚNICO (`config.etapa_activa`).

    OJO: el toggle SOLO decide el estado de etapas FUTURAS (sin evidencia persistida en la
    run). Una etapa que YA corrió se pinta por lo que dejó escrito (cluster, veredicto,
    copy, arte), no por el interruptor de hoy: encender/apagar un toggle no re-pinta la
    historia de las runs.
    """
    return not config.etapa_activa(env_flag, marca)


def _qa_off(marca: str) -> bool:
    """Etapa QA desactivada para `marca` (solo aplica a runs SIN veredicto persistido)."""
    return _etapa_off(config.ENV_PIPELINE_VALIDACION, marca)


def _cd_off(marca: str) -> bool:
    """Etapa Copy desactivada para `marca` (solo aplica a runs SIN copy persistido)."""
    return _etapa_off(config.ENV_PIPELINE_COPY, marca)


def _arte_off(marca: str) -> bool:
    """Etapa Arte desactivada para `marca` (solo aplica a runs SIN arte persistido)."""
    return _etapa_off(config.ENV_PIPELINE_ARTE, marca)


def _pieza_de(plat: dict) -> dict:
    """Forma reducida de una fila por plataforma (lista + derivación de etapas)."""
    return {
        "red": plat.get("red", ""),
        "red_nombre": _red_nombre(plat.get("red", "")),
        "estado": plat.get("estado", "") or "pendiente",
        "veredicto": plat.get("veredicto", "") or "",
        "falta_copy": bool(plat.get("falta_copy", True)),
        "falta_imagen": bool(plat.get("falta_imagen", True)),
    }


def _pieza_detalle(plat: dict) -> dict:
    """Forma COMPLETA de una pieza para el detalle: lo que ocurrió de verdad en cada etapa.

    Sobre la forma reducida añade el COPY generado (texto por red + copy-in), la imagen de
    la placa, las OBSERVACIONES de la validación (recalculadas con la misma QA léxica, para
    mostrar el "por qué" del veredicto) y la traza de revisión humana (revisor + fechas).
    """
    base = _pieza_de(plat)
    copy = plat.get("copy", "") or ""
    imagen = plat.get("imagen", "") or ""
    qa = qa_lexico({"red": base["red"], "contenido": copy})
    return {
        **base,
        "copy": copy,
        "copy_in": plat.get("copy_in", "") or "",
        "imagen_url": f"/api/media/{imagen}" if imagen else "",
        "observaciones": qa["observaciones"],
        "revisor_nombre": plat.get("revisor_nombre", "") or "",
        "revisado_en": plat.get("revisado_en", "") or "",
        "enviado_a_revision_en": plat.get("enviado_a_revision_en", "") or "",
        "creado": plat.get("creado", "") or "",
    }


def _fusion_de(cluster: dict | None, marca: str, *, corrio_pool: bool = False) -> dict:
    """Etapa "Fusión": dedup IA del pool. SOLO evidencia persistida: con historia (cluster)
    enlazada corrió (ok). Sin historia, `corrio_pool` desempata: si la IA del pool corrió
    para la marca (hay generación "Fusión de historias"), la etapa CORRIÓ y esta historia
    simplemente no se agrupó con otras — antes se pintaba "Saltada" con un bloque IA
    completado al lado (contradicción visible). Solo sin evidencia alguna queda saltada."""
    if not cluster:
        if corrio_pool:
            return {
                "clave": "fusion", "nombre": "Fusión", "estado": "ok",
                "detalle": "Sin grupo: no se fusionó con otras historias", "ts": "",
            }
        return {"clave": "fusion", "nombre": "Fusión", "estado": _ESTADO_SALTADA, "detalle": "", "ts": ""}
    n_fuentes = int(cluster.get("n_fuentes", 0) or 0)
    n_items = int(cluster.get("n_items", 0) or 0)
    detalle = f"{n_fuentes} fuentes" + (f" · {n_items} notas" if n_items > 1 else "")
    return {
        "clave": "fusion", "nombre": "Fusión", "estado": "ok",
        "detalle": detalle, "ts": cluster.get("primer_visto", "") or "",
    }


def _editorial_de(cluster: dict | None, marca: str, *, corrio_pool: bool = False) -> dict:
    """Etapa "Editorial": encaje editorial IA + score. SOLO evidencia persistida (el score del
    cluster). Sin historia, `corrio_pool` (hay generación "Encaje editorial" de la marca)
    pinta la etapa como corrida sin score propio, igual que en Fusión (fix "Saltada")."""
    if not cluster:
        if corrio_pool:
            return {
                "clave": "editorial", "nombre": "Editorial", "estado": "ok",
                "detalle": "Sin score: el tema no venía de una historia del pool", "ts": "",
            }
        return {"clave": "editorial", "nombre": "Editorial", "estado": _ESTADO_SALTADA, "detalle": "", "ts": ""}
    score = round(float(cluster.get("score", 0.0) or 0.0), 2)
    detalle = f"Score {score}" + (" · 🔥" if cluster.get("breaking") else "")
    return {
        "clave": "editorial", "nombre": "Editorial", "estado": "ok",
        "detalle": detalle, "ts": cluster.get("primer_visto", "") or "",
    }


def _etapas_de_run(
    item: dict,
    piezas: list[dict],
    cluster: dict | None = None,
    *,
    pool_fusion: bool = False,
    pool_editorial: bool = False,
    arte_ia: bool = False,
) -> list[dict]:
    """Deriva las 7 etapas de una run: Fusión + Editorial (pool) + Selección/Validación/Copy/Arte
    (toggles) + Aprobación (humana).

    Fusión y Editorial se derivan de la HISTORIA enlazada (cluster): el dedup y el encaje/score del pool,
    previos al tema; sin historia, `pool_fusion`/`pool_editorial` (hay generación de pool de la
    marca) las pintan como corridas sin grupo/score, no "saltada". Las togglables
    (Selección/Validación/Copy/Arte) están activas o "saltada"
    según su toggle por-marca; si activas, su estado se deriva del estado real (no de logs): el
    `qa_veredicto` del tema y las publicaciones por plataforma (auto-curativo). La Validación
    (criba pre-copy) va ANTES del copy; un `problema` NO genera copy. Arte exige `arte_ia`
    (evidencia de arte GENERADO: marcador/generación de arte de la run): una imagen de fuente
    propia en la pieza no enciende la etapa. Aprobación es el
    gate humano (nunca saltada). Cada etapa es `{clave, nombre, estado, detalle, ts}`.

    Un tema del TABLERO (origen != 'pipeline': rss/equipo/historia/importación, redactado
    por la etapa de copy) no pasa por el pool ni por la criba: Fusión/Editorial/Validación
    se pintan saltadas con el motivo "no aplica", honestas en vez de "pendiente" eterno.
    """
    marca = item.get("marca", "") or ""
    es_tablero = (item.get("origen") or "") != ORIGEN_PIPELINE
    if es_tablero:
        # El tema entró por el tablero, no por el pool de noticias: la fusión/encaje del pool
        # no aplican (la evidencia de pool de la MARCA es de otros temas; no se hereda).
        no_aplica = "No aplica: tema del tablero (sin pool de noticias)"
        fusion = {"clave": "fusion", "nombre": "Fusión", "estado": _ESTADO_SALTADA, "detalle": no_aplica, "ts": ""}
        editorial = {"clave": "editorial", "nombre": "Editorial", "estado": _ESTADO_SALTADA, "detalle": no_aplica, "ts": ""}
    else:
        fusion = _fusion_de(cluster, marca, corrio_pool=pool_fusion)
        editorial = _editorial_de(cluster, marca, corrio_pool=pool_editorial)
    creado = item.get("creado", "") or ""
    actualizado = item.get("actualizado", "") or ""
    total = len(piezas)
    qa_veredicto = (item.get("qa_veredicto", "") or "").strip()
    es_problema = qa_veredicto == VERDICTO_PROBLEMA

    # --- Selección: el tema EXISTE, luego la selección CORRIÓ (evidencia, no toggle). --------
    ci_detalle = f"Del tablero · {item.get('origen') or ''}" if es_tablero else ""
    ci = {"clave": "ci", "nombre": "Selección", "estado": "ok", "detalle": ci_detalle, "ts": creado}

    # --- Validación: PRIMERO el veredicto persistido en el TEMA (lo que de verdad pasó); el
    # toggle solo decide el estado de una run que AÚN no tiene veredicto (futuro).
    if es_tablero and not qa_veredicto:
        # La criba valida la FUENTE de una noticia ingerida; un tema del tablero no la tiene.
        qa_estado, qa_detalle = _ESTADO_SALTADA, "No aplica: sin criba (tema del tablero)"
    elif qa_veredicto == QA_SALTADA:
        qa_estado, qa_detalle = _ESTADO_SALTADA, ""
    elif qa_veredicto == QA_CADUCADA:
        qa_estado, qa_detalle = _ESTADO_SALTADA, "Caducada: el pipeline priorizó lo fresco"
    elif qa_veredicto == VERDICTO_PROBLEMA:
        qa_estado, qa_detalle = "revisar", "Problema en la fuente"
    elif qa_veredicto == "en_curso":
        qa_estado, qa_detalle = "en_curso", ""
    elif qa_veredicto == VERDICTO_NO_VERIFICADO:
        qa_estado, qa_detalle = "ok", "No verificado"
    elif _qa_off(marca):
        qa_estado, qa_detalle = _ESTADO_SALTADA, ""
    else:
        qa_estado, qa_detalle = "pendiente", ""
    qa = {"clave": "qa", "nombre": "Validación", "estado": qa_estado, "detalle": qa_detalle, "ts": ""}

    # --- Copy: PRIMERO el copy persistido (≥1 pieza con copy = corrió, diga lo que diga el
    # toggle de hoy); 'problema'/'caducada' lo omiten; el toggle solo pinta el futuro.
    con_copy = sum(1 for p in piezas if not p["falta_copy"])
    if con_copy:
        cd_estado, cd_detalle = "ok", f"{con_copy}/{total}"
    elif es_problema:
        cd_estado, cd_detalle = "pendiente", "Omitido"
    elif qa_veredicto == QA_CADUCADA:
        cd_estado, cd_detalle = _ESTADO_SALTADA, "Caducada"
    elif _cd_off(marca):
        cd_estado, cd_detalle = _ESTADO_SALTADA, ""
    else:
        cd_estado, cd_detalle = "pendiente", ""
    cd = {"clave": "cd", "nombre": "Copy", "estado": cd_estado, "detalle": cd_detalle, "ts": ""}

    # --- Arte: SOLO evidencia de arte IA (marcador ARTE / generación de arte correlacionada).
    # Una pieza puede traer IMAGEN sin que el arte IA corriera (la foto de la nota de una
    # fuente PROPIA, bajada en la ingesta): eso NO es trabajo de esta etapa y antes la
    # pintaba "ok" con el toggle apagado. La foto de fuente vive en la pieza (feed), no aquí.
    con_arte = sum(1 for p in piezas if not p["falta_imagen"])
    if arte_ia:
        arte_estado, arte_detalle = "ok", f"{con_arte}/{total}"
    elif qa_veredicto == QA_CADUCADA:
        arte_estado, arte_detalle = _ESTADO_SALTADA, "Caducada"
    elif _arte_off(marca):
        arte_estado, arte_detalle = _ESTADO_SALTADA, ""
    else:
        arte_estado, arte_detalle = "pendiente", ""
    arte = {"clave": "arte", "nombre": "Arte", "estado": arte_estado, "detalle": arte_detalle, "ts": ""}

    # --- Aprobación: del estado de las piezas (revisión humana en la parrilla). ---------
    aprobadas = sum(1 for p in piezas if p["estado"] in _ESTADOS_APROBADOS)
    en_curso = any(p["estado"] in _ESTADOS_EN_CURSO for p in piezas)
    if total and aprobadas == total:
        ap_estado, ap_detalle = "ok", ""
    elif aprobadas:
        ap_estado, ap_detalle = "en_curso", f"{aprobadas}/{total}"
    elif en_curso:
        # Esperando al HUMANO (piezas en revisión, ninguna aprobada aún): es "pendiente", no
        # "en curso" — la máquina no está haciendo nada. Antes esto pintaba runs de hace una
        # semana como "En curso" en la lista solo porque nadie llegó a aprobarlas.
        ap_estado, ap_detalle = "pendiente", "En revisión"
    elif qa_veredicto == QA_CADUCADA and not total:
        # Run CADUCADA sin piezas: cerrada sin producto (no quede "pendiente" para siempre).
        ap_estado, ap_detalle = _ESTADO_SALTADA, "Caducada"
    else:
        ap_estado, ap_detalle = "pendiente", ""
    aprobacion = {
        "clave": "aprobacion", "nombre": "Aprobación", "estado": ap_estado,
        "detalle": ap_detalle, "ts": actualizado if ap_estado == "ok" else "",
    }

    etapas = [fusion, editorial, ci, qa, cd, arte, aprobacion]
    for e in etapas:
        e["es_ia"] = e["clave"] in _ETAPAS_IA
    return etapas


def _estado_global(etapas: list[dict]) -> str:
    """Estado global de la run: 'fallo' si alguna etapa falló; si no, la primera no-{ok,saltada}.

    Una etapa 'saltada' (toggle off para la marca) NO bloquea ni cuenta como fallo: se trata como
    'ok' a efectos de avance, así un run con QA saltada y todo lo demás ok queda 'ok'.
    """
    for etapa in etapas:
        if etapa["estado"] == "fallo":
            return "fallo"
    for etapa in etapas:
        if etapa["estado"] not in ("ok", _ESTADO_SALTADA):
            return etapa["estado"]
    return "ok"


def _etapa_actual(etapas: list[dict]) -> str:
    """Clave de la etapa donde la run está «parada» (la 1ª no-{ok,saltada}); "" si todas hechas.

    Es lo que filtra `?etapa=`: «enséñame todo lo que espera en Aprobación / en QA». Coherente
    con `_estado_global`, que toma el estado de esa misma etapa. "" cuando todo está ok/saltada.
    """
    for etapa in etapas:
        if etapa["estado"] not in ("ok", _ESTADO_SALTADA):
            return etapa["clave"]
    return ""


def _run_de(
    item: dict,
    piezas_plat: list[dict],
    *,
    completo: bool = False,
    cluster: dict | None = None,
    metricas: dict | None = None,
    pool_fusion: bool = False,
    pool_editorial: bool = False,
    arte_ia: bool = False,
) -> dict:
    """Construye el objeto `run` de un contenido del pipeline y sus piezas por plataforma.

    `completo`: en el DETALLE, las piezas llevan la forma COMPLETA (`_pieza_detalle`: copy,
    placa, observaciones, traza de revisión) para mostrar todo lo ocurrido por etapa. En la
    LISTA basta la reducida. Las ETAPAS se derivan SIEMPRE de la forma reducida (mismos campos).
    `cluster`: la HISTORIA de la que nació el tema (None si no nació de una); alimenta la etapa
    Jerarquización y el bloque `cluster` (procedencia IA: corroboración, fusión, score).
    `metricas`: suma de las generaciones correlacionadas a la run (items/tokens/coste/duración);
    None cae a ceros (forma estable). `pool_fusion`/`pool_editorial`: evidencia de que la IA del
    pool corrió para la marca (pinta Fusión/Editorial sin historia como corridas, no saltadas).
    """
    base = [_pieza_de(p) for p in piezas_plat]
    etapas = _etapas_de_run(
        item, base, cluster,
        pool_fusion=pool_fusion, pool_editorial=pool_editorial, arte_ia=arte_ia,
    )
    marca = item.get("marca", "") or ""
    # `origen` real de la pieza padre (la fuente RSS que la ingirió): contexto de la etapa CI.
    return {
        "clase": "run",
        "id": item.get("id", ""),
        "titulo": item.get("titulo", "") or "",
        "marca": marca,
        "marca_nombre": _marca_nombre(marca),
        "origen": item.get("origen", "") or "",
        "descripcion": item.get("descripcion", "") or "",
        "creado": item.get("creado", "") or "",
        "actualizado": item.get("actualizado", "") or "",
        "estado_global": _estado_global(etapas),
        # Etapa donde la run está «parada» (para el filtro `?etapa=` y el resaltado en la UI).
        "etapa_actual": _etapa_actual(etapas),
        "etapas": etapas,
        # Criba de la fuente (⚠️/❗ + hallazgos): la señal de QA pre-copy del tema.
        "qa_fuente": _qa_fuente_de(item),
        # Procedencia IA del tema (historia/cluster): None si se creó a mano o pre-ranking.
        "cluster": _cluster_publico(cluster),
        # Coste real de la run: la suma de sus generaciones (`contenido_id` correlacionado).
        "metricas": metricas or dict(_METRICAS_CERO),
        "piezas": [_pieza_detalle(p) for p in piezas_plat] if completo else base,
    }
