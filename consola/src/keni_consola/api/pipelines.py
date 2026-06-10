"""API PIPELINES: el feed UNIFICADO de Producción (runs del pipeline + actividad suelta).

Cada `contenido` con `origen='pipeline'` (los que produce el daemon
`pipeline_contenido`) es una RUN: el recorrido de UNA pieza por las etapas
CI (Ingesta) → CD (Copy + placa) → QA (Validación) → Aprobación, con un estado por
etapa derivado del ESTADO REAL de la pieza y sus publicaciones por plataforma (no solo
de los logs: robusto y auto-curativo). El detalle por run añade el LOG de actividad de
las etapas (las generaciones-marcador `tipo='pipeline'` correlacionadas por `contenido_id`).

La LISTA ya no es solo de runs: es el feed de la página Producción, que MEZCLA en una
sola línea temporal las runs del pipeline (`clase: "run"`) y la ACTIVIDAD SUELTA
(`clase: "actividad"`): generaciones que no nacieron de una run (copy manual, imágenes,
investigación, importaciones…) y los runs de agente. Cada item suelto se presenta con la
MISMA forma que una run, con UNA etapa (su tipo de trabajo), para que la UI lo pinte con
la misma tarjeta y el mismo detalle entrada/salida. Antes esto vivía partido en dos
pestañas (Feed / Pipelines) con contenido medio duplicado y medio faltante en ambas.
Todos los items (runs incluidas) llevan `metricas` (items, tokens, coste, duración)
sumadas de sus generaciones correlacionadas.

Endpoints (solo lectura):
  - `GET /api/pipelines?marca=&etapa=&estado=&tipo=&clase=&limite=50`
      -> `{"pipelines": [item, ...], "paginacion": {...}}`
  - `GET /api/pipelines/problemas?marca=&limite=50` -> `{"problemas": [tema, ...], "total": n}`
  - `GET /api/pipelines/{pipeline_id}` -> `{"pipeline": run, "actividad": [evento, ...]}`

Errores en español como `{"error": "..."}`; sin tracebacks crudos.
"""

from __future__ import annotations

import json

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import actividad, agentes, config, generaciones, marcas, redes, repos
from .._http_json import _entero_query, envoltura_paginacion
from .actividad import _es_marcador_pipeline
from ..pipeline_contenido import (
    ORIGEN_PIPELINE,
    QA_CADUCADA,
    QA_SALTADA,
    TIPO_ACTIVIDAD,
    VERDICTO_NO_VERIFICADO,
    VERDICTO_PROBLEMA,
    intentos_de,
    qa_lexico,
)

# Estado de etapa cuando su toggle está DESACTIVADO para la marca (1 toggle = 1 etapa): la etapa
# no se ejecuta y se pinta "Saltada" (no bloquea el estado global ni cuenta como fallo).
_ESTADO_SALTADA = "saltada"


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


# Tope por defecto de runs por página (alineado con el resto de la consola).
_LIMITE_DEF = 50
_LIMITE_MAX = 200

# Catálogo de etapas del pipeline (clave → nombre) en orden de flujo. Fusión y Editorial son el
# trabajo del POOL (dedup + encaje/score), DERIVADO de la historia (cluster), no de un toggle.
# Selección/Validación/Copy son TOGGLABLES por marca (activa = estado real; desactivada = "saltada").
# Aprobación es el gate humano. `estado_global` toma la primera no-{ok,saltada}.
_ETAPAS = (
    ("fusion", "Fusión"),
    ("editorial", "Editorial"),
    ("ci", "Selección"),
    ("qa", "Validación"),
    ("cd", "Copy"),
    ("arte", "Arte"),
    ("aprobacion", "Aprobación"),
)
# Claves válidas para el filtro `?etapa=` (la etapa donde la run está parada). Catálogo de
# `_ETAPAS`, sin duplicar la fuente de verdad.
_ETAPA_CLAVES = frozenset(clave for clave, _ in _ETAPAS)
# Etapas que SON una llamada a un LLM (la UI las marca "IA" y enseña prompt+proceso+resultado).
# Selección (crea el tema en BD) y Aprobación (humana) NO lo son.
_ETAPAS_IA = frozenset({"fusion", "editorial", "qa", "cd", "arte"})
# Prompt de la Biblioteca de Texto que usa cada etapa IA (código de etapa → id editable). Permite
# enseñar el PROMPT de entrada SIEMPRE, aunque la etapa aún no haya corrido (plantilla).
_PROMPT_POR_ETAPA = {
    "FUSION": "prompt/noticias/fusion-historias",
    "EDITORIAL": "prompt/noticias/perfil-editorial",
    "QA": "prompt/qa-fuente",
    "CD": "prompt/copy-desde-nota",
    "ARTE": "prompt/imagen/arte-noticia",
}
# Valores válidos del filtro `?estado=` (el `estado_global` de la run).
_ESTADOS_GLOBAL = frozenset({"ok", "en_curso", "pendiente", "revisar", "fallo"})
# Valores válidos del filtro `?clase=` (qué mitad del feed unificado se quiere ver).
_CLASES = frozenset({"run", "actividad"})
# Estado de una generación/run de agente -> `estado_global` del item suelto (mismo chip
# que las runs). Lo que no casa (p. ej. un estado raro/legado) cae a "pendiente".
_ESTADO_ACTIVIDAD = {
    "completado": "ok",
    "error": "fallo",
    "ejecutando": "en_curso",
}
# Prefijos de etiqueta de la IA del POOL (lote por marca): "Fusión de historias" alimenta
# la etapa Fusión y "Encaje editorial" la etapa Editorial. Fuente única para el detalle
# (enlazar la generación) y la lista (evidencia de que el pool corrió: fix "Saltada").
_PREFIJO_POOL_FUSION = "Fusión"
_PREFIJO_POOL_EDITORIAL = "Encaje"
# Métricas a cero de un item sin generaciones correlacionadas (forma estable para la UI).
_METRICAS_CERO = {"items": 0, "tokens": 0, "coste_usd": 0.0, "duration_ms": 0}
# Tope de runs a MATERIALIZAR antes de filtrar/paginar en memoria. El tablero del equipo es
# pequeño en el piloto; esto acota el coste si el histórico de runs creciera mucho (se sirven los
# más recientes). `log()` no aplica aquí: la paginación reporta el `total` ya acotado a esto.
_UNIVERSO_MAX = 500

# Verificación por corroboración (Ola D) -> texto legible para la etapa Jerarquización.
_VERIFICACION_TEXTO = {
    "corroborada": "corroborada por varias fuentes",
    "unica_fuente": "de una sola fuente",
    "dudosa": "dudosa (fuentes en conflicto)",
}

# Estados de plataforma que cuentan como "aprobado" para la etapa de Aprobación.
_ESTADOS_APROBADOS = frozenset({"aprobado", "programado", "publicado"})
# Estados de plataforma "en curso" de revisión humana (aún no aprobados).
_ESTADOS_EN_CURSO = frozenset({"en_curso", "en_revision"})


def _red_nombre(red: str) -> str:
    return "Web" if red == "web" else redes.nombre_por_id(red)


def _marca_nombre(marca: str) -> str:
    return marcas.etiqueta_de(marca) if marca else ""


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
    """
    marca = item.get("marca", "") or ""
    fusion = _fusion_de(cluster, marca, corrio_pool=pool_fusion)
    editorial = _editorial_de(cluster, marca, corrio_pool=pool_editorial)
    creado = item.get("creado", "") or ""
    actualizado = item.get("actualizado", "") or ""
    total = len(piezas)
    qa_veredicto = (item.get("qa_veredicto", "") or "").strip()
    es_problema = qa_veredicto == VERDICTO_PROBLEMA

    # --- Selección: el tema EXISTE, luego la selección CORRIÓ (evidencia, no toggle). --------
    ci = {"clave": "ci", "nombre": "Selección", "estado": "ok", "detalle": "", "ts": creado}

    # --- Validación: PRIMERO el veredicto persistido en el TEMA (lo que de verdad pasó); el
    # toggle solo decide el estado de una run que AÚN no tiene veredicto (futuro).
    if qa_veredicto == QA_SALTADA:
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


def _qa_fuente_de(item: dict) -> dict:
    """Veredicto ESTRUCTURADO de la criba de la fuente (rediseño QPC), para la UI.

    Lee el veredicto persistido en el TEMA (`qa_veredicto`/`qa_hallazgos`):
      - `no_verificado` (⚠️): apta, no verificada a fondo; las piezas llevan el aviso.
      - `problema` (❗): algo de peso; NO se generó copy. `hallazgos` trae el detalle.
    `hallazgos` se parsea del JSON guardado (`{resumen, hallazgos:[...]}`); [] si vacío/ilegible.
    """
    veredicto = (item.get("qa_veredicto", "") or "").strip()
    resumen = ""
    hallazgos: list[dict] = []
    crudo = (item.get("qa_hallazgos", "") or "").strip()
    if crudo:
        try:
            datos = json.loads(crudo)
        except (json.JSONDecodeError, ValueError):
            datos = None
        if isinstance(datos, dict):
            resumen = str(datos.get("resumen", "") or "")
            h = datos.get("hallazgos")
            if isinstance(h, list):
                hallazgos = [x for x in h if isinstance(x, dict)]
    return {
        "veredicto": veredicto,
        "no_verificado": veredicto == VERDICTO_NO_VERIFICADO,
        "problema": veredicto == VERDICTO_PROBLEMA,
        "copy_omitido": veredicto == VERDICTO_PROBLEMA,
        "resumen": resumen,
        "hallazgos": hallazgos,
    }


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


def _metricas_por_run(gens: list[dict], ids_runs: set[str]) -> dict[str, dict]:
    """Suma las métricas de las generaciones REALES (no marcadores) por run (`contenido_id`).

    Devuelve `contenido_id -> {items, tokens, coste_usd, duration_ms}` solo para los ids de
    `ids_runs`. La normalización de métricas es la del dominio `actividad` (la misma del feed):
    tokens_in+tokens_out -> tokens, total_cost_usd -> coste_usd. Los marcadores de etapa
    (sin coste) no suman.
    """
    out: dict[str, dict] = {}
    for g in gens:
        if _es_marcador_pipeline(g):
            continue
        cid = g.get("contenido_id") or ""
        if cid not in ids_runs:
            continue
        m = actividad.normalizar_generacion(g)["metricas"]
        acc = out.setdefault(cid, dict(_METRICAS_CERO))
        acc["items"] += 1
        acc["tokens"] += m["tokens"] or 0
        acc["coste_usd"] = round(acc["coste_usd"] + (m["coste_usd"] or 0.0), 6)
        acc["duration_ms"] += m["duration_ms"] or 0
    return out


def _runs_con_arte_ia(gens: list[dict]) -> set[str]:
    """Ids de contenido con EVIDENCIA de arte GENERADO por IA (auto-arte).

    El auto-arte deja dos trazas correlacionadas al tema: el MARCADOR de etapa
    (`tipo='pipeline_etapa'`, etiqueta "ARTE · …") y la generación con el prompt real
    (`tipo='pipeline'`, etiqueta "Arte — …"). Cualquiera de las dos vale. La etapa Arte se
    deriva de ESTA evidencia, no de si la pieza tiene imagen (la foto de la nota de una
    fuente propia no es arte IA).
    """
    out: set[str] = set()
    for g in gens:
        cid = g.get("contenido_id") or ""
        if not cid:
            continue
        etiqueta = (g.get("etiqueta", "") or "")
        tipo = g.get("tipo") or ""
        if (tipo == TIPO_ACTIVIDAD and etiqueta.startswith("ARTE")) or (
            tipo == "pipeline" and etiqueta.startswith("Arte")
        ):
            out.add(cid)
    return out


def _marcas_con_pool(gens: list[dict], prefijo: str) -> set[str]:
    """Marcas con alguna generación de POOL (tipo `pipeline`, etiqueta con `prefijo`).

    Es la evidencia de que la IA del pool (Fusión / Encaje editorial, por lote de marca)
    CORRIÓ: la usa la derivación de etapas para no pintar "Saltada" una fase con output.
    """
    return {
        (g.get("marca", "") or "")
        for g in gens
        if (g.get("tipo") or "") == "pipeline"
        and (g.get("etiqueta", "") or "").startswith(prefijo)
    }


def _item_de_actividad(it: dict) -> dict:
    """Presenta un item SUELTO de actividad (generación manual / run de agente) como una
    "run" de UNA etapa, con la MISMA forma que las runs del pipeline.

    Así la UI lo pinta con la misma tarjeta (tira de etapas + métricas) y el mismo patrón de
    detalle entrada/salida. `it` es el item YA normalizado por el dominio `actividad`. La
    etapa única lleva `clave="trabajo"` y `nombre` = el tipo crudo (la UI lo etiqueta con su
    catálogo de tipos); `tipo`/`fuente` viajan para filtros y navegación.
    """
    estado = _ESTADO_ACTIVIDAD.get(it["estado"], "pendiente")
    marca = it["marca"]
    etapa = {
        "clave": "trabajo",
        "nombre": it["tipo"] or "trabajo",
        "estado": estado,
        "detalle": "",
        "ts": it["fecha"],
        "es_ia": True,
    }
    return {
        "clase": "actividad",
        "id": it["id"],
        "titulo": it["etiqueta"] or it["tipo"] or "Sin etiqueta",
        "marca": marca,
        "marca_nombre": _marca_nombre(marca) or marca,
        "origen": it["fuente"],  # "generacion" | "run" (run de agente)
        "tipo": it["tipo"],
        "descripcion": "",
        "creado": it["fecha"],
        "actualizado": it["fecha"],
        "estado_global": estado,
        "etapa_actual": "",
        "etapas": [etapa],
        "qa_fuente": None,
        "cluster": None,
        "metricas": {"items": 1, **{k: v for k, v in it["metricas"].items() if k != "num_turns"}},
        "piezas": [],
        # Ruta del SPA al resultado (si su tipo tiene página); la UI la ofrece en el detalle.
        "resultado_url": it["resultado_url"],
    }


def _actividad_suelta(gens: list[dict], ids_runs: set[str], marca: str | None) -> list[dict]:
    """Items SUELTOS del feed: generaciones que no pertenecen a una run listada + runs de agente.

    Excluye los marcadores de etapa (sin coste), el trabajo del POOL y de etapas del pipeline
    (`tipo='pipeline'`: ya está representado DENTRO de las runs) y toda generación cuyo
    `contenido_id` apunte a una run de `ids_runs` (su coste ya viaja en la run; listarla otra
    vez sería la duplicación que teníamos con dos pestañas). Una generación correlacionada a un
    contenido que NO es run del pipeline (p. ej. autogen sobre el tablero) SÍ sale suelta.
    """
    sueltas = [
        actividad.normalizar_generacion(g)
        for g in gens
        if not _es_marcador_pipeline(g)
        and (g.get("tipo") or "") != "pipeline"
        and (g.get("contenido_id") or "") not in ids_runs
    ]
    runs_agente = agentes.listar_runs_globales()
    if marca:
        runs_agente = [
            r for r in runs_agente if (r.get("agente") or r.get("marca") or "") == marca
        ]
    sueltas.extend(actividad.normalizar_run(r) for r in runs_agente)
    return [_item_de_actividad(it) for it in sueltas]


def _runs_del_pipeline(marca: str | None) -> list[dict]:
    """Contenidos `origen='pipeline'`, más recientes primero, acotados a `_UNIVERSO_MAX`.

    `listar_contenido` no filtra por `origen`, así que filtramos en memoria. El listado de
    contenido ya viene acotado al tablero del equipo; reordenamos por recencia (`creado` desc) y
    acotamos al universo máximo (los filtros y la paginación se aplican sobre este conjunto).

    NO oculta runs por el toggle de la marca: un tema que NACIÓ del pipeline sigue siendo
    localizable aunque luego apaguen "Crear noticias" (antes se ocultaban y aparecían posts en
    el feed sin pipeline que encontrar). Con la marca apagada, la etapa CI se pinta "saltada"
    (lo refleja `_etapas_de_run`), pero la run NO desaparece de Pipelines.
    """
    items = repos.listar_contenido(marca=marca or None)
    pipeline = [
        it
        for it in items
        if (it.get("origen") or "") == ORIGEN_PIPELINE
    ]
    pipeline.sort(key=lambda it: (it.get("creado", "") or "", it.get("id", "")), reverse=True)
    return pipeline[:_UNIVERSO_MAX]


async def listar(request: Request) -> Response:
    """GET /api/pipelines?marca=&etapa=&estado=&tipo=&clase=&limite=50&desplazamiento=0.

    Feed UNIFICADO de Producción, recientes primero: runs del pipeline (`clase="run"`) +
    actividad suelta (`clase="actividad"`), con FILTROS y PAGINACIÓN offset (envelope
    `paginacion:{total, limite, desplazamiento}`). Mantiene la clave `pipelines`
    retrocompatible. Filtros (se IGNORAN si el valor no es válido: el cliente ve el
    conjunto sin filtrar, no un 400):
      - `etapa`: la etapa del pipeline donde la run está parada (solo casa runs).
      - `estado`: el `estado_global` del item (runs y sueltos).
      - `tipo`: el tipo de trabajo de un item suelto (copy/rss/imagen/run/…; solo casa sueltos).
      - `clase`: "run" (solo pipeline) o "actividad" (solo sueltos).
    Los filtros se aplican sobre el objeto DERIVADO (etapa_actual/estado_global), por eso se
    materializa el universo y se filtra/pagina en memoria.
    """
    qp = request.query_params
    marca = (qp.get("marca") or "").strip()
    if marca and not marcas.es_marca(marca):
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    etapa = (qp.get("etapa") or "").strip()
    if etapa and etapa not in _ETAPA_CLAVES:
        etapa = ""
    estado = (qp.get("estado") or "").strip()
    if estado and estado not in _ESTADOS_GLOBAL:
        estado = ""
    tipo = (qp.get("tipo") or "").strip()
    clase = (qp.get("clase") or "").strip()
    if clase and clase not in _CLASES:
        clase = ""
    limite = _entero_query(qp.get("limite"), minimo=1)
    if limite is None:
        limite = _LIMITE_DEF
    limite = min(limite, _LIMITE_MAX)
    desplazamiento = _entero_query(qp.get("desplazamiento"), minimo=0) or 0

    runs_items = _runs_del_pipeline(marca or None)
    ids_runs = {it.get("id", "") or "" for it in runs_items}
    # UNA sola lectura del almacén de generaciones: alimenta las métricas por run, la
    # evidencia del pool (fix "Saltada") y los items sueltos del feed.
    gens = generaciones.listar(limite=None, marca=marca or None)
    met_por_run = _metricas_por_run(gens, ids_runs)
    pool_fusion = _marcas_con_pool(gens, _PREFIJO_POOL_FUSION)
    pool_editorial = _marcas_con_pool(gens, _PREFIJO_POOL_EDITORIAL)
    arte_ia_runs = _runs_con_arte_ia(gens)
    # Una sola lectura de TODAS las plataformas, agrupadas por contenido (evita N consultas).
    por_contenido: dict[str, list[dict]] = {}
    for plat in repos.listar_contenido_plataforma():
        por_contenido.setdefault(plat.get("contenido_id", ""), []).append(plat)
    # Una sola lectura de las HISTORIAS (clusters) de estos temas (procedencia IA; evita N consultas).
    clusters = repos.clusters_por_contenidos([it.get("id", "") or "" for it in runs_items])
    todas = [
        _run_de(
            it,
            por_contenido.get(it.get("id", ""), []),
            cluster=clusters.get(it.get("id", "")),
            metricas=met_por_run.get(it.get("id", "")),
            pool_fusion=(it.get("marca", "") or "") in pool_fusion,
            pool_editorial=(it.get("marca", "") or "") in pool_editorial,
            arte_ia=(it.get("id", "") or "") in arte_ia_runs,
        )
        for it in runs_items
    ]
    todas.extend(_actividad_suelta(gens, ids_runs, marca or None))
    # Mezcla cronológica (recientes primero) de runs + sueltos; empata por id (estable).
    todas.sort(key=lambda r: (r.get("creado", "") or "", r.get("id", "") or ""), reverse=True)
    if etapa:
        todas = [r for r in todas if r["clase"] == "run" and r["etapa_actual"] == etapa]
    if estado:
        todas = [r for r in todas if r["estado_global"] == estado]
    if tipo:
        todas = [r for r in todas if r["clase"] == "actividad" and r.get("tipo") == tipo]
    if clase:
        todas = [r for r in todas if r["clase"] == clase]
    total = len(todas)
    # SUMATORIO del universo filtrado (no solo la página): el coste agregado de lo listado.
    totales = dict(_METRICAS_CERO)
    for r in todas:
        m = r.get("metricas") or {}
        totales["items"] += int(m.get("items") or 0)
        totales["tokens"] += int(m.get("tokens") or 0)
        totales["coste_usd"] = round(totales["coste_usd"] + (m.get("coste_usd") or 0.0), 6)
        totales["duration_ms"] += int(m.get("duration_ms") or 0)
    pagina = todas[desplazamiento : desplazamiento + limite]
    return JSONResponse(
        {
            "pipelines": pagina,
            "paginacion": envoltura_paginacion(total, limite, desplazamiento),
            # Suma de las métricas de TODOS los items que casan el filtro (tokens/coste/
            # duración; `items` = generaciones sumadas). La UI lo pinta junto al conteo.
            "totales": totales,
        }
    )


def _problema_de(item: dict) -> dict:
    """Forma pública de un tema BLOQUEADO (veredicto `problema`): qué falló, dónde y cuántas veces.

    `etapa`/`error` salen del ÚLTIMO hallazgo: los fallos repetidos de etapa
    (`marcar_fallo_etapa`) dejan un hallazgo `tipo='sistema'` con la etapa en `fragmento`;
    un 🔴 de la propia criba (sin hallazgo de sistema) es un problema de "Validación".
    `intentos` lee los contadores de reintento de `copy_pendiente` (qa/cd).
    """
    qa = _qa_fuente_de(item)
    ultimo = qa["hallazgos"][-1] if qa["hallazgos"] else {}
    es_sistema = (ultimo.get("tipo") or "") == "sistema"
    marca = item.get("marca", "") or ""
    return {
        "id": item.get("id", "") or "",
        "titulo": item.get("titulo", "") or "",
        "marca": marca,
        "marca_nombre": _marca_nombre(marca),
        "etapa": (ultimo.get("fragmento") or "") if es_sistema else "Validación",
        "intentos": {
            "qa": intentos_de(item, "qa_intentos"),
            "cd": intentos_de(item, "cd_intentos"),
        },
        "error": str(ultimo.get("explicacion") or "") or qa["resumen"],
        "resumen": qa["resumen"],
        "hallazgos": qa["hallazgos"],
        "creado": item.get("creado", "") or "",
        "actualizado": item.get("actualizado", "") or "",
    }


async def problemas(request: Request) -> Response:
    """GET /api/pipelines/problemas?marca=&limite=50: temas BLOQUEADOS del pipeline (solo lectura).

    Tras agotar sus reintentos (o una criba 🔴 de peso), un tema queda con veredicto `problema`
    y SALE del flujo (no se reintenta ni cuenta en el cupo en vuelo): esta lista lo hace VISIBLE
    para que un humano decida (relanzar a mano / descartar). Recientes (por `actualizado`)
    primero. Aún sin UI propia: lo consume quien monitorea (curl / consola / vista futura).
    """
    qp = request.query_params
    marca = (qp.get("marca") or "").strip()
    if marca and not marcas.es_marca(marca):
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    limite = _entero_query(qp.get("limite"), minimo=1)
    if limite is None:
        limite = _LIMITE_DEF
    limite = min(limite, _LIMITE_MAX)

    bloqueados = [
        it
        for it in repos.listar_contenido(marca=marca or None)
        if (it.get("origen") or "") == ORIGEN_PIPELINE
        and (it.get("qa_veredicto") or "").strip() == VERDICTO_PROBLEMA
    ]
    bloqueados.sort(
        key=lambda it: (it.get("actualizado") or it.get("creado") or "", it.get("id", "")),
        reverse=True,
    )
    total = len(bloqueados)
    return JSONResponse({
        "problemas": [_problema_de(it) for it in bloqueados[:limite]],
        "total": total,
    })


def _generacion_publica(gen_id: str) -> dict | None:
    """Resuelve una generación REAL (`claude -p`) por id y devuelve su STREAM + estado.

    Solo los campos que la vista necesita para pintar el proceso del agente: `salida` es el
    stream token a token (el "proceso de pensamiento"); `fase`/`estado` dicen en qué punto va
    (Razonando/Escribiendo/Completado). None si el id no resuelve (best-effort, no rompe).
    """
    if not gen_id:
        return None
    gen = generaciones.obtener(gen_id)
    if gen is None:
        return None
    return {
        "id": gen.get("id", "") or "",
        "estado": gen.get("estado", "") or "",
        "fase": gen.get("fase", "") or "",
        # Prompt EXACTO que se le mandó a la IA (transparencia: qué se le pidió).
        "prompt": gen.get("prompt", "") or "",
        "salida": gen.get("salida", "") or "",
        "metricas": gen.get("metricas"),
    }


def _prompts_plantilla() -> dict[str, str]:
    """Plantilla (texto) del prompt de cada etapa IA, desde la Biblioteca de Texto (editable).

    Permite que la UI enseñe SIEMPRE el prompt de entrada de una etapa IA, aunque aún no haya
    corrido (entonces es la plantilla; cuando corre, se prefiere el prompt REAL de la generación).
    Best-effort: una etapa cuyo prompt no resuelva simplemente no aparece.
    """
    out: dict[str, str] = {}
    for code, pid in _PROMPT_POR_ETAPA.items():
        try:
            from .. import libtexto

            cuerpo = (libtexto.cuerpo_efectivo(pid) or "").strip()
        except Exception:  # noqa: BLE001 -- sin Biblioteca legible, esa etapa no trae plantilla
            cuerpo = ""
        if cuerpo:
            out[code] = cuerpo
    return out


def _generacion_pool_de_marca(marca: str, gens: list[dict], *, prefijo: str) -> dict | None:
    """La generación de pool (tipo `pipeline`, Haiku) más reciente de `marca` con etiqueta `prefijo`.

    La IA del POOL (Fusión / Encaje) corre por LOTE de marca, no 1:1 con cada pieza. Para dar
    transparencia del Haiku REAL en las etapas Fusión/Editorial, enlazamos su generación de pool más
    reciente (con prompt+salida reales). `prefijo` distingue "Fusión de historias" (→ Fusión) de
    "Encaje editorial" (→ Editorial). `gens` es la lista YA leída (evita re-escanear el almacén).
    None si no hay ninguna.
    """
    if not marca:
        return None
    pool = [
        g for g in gens
        if (g.get("marca", "") or "") == marca
        and (g.get("tipo") or "") == "pipeline"
        and (g.get("etiqueta", "") or "").startswith(prefijo)
    ]
    if not pool:
        return None
    pool.sort(key=lambda g: g.get("fecha_fin") or g.get("fecha_inicio") or "", reverse=True)
    return _generacion_publica(pool[0].get("id", "") or "")


def _actividad_y_generaciones(contenido_id: str, gens: list[dict]) -> tuple[list[dict], dict[str, dict]]:
    """Log de etapas (`tipo='pipeline'`) de un contenido + sus generaciones por etapa.

    Lee TODAS las generaciones-marcador del pipeline y filtra por el `contenido_id` que
    sella `pipeline_contenido.registrar_etapa` (CD/QA lo llevan; CI es brand-level y no
    queda atado a un contenido). Recientes primero. Cada evento normaliza la etiqueta
    ("CI · ..."/"CD · ..."/"QA · ...") a `{etapa, etiqueta, estado, fecha}`.

    Además devuelve `generaciones_por_etapa`: un mapa código-de-etapa (CI/CD/QA) -> la
    generación REAL de `claude -p` (resuelta por el `gen_id` del marcador) con su STREAM, para
    que el detalle muestre el proceso del agente por etapa. Solo se incluye la etapa cuyo
    marcador trae `gen_id` resoluble; si una etapa tiene varios (raro), gana el más reciente.
    """
    eventos: list[dict] = []
    # Recolectamos (etapa, fecha, gen_pub) para quedarnos con la generación más reciente por
    # etapa (los eventos vienen recientes-primero tras ordenar; iteramos sobre esa lista).
    gens_por_etapa: dict[str, dict] = {}
    for gen in gens:
        if gen.get("tipo") != TIPO_ACTIVIDAD:
            continue
        if (gen.get("contenido_id") or "") != contenido_id:
            continue
        etiqueta = gen.get("etiqueta", "") or ""
        etapa = etiqueta.split(" · ", 1)[0].strip() if " · " in etiqueta else ""
        fecha = gen.get("fecha_fin") or gen.get("fecha_inicio") or ""
        eventos.append(
            {
                "etapa": etapa,
                "etiqueta": etiqueta,
                "estado": gen.get("estado", "") or "",
                "fecha": fecha,
            }
        )
        gen_real = _generacion_publica(gen.get("gen_id", "") or "")
        if gen_real is not None and etapa:
            # Por etapa nos quedamos con la generación COMPLETADA más reciente (su salida ES
            # el resultado real); solo si ninguna terminó aún, la más reciente en curso (el
            # stream vivo). Antes ganaba "la más reciente" a secas: con un relanzamiento, el
            # duplicado recién arrancado TAPABA la salida del que ya completó (la etapa decía
            # "Completado" y su cuadro "En curso…", sin resultado que mirar).
            terminada = gen_real.get("estado") == "completado"
            previa = gens_por_etapa.get(etapa)
            if (
                previa is None
                or (terminada and not previa[1])
                or (terminada == previa[1] and fecha >= previa[0])
            ):
                gens_por_etapa[etapa] = (fecha, terminada, gen_real)
    eventos.sort(key=lambda e: e["fecha"], reverse=True)
    generaciones_por_etapa = {etapa: tupla[2] for etapa, tupla in gens_por_etapa.items()}
    return eventos, generaciones_por_etapa


async def detalle(request: Request) -> Response:
    """GET /api/pipelines/{pipeline_id}: una run + su log de actividad por etapas."""
    pipeline_id = request.path_params["pipeline_id"]
    item = repos.obtener_contenido(pipeline_id)
    if item is None or (item.get("origen") or "") != ORIGEN_PIPELINE:
        return JSONResponse({"error": "Ese pipeline ya no existe."}, status_code=404)
    piezas = repos.listar_contenido_plataforma(pipeline_id)
    cluster = repos.cluster_por_contenido(pipeline_id)
    # UNA sola lectura del almacén de generaciones (antes 3×, ~3 s cada una); se reparte.
    gens = generaciones.listar(limite=None)
    eventos, generaciones_por_etapa = _actividad_y_generaciones(pipeline_id, gens)
    # Fusión/Editorial: la IA del pool (Haiku) es a nivel de marca/lote; enlazamos su generación más
    # reciente para enseñar el prompt+salida REALES del Haiku en cada etapa (por su etiqueta).
    marca_tema = item.get("marca", "") or ""
    gen_fusion = _generacion_pool_de_marca(marca_tema, gens, prefijo=_PREFIJO_POOL_FUSION)
    if gen_fusion is not None:
        generaciones_por_etapa.setdefault("FUSION", gen_fusion)
    gen_encaje = _generacion_pool_de_marca(marca_tema, gens, prefijo=_PREFIJO_POOL_EDITORIAL)
    if gen_encaje is not None:
        generaciones_por_etapa.setdefault("EDITORIAL", gen_encaje)
    # Métricas de la run + evidencia del pool y del arte IA: las MISMAS derivaciones que la
    # lista, para que detalle y tarjeta no se contradigan (p. ej. "Saltada" aquí y "ok" allá).
    met = _metricas_por_run(gens, {pipeline_id}).get(pipeline_id)
    return JSONResponse(
        {
            "pipeline": _run_de(
                item,
                piezas,
                completo=True,
                cluster=cluster,
                metricas=met,
                pool_fusion=gen_fusion is not None,
                pool_editorial=gen_encaje is not None,
                arte_ia=pipeline_id in _runs_con_arte_ia(gens),
            ),
            "actividad": eventos,
            # Stream del agente (`claude -p`) por código de etapa. Aditivo y back-compat: vacío si
            # ninguna etapa tiene una generación correlacionada.
            "generaciones_por_etapa": generaciones_por_etapa,
            # Plantilla del prompt de cada etapa IA (para enseñar el prompt de ENTRADA aunque la
            # etapa aún no haya corrido; cuando corre, se prefiere el prompt real de la generación).
            "prompts_por_etapa": _prompts_plantilla(),
        }
    )


RUTAS = [
    Route("/api/pipelines", listar, methods=["GET"]),
    # ANTES del detalle: Starlette matchea en orden y `{pipeline_id}` capturaría "problemas".
    Route("/api/pipelines/problemas", problemas, methods=["GET"]),
    Route("/api/pipelines/{pipeline_id}", detalle, methods=["GET"]),
]
