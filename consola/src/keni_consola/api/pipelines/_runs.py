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
    VERIFICACION_CADUCADA,
    VERIFICACION_SALTADA,
    VERIFICACION_VERIFICADO,
    VERIFICACION_REQUIERE_HUMANO,
    VERIFICACION_RECHAZADO,
    verificacion_lexica,
)
from ._comun import (
    _ESTADO_SALTADA,
    _ESTADOS_APROBADOS,
    _ESTADOS_EN_CURSO,
    _ETAPAS_IA,
    _METRICAS_CERO,
    _marca_nombre,
    _verificacion_fuente_de,
    _red_nombre,
)


def _cluster_publico(cluster: dict | None) -> dict | None:
    """Forma reducida de la HISTORIA (cluster) de la que nació el tema, para la UI. None si no hay.

    Es la PRUEBA de que hubo dedup + priorización por IA antes en el flujo (pool de noticias): cuántas
    fuentes corroboran, cuántas notas se agruparon (fusionar), el score de Priorizar, la verificación
    por corroboración y si fue breaking. La vista lo pinta junto a la etapa Priorizar.
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
    run). Una etapa que YA corrió se pinta por lo que dejó escrito (cluster, verificacion,
    copy, arte), no por el interruptor de hoy: encender/apagar un toggle no re-pinta la
    historia de las runs.
    """
    return not config.etapa_activa(env_flag, marca)


def _verificar_off(marca: str) -> bool:
    """Etapa Verificar desactivada para `marca` (solo aplica a runs SIN verificacion persistida)."""
    return _etapa_off(config.ENV_PIPELINE_VERIFICAR, marca)


def _redactar_off(marca: str) -> bool:
    """Etapa Redactar desactivada para `marca` (solo aplica a runs SIN copy persistido)."""
    return _etapa_off(config.ENV_PIPELINE_REDACTAR, marca)


def _ilustrar_off(marca: str) -> bool:
    """Etapa Ilustrar desactivada para `marca` (solo aplica a runs SIN arte persistido)."""
    return _etapa_off(config.ENV_PIPELINE_ILUSTRAR, marca)


def _hashtags_off(marca: str) -> bool:
    """Etapa Sugerir hashtags desactivada para `marca`."""
    return _etapa_off(config.ENV_PIPELINE_SUGERIR_HASHTAGS, marca)


def _decisor_off(marca: str) -> bool:
    """Etapa Decisor (formato foto/carrusel) desactivada para `marca` (OFF por defecto)."""
    return _etapa_off(config.ENV_PIPELINE_DECISOR, marca)


def _critica_off(marca: str) -> bool:
    """Nivel Crítica IA desactivado para `marca`."""
    return _etapa_off(config.ENV_CRITICA_IA, marca)


def _pieza_de(plat: dict) -> dict:
    """Forma reducida de una fila por plataforma (lista + derivación de etapas)."""
    return {
        "red": plat.get("red", ""),
        "red_nombre": _red_nombre(plat.get("red", "")),
        "estado": plat.get("estado", "") or "pendiente",
        "revision": plat.get("revision", "") or "",
        "falta_copy": bool(plat.get("falta_copy", True)),
        "falta_imagen": bool(plat.get("falta_imagen", True)),
    }


def _pieza_detalle(plat: dict) -> dict:
    """Forma COMPLETA de una pieza para el detalle: lo que ocurrió de verdad en cada etapa.

    Sobre la forma reducida añade el COPY generado (texto por red + copy-in), la imagen de
    la placa, las OBSERVACIONES de la verificación (recalculadas con la misma verificación léxica, para
    mostrar el "por qué" de la revisión) y la traza de revisión humana (revisor + fechas).
    """
    base = _pieza_de(plat)
    copy = plat.get("copy", "") or ""
    imagen = plat.get("imagen", "") or ""
    verificación = verificacion_lexica({"red": base["red"], "contenido": copy})
    return {
        **base,
        "copy": copy,
        "copy_in": plat.get("copy_in", "") or "",
        "imagen_url": f"/api/media/{imagen}" if imagen else "",
        "observaciones": verificación["observaciones"],
        "revisor_nombre": plat.get("revisor_nombre", "") or "",
        "revisado_en": plat.get("revisado_en", "") or "",
        "enviado_a_revision_en": plat.get("enviado_a_revision_en", "") or "",
        "creado": plat.get("creado", "") or "",
    }


def _fusionar_de(cluster: dict | None, marca: str, *, corrio_pool: bool = False) -> dict:
    """Etapa "Fusionar": dedup IA del pool. SOLO evidencia persistida: con historia (cluster)
    enlazada corrió (ok). Sin historia, `corrio_pool` desempata: si la IA del pool corrió
    para la marca (hay generación "Fusionar historias"), la etapa CORRIÓ y esta historia
    simplemente no se agrupó con otras. Solo sin evidencia alguna queda saltada."""
    if not cluster:
        if corrio_pool:
            return {
                "clave": "fusionar", "nombre": "Fusionar", "estado": "ok",
                "detalle": "Sin grupo: no se fusionó con otras historias", "ts": "",
            }
        return {"clave": "fusionar", "nombre": "Fusionar", "estado": _ESTADO_SALTADA, "detalle": "", "ts": ""}
    n_fuentes = int(cluster.get("n_fuentes", 0) or 0)
    n_items = int(cluster.get("n_items", 0) or 0)
    detalle = f"{n_fuentes} fuentes" + (f" · {n_items} notas" if n_items > 1 else "")
    return {
        "clave": "fusionar", "nombre": "Fusionar", "estado": "ok",
        "detalle": detalle, "ts": cluster.get("primer_visto", "") or "",
    }


def _priorizar_de(cluster: dict | None, marca: str, *, corrio_pool: bool = False) -> dict:
    """Etapa "Priorizar": encaje editorial IA + score. SOLO evidencia persistida (el score del
    cluster). Sin historia, `corrio_pool` (hay generación "Priorizar historias" de la marca)
    pinta la etapa como corrida sin score propio, igual que en Fusionar (fix "Saltada")."""
    if not cluster:
        if corrio_pool:
            return {
                "clave": "priorizar", "nombre": "Priorizar", "estado": "ok",
                "detalle": "Sin score: el tema no venía de una historia del pool", "ts": "",
            }
        return {"clave": "priorizar", "nombre": "Priorizar", "estado": _ESTADO_SALTADA, "detalle": "", "ts": ""}
    score = round(float(cluster.get("score", 0.0) or 0.0), 2)
    detalle = f"Score {score}" + (" · 🔥" if cluster.get("breaking") else "")
    return {
        "clave": "priorizar", "nombre": "Priorizar", "estado": "ok",
        "detalle": detalle, "ts": cluster.get("primer_visto", "") or "",
    }


def _etapas_de_run(
    item: dict,
    piezas: list[dict],
    cluster: dict | None = None,
    *,
    pool_fusion: bool = False,
    pool_editorial: bool = False,
    hashtags_ia: bool = False,
    arte_ia: bool = False,
    critica_ia: bool = False,
    decisor_ia: bool = False,
) -> list[dict]:
    """Deriva las etapas de una run: Fusionar + Priorizar (pool) + Admitir/Verificar/Decisor/
    Redactar/Sugerir hashtags/Ilustrar (toggles) + Aprobar (humana).

    Fusionar y Priorizar se derivan de la HISTORIA enlazada (cluster): el dedup y el encaje/score del pool,
    previos al tema; sin historia, `pool_fusion`/`pool_editorial` (hay generación de pool de la
    marca) las pintan como corridas sin grupo/score, no "saltada". Las togglables
    (Admitir/Verificar/Decisor/Redactar/Ilustrar) están activas o "saltada"
    según su toggle por-marca; si activas, su estado se deriva del estado real (no de logs): el
    `verificacion_fuente` del tema y las piezas por plataforma (auto-curativo). La etapa Verificar
    (verificación pre-copy) va ANTES del copy; un `problema` NO genera copy. Decisor (elige el
    formato foto/carrusel) va JUSTO ANTES de Redactar y bloquea su arranque mientras está
    pendiente (`pipeline_contenido._barrido.ejecutar_redactar`): exige `decisor_ia` (evidencia de
    una generación `decisor` correlacionada al tema), igual patrón que Ilustrar exige `arte_ia`
    (evidencia de arte GENERADO: marcador/generación de arte de la run): una imagen de fuente
    propia en la pieza no enciende la etapa. Aprobar es el
    gate humano (nunca saltada). Cada etapa es `{clave, nombre, estado, detalle, ts}`.

    Un tema del TABLERO (origen != 'pipeline': rss/equipo/historia/importación, redactado
    por la etapa Redactar) no pasa por el pool ni por la verificación: Fusionar/Priorizar/Verificar
    se pintan saltadas con el motivo "no aplica", honestas en vez de "pendiente" eterno.
    """
    marca = item.get("marca", "") or ""
    es_tablero = (item.get("origen") or "") != ORIGEN_PIPELINE
    if es_tablero:
        # El tema entró por el tablero, no por el pool de noticias: el fusionar/encaje del pool
        # no aplican (la evidencia de pool de la MARCA es de otros temas; no se hereda).
        no_aplica = "No aplica: tema del tablero (sin pool de noticias)"
        fusion = {"clave": "fusionar", "nombre": "Fusionar", "estado": _ESTADO_SALTADA, "detalle": no_aplica, "ts": ""}
        editorial = {"clave": "priorizar", "nombre": "Priorizar", "estado": _ESTADO_SALTADA, "detalle": no_aplica, "ts": ""}
    else:
        fusion = _fusionar_de(cluster, marca, corrio_pool=pool_fusion)
        editorial = _priorizar_de(cluster, marca, corrio_pool=pool_editorial)
    creado = item.get("creado", "") or ""
    actualizado = item.get("actualizado", "") or ""
    total = len(piezas)
    verificacion_fuente = (item.get("verificacion_fuente", "") or "").strip()
    es_bloqueado = verificacion_fuente in (VERIFICACION_REQUIERE_HUMANO, VERIFICACION_RECHAZADO)

    # --- Admitir: el tema EXISTE, luego Admitir CORRIÓ (evidencia, no toggle). --------
    ci_detalle = f"Del tablero · {item.get('origen') or ''}" if es_tablero else ""
    ci = {"clave": "admitir", "nombre": "Admitir", "estado": "ok", "detalle": ci_detalle, "ts": creado}

    # --- Verificar: PRIMERO la verificacion persistida en el TEMA (lo que de verdad pasó); el
    # toggle solo decide el estado de una run que AÚN no tiene verificacion (futuro).
    if es_tablero and not verificacion_fuente:
        # La verificación verifica la FUENTE de una noticia recolectada; un tema del tablero no la tiene.
        verificacion_estado, verificacion_detalle = _ESTADO_SALTADA, "No aplica: sin verificación (tema del tablero)"
    elif verificacion_fuente == VERIFICACION_SALTADA:
        verificacion_estado, verificacion_detalle = _ESTADO_SALTADA, ""
    elif verificacion_fuente == VERIFICACION_CADUCADA:
        verificacion_estado, verificacion_detalle = _ESTADO_SALTADA, "Caducada: el pipeline priorizó lo fresco"
    elif verificacion_fuente == VERIFICACION_RECHAZADO:
        verificacion_estado, verificacion_detalle = "revisar", "Rechazada en la fuente"
    elif verificacion_fuente == VERIFICACION_REQUIERE_HUMANO:
        verificacion_estado, verificacion_detalle = "revisar", "La IA no pudo verificar: requiere revisión"
    elif verificacion_fuente == "en_curso":
        verificacion_estado, verificacion_detalle = "en_curso", ""
    elif verificacion_fuente == VERIFICACION_VERIFICADO:
        verificacion_estado, verificacion_detalle = "ok", "Verificada"
    elif _verificar_off(marca):
        verificacion_estado, verificacion_detalle = _ESTADO_SALTADA, ""
    else:
        verificacion_estado, verificacion_detalle = "pendiente", ""
    verificación = {"clave": "verificar", "nombre": "Verificar", "estado": verificacion_estado, "detalle": verificacion_detalle, "ts": ""}

    # --- Decisor: elige el formato (foto/carrusel) JUSTO ANTES de Redactar. SOLO evidencia
    # (una generación `decisor` correlacionada al tema): sin ella, "pendiente" si el toggle está
    # activo (bloquea a Redactar de verdad, ver `_barrido.ejecutar_redactar`) o "saltada" si no.
    if decisor_ia:
        decisor_estado, decisor_detalle = "ok", ""
    elif es_bloqueado:
        decisor_estado, decisor_detalle = "pendiente", "Omitido"
    elif verificacion_fuente == VERIFICACION_CADUCADA:
        decisor_estado, decisor_detalle = _ESTADO_SALTADA, "Caducada"
    elif _decisor_off(marca):
        decisor_estado, decisor_detalle = _ESTADO_SALTADA, ""
    else:
        decisor_estado, decisor_detalle = "pendiente", ""
    decisor = {
        "clave": "decisor", "nombre": "Decisor",
        "estado": decisor_estado, "detalle": decisor_detalle, "ts": "",
    }

    # --- Redactar: PRIMERO el copy persistido (≥1 pieza con copy = corrió, diga lo que diga el
    # toggle de hoy); 'requiere_humano'/'rechazado'/'caducada' lo omiten; el toggle solo pinta el futuro.
    con_copy = sum(1 for p in piezas if not p["falta_copy"])
    if con_copy:
        cd_estado, cd_detalle = "ok", f"{con_copy}/{total}"
    elif es_bloqueado:
        cd_estado, cd_detalle = "pendiente", "Omitido"
    elif verificacion_fuente == VERIFICACION_CADUCADA:
        cd_estado, cd_detalle = _ESTADO_SALTADA, "Caducada"
    elif _redactar_off(marca):
        cd_estado, cd_detalle = _ESTADO_SALTADA, ""
    else:
        cd_estado, cd_detalle = "pendiente", ""
    cd = {"clave": "redactar", "nombre": "Redactar", "estado": cd_estado, "detalle": cd_detalle, "ts": ""}

    # --- Sugerir hashtags: tras Redactar, antes de Ilustrar. SOLO evidencia (una generación
    # `sugerir-hashtags` correlacionada). Es una etapa CONDICIONAL (solo corre cuando al copy le
    # faltan hashtags), así que sin evidencia NUNCA queda "pendiente" —bloquearía el estado global
    # de toda run cuyo copy ya traía hashtags—: se pinta "saltada" (no corrió / etapa apagada) y la
    # tira la oculta conservando su ranura.
    if hashtags_ia:
        hash_estado, hash_detalle = "ok", ""
    elif _hashtags_off(marca):
        hash_estado, hash_detalle = _ESTADO_SALTADA, "Desactivada"
    else:
        hash_estado, hash_detalle = _ESTADO_SALTADA, ""
    hashtags = {
        "clave": "sugerir_hashtags", "nombre": "Keywords",
        "estado": hash_estado, "detalle": hash_detalle, "ts": "",
    }

    # --- Ilustrar: SOLO evidencia de arte IA (marcador ARTE / generación de arte correlacionada).
    # Una pieza puede traer IMAGEN sin que el arte IA corriera (la foto de la nota de una
    # fuente PROPIA, bajada al recolectar): eso NO es trabajo de esta etapa. La foto de fuente vive en la pieza (feed), no aquí.
    con_arte = sum(1 for p in piezas if not p["falta_imagen"])
    if arte_ia:
        arte_estado, arte_detalle = "ok", f"{con_arte}/{total}"
    elif verificacion_fuente == VERIFICACION_CADUCADA:
        arte_estado, arte_detalle = _ESTADO_SALTADA, "Caducada"
    elif _ilustrar_off(marca):
        arte_estado, arte_detalle = _ESTADO_SALTADA, ""
    else:
        arte_estado, arte_detalle = "pendiente", ""
    arte = {"clave": "ilustrar", "nombre": "Ilustrar", "estado": arte_estado, "detalle": arte_detalle, "ts": ""}

    # --- Aprobar: del estado de las piezas (revisión humana en la parrilla). ---------
    aprobadas = sum(1 for p in piezas if p["estado"] in _ESTADOS_APROBADOS)
    en_curso = any(p["estado"] in _ESTADOS_EN_CURSO for p in piezas)
    if total and aprobadas == total:
        ap_estado, ap_detalle = "ok", ""
    elif aprobadas:
        ap_estado, ap_detalle = "en_curso", f"{aprobadas}/{total}"
    elif en_curso:
        # Esperando al HUMANO (piezas en revisión, ninguna aprobada aún): es "pendiente", no
        # "en curso" — la máquina no está haciendo nada.
        ap_estado, ap_detalle = "pendiente", "En revisión"
    elif verificacion_fuente == VERIFICACION_CADUCADA and not total:
        # Run CADUCADA sin piezas: cerrada sin producto (no quede "pendiente" para siempre).
        ap_estado, ap_detalle = _ESTADO_SALTADA, "Caducada"
    else:
        ap_estado, ap_detalle = "pendiente", ""
    aprobacion = {
        "clave": "aprobar", "nombre": "Aprobar", "estado": ap_estado,
        "detalle": ap_detalle, "ts": actualizado if ap_estado == "ok" else "",
    }

    # --- Crítica IA: nivel opcional de la cadena de aprobación (tras los OK humanos), gateado
    # por `KENI_CRITICA_IA`. OFF -> "saltada" (Desactivada). ON -> "ok" si hay evidencia de que
    # corrió (job `critica-ia`), "pendiente" mientras no. Corre DESPUÉS de Aprobar.
    if _critica_off(marca):
        cr_estado, cr_detalle = _ESTADO_SALTADA, "Desactivada"
    elif critica_ia:
        cr_estado, cr_detalle = "ok", ""
    else:
        cr_estado, cr_detalle = "pendiente", ""
    critica = {"clave": "critica", "nombre": "Crítica", "estado": cr_estado, "detalle": cr_detalle, "ts": ""}

    etapas = [fusion, editorial, ci, verificación, decisor, cd, hashtags, arte, aprobacion, critica]
    for e in etapas:
        e["es_ia"] = e["clave"] in _ETAPAS_IA
    return etapas


def _estado_global(etapas: list[dict]) -> str:
    """Estado global de la run: 'fallo' si alguna etapa falló; si no, la primera no-{ok,saltada}.

    Una etapa 'saltada' (toggle off para la marca) NO bloquea ni cuenta como fallo: se trata como
    'ok' a efectos de avance, así un run con Verificar saltada y todo lo demás ok queda 'ok'.
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

    Es lo que filtra `?etapa=`: «enséñame todo lo que espera en Aprobación / en verificación». Coherente
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
    hashtags_ia: bool = False,
    arte_ia: bool = False,
    critica_ia: bool = False,
    decisor_ia: bool = False,
) -> dict:
    """Construye el objeto `run` de un contenido del pipeline y sus piezas por plataforma.

    `completo`: en el DETALLE, las piezas llevan la forma COMPLETA (`_pieza_detalle`: copy,
    placa, observaciones, traza de revisión) para mostrar todo lo ocurrido por etapa. En la
    LISTA basta la reducida. Las ETAPAS se derivan SIEMPRE de la forma reducida (mismos campos).
    `cluster`: la HISTORIA de la que nació el tema (None si no nació de una); alimenta la etapa
    Priorizar y el bloque `cluster` (procedencia IA: corroboración, fusionar, score).
    `metricas`: suma de las generaciones correlacionadas a la run (items/tokens/coste/duración);
    None cae a ceros (forma estable). `pool_fusion`/`pool_editorial`: evidencia de que la IA del
    pool corrió para la marca (pinta Fusionar/Priorizar sin historia como corridas, no saltadas).
    `decisor_ia`: evidencia de que el Decisor de formato corrió para este tema (ver `_ETAPAS`).
    """
    base = [_pieza_de(p) for p in piezas_plat]
    etapas = _etapas_de_run(
        item, base, cluster,
        pool_fusion=pool_fusion, pool_editorial=pool_editorial,
        hashtags_ia=hashtags_ia, arte_ia=arte_ia,
        critica_ia=critica_ia, decisor_ia=decisor_ia,
    )
    marca = item.get("marca", "") or ""
    # `origen` real de la pieza padre (la fuente RSS que la recolectó): contexto de la etapa Admitir.
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
        # Verificación de la fuente (⚠️/❗ + hallazgos): la señal de Verificar pre-copy del tema.
        "verificacion": _verificacion_fuente_de(item),
        # Procedencia IA del tema (historia/cluster): None si se creó a mano o pre-priorización.
        "cluster": _cluster_publico(cluster),
        # Coste real de la run: la suma de sus generaciones (`publicacion_id` correlacionado).
        "metricas": metricas or dict(_METRICAS_CERO),
        "piezas": [_pieza_detalle(p) for p in piezas_plat] if completo else base,
    }
