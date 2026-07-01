"""PIPELINES · `GET /api/pipelines/{id}`: una run + su log de actividad por etapas.

Sobre el objeto `run` (motor compartido en `_runs`) añade el LOG de etapas, el STREAM real de
`claude -p` por etapa (incluida la IA del POOL, a nivel de marca) y las plantillas de prompt,
para mostrar el proceso del agente entrada/salida en cada fase.
"""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ... import actividad, generaciones, repos
from ...pipeline_contenido import ORIGEN_PIPELINE, TIPO_ACTIVIDAD
from ..actividad import _es_marcador_pipeline
from ._comun import (
    _ORIGENES_RUN,
    _PREFIJO_POOL_EDITORIAL,
    _PREFIJO_POOL_FUSION,
    _PROMPT_POR_ETAPA,
)
from ._metricas import (
    _con_pool,
    _metricas_por_run,
    _pool_por_marca,
    _runs_con_arte_ia,
    _runs_con_critica_ia,
    _runs_con_decisor,
    _runs_con_hashtags,
)
from ._runs import _run_de

# Orden temporal de las etapas en la LÍNEA DE TIEMPO unificada. Reúne el orden de flujo del
# catálogo de runs (`_runs._ETAPAS`) con las etapas que NO son ranuras fijas de la run y que
# `etapa_economia` nombra aparte (Recolectar, Decisor, Revisión editorial, Carrusel): cada una
# en su sitio del flujo. Una etapa que no esté aquí cae al final, ordenada por su fecha.
_ORDEN_LINEA_TIEMPO = (
    "Recolectar",
    "Fusionar",
    "Priorizar",
    "Decisor",
    "Admitir",
    "Verificar",
    "Revisión editorial",
    "Redactar",
    "Keywords",
    "Ilustrar",
    "Carrusel",
    "Aprobar",
    "Crítica",
)
_ORDEN_POR_ETAPA = {nombre: i for i, nombre in enumerate(_ORDEN_LINEA_TIEMPO)}


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
    """Plantilla (texto) del prompt de cada etapa IA, desde la Prompts de Texto (editable).

    Permite que la UI enseñe SIEMPRE el prompt de entrada de una etapa IA, aunque aún no haya
    corrido (entonces es la plantilla; cuando corre, se prefiere el prompt REAL de la generación).
    Best-effort: una etapa cuyo prompt no resuelva simplemente no aparece.
    """
    out: dict[str, str] = {}
    for code, pid in _PROMPT_POR_ETAPA.items():
        try:
            from ... import libprompts

            cuerpo = (libprompts.cuerpo_efectivo(pid) or "").strip()
        except Exception:  # noqa: BLE001 -- sin Prompts legible, esa etapa no trae plantilla
            cuerpo = ""
        if cuerpo:
            out[code] = cuerpo
    return out


def _generacion_pool_de_marca(marca: str, gens: list[dict], *, prefijo: str) -> dict | None:
    """La generación de pool (tipo `pipeline`, Haiku) más reciente de `marca` con etiqueta `prefijo`.

    La IA del POOL (Fusionar / Encaje) corre por LOTE de marca, no 1:1 con cada pieza. Para dar
    transparencia del Haiku REAL en las etapas Fusionar/Priorizar, enlazamos su generación de pool más
    reciente (con prompt+salida reales). `prefijo` distingue "Fusionar historias" (→ Fusionar) de
    "Priorizar historias" (→ Priorizar). `gens` es la lista YA leída (evita re-escanear el almacén).
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


def _actividad_y_generaciones(publicacion_id: str, gens: list[dict]) -> tuple[list[dict], dict[str, dict]]:
    """Log de etapas (`tipo='pipeline'`) de un contenido + sus generaciones por etapa.

    Lee TODAS las generaciones-marcador del pipeline y filtra por el `publicacion_id` que
    sella `pipeline_contenido.registrar_etapa` (REDACTAR/VERIFICAR lo llevan; ADMITIR es brand-level y no
    queda atado a un contenido). Recientes primero. Cada evento normaliza la etiqueta
    ("ADMITIR · ..."/"REDACTAR · ..."/"VERIFICAR · ...") a `{etapa, etiqueta, estado, fecha}`.

    Además devuelve `generaciones_por_etapa`: un mapa código-de-etapa (ADMITIR/REDACTAR/VERIFICAR) -> la
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
        if (gen.get("publicacion_id") or "") != publicacion_id:
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


def _etapa_de_gen(gen: dict) -> str:
    """Etapa legible de UNA generación real: la `etapa` que selló el job, o la derivada del par
    (proceso, tipo) vía `etapa_economia`. Cubre TODOS los tipos (decisor, copy/autogen, imagen,
    sugerir-hashtags, critica-ia, carrusel, verificación…), no solo las ranuras de la run."""
    etapa = (gen.get("etapa") or "").strip()
    if etapa:
        return etapa
    return repos.etapa_economia(gen.get("proceso") or "", gen.get("tipo") or "")


def _gen_linea(gen: dict) -> dict:
    """Forma mínima de una generación dentro de una entrada de etapa de la línea de tiempo."""
    m = actividad.normalizar_generacion(gen)["metricas"]
    return {
        "gen_id": gen.get("id", "") or "",
        "estado": gen.get("estado", "") or "",
        "fecha": gen.get("fecha_fin") or gen.get("fecha_inicio") or "",
        "coste_usd": m.get("coste_usd"),
        "tokens": m.get("tokens"),
    }


def _mas_reciente(gens: list[dict], pred) -> dict | None:
    """La generación más reciente (por `fecha_fin`/`fecha_inicio`) que cumple `pred`; None si ninguna."""
    cand = [g for g in gens if pred(g)]
    if not cand:
        return None
    cand.sort(key=lambda g: g.get("fecha_fin") or g.get("fecha_inicio") or "", reverse=True)
    return cand[0]


def _linea_tiempo(
    pipeline_id: str,
    marca_tema: str,
    gens: list[dict],
    *,
    cluster: dict | None,
    es_pipeline: bool,
) -> list[dict]:
    """LÍNEA DE TIEMPO unificada de un POST: TODA la actividad real del mismo tema, en una sola
    secuencia por etapa con los REINTENTOS COLAPSADOS.

    Reúne (a) TODAS las generaciones REALES cuyo `publicacion_id == pipeline_id` —no solo las del
    catálogo de etapas: INCLUYE el DECISOR y cualquier otro tipo, que hoy se caían del detalle— y
    (b) la fase PREVIA al tablero (pool Fusionar/Priorizar) cuando el tema nació de una HISTORIA
    (`cluster` resuelto). La fase previa es de LOTE de marca (sus generaciones llevan
    `publicacion_id=""`), así que se correla por `marca` y se marca `fase_previa=True` para que la
    UI la pinte "antes del tablero".

    Cada etapa colapsa sus reintentos en UNA entrada `{etapa, intentos, estado_final, ultima_gen_id,
    primera_fecha, ultima_fecha, fase_previa, generaciones:[...]}`: `intentos` es el nº de
    generaciones de ese tema+etapa, `estado_final`/`ultima_gen_id` los de la más reciente, y la
    lista interna (orden cronológico) permite expandir intento a intento. Las etapas se ordenan por
    el flujo del pipeline (`_ORDEN_LINEA_TIEMPO`); una etapa desconocida cae al final, por fecha.
    """
    # (etapa, fase_previa) -> [generaciones de ese grupo]
    grupos: dict[tuple[str, bool], list[dict]] = {}

    # (a) Generaciones REALES del propio tema (decisor, copy/autogen, imagen, hashtags, crítica,
    # carrusel…). Se excluyen los MARCADORES de etapa (no son trabajo con coste; su gen real ya
    # entra por su `publicacion_id`).
    for gen in gens:
        if _es_marcador_pipeline(gen):
            continue
        if (gen.get("publicacion_id") or "") != pipeline_id:
            continue
        etapa = _etapa_de_gen(gen)
        if not etapa:
            continue
        grupos.setdefault((etapa, False), []).append(gen)

    # (b) Fase PREVIA al tablero (pool de noticias): solo si el tema nació de una historia
    # (`cluster` resuelto) y es del pipeline. El pool corre por LOTE de marca, así que se enlaza la
    # generación más reciente de la marca por etiqueta (misma selección que el resto del detalle).
    if es_pipeline and cluster is not None:
        for prefijo, etapa in ((_PREFIJO_POOL_FUSION, "Fusionar"), (_PREFIJO_POOL_EDITORIAL, "Priorizar")):
            gen = _mas_reciente(
                gens,
                lambda g, _pref=prefijo: (g.get("marca", "") or "") == marca_tema
                and (g.get("tipo") or "") == "pipeline"
                and (g.get("etiqueta", "") or "").startswith(_pref),
            )
            if gen is not None:
                # La etapa la fija la ETIQUETA del lote (Fusionar/Priorizar), no `etapa_economia`:
                # un job de pool comparte `tipo='pipeline'` con la redacción (ambigüedad que solo
                # su etiqueta desambigua, igual que en el resto del detalle).
                grupos.setdefault((etapa, True), []).append(gen)

    entradas: list[dict] = []
    for (etapa, fase_previa), bucket in grupos.items():
        bucket.sort(key=lambda g: g.get("fecha_fin") or g.get("fecha_inicio") or "")
        gens_linea = [_gen_linea(g) for g in bucket]
        ultima = bucket[-1]
        entradas.append(
            {
                "etapa": etapa,
                "intentos": len(bucket),
                "estado_final": ultima.get("estado", "") or "",
                "ultima_gen_id": ultima.get("id", "") or "",
                "primera_fecha": gens_linea[0]["fecha"],
                "ultima_fecha": gens_linea[-1]["fecha"],
                "fase_previa": fase_previa,
                "generaciones": gens_linea,
            }
        )

    # Orden de flujo del pipeline para las etapas conocidas; las desconocidas al final, por fecha.
    desconocida = len(_ORDEN_LINEA_TIEMPO)
    entradas.sort(key=lambda e: (_ORDEN_POR_ETAPA.get(e["etapa"], desconocida), e["primera_fecha"]))
    return entradas


def _detalle(pipeline_id: str) -> tuple[int, dict]:
    item = repos.obtener_publicacion(pipeline_id)
    if item is None or (item.get("origen") or "") not in _ORIGENES_RUN:
        return 404, {"error": "Ese pipeline ya no existe."}
    es_pipeline = (item.get("origen") or "") == ORIGEN_PIPELINE
    piezas = repos.listar_piezas_fila(pipeline_id)
    cluster = repos.cluster_por_contenido(pipeline_id)
    gens = generaciones.listar(limite=None)
    eventos, generaciones_por_etapa = _actividad_y_generaciones(pipeline_id, gens)
    # Fusionar/Priorizar: la IA del pool (Haiku) es a nivel de marca/lote; enlazamos su generación más
    # reciente para enseñar el prompt+salida REALES del Haiku en cada etapa (por su etiqueta).
    # SOLO en temas del pipeline: a un tema del tablero el pool no le aplica (etapas "No aplica").
    marca_tema = item.get("marca", "") or ""
    gen_fusion = _generacion_pool_de_marca(marca_tema, gens, prefijo=_PREFIJO_POOL_FUSION) if es_pipeline else None
    if gen_fusion is not None:
        generaciones_por_etapa.setdefault("FUSIONAR", gen_fusion)
    gen_encaje = _generacion_pool_de_marca(marca_tema, gens, prefijo=_PREFIJO_POOL_EDITORIAL) if es_pipeline else None
    if gen_encaje is not None:
        generaciones_por_etapa.setdefault("PRIORIZAR", gen_encaje)
    # Crítica IA: su job (`tipo='critica-ia'`) corre por pieza y sella el `publicacion_id` del tema
    # (= esta run). Enlazamos el más reciente para enseñar su prompt+salida REALES en la etapa.
    crit = [g for g in gens if (g.get("tipo") or "") == "critica-ia" and (g.get("publicacion_id") or "") == pipeline_id]
    if crit:
        crit.sort(key=lambda g: g.get("fecha_fin") or g.get("fecha_inicio") or "", reverse=True)
        gen_crit = _generacion_publica(crit[0].get("id", "") or "")
        if gen_crit is not None:
            generaciones_por_etapa.setdefault("CRITICA", gen_crit)
    # Sugerir hashtags: su job (`tipo='sugerir-hashtags'`) corre por contenido y sella el
    # `publicacion_id` del tema (= esta run). Enlazamos el más reciente para enseñar su
    # prompt+salida REALES en la etapa.
    hashtags = [g for g in gens if (g.get("tipo") or "") == "sugerir-hashtags" and (g.get("publicacion_id") or "") == pipeline_id]
    if hashtags:
        hashtags.sort(key=lambda g: g.get("fecha_fin") or g.get("fecha_inicio") or "", reverse=True)
        gen_hashtags = _generacion_publica(hashtags[0].get("id", "") or "")
        if gen_hashtags is not None:
            generaciones_por_etapa.setdefault("SUGERIR_HASHTAGS", gen_hashtags)
    # Decisor: su job (`tipo='decisor'`) corre por tema y sella el `publicacion_id` del tema
    # (= esta run). Enlazamos el más reciente para enseñar su prompt+salida REALES en la etapa.
    decisor_gens = [g for g in gens if (g.get("tipo") or "") == "decisor" and (g.get("publicacion_id") or "") == pipeline_id]
    if decisor_gens:
        decisor_gens.sort(key=lambda g: g.get("fecha_fin") or g.get("fecha_inicio") or "", reverse=True)
        gen_decisor = _generacion_publica(decisor_gens[0].get("id", "") or "")
        if gen_decisor is not None:
            generaciones_por_etapa.setdefault("DECISOR", gen_decisor)
    # Métricas de la run + evidencia del pool y del arte IA: las MISMAS derivaciones que la
    # lista, para que detalle y tarjeta no se contradigan (p. ej. "Saltada" aquí y "ok" allá).
    # La suma incluye las etapas de POOL enlazadas (Fusionar/Encaje): la cabecera cuadra con el
    # agregado de los bloques de etapa que esta misma página enseña.
    met = _metricas_por_run(gens, {pipeline_id}).get(pipeline_id)
    if es_pipeline:
        met = _con_pool(met, _pool_por_marca(gens).get(marca_tema, []))
    return 200, {
        "pipeline": _run_de(
            item,
            piezas,
            completo=True,
            cluster=cluster,
            metricas=met,
            pool_fusion=gen_fusion is not None,
            pool_editorial=gen_encaje is not None,
            hashtags_ia=pipeline_id in _runs_con_hashtags(gens),
            arte_ia=pipeline_id in _runs_con_arte_ia(gens),
            critica_ia=pipeline_id in _runs_con_critica_ia(gens),
            decisor_ia=pipeline_id in _runs_con_decisor(gens),
        ),
        "actividad": eventos,
        # Línea de tiempo unificada del POST: TODA la actividad real del mismo tema (incluido el
        # DECISOR y la fase previa al tablero) en una secuencia por etapa, con los reintentos
        # colapsados (una entrada por etapa con `intentos`). Aditivo y back-compat.
        "linea_tiempo": _linea_tiempo(
            pipeline_id, marca_tema, gens, cluster=cluster, es_pipeline=es_pipeline
        ),
        # Stream del agente (`claude -p`) por código de etapa. Aditivo y back-compat: vacío si
        # ninguna etapa tiene una generación correlacionada.
        "generaciones_por_etapa": generaciones_por_etapa,
        # Plantilla del prompt de cada etapa IA (para enseñar el prompt de ENTRADA aunque la
        # etapa aún no haya corrido; cuando corre, se prefiere el prompt real de la generación).
        "prompts_por_etapa": _prompts_plantilla(),
    }


async def detalle(request: Request) -> Response:
    """GET /api/pipelines/{pipeline_id}: una run + su log de actividad por etapas.

    Acepta tanto los temas del pipeline (`origen='pipeline'`) como los del TABLERO que su
    etapa Redactar redacta (`ORIGENES_AUTOGEN`): ambos son runs del feed de Producción.
    """
    pipeline_id = request.path_params["pipeline_id"]
    status, cuerpo = await run_in_threadpool(_detalle, pipeline_id)
    return JSONResponse(cuerpo, status_code=status)
